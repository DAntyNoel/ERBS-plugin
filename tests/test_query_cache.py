from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime

import pytest

import erbs_plugin.api as api_module
import erbs_plugin.cache.query as query_cache_module
from erbs_plugin.cache import QueryCacheDatabase, query_cache_spec
from erbs_plugin.config import ERBSConfig
from erbs_plugin.models import CardPayload

EXPECTED_OPERATIONS = {
    "overview",
    "rank",
    "stats",
    "matches",
    "recent",
    "radar",
    "characters",
    "skins",
    "teammates",
    "multi",
    "compare",
    "best-match",
    "hero-pool",
    "equipment",
    "leaderboard",
    "character",
    "item",
    "routes",
}


def _spec(operation: str) -> dict[str, object]:
    return query_cache_spec(
        operation,
        ("player",),
        api_base_url="https://example.test",
        language="zh-CN",
        count=5,
        page=1,
        season=None,
        weapon=None,
    )


def test_default_ttls_cover_every_query_operation() -> None:
    config = ERBSConfig(query_cache_enabled=False)

    assert set(config.query_cache_seconds) == EXPECTED_OPERATIONS
    assert config.query_cache_seconds["leaderboard"] < config.query_cache_seconds["overview"]
    assert config.query_cache_seconds["overview"] < config.query_cache_seconds["item"]


@pytest.mark.asyncio
async def test_private_database_round_trip_marks_cached_payload(tmp_path) -> None:
    path = tmp_path / "private" / "queries.sqlite3"
    database = QueryCacheDatabase(path)
    payload = CardPayload(
        kind="player",
        title="player",
        sections=({"title": "统计", "type": "stats", "items": []},),
        footer={"source": "DAK.GG", "cached": False},
    )

    await database.set(_spec("overview"), payload, ttl=300)
    cached = await database.get(_spec("overview"))

    assert path.is_file()
    assert cached is not None
    assert cached.title == "player"
    assert cached.footer["cached"] is True
    assert cached.footer["notice"] == "缓存命中，数据可能不是最新"
    datetime.fromisoformat(str(cached.footer["updatedAt"]))
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT operation, expires_at > created_at FROM query_cache"
        ).fetchone()
    assert row == ("overview", 1)


@pytest.mark.asyncio
async def test_query_types_honor_independent_database_expiry(monkeypatch, tmp_path) -> None:
    now = 1_000.0
    calls: Counter[str] = Counter()
    config = ERBSConfig(
        private_database_path=tmp_path / "queries.sqlite3",
        query_cache_seconds={"overview": 10, "rank": 20},
    )

    class FakeClient:
        def __init__(self) -> None:
            self.config = config

        async def aclose(self) -> None:
            return None

    class FakeService:
        async def player_overview(self, nickname: str) -> CardPayload:
            calls["overview"] += 1
            return CardPayload(kind="player", title=nickname, footer={"cached": False})

        async def rank_card(self, nickname: str, *, season: str | None) -> CardPayload:
            calls["rank"] += 1
            return CardPayload(kind="player", title=nickname, footer={"cached": False})

    monkeypatch.setattr(query_cache_module.time, "time", lambda: now)
    monkeypatch.setattr(api_module, "ERBSService", lambda _: FakeService())
    client = FakeClient()

    await api_module.query("overview", "player", client=client)
    await api_module.query("rank", "player", client=client)
    now = 1_015.0
    overview = json.loads(await api_module.query("overview", "player", client=client))
    rank = json.loads(await api_module.query("rank", "player", client=client))

    assert calls == Counter({"overview": 2, "rank": 1})
    assert overview["footer"]["cached"] is False
    assert overview["footer"]["updatedAt"] == "1970-01-01T00:16:55+00:00"
    assert "notice" not in overview["footer"]
    assert rank["footer"]["cached"] is True
    assert rank["footer"]["updatedAt"] == "1970-01-01T00:16:40+00:00"
    assert rank["footer"]["notice"] == "缓存命中，数据可能不是最新"
