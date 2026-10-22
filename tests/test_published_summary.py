from __future__ import annotations

from copy import deepcopy

import httpx
import pytest

from erbs_plugin import (
    AsyncERBSClient,
    ERBSConfig,
    ERBSService,
    PlayerNotFound,
    UpstreamUnavailable,
)
from erbs_plugin.published_summary import published_summary_grade
from erbs_plugin.radar import RadarScorer
from erbs_plugin.scoring.axes import AXIS_ORDER


def report() -> dict:
    return {
        "requestStatus": "ready",
        "scope": {"displaySeasonId": 12, "apiSeasonId": 41, "analysisScope": "overall",
                  "computedAt": "2026-08-30T15:11:27.049Z"},
        "report": {
            "version": "published-role-analysis.v4",
            "axisFormulaVersion": "s12-six-axis-role-reference.v2",
            "comparisonTierBand": None,
            "target": {
                "ownerPlayerId": "player:test",
                "overallAxes": [{
                    "axis": key, "combinedScore": 90 - index,
                    "percentile": percentile, "grade": grade, "status": "partial",
                    "sourceGames": 210, "eligibleGames": 210 - index,
                    "samplePlayers": 7000 + index, "components": [],
                } for index, (key, percentile, grade) in enumerate(zip(
                    AXIS_ORDER, (65.56, 35.19, 95, 85, 10.12, 69.99999999),
                    ("A", "C", "SSS", "SS", "D", "A"), strict=True,
                ))],
                "characterScopes": [{"characterNum": 67, "sourceGames": 208},
                                    {"characterNum": 31, "sourceGames": 2}],
            },
        },
    }


def identity() -> dict:
    return {"data": {
        "playerId": "player:test", "currentSeason": 12, "nickname": "Player Name",
        "rp": 4445, "tier": "Platinum 2", "normalizedTier": {"tierId": "platinum-2"},
    }, "source": "cache"}


def make_client(tmp_path, *, payload=None, summary=None, metadata_status=200):
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        assert request.method == "GET"
        if request.url.host == "er.dakgg.io":
            assert request.url.path == "/api/v1/data/characters"
            return httpx.Response(metadata_status, json={"characters": [{
                "id": 67, "name": "艾比盖尔",
                "skins": [{"id": 1067000, "grade": 1}, {"id": 1067003, "grade": 4}],
            }, {"id": 31, "skins": [{"id": 1031000, "grade": 1}]}]})
        assert request.url.host == "api.ercraft.net"
        if request.url.path.endswith("/summary"):
            assert request.url.path == "/api/players/Player Name/summary"
            assert request.url.params["cacheOnly"] == "true"
            return httpx.Response(200, json=summary if summary is not None else identity())
        assert request.url.path == "/api/player-analysis/roles"
        assert dict(request.url.params) == {
            "ownerPlayerId": "player:test", "displaySeasonId": "12", "scope": "overall",
        }
        assert "x-er-cache-only" not in request.headers
        return httpx.Response(200, json=payload if payload is not None else report())

    return AsyncERBSClient(ERBSConfig(
        asset_directory=tmp_path, retry_count=0,
    ), transport=httpx.MockTransport(handler)), requested


@pytest.mark.asyncio
async def test_website_report_is_used_without_dak_matches_or_local_scoring(tmp_path, monkeypatch):
    def no_local_scores(*args, **kwargs):
        raise AssertionError("published summary must not compute local scores")

    monkeypatch.setattr(RadarScorer, "score", no_local_scores)
    client, requested = make_client(tmp_path)
    async with client:
        card = await ERBSService(client).published_player_summary(" Player Name ")
        cached_card = await ERBSService(client).published_player_summary("Player Name")
    assert len(requested) == 3  # Two Craft APIs and optional static DAK metadata only.
    assert card == cached_card
    section = card.sections[0]
    assert section["source"] == card.footer["scoringSource"] == "ercraft-api"
    assert section["rp"] == 4445
    assert section["displaySeasonId"] == 12 and section["seasonId"] == 41
    assert section["sourceMeta"]["scope"]["computedAt"] == "2026-08-30T15:11:27.049Z"
    assert [axis["grade"] for axis in section["axes"]] == ["A", "C", "SSS", "SS", "D", "A"]
    for actual, original in zip(section["axes"], report()["report"]["target"]["overallAxes"],
                                strict=True):
        for key in ("percentile", "grade", "eligibleGames", "samplePlayers", "combinedScore"):
            assert actual[key] == original[key]
        assert actual["sampleCount"] == original["eligibleGames"]
    assert [c["weight"] for c in section["artCandidates"]] == [2, 208]
    assert [s["weight"] for s in section["artCandidates"][1]["skins"]] == [1, 10]


