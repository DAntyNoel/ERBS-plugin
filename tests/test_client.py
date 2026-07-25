from __future__ import annotations

import httpx
import pytest

from erbs_plugin import (
    AsyncERBSClient,
    ERBSConfig,
    PlayerNotFound,
    RateLimited,
    UpstreamUnavailable,
)
from erbs_plugin.client import dak as dak_module


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


@pytest.mark.asyncio
async def test_character_detail_uses_current_character_stats_endpoint() -> None:
    seen_path = ""
    seen_query = ""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path, seen_query
        seen_path = request.url.path
        seen_query = request.url.query.decode()
        return httpx.Response(200, json={"characterDetailStatSnapshot": {}})

    client = AsyncERBSClient(ERBSConfig(language="zh-CN"), transport=httpx.MockTransport(handler))
    try:
        await client.character_detail("Emma", weapon_type="Arcana")
    finally:
        await client.aclose()

    assert seen_path == "/api/v1/character-stats"
    assert "character=Emma" in seen_query
    assert "matchingMode=RANK" in seen_query
    assert "teamMode=SQUAD" in seen_query
    assert "weaponType=Arcana" in seen_query


@pytest.mark.asyncio
async def test_transient_failures_are_retried_until_success() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary disconnect", request=request)
        if calls == 2:
            return httpx.Response(502, request=request)
        return httpx.Response(200, json={"characters": []}, request=request)

    config = ERBSConfig(retry_count=2, retry_backoff_seconds=0)
    client = AsyncERBSClient(config, transport=httpx.MockTransport(handler))
    try:
        result = await client.metadata("characters")
    finally:
        await client.aclose()

    assert result == {"characters": []}
    assert calls == 3


@pytest.mark.asyncio
async def test_invalid_json_is_treated_as_a_transient_failure() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, text="temporary proxy error", request=request)
        return httpx.Response(200, json={"characters": []}, request=request)

    config = ERBSConfig(retry_count=1, retry_backoff_seconds=0)
    client = AsyncERBSClient(config, transport=httpx.MockTransport(handler))
    try:
        result = await client.metadata("characters")
    finally:
        await client.aclose()

    assert result == {"characters": []}
    assert calls == 2


@pytest.mark.asyncio
async def test_rate_limit_retries_then_raises_rate_limited() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "1"}, request=request)

    config = ERBSConfig(retry_count=1, retry_max_delay_seconds=0)
    client = AsyncERBSClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RateLimited):
            await client.metadata("characters")
    finally:
        await client.aclose()

    assert calls == 2


@pytest.mark.asyncio
async def test_retry_after_controls_bounded_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"}, request=request)
        return httpx.Response(200, json={"characters": []}, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(dak_module.asyncio, "sleep", fake_sleep)
    config = ERBSConfig(retry_count=1, retry_max_delay_seconds=1)
    client = AsyncERBSClient(config, transport=httpx.MockTransport(handler))
    try:
        result = await client.metadata("characters")
    finally:
        await client.aclose()

    assert result == {"characters": []}
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_stale_cache_is_used_after_transient_failure() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"characters": [{"name": "Emma"}]}, request=request)
        raise httpx.ReadError("temporary disconnect", request=request)

    config = ERBSConfig(
        metadata_cache_seconds=0,
        stale_cache_seconds=60,
        retry_count=0,
    )
    client = AsyncERBSClient(config, transport=httpx.MockTransport(handler))
    try:
        fresh = await client.metadata("characters")
        stale = await client.metadata("characters")
    finally:
        await client.aclose()

    assert fresh == {"characters": [{"name": "Emma"}]}
    assert stale["characters"] == [{"name": "Emma"}]
    assert stale["_erbs_cached"] is True
    assert stale["_erbs_stale"] is True
    assert calls == 2


@pytest.mark.asyncio
async def test_non_retryable_client_error_is_not_cached() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"message": "forbidden"}, request=request)

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(UpstreamUnavailable):
            await client.metadata("characters")
        with pytest.raises(UpstreamUnavailable):
            await client.metadata("characters")
    finally:
        await client.aclose()

    assert calls == 2
