"""Wait for ERCraft's website lookup and published report without a total deadline."""

from __future__ import annotations

from asyncio import sleep
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from ..exceptions import UpstreamUnavailable
from ..published_summary import SummaryProgressCallback

if TYPE_CHECKING:
    from .dak import AsyncERBSClient


class _Pending(Exception):
    pass


def _payload(response: httpx.Response) -> Mapping[str, Any]:
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise UpstreamUnavailable("ERCraft 返回了无法读取的响应。")
    _check_error(payload)
    return payload


def _check_error(payload: Mapping) -> None:
    for data in (payload, payload.get("data")):
        if not isinstance(data, Mapping):
            continue
        error = data.get("error") or data.get("errorCode")
        failed = any(data.get(key) in ("failed", "error") for key in (
            "status", "requestStatus", "jobStatus", "overallStatus",
        ))
        if error or failed:
            detail = error or data.get("message") or data.get("reason") or "查询失败"
            raise UpstreamUnavailable(f"ERCraft 查询失败：{detail}")


def _identity(response: httpx.Response) -> Mapping[str, Any]:
    payload = _payload(response)
    data = payload.get("data")
    if isinstance(data, Mapping) and data.get("playerId") and data.get("currentSeason"):
        return payload
    raise _Pending


def _report(response: httpx.Response) -> Mapping[str, Any]:
    payload = _payload(response)
    if isinstance(payload.get("report"), Mapping):
        return payload
    if payload.get("requestStatus") == "ready":
        raise UpstreamUnavailable("ERCraft 已完成评价，但未返回报告。")
    raise _Pending


async def _lookup(
    client: AsyncERBSClient, nickname: str, *, start: bool,
) -> Mapping[str, Any]:
    action = "lookup-start" if start else "lookup-status"
    payload = await client._request_json(
        f"{client.config.ercraft_api_base_url}/api/players/{quote(nickname, safe='')}/{action}",
        method="POST" if start else "GET",
        ttl=0, use_cache=False, service="ERCraft", response_parser=_payload,
    )
    data = payload.get("data")
    return data if isinstance(data, Mapping) else payload


async def _wait(
    phase: str, nickname: str | None, status: Mapping,
    progress: SummaryProgressCallback | None, *, default_delay: float,
) -> None:
    if progress is not None:
        await progress({**status, "phase": phase, "nickname": nickname})
    retry = status.get("retryAfterMs")
    delay = retry / 1000 if isinstance(retry, (int, float)) and retry > 0 else default_delay
    await sleep(max(1.0, min(30.0, delay)))


async def player_summary(
    client: AsyncERBSClient, nickname: str, *, progress: SummaryProgressCallback | None = None,
) -> Mapping[str, Any]:
    started = False
    while True:
        try:
            return await client._request_json(
                f"{client.config.ercraft_api_base_url}/api/players/"
                f"{quote(nickname, safe='')}/summary",
                params={"cacheOnly": "true"},
                headers={"x-er-cache-only": "true", "x-er-no-upstream": "true"},
                ttl=client.config.player_cache_seconds, player_lookup=True,
                service="ERCraft", response_parser=_identity,
            )
        except _Pending:
            status = await _lookup(client, nickname, start=not started)
            started = True
            await _wait("identity", nickname, status, progress, default_delay=3.0)


async def overall_analysis(
    client: AsyncERBSClient, player_id: str, display_season: int, *,
    nickname: str | None = None, progress: SummaryProgressCallback | None = None,
) -> Mapping[str, Any]:
    attempts = 0
    while True:
        try:
            return await client._request_json(
                f"{client.config.ercraft_api_base_url}/api/player-analysis/roles",
                params={
                    "ownerPlayerId": player_id, "displaySeasonId": display_season,
                    "scope": "overall",
                },
                ttl=client.config.match_cache_seconds, service="ERCraft", response_parser=_report,
            )
        except _Pending:
            status = await _lookup(client, nickname, start=attempts == 0) if nickname else {}
            attempts += 1
            await _wait("report", nickname, status, progress,
                        default_delay=2.0 if attempts <= 30 else 15.0)
