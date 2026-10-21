from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService, UpstreamUnavailable
from erbs_plugin.cache import query_cache_spec

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text()
)
RAW = REFERENCE["matches"][0]["raw"]
KEYS = ("survival", "combat", "macro", "support", "finish", "consistency")


def published_report() -> dict:
    # Synthetic protocol fixture; the current live recent20 report may be unavailable.
    return {
        "requestStatus": "ready",
        "scope": {"displaySeasonId": 12, "analysisScope": "recent20", "apiSeasonId": 41},
        "report": {
            "version": "published-role-analysis.v4",
            "axisFormulaVersion": "s12-six-axis-role-reference.v2",
            "sourceContract": "test-contract",
            "authority": "test",
            "target": {
                "ownerPlayerId": "player:test",
                "overallAxes": [
                    {
                        "axis": key,
                        "combinedScore": 60 + index,
                        "sourceGames": 20,
                        "eligibleGames": 20,
                        "status": "ready",
                        "components": [],
                        "percentile": 70 + index,
                        "grade": "S",
                        "samplePlayers": 100,
                    }
                    for index, key in enumerate(KEYS)
                ],
            },
        },
    }


def make_client(*, fallback: bool, raw: dict, report: dict | None = None):
    requested = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        if request.url.host == "er.dakgg.io":
            return httpx.Response(200, json={"matches": [raw] * 20})
        assert request.method == "GET"
        assert request.headers["x-er-cache-only"] == "true"
        assert request.headers["x-er-no-upstream"] == "true"
        assert request.url.params["cacheOnly"] == "true"
        if request.url.path.endswith("/summary"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "playerId": "player:test",
                        "currentSeason": 12,
                    }
                },
            )
        assert request.url.path == "/api/player-analysis/roles"
        assert request.url.params["scope"] == "recent20"
        assert request.url.params["ownerPlayerId"] == "player:test"
        return httpx.Response(200, json=report or published_report())

    return AsyncERBSClient(
        ERBSConfig(ercraft_api_fallback=fallback),
        transport=httpx.MockTransport(handler),
    ), requested


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_local_computation_never_calls_api_when_six_axes_available(enabled: bool) -> None:
    raw = deepcopy(RAW)
    # Distinct IDs preserve 20 games through data-source deduplication.
    client, requested = make_client(fallback=enabled, raw=raw)
    async with client:
        # Direct service scoring allows repeated rows; dataset content is deliberately identical.
        from erbs_plugin.radar import RadarSample

        profile = await ERBSService(client)._radar_profile(
            RadarSample("sample", tuple(raw for _ in range(20))),
            count=20,
        )
    assert profile.source == "local"
    assert len(profile.dimensions) == 6
    assert requested == []


@pytest.mark.asyncio
async def test_fallback_is_opt_in_and_replaces_all_axes_without_blending() -> None:
    raw = {**RAW, "characterNum": 9999}
    client, requested = make_client(fallback=True, raw=raw)
    async with client:
        card = await ERBSService(client).radar_card("sample")
    section = card.sections[0]
    assert section["source"] == "ercraft-api-fallback"
    assert section["sourceMeta"]["scope"]["analysisScope"] == "recent20"
    assert [axis["score"] for axis in section["axes"]] == list(range(60, 66))
    assert [axis["percentile"] for axis in section["axes"]] == list(range(70, 76))
    assert len(requested) == 3


@pytest.mark.asyncio
async def test_disabled_fallback_preserves_local_missing_state() -> None:
    client, requested = make_client(fallback=False, raw={**RAW, "characterNum": 9999})
    async with client:
        card = await ERBSService(client).radar_card("sample")
    assert card.sections[0]["source"] == "local"
    assert all(axis["score"] is None for axis in card.sections[0]["axes"])
    assert len(requested) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["scope", "season", "identity", "axes", "missing-score"])
async def test_fallback_rejects_incompatible_scope_identity_or_axes(change: str) -> None:
    payload = published_report()
    if change == "scope":
        payload["scope"]["analysisScope"] = "overall"
    elif change == "season":
        payload["scope"]["displaySeasonId"] = 11
    elif change == "identity":
        payload["report"]["target"]["ownerPlayerId"] = "player:other"
    elif change == "axes":
        payload["report"]["target"]["overallAxes"].pop()
    else:
        payload["report"]["target"]["overallAxes"][0]["combinedScore"] = None
    client, _ = make_client(fallback=True, raw={**RAW, "characterNum": 9999}, report=payload)
    async with client:
        card = await ERBSService(client).radar_card("sample")
    assert card.sections[0]["source"] == "local"
    assert card.sections[0]["fallbackReason"]


@pytest.mark.asyncio
async def test_fallback_never_substitutes_twenty_matches_for_different_requested_count() -> None:
    client, requested = make_client(fallback=True, raw=RAW)
    async with client:
        with pytest.raises(UpstreamUnavailable):
            await client.published_role_axes("sample", count=60)
    assert requested == []


def test_fallback_settings_and_axes_version_are_part_of_cache_identity() -> None:
    options = dict(
        api_base_url="https://er.dakgg.io",
        language="zh-CN",
        count=20,
        page=1,
        season=None,
        weapon=None,
    )
    local = query_cache_spec("radar", ("sample",), **options)
    backup = query_cache_spec("radar", ("sample",), ercraft_api_fallback=True, **options)
    assert local != backup
    assert local["radarVersion"] == "production-analysis-axes.v1.1"
