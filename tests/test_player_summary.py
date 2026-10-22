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
            assert request.url.params["teamMode"] == "SQUAD"
            if request.url.params["matchingMode"] == "NORMAL":
                return httpx.Response(200, json={"matches": []})
            assert request.url.params["matchingMode"] == "RANK"
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
    assert section["scopeLabel"] == "本赛季全部排位 2 场（不足 20 场）"
    assert section["rankedCount"] == 2
    assert section["normalCount"] == 0
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
    assert len(requests) == 5


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
    assert default.summary_match_limit == 500
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


@pytest.mark.asyncio
@pytest.mark.parametrize("ranked_count", [0, 7, 19, 20, 21, 85, 500, 501])
async def test_summary_scores_every_current_season_ranked_game_and_fills_only_below_20(
    ranked_count: int,
) -> None:
    calls: list[tuple[str, int]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/data/seasons"):
            return httpx.Response(200, json={"seasons": [
                {"id": 39, "key": "SEASON_11"},
                {"id": 41, "key": "SEASON_12", "isCurrent": True},
            ]})
        if request.url.path.endswith("/profile"):
            assert request.url.params["season"] == "SEASON_12"
            return httpx.Response(200, json={
                "player": {"name": "Kanami"},
                "playerSeasons": [
                    {"seasonId": 39, "mmr": 9000},
                    *([{"seasonId": 41, "mmr": 0}] if ranked_count else []),
                ],
            })
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": []})
        if request.url.path.endswith("/matches"):
            assert request.url.params["season"] == "SEASON_12"
            mode, page = request.url.params["matchingMode"], int(request.url.params["page"])
            calls.append((mode, page))
            total = ranked_count if mode == "RANK" else 50
            rows = [
                {**reference_match(i + (1000 if mode == "NORMAL" else 0)),
                 "matchingMode": 3 if mode == "RANK" else 2,
                 "seasonId": 41 if mode == "RANK" else 0,
                 **({"mmrAfter": 0, "mmrGain": 0} if mode == "NORMAL" else {})}
                for i in range((page - 1) * 20 + 1, min(page * 20, total) + 1)
            ]
            return httpx.Response(200, json={
                "meta": {"season": "SEASON_12", "count": total}, "matches": rows,
            })
        raise AssertionError(request.url)

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        # The legacy count must never truncate all-season ranked data or change the fill target.
        card = await ERBSService(client).player_summary("Kanami", count=5)

    section, = card.sections
    assert section["seasonId"] == 41
    assert section["rp"] == (0 if ranked_count else None)
    assert section["sampleSize"] == min(500, max(20, ranked_count))
    assert section["rankedCount"] == min(500, ranked_count)
    assert section["rankedTotal"] == ranked_count
    assert section["truncated"] is (ranked_count > 500)
    assert section["normalCount"] == max(0, 20 - ranked_count)
    assert section["normalBaselineTier"] == ("iron" if ranked_count < 20 else None)
    assert all(
        axis["sampleCount"] == min(500, max(20, ranked_count)) for axis in section["axes"]
    )
    if ranked_count > 500:
        assert section["scopeLabel"] == f"本赛季最近 500 场排位（共 {ranked_count} 场）"
    else:
        assert section["scopeLabel"] == (
            f"本赛季全部排位 {ranked_count} 场"
            + (f" + 匹配 {20 - ranked_count} 场" if ranked_count < 20 else "")
        )
    assert ("NORMAL", 1) in calls if ranked_count < 20 else all(
        mode == "RANK" for mode, _ in calls
    )
    assert len([mode for mode, _ in calls if mode == "RANK"]) == max(
        1, (min(500, ranked_count) + 19) // 20,
    )


@pytest.mark.parametrize("limit", [0, 19, True, 20.5, "500"])
def test_summary_config_rejects_invalid_limit(limit: object) -> None:
    with pytest.raises(ValueError, match="summary_match_limit"):
        ERBSConfig(summary_match_limit=limit)
