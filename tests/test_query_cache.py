from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime

import pytest

import erbs_plugin.api as api_module
import erbs_plugin.cache.query as query_cache_module
import erbs_plugin.summary_art as summary_art_module
from erbs_plugin.cache import QueryCacheDatabase, query_cache_spec
from erbs_plugin.config import ERBSConfig
from erbs_plugin.models import CardPayload
from erbs_plugin.scoring.grades import SUMMARY_GRADE_VERSION
from erbs_plugin.summary_art import SUMMARY_ART_VERSION
from erbs_plugin.summary_scope import SUMMARY_SCOPE_VERSION

EXPECTED_OPERATIONS = {
    "search", "character-stats", "character-equipment", "tier-stats", "tier-cutoffs",
    "overview",
    "rank",
    "stats",
    "matches",
    "recent",
    "radar",
    "summary",
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
    assert config.query_cache_seconds["summary"] == 180


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
async def test_scoring_version_prevents_reusing_old_style_payloads(tmp_path) -> None:
    database = QueryCacheDatabase(tmp_path / "queries.sqlite3")
    old_spec = _spec("radar")
    del old_spec["scoringVersion"]
    await database.set(old_spec, CardPayload(kind="radar", title="old style"), ttl=300)
    assert await database.get(_spec("radar")) is None


@pytest.mark.asyncio
async def test_summary_cache_is_distinct_from_radar_and_requested_sample_count(tmp_path) -> None:
    database = QueryCacheDatabase(tmp_path / "queries.sqlite3")
    summary_spec = {**_spec("summary"), "count": 20}
    await database.set(summary_spec, CardPayload(kind="summary", title="local summary"), ttl=180)

    assert await database.get({**summary_spec, "operation": "radar"}) is None
    assert await database.get({**summary_spec, "count": 40}) is None
    cached = await database.get(summary_spec)
    assert cached is not None and cached.kind == "summary"


@pytest.mark.asyncio
async def test_summary_scope_version_rejects_recent_20_cache(tmp_path) -> None:
    database = QueryCacheDatabase(tmp_path / "queries.sqlite3")
    current_spec = _spec("summary")
    assert current_spec["summaryScopeVersion"] == SUMMARY_SCOPE_VERSION
    old_spec = {key: value for key, value in current_spec.items() if key != "summaryScopeVersion"}
    await database.set(old_spec, CardPayload(kind="summary", title="recent20"), ttl=180)

    assert await database.get(current_spec) is None
    assert "summaryScopeVersion" not in _spec("radar")
    assert "summaryMatchLimit" not in _spec("radar")
    assert current_spec["summaryMatchLimit"] == 500
    await database.set(current_spec, CardPayload(kind="summary", title="capped500"), ttl=180)
    assert await database.get({**current_spec, "summaryMatchLimit": 1000}) is None


@pytest.mark.asyncio
async def test_summary_grade_version_rejects_old_numeric_only_payload_cache(tmp_path) -> None:
    database = QueryCacheDatabase(tmp_path / "queries.sqlite3")
    current_spec = _spec("summary")
    assert current_spec["summaryGradeVersion"] == SUMMARY_GRADE_VERSION
    old_spec = {key: value for key, value in current_spec.items() if key != "summaryGradeVersion"}
    await database.set(old_spec, CardPayload(kind="summary", title="numeric-only"), ttl=180)

    assert await database.get(current_spec) is None


@pytest.mark.parametrize("operation", sorted(EXPECTED_OPERATIONS - {"summary"}))
def test_summary_grade_version_does_not_change_other_query_cache_specs(operation: str) -> None:
    assert "summaryGradeVersion" not in _spec(operation)


@pytest.mark.asyncio
async def test_summary_art_version_rejects_previous_fixed_art_cache(tmp_path) -> None:
    database = QueryCacheDatabase(tmp_path / "queries.sqlite3")
    current_spec = _spec("summary")
    assert current_spec["summaryArtVersion"] == SUMMARY_ART_VERSION
    old_spec = {key: value for key, value in current_spec.items() if key != "summaryArtVersion"}
    await database.set(old_spec, CardPayload(kind="summary", title="fixed art"), ttl=180)

    assert await database.get(current_spec) is None


@pytest.mark.parametrize("operation", sorted(EXPECTED_OPERATIONS - {"summary"}))
def test_summary_art_version_does_not_change_other_query_cache_specs(operation: str) -> None:
    assert "summaryArtVersion" not in _spec(operation)


@pytest.mark.asyncio
@pytest.mark.parametrize("output_format", ["json", "bytes"])
async def test_summary_cache_hit_redraws_skin_without_consuming_candidates(
    monkeypatch, tmp_path, output_format: str,
) -> None:
    config = ERBSConfig(
        api_base_url="https://example.test",
        private_database_path=tmp_path / "queries.sqlite3",
    )
    candidates = [{
        "characterId": 1,
        "characterName": "杰琪",
        "weight": 4,
        "skins": [
            {"skinId": 1001000, "skinName": "杰琪", "skinGrade": 1, "weight": 1,
             "characterImageUrl": "https://cdn.dak.gg/base.png"},
            {"skinId": 1001003, "skinName": "系统冲击 杰琪", "skinGrade": 4, "weight": 10,
             "characterImageUrl": "https://cdn.dak.gg/epic.png"},
        ],
    }]
    source = CardPayload(
        kind="summary", title="player",
        sections=({"type": "player-summary", "artCandidates": candidates},),
    )
    service_calls = 0
    selected_sections: list[dict[str, object]] = []
    next_skin = iter((0, 1))

    class FakeClient:
        def __init__(self) -> None:
            self.config = config

    class FakeService:
        async def player_summary(
            self, nickname: str, *, count: int, season: str | None,
        ) -> CardPayload:
            nonlocal service_calls
            service_calls += 1
            assert nickname == "player" and count == 20 and season is None
            return source

    class FakeRenderer:
        async def render(self, payload: CardPayload) -> bytes:
            section = dict(payload.sections[0])
            assert "artCandidates" not in section
            selected_sections.append(section)
            return str(section["skinId"]).encode()

    def choices(population, *, weights, k):
        assert k == 1
        if "skins" in population[0]:
            assert weights == [4]
            return [population[0]]
        assert weights == [1, 10]
        return [population[next(next_skin)]]

    monkeypatch.setattr(api_module, "ERBSService", lambda _: FakeService())
    monkeypatch.setattr(summary_art_module.random, "choices", choices)
    client = FakeClient()
    renderer = FakeRenderer()
    first = await api_module.query(
        "summary", "player", format=output_format, client=client, renderer=renderer,
    )
    second = await api_module.query(
        "summary", "player", format=output_format, client=client, renderer=renderer,
    )

    assert service_calls == 1
    if output_format == "json":
        first_payload, second_payload = json.loads(first), json.loads(second)
        assert first_payload["footer"]["cached"] is False
        assert second_payload["footer"]["cached"] is True
        selected_sections = [first_payload["sections"][0], second_payload["sections"][0]]
    else:
        assert (first, second) == (b"1001000", b"1001003")
    assert [section["skinId"] for section in selected_sections] == [1001000, 1001003]
    assert all("artCandidates" not in section for section in selected_sections)

    cached = await QueryCacheDatabase(config.private_database_path).get(
        {**_spec("summary"), "count": 20}
    )
    assert cached is not None
    assert cached.sections[0]["artCandidates"] == candidates
    assert "skinId" not in cached.sections[0]
    assert source.sections[0]["artCandidates"] == candidates
    assert "skinId" not in source.sections[0]


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
