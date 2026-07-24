from __future__ import annotations

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, PlayerNotFound


@pytest.mark.asyncio
async def test_player_profile_is_cached() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"player": {"name": "test", "accountLevel": 1}, "playerSeasons": []},
        )

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        first = await client.player_profile("test")
        second = await client.player_profile("test")
    finally:
        await client.aclose()

    assert calls == 1
    assert not first.get("_erbs_cached")
    assert second["_erbs_cached"] is True


@pytest.mark.asyncio
async def test_player_not_found_uses_negative_cache() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"message": "not found"})

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(PlayerNotFound):
            await client.player_profile("missing")
        with pytest.raises(PlayerNotFound):
            await client.player_profile("missing")
    finally:
        await client.aclose()

    assert calls == 1


@pytest.mark.asyncio
async def test_metadata_adds_language_parameter() -> None:
    seen_query = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_query
        seen_query = request.url.query.decode()
        return httpx.Response(200, json={"characters": []})

    client = AsyncERBSClient(ERBSConfig(language="zh-CN"), transport=httpx.MockTransport(handler))
    try:
        await client.metadata("characters")
    finally:
        await client.aclose()

    assert "hl=zh-CN" in seen_query
