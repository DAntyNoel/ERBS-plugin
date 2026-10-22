from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from ..cache import AsyncTTLCache
from ..config import ERBSConfig
from ..exceptions import PlayerNotFound, RateLimited, UpstreamUnavailable
from .page import extract_character_analysis


class AsyncERBSClient:
    def __init__(
        self,
        config: ERBSConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config or ERBSConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.api_base_url,
            timeout=self.config.timeout_seconds,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": "ERBS-plugin/0.1.0"},
        )
        self._cache: AsyncTTLCache[Mapping[str, Any]] = AsyncTTLCache()
        self._stale_cache: AsyncTTLCache[Mapping[str, Any]] = AsyncTTLCache()
        self._negative_cache: AsyncTTLCache[bool] = AsyncTTLCache()
        self._semaphore = asyncio.Semaphore(self.config.request_concurrency)

    async def __aenter__(self) -> AsyncERBSClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        delay = self.config.retry_backoff_seconds * (2**attempt)
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=UTC)
                        delay = max(delay, (retry_at - datetime.now(UTC)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        pass
        return min(self.config.retry_max_delay_seconds, max(0.0, delay))

    async def _stale_result(self, key: str) -> Mapping[str, Any] | None:
        stale = await self._stale_cache.get(key)
        if stale is None:
            return None
        return {**stale, "_erbs_cached": True, "_erbs_stale": True}

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        ttl: int,
        player_lookup: bool = False,
        headers: Mapping[str, str] | None = None,
        service: str = "DAK.GG",
        response_parser: Callable[[httpx.Response], Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any]:
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        key = f"{path}?{json.dumps(clean_params, sort_keys=True, ensure_ascii=False)}"
        if player_lookup and await self._negative_cache.get(key):
            raise PlayerNotFound(path.rsplit("/", 1)[-1])
        cached = await self._cache.get(key)
        if cached is not None:
            return {**cached, "_erbs_cached": True}

        last_error: Exception | None = None
        rate_limited = False
        async with self._semaphore:
            # Another request may have populated the cache while this request waited.
            cached = await self._cache.get(key)
            if cached is not None:
                return {**cached, "_erbs_cached": True}
            for attempt in range(self.config.retry_count + 1):
                rate_limited = False
                response: httpx.Response | None = None
                try:
                    response = await self._client.get(path, params=clean_params, headers=headers)
                except httpx.TransportError as exc:
                    last_error = exc
                else:
                    if response.status_code == 404:
                        if player_lookup:
                            await self._negative_cache.set(
                                key, True, self.config.negative_cache_seconds
                            )
                            raise PlayerNotFound(path.rsplit("/", 1)[-1])
                        raise UpstreamUnavailable(f"{service} returned 404 for {path}")
                    if response.status_code in {408, 425, 429} or response.status_code >= 500:
                        rate_limited = response.status_code == 429
                        last_error = httpx.HTTPStatusError(
                            f"{service} returned {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    elif response.is_error:
                        error = httpx.HTTPStatusError(
                            f"{service} returned {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                        raise UpstreamUnavailable(
                            f"{service} returned {response.status_code} for {path}"
                        ) from error
                    else:
                        try:
                            payload = (
                                response_parser(response) if response_parser else response.json()
                            )
                        except ValueError as exc:
                            last_error = exc
                        else:
                            if isinstance(payload, Mapping):
                                await self._cache.set(key, payload, ttl)
                                await self._stale_cache.set(
                                    key, payload, ttl + self.config.stale_cache_seconds
                                )
                                return payload
                            last_error = TypeError(f"{service} returned an unexpected payload")
                if attempt < self.config.retry_count:
                    delay = self._retry_delay(attempt, response)
                    if delay > 0:
                        await asyncio.sleep(delay)

            if stale := await self._stale_result(key):
                return stale
        if rate_limited:
            raise RateLimited(f"{service} rate limit reached") from last_error
        raise UpstreamUnavailable(f"{service} is unavailable") from last_error

    async def published_role_axes(self, nickname: str, *, count: int = 20) -> Mapping[str, Any]:
        """Optional cache-only recent20 fallback; never substitute a full-season report."""
        if count != 20:
            raise UpstreamUnavailable("ERCraft 备选接口仅支持最近 20 场口径")
        base = self.config.ercraft_api_base_url
        headers = {"x-er-cache-only": "true", "x-er-no-upstream": "true"}
        summary = await self._request_json(
            f"{base}/api/players/{quote(nickname, safe='')}/summary",
            params={"cacheOnly": "true"},
            headers=headers,
            ttl=self.config.player_cache_seconds,
            service="ERCraft",
        )
        data = summary.get("data")
        if not isinstance(data, Mapping):
            raise UpstreamUnavailable("ERCraft 缺少玩家身份")
        player_id, season = data.get("playerId"), data.get("currentSeason")
        if not isinstance(player_id, str) or not isinstance(season, int):
            raise UpstreamUnavailable("ERCraft 缺少玩家身份或赛季")
        payload = await self._request_json(
            f"{base}/api/player-analysis/roles",
            params={
                "ownerPlayerId": player_id,
                "displaySeasonId": season,
                "scope": "recent20",
                "cacheOnly": "true",
            },
            headers=headers,
            ttl=self.config.match_cache_seconds,
            service="ERCraft",
        )
        report, scope = payload.get("report"), payload.get("scope")
        if not isinstance(report, Mapping) or not isinstance(scope, Mapping):
            raise UpstreamUnavailable("ERCraft 最近 20 场六维报告不可用")
        target = report.get("target")
        if not isinstance(target, Mapping):
            raise UpstreamUnavailable("ERCraft 缺少六维目标记录")
        if (
            scope.get("analysisScope") != "recent20"
            or scope.get("displaySeasonId") != season
            or target.get("ownerPlayerId") != player_id
        ):
            raise UpstreamUnavailable("ERCraft 六维身份、赛季或样本口径不匹配")
        axes = target.get("overallAxes")
        keys = {"survival", "combat", "macro", "support", "finish", "consistency"}
        if (
            not isinstance(axes, list)
            or len(axes) != 6
            or any(not isinstance(row, Mapping) for row in axes)
            or {row.get("axis") for row in axes} != keys
            or not isinstance(report.get("version"), str)
            or not isinstance(report.get("axisFormulaVersion"), str)
        ):
            raise UpstreamUnavailable("ERCraft 六维报告结构不匹配")
        from ..scoring.core import number

        for row in axes:
            score = number(row.get("combinedScore"))
            if score is None or not 0 <= score <= 100:
                raise UpstreamUnavailable("ERCraft 六维报告存在缺失评分")
            if any(
                number(row.get(key)) is None or number(row[key]) < 0
                for key in ("sourceGames", "eligibleGames")
            ):
                raise UpstreamUnavailable("ERCraft 六维报告缺少有效样本数")
            components = row.get("components", [])
            if not isinstance(components, list) or any(
                not isinstance(component, Mapping) for component in components
            ):
                raise UpstreamUnavailable("ERCraft 六维组件结构不匹配")
        return payload

    async def ercraft_player_summary(self, nickname: str) -> Mapping[str, Any]:
        """Resolve the public website identity and current display season."""
        return await self._request_json(
            f"{self.config.ercraft_api_base_url}/api/players/{quote(nickname, safe='')}/summary",
            params={"cacheOnly": "true"},
            headers={"x-er-cache-only": "true", "x-er-no-upstream": "true"},
            ttl=self.config.player_cache_seconds,
            player_lookup=True,
            service="ERCraft",
        )

    async def ercraft_overall_analysis(
        self, player_id: str, display_season: int,
    ) -> Mapping[str, Any]:
        """Read the website's overall report, including its published percentiles."""
        def ready_report(response: httpx.Response) -> Mapping[str, Any]:
            payload = response.json()
            if not isinstance(payload, Mapping) or payload.get("requestStatus") != "ready":
                # HTTP 200 can mean preparing. Do not cache that as a successful report.
                raise UpstreamUnavailable("ERCraft 评价报告尚未就绪，请稍后再试。")
            return payload

        return await self._request_json(
            f"{self.config.ercraft_api_base_url}/api/player-analysis/roles",
            params={
                "ownerPlayerId": player_id, "displaySeasonId": display_season,
                "scope": "overall",
            },
            ttl=self.config.match_cache_seconds,
            service="ERCraft",
            response_parser=ready_report,
        )

    async def player_default(self, nickname: str) -> Mapping[str, Any]:
        return await self._request_json(
            f"/api/v1/players/{quote(nickname, safe='')}",
            ttl=self.config.player_cache_seconds,
            player_lookup=True,
        )

    async def player_profile(
        self, nickname: str, *, season: str | None = None
    ) -> Mapping[str, Any]:
        return await self._request_json(
            f"/api/v1/players/{quote(nickname, safe='')}/profile",
            params={"season": season},
            ttl=self.config.player_cache_seconds,
            player_lookup=True,
        )

    async def player_matches(
        self,
        nickname: str,
        *,
        season: str | None = None,
        matching_mode: str | None = None,
        team_mode: str | None = None,
        page: int = 1,
        character: int | None = None,
    ) -> Mapping[str, Any]:
        return await self._request_json(
            f"/api/v1/players/{quote(nickname, safe='')}/matches",
            params={
                "season": season,
                "matchingMode": matching_mode,
                "teamMode": team_mode,
                "page": page,
                "character": character,
            },
            ttl=self.config.match_cache_seconds,
            player_lookup=True,
        )

    async def match_detail(self, nickname: str, season_id: int, game_id: int) -> Mapping[str, Any]:
        return await self._request_json(
            f"/api/v1/players/{quote(nickname, safe='')}/matches/{season_id}/{game_id}",
            ttl=self.config.match_cache_seconds,
        )

    async def metadata(self, name: str) -> Mapping[str, Any]:
        allowed = {
            "areas",
            "characters",
            "infusions",
            "items",
            "masteries",
            "monsters",
            "seasons",
            "skills",
            "tactical-skills",
            "tiers",
            "trait-skills",
            "weathers",
        }
        if name not in allowed:
            raise ValueError(f"Unsupported metadata name: {name}")
        return await self._request_json(
            f"/api/v1/data/{name}",
            params={"hl": self.config.language},
            ttl=self.config.metadata_cache_seconds,
        )

    async def leaderboard(
        self,
        *,
        page: int = 1,
        season_key: str | None = None,
        server_name: str | None = None,
        team_mode: str = "SQUAD",
    ) -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v0/leaderboard",
            params={
                "page": page,
                "seasonKey": season_key,
                "serverName": server_name,
                "teamMode": team_mode,
                "hl": self.config.language,
            },
            ttl=self.config.metadata_cache_seconds,
        )

    async def character_detail(
        self,
        character: str | int,
        *,
        matching_mode: str = "RANK",
        team_mode: str = "SQUAD",
        weapon_type: str | None = None,
        tier: str = "diamond_plus",
    ) -> Mapping[str, Any]:
        # Weapon selection happens after parsing; the page contains all weapon builds.
        return await self._request_json(
            f"{self.config.web_base_url}/characters/{quote(str(character), safe='')}",
            params={
                "hl": self.config.language,
                "tab": "introduction",
                "matchingMode": matching_mode,
                "teamMode": team_mode,
                "tier": tier if matching_mode == "RANK" else None,
            },
            ttl=self.config.metadata_cache_seconds,
            response_parser=lambda response: extract_character_analysis(response.text),
        )

    async def character_stats(
        self,
        *,
        matching_mode: str = "RANK",
        team_mode: str = "SQUAD",
        tier: str = "diamond_plus",
    ) -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v1/character-stats",
            params={
                "dt": 7,
                "matchingMode": matching_mode,
                "teamMode": team_mode,
                "tier": tier if matching_mode == "RANK" else None,
            },
            ttl=self.config.metadata_cache_seconds,
        )

    async def current_season(self) -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v0/current-season",
            params={"hl": self.config.language},
            ttl=self.config.metadata_cache_seconds,
        )

    async def tier_distribution(self, *, team_mode: str = "SQUAD") -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v0/statistics/tier-distribution",
            params={"teamMode": team_mode, "hl": self.config.language},
            ttl=self.config.metadata_cache_seconds,
        )

    async def routes(self, **params: Any) -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v1/routes",
            params={"hl": self.config.language, **params},
            ttl=self.config.metadata_cache_seconds,
        )
