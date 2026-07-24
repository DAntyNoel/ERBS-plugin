from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from ..cache import AsyncTTLCache
from ..config import ERBSConfig
from ..exceptions import PlayerNotFound, RateLimited, UpstreamUnavailable


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
        self._negative_cache: AsyncTTLCache[bool] = AsyncTTLCache()
        self._semaphore = asyncio.Semaphore(self.config.request_concurrency)

    async def __aenter__(self) -> AsyncERBSClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        ttl: int,
        player_lookup: bool = False,
    ) -> Mapping[str, Any]:
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        key = f"{path}?{json.dumps(clean_params, sort_keys=True, ensure_ascii=False)}"
        if player_lookup and await self._negative_cache.get(key):
            raise PlayerNotFound(path.rsplit("/", 1)[-1])
        if cached := await self._cache.get(key):
            return {**cached, "_erbs_cached": True}

        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(self.config.retry_count + 1):
                try:
                    response = await self._client.get(path, params=clean_params)
                except httpx.HTTPError as exc:
                    last_error = exc
                else:
                    if response.status_code == 404:
                        if player_lookup:
                            await self._negative_cache.set(
                                key, True, self.config.negative_cache_seconds
                            )
                            raise PlayerNotFound(path.rsplit("/", 1)[-1])
                        raise UpstreamUnavailable(f"DAK.GG returned 404 for {path}")
                    if response.status_code == 429:
                        raise RateLimited("DAK.GG rate limit reached")
                    if response.status_code < 500:
                        try:
                            payload = response.json()
                        except ValueError as exc:
                            raise UpstreamUnavailable("DAK.GG returned invalid JSON") from exc
                        if not isinstance(payload, Mapping):
                            raise UpstreamUnavailable("DAK.GG returned an unexpected payload")
                        await self._cache.set(key, payload, ttl)
                        return payload
                    last_error = httpx.HTTPStatusError(
                        f"DAK.GG returned {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if attempt < self.config.retry_count:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise UpstreamUnavailable("DAK.GG is unavailable") from last_error

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

    async def match_detail(
        self, nickname: str, season_id: int, game_id: int
    ) -> Mapping[str, Any]:
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
        character_id: int,
        *,
        team_mode: str = "SQUAD",
        weapon_type: str | None = None,
    ) -> Mapping[str, Any]:
        return await self._request_json(
            f"/api/v0/characters/{character_id}",
            params={
                "hl": self.config.language,
                "teamMode": team_mode,
                "weaponType": weapon_type,
            },
            ttl=self.config.metadata_cache_seconds,
        )

    async def routes(self, **params: Any) -> Mapping[str, Any]:
        return await self._request_json(
            "/api/v1/routes",
            params={"hl": self.config.language, **params},
            ttl=self.config.metadata_cache_seconds,
        )
