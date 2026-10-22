from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from erbs_plugin import AXES_VERSION, AsyncERBSClient, ERBSConfig, ERBSService, InvalidQuery
from erbs_plugin.radar import RadarDataSource
from erbs_plugin.scoring.grades import SUMMARY_GRADE_VERSION, summary_grade


def reference_match(game_id: int) -> dict[str, object]:
    reference = json.loads(
        (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text(
            encoding="utf-8"
        )
    )
    return {**reference["matches"][0]["raw"], "gameId": game_id, "skinCode": 1067000}


@pytest.mark.asyncio
async def test_summary_uses_profile_season_local_scores_and_real_sample_counts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "er.dakgg.io"
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [{"id": 41, "key": "SEASON_12"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={
                "player": {"name": "Kanami"},
                "playerSeasons": [{"seasonId": 41, "mmr": 4445, "tierId": 6}],
            })
        if request.url.path.endswith("/matches"):
            assert request.url.params["season"] == "SEASON_12"
            assert request.url.params["matchingMode"] == "RANK"
            assert request.url.params["teamMode"] == "SQUAD"
            return httpx.Response(200, json={"matches": [
                reference_match(1),
                {**reference_match(2), "seasonId": 39},
                {**reference_match(3), "matchingMode": 2},
                reference_match(4),
            ]})
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": [{
                "id": "67", "name": "卡佳", "imageUrl": "//cdn.dak.gg/portrait.png",
                "skins": [{"id": "1067000", "fullImageUrl": "//cdn.dak.gg/full.png"}],
            }]})
        raise AssertionError(request.url)

    client = AsyncERBSClient(
        ERBSConfig(query_cache_enabled=False, ercraft_api_fallback=True),
        transport=httpx.MockTransport(handler),
    )
    try:
        card = await ERBSService(client).player_summary(" Kanami ")
    finally:
        await client.aclose()

    assert card.kind == "summary"
    assert card.title == "Kanami"
    section, = card.sections
    assert section["type"] == "player-summary"
    assert section["sampleSize"] == 2
    assert section["requestedCount"] == 20
    assert section["scopeLabel"] == "最近 2 场排位三排"
    assert section["source"] == "local"
    assert section["sourceLabel"] == "本地计算"
    assert section["formulaVersion"] == AXES_VERSION
    assert section["seasonId"] == 41
    assert section["rp"] == 4445
    assert section["tierName"] == "灭钻"
    assert section["tierImageUrl"].endswith("/6.png")
    assert section["characterId"] == 67
    assert section["characterName"] == "卡佳"
    assert section["characterImageUrl"] == "//cdn.dak.gg/full.png"
    assert section["displayTitle"] == "六维实战档案"
    assert len(section["axes"]) == 6
    assert section["gradeVersion"] == SUMMARY_GRADE_VERSION
    assert all(axis["percentile"] is None for axis in section["axes"])
    assert all(axis["gradeVersion"] == SUMMARY_GRADE_VERSION for axis in section["axes"])
    assert all(axis["grade"] == summary_grade(axis["score"]) for axis in section["axes"])
    assert section["axes"][-1]["score"] == 100
    assert section["axes"][-1]["grade"] == "S"
    assert section["axes"][-1]["sampleCount"] == 2
    assert card.footer["scoringSource"] == "local"
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_summary_preserves_unavailable_axes_and_does_not_use_fallback() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [{"id": 41, "key": "SEASON_12"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={
                "player": {"name": "Kanami"}, "playerSeasons": [{"seasonId": 41, "mmr": 1}],
            })
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json={"matches": [{
                "gameId": 1, "seasonId": 41, "matchingMode": 3, "matchingTeamMode": 3,
            }]})
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": []})
        raise AssertionError("summary must not request ERCraft's API")

    client = AsyncERBSClient(
        ERBSConfig(ercraft_api_fallback=True), transport=httpx.MockTransport(handler)
    )
    try:
        card = await ERBSService(client).player_summary("Kanami")
    finally:
        await client.aclose()

    assert all(axis["score"] is None for axis in card.sections[0]["axes"])
    assert all(axis["grade"] is None for axis in card.sections[0]["axes"])
    assert all(axis["percentile"] is None for axis in card.sections[0]["axes"])
    assert card.sections[0]["gradeVersion"] == SUMMARY_GRADE_VERSION
    assert card.sections[0]["source"] == "local"
    assert card.sections[0]["characterImageUrl"] is None


