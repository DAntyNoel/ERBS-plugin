"""Refresh dated ERCraft profile snapshots before using their RP and report."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from ..exceptions import RateLimited, UpstreamUnavailable
from ..published_summary import SummaryProgressCallback

if TYPE_CHECKING:
    from .dak import AsyncERBSClient


def _observed_at(identity: Mapping) -> datetime | None:
    # The outer response's refreshedAt is just its serving time, not rank freshness.
    for key in ("currentRankObservedAt", "lastRefreshedAt", "lastCheckedAt"):
        value = identity.get(key)
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed
    return None


async def _refresh_request(
    client: AsyncERBSClient, path: str, *, method: str = "GET",
    params: Mapping | None = None, body: Mapping | None = None,
) -> Mapping[str, Any]:
    try:
        async with client._semaphore:
            response = await client._client.request(method, path, params=params, json=body)
        if response.status_code == 429:
            raise RateLimited("ERCraft 刷新请求过于频繁，请稍后重试。")
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamUnavailable("ERCraft 玩家资料已过期，刷新失败，请稍后重试。") from exc
    data = payload.get("data", payload) if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        raise UpstreamUnavailable("ERCraft 刷新响应不完整，未使用旧分数。")
    return data


async def refresh_stale_player_summary(
    client: AsyncERBSClient, nickname: str, summary: Mapping[str, Any], *,
    progress: SummaryProgressCallback | None = None,
) -> Mapping[str, Any]:
    identity = summary.get("data")
    if not isinstance(identity, Mapping):
        return summary
    observed = _observed_at(identity)
    if observed is None or (datetime.now(UTC) - observed).total_seconds() <= max(
        60, client.config.player_cache_seconds,
    ):
        return summary

    base = client.config.ercraft_api_base_url
    player_path = f"{base}/api/players/{quote(nickname, safe='')}"
    status = await _refresh_request(
        client, f"{player_path}/refresh", method="POST",
        params={"seasonId": identity.get("currentSeason")}, body={"mode": "rank"},
    )
    while status.get("status") not in {"success-changed", "success-no-change", "completed"}:
        state = status.get("status") or status.get("jobStatus")
        job = status.get("jobId")
        if state not in {
            "queued", "running", "pending", "resolving", "collecting-matches",
            "fetching-latest-matches",
        } or not isinstance(job, str) or not job:
            reason = status.get("lastError") or status.get("lastErrorCode") or state or "未知状态"
            raise UpstreamUnavailable(f"ERCraft 玩家资料已过期，刷新未完成：{reason}")
        if progress is not None:
            await progress({**status, "phase": "refresh", "nickname": nickname})
        await asyncio.sleep(3)
        status = await _refresh_request(client, f"{player_path}/refresh/{quote(job, safe='')}")

    # Refresh invalidates both remote snapshots. Evict their local copies too, including
    # the outage fallback, or a new RP could be paired with the old six-axis report.
    requests = (
        (f"{player_path}/summary", {"cacheOnly": "true"}),
        (f"{base}/api/player-analysis/roles", {
            "ownerPlayerId": identity.get("playerId"),
            "displaySeasonId": identity.get("currentSeason"), "scope": "overall",
        }),
    )
    for path, params in requests:
        key = f"{path}?{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
        await client._cache.delete(key)
        await client._stale_cache.delete(key)
    refreshed = await client.ercraft_player_summary(nickname)
    data = refreshed.get("data")
    if not isinstance(data, Mapping) or data.get("playerId") != identity.get("playerId"):
        raise UpstreamUnavailable("ERCraft 刷新后的玩家身份不匹配。")
    checked = _observed_at(data)
    if checked is None or (datetime.now(UTC) - checked).total_seconds() > max(
        60, client.config.player_cache_seconds,
    ):
        raise UpstreamUnavailable("ERCraft 刷新后仍返回过期资料，未使用旧分数。")
    return refreshed