@pytest.mark.asyncio
async def test_optional_dak_art_metadata_failure_keeps_craft_report(tmp_path):
    client, _ = make_client(tmp_path, metadata_status=503)
    async with client:
        card = await ERBSService(client).published_player_summary("Player Name")
    assert card.sections[0]["axes"][0]["grade"] == "A"
    assert card.sections[0]["artCandidates"][1]["skins"][0]["summaryArtUrl"].endswith("67/10.webp")


@pytest.mark.asyncio
@pytest.mark.parametrize("rp", [0, None])
async def test_rp_zero_and_missing_remain_distinct(tmp_path, rp):
    data = identity()
    data["data"]["rp"] = rp
    client, _ = make_client(tmp_path, summary=data)
    async with client:
        card = await ERBSService(client).published_player_summary("Player Name")
    assert card.sections[0]["rp"] == rp


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "identity", "season", "scope", "tier", "duplicate-axis", "missing-axis",
    "missing-percentile", "grade-mismatch", "insufficient", "unavailable", "no-identity",
])
async def test_invalid_reports_never_become_local_evaluations(tmp_path, change):
    payload, summary = report(), identity()
    rows = payload["report"]["target"]["overallAxes"]
    if change == "identity":
        payload["report"]["target"]["ownerPlayerId"] = "player:other"
    elif change == "season":
        payload["scope"]["displaySeasonId"] = 11
    elif change == "scope":
        payload["scope"]["analysisScope"] = "recent20"
    elif change == "tier":
        payload["report"]["comparisonTierBand"] = "platinum"
    elif change == "duplicate-axis":
        rows[1]["axis"] = rows[0]["axis"]
    elif change == "missing-axis":
        rows.pop()
    elif change == "missing-percentile":
        rows[0]["percentile"] = None
    elif change == "grade-mismatch":
        rows[0]["grade"] = "S"
    elif change == "insufficient":
        rows[0]["eligibleGames"] = 9
    elif change == "unavailable":
        payload = {"requestStatus": "unavailable", "reason": "role-analysis-preparing"}
    else:
        summary = {"data": None}
    client, requested = make_client(tmp_path, payload=payload, summary=summary)
    async with client:
        with pytest.raises(UpstreamUnavailable, match="ERCraft"):
            await ERBSService(client).published_player_summary("Player Name")
    assert all(request.url.host == "api.ercraft.net" for request in requested)


@pytest.mark.asyncio
async def test_preparing_http_200_is_not_cached(tmp_path):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=(
            {"requestStatus": "unavailable"} if calls == 1 else report()
        ))

    async with AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamUnavailable, match="尚未就绪"):
            await client.ercraft_overall_analysis("player:test", 12)
        ready = await client.ercraft_overall_analysis("player:test", 12)
        assert ready["requestStatus"] == "ready"
    assert calls == 2


@pytest.mark.asyncio
async def test_missing_player_and_encoded_nickname(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(404)

    async with AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PlayerNotFound):
            await ERBSService(client).published_player_summary("玩家 /?#")
    assert "%2F%3F%23/summary" in seen[0]


@pytest.mark.parametrize("percentile,grade", [
    (0, "E"), (10, "D"), (25, "C"), (40, "B"), (55, "A"),
    (69.99999999, "A"), (70, "S"), (85, "SS"), (95, "SSS"), (100, "SSS"),
])
def test_only_matching_api_grade_is_accepted_before_display_rounding(percentile, grade):
    axis = deepcopy(report()["report"]["target"]["overallAxes"][0])
    axis.update(percentile=percentile, grade=grade)
    assert published_summary_grade(axis) == grade
    axis["grade"] = None
    assert published_summary_grade(axis) is None