@pytest.mark.asyncio
async def test_summary_rejects_empty_season_sample_instead_of_fabricating_scores() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [{"id": 41, "key": "SEASON_12"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={
                "player": {"name": "Kanami"}, "playerSeasons": [{"seasonId": 41, "mmr": 1}],
            })
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json={"matches": [{**reference_match(1), "seasonId": 39}]})
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": []})
        raise AssertionError(request.url)

    client = AsyncERBSClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(InvalidQuery, match="没有可用于总结图"):
            await ERBSService(client).player_summary("Kanami")
    finally:
        await client.aclose()


def test_summary_display_config_defaults_and_normalization() -> None:
    default = ERBSConfig()
    assert default.summary_art_path is None
    assert default.summary_title is None
    config = ERBSConfig(summary_art_path="illustration.png", summary_title="  实战档案  ")
    assert config.summary_art_path == Path("illustration.png")
    assert config.summary_title == "实战档案"


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_season", [None, "41", "season_12"])
@pytest.mark.parametrize("rp", [None, 0, 4445])
async def test_summary_selects_target_rank_season_and_preserves_unknown_or_zero_rp(
    requested_season: str | None, rp: int | None,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [
                {"id": "41", "key": "SEASON_12"}, {"id": 39, "key": "SEASON_11"},
            ]})
        if request.url.path.endswith("/profile"):
            assert request.url.params.get("season") == (
                "SEASON_12" if requested_season is not None else None
            )
            return httpx.Response(200, json={
                "player": {"name": "Kanami"},
                "playerSeasons": [
                    {"seasonId": 41, "mmr": 9999, "matchingModeId": 2, "teamModeId": 3},
                    {"seasonId": "41", "mmr": rp, "tierId": 6},
                    {"seasonId": 39, "mmr": 8000, "tierId": 7},
                ],
            })
        if request.url.path.endswith("/matches"):
            assert request.url.params["season"] == "SEASON_12"
            return httpx.Response(200, json={"matches": [reference_match(1)]})
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": []})
        raise AssertionError(request.url)

    client = AsyncERBSClient(transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).player_summary("Kanami", season=requested_season)
    finally:
        await client.aclose()

    section, = card.sections
    assert section["seasonId"] == 41
    assert section["rp"] == rp
    assert section["tierName"] == "灭钻"


@pytest.mark.asyncio
async def test_summary_explicit_old_season_uses_its_rank_not_latest_rank() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [
                {"id": 41, "key": "SEASON_12"}, {"id": 39, "key": "SEASON_11"},
            ]})
        if request.url.path.endswith("/profile"):
            assert request.url.params["season"] == "SEASON_11"
            return httpx.Response(200, json={
                "player": {"name": "Kanami"},
                "playerSeasons": [
                    {"seasonId": 41, "mmr": 5000, "tierId": 6},
                    {"seasonId": 39, "mmr": 8000, "tierId": 7},
                ],
            })
        if request.url.path.endswith("/matches"):
            assert request.url.params["season"] == "SEASON_11"
            return httpx.Response(200, json={"matches": [
                reference_match(1), {**reference_match(2), "seasonId": 39},
            ]})
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": []})
        raise AssertionError(request.url)

    client = AsyncERBSClient(transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).player_summary("Kanami", season="39")
    finally:
        await client.aclose()

    section, = card.sections
    assert section["seasonId"] == 39
    assert section["rp"] == 8000
    assert section["tierName"] == "半神"
    assert section["sampleSize"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 61])
async def test_summary_invalid_count_does_not_query_network(count: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid count should be rejected before network access")

    client = AsyncERBSClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(InvalidQuery, match="1 到 60"):
            await ERBSService(client).player_summary("Kanami", count=count)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_season_filter_is_optional_and_deduplicates_matching_pages() -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def player_matches(self, nickname: str, **options: object):
            calls.append(options)
            return {"matches": [reference_match(1), {**reference_match(2), "seasonId": 39}]}

    source = RadarDataSource(FakeClient())  # type: ignore[arg-type]
    filtered = await source.fetch("Kanami", count=21, season="SEASON_12", season_id=41)
    unfiltered = await source.fetch("Kanami")

    assert [row["gameId"] for row in filtered.matches] == [1]
    assert len(unfiltered.matches) == 2
    assert [call.get("season") for call in calls] == ["SEASON_12", "SEASON_12", None]
