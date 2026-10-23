from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService, UpstreamUnavailable
from erbs_plugin.client import ercraft_refresh
from erbs_plugin.rendering import SkiaCardRenderer
from erbs_plugin.scoring.axes import AXIS_ORDER


def profile(*, stale=False, rp=7919):
    observed = datetime.now(UTC) - timedelta(days=50 if stale else 0)
    return {"data": {
        "playerId": "player:yulinh", "nickname": "宇麟涵", "currentSeason": 12,
        "rp": rp, "tier": "미스릴", "normalizedTier": {"tierId": "mithril"},
        "currentRankObservedAt": observed.isoformat(),
        "lastCheckedAt": datetime.now(UTC).isoformat(),
    }, "refreshedAt": datetime.now(UTC).isoformat()}


def report(games):
    return {"requestStatus": "ready", "scope": {
        "displaySeasonId": 12, "apiSeasonId": 41, "analysisScope": "overall",
    }, "report": {
        "version": "published-role-analysis.v4", "axisFormulaVersion": "test.v1",
        "comparisonTierBand": None, "target": {
            "ownerPlayerId": "player:yulinh", "characterScopes": [],
            "overallAxes": [{
                "axis": axis, "combinedScore": 66, "percentile": 44.1, "grade": "B",
                "status": "available", "sourceGames": games, "eligibleGames": games,
            } for axis in AXIS_ORDER],
        },
    }}


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["success-changed", "success-no-change", "completed"])
async def test_stale_profile_refreshes_rp_and_evicts_old_report(tmp_path, monkeypatch, terminal):
    calls, events = [], []
    refreshed = False
    polls = 0

    async def no_sleep(_):
        pass

    async def progress(event):
        events.append(event)

    monkeypatch.setattr(ercraft_refresh.asyncio, "sleep", no_sleep)

    def handler(request):
        nonlocal refreshed, polls
        calls.append(request)
        assert request.url.host == "api.ercraft.net"
        if request.url.path.endswith("/summary"):
            return httpx.Response(200, json=profile(stale=not refreshed,
                                                   rp=7919 if refreshed else 7115))
        if request.url.path.endswith("/refresh"):
            assert request.method == "POST"
            assert json.loads(request.content) == {"mode": "rank"}
            assert request.url.params["seasonId"] == "12"
            return httpx.Response(202, json={"data": {"status": "queued", "jobId": "job-1"}})
        if request.url.path.endswith("/refresh/job-1"):
            polls += 1
            if polls == 1:
                return httpx.Response(200, json={"data": {
                    "status": "collecting-matches", "jobId": "job-1",
                }})
            refreshed = True
            return httpx.Response(200, json={"data": {"status": terminal, "jobId": "job-1"}})
        assert request.url.path == "/api/player-analysis/roles"
        return httpx.Response(200, json=report(362 if refreshed else 106))

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        # This report must be evicted even if it is still within its local cache TTL.
        await client.ercraft_overall_analysis("player:yulinh", 12)
        await client._cache.set("another-player", {"rp": 1000}, 60)
        card = await ERBSService(client).published_player_summary("宇麟涵", progress=progress)
        assert await client._cache.get("another-player") == {"rp": 1000}
        again = await ERBSService(client).published_player_summary("宇麟涵")
    assert card.sections == again.sections
    assert again.footer["cached"] is True
    section = card.sections[0]
    assert section["rp"] == 7919
    assert section["tierImageUrl"].endswith("/66.png")
    assert section["sampleSize"] == 362
    assert section["scopeLabel"] == "S12 ERCraft 样本 362 场"
    assert [axis["sampleCount"] for axis in section["axes"]] == [362] * 6
    assert [axis["percentile"] for axis in section["axes"]] == [44.1] * 6
    assert sum(r.method == "POST" for r in calls) == 1
    assert events[0]["phase"] == "refresh"


@pytest.mark.asyncio
@pytest.mark.parametrize("rp", [0, 7919])
async def test_fresh_identity_does_not_enqueue_refresh(tmp_path, rp):
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json=profile(rp=rp) if request.url.path.endswith(
            "/summary",
        ) else report(362))

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        card = await ERBSService(client).published_player_summary("宇麟涵")
    assert card.sections[0]["rp"] == rp


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [
    "waiting-retry", "matches-updated", "refreshing-summary", "refreshing-stats",
    "refreshing-aggregate", "future-processing-state",
])
@pytest.mark.parametrize("code", ["upstream-error", "refresh-error"])
async def test_refresh_waits_through_retryable_and_new_intermediate_states(
    tmp_path, monkeypatch, state, code,
):
    sleep, progress = AsyncMock(), AsyncMock()
    monkeypatch.setattr(ercraft_refresh.asyncio, "sleep", sleep)
    calls = []
    refreshed = False

    def handler(request):
        nonlocal refreshed
        calls.append(request)
        if request.url.path.endswith("/summary"):
            return httpx.Response(200, json=profile(stale=not refreshed,
                                                   rp=7919 if refreshed else 7115))
        if request.url.path.endswith("/refresh"):
            return httpx.Response(202, json={"data": {
                "status": state, "jobId": "job-1", "lastErrorCode": code,
                "lastError": "previous upstream attempt failed", "retryableUpstreamFailure": True,
            }})
        if request.url.path.endswith("/refresh/job-1"):
            refreshed = True
            # Some responses expose jobStatus instead of status.
            return httpx.Response(200, json={"data": {"jobStatus": "completed", "jobId": "job-1"}})
        assert request.url.path == "/api/player-analysis/roles"
        return httpx.Response(200, json=report(362))

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        card = await ERBSService(client).published_player_summary("宇麟涵", progress=progress)
    assert card.sections[0]["rp"] == 7919
    assert card.sections[0]["sampleSize"] == 362
    assert sum(request.method == "POST" for request in calls) == 1
    sleep.assert_awaited_once_with(3)
    assert progress.await_args.args[0]["status"] == state
    assert progress.await_args.args[0]["lastErrorCode"] == code


@pytest.mark.asyncio
async def test_refresh_has_no_total_wait_limit_or_repeated_submissions(tmp_path, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(ercraft_refresh.asyncio, "sleep", sleep)
    posts, polls = 0, 0

    def handler(request):
        nonlocal posts, polls
        if request.url.path.endswith("/summary"):
            return httpx.Response(200, json=profile(stale=polls < 101))
        if request.url.path.endswith("/refresh"):
            posts += 1
            return httpx.Response(202, json={"data": {"status": "queued", "jobId": "job-1"}})
        if request.url.path.endswith("/refresh/job-1"):
            polls += 1
            return httpx.Response(200, json={"data": {
                "status": "waiting-retry" if polls <= 100 else "success-no-change",
                "jobId": "job-1", "lastErrorCode": "upstream-error",
            }})
        return httpx.Response(200, json=report(362))

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        card = await ERBSService(client).published_player_summary("宇麟涵")
    assert card.sections[0]["sampleSize"] == 362
    assert posts == 1 and polls == 101 and sleep.await_count == 101


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["failed", "error", "partial-failed", "timed-out", "partial"])
@pytest.mark.parametrize("code", ["upstream-error", "refresh-error"])
async def test_refresh_stops_at_terminal_failure_even_when_marked_retryable(
    tmp_path, monkeypatch, state, code,
):
    sleep = AsyncMock()
    monkeypatch.setattr(ercraft_refresh.asyncio, "sleep", sleep)
    polls = 0

    def handler(request):
        nonlocal polls
        if request.url.path.endswith("/summary"):
            return httpx.Response(200, json=profile(stale=True, rp=7115))
        if request.url.path.endswith("/refresh"):
            return httpx.Response(202, json={"data": {"status": "queued", "jobId": "job-1"}})
        assert request.url.path.endswith("/refresh/job-1")
        polls += 1
        return httpx.Response(200, json={"data": {
            "status": state, "jobId": "job-1", "lastErrorCode": code,
            "retryableUpstreamFailure": True,
        }})

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(UpstreamUnavailable, match=code):
            await ERBSService(client).published_player_summary("宇麟涵")
    assert polls == 1
    sleep.assert_awaited_once_with(3)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["failed", "upstream-game-list-stale", "http-error",
                                     "old-snapshot", "other-player"])
async def test_refresh_failure_does_not_publish_old_rank(tmp_path, failure):
    attempted = False

    def handler(request):
        nonlocal attempted
        if request.url.path.endswith("/summary"):
            payload = profile(stale=not attempted or failure == "old-snapshot", rp=7115)
            if attempted and failure == "other-player":
                payload["data"]["playerId"] = "player:someone-else"
            return httpx.Response(200, json=payload)
        assert request.url.path.endswith("/refresh")
        attempted = True
        state = "success-no-change" if failure in {"old-snapshot", "other-player"} else failure
        return httpx.Response(503 if failure == "http-error" else 200,
                              json={"data": {"status": state}})

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(UpstreamUnavailable, match="ERCraft"):
            await ERBSService(client).published_player_summary("宇麟涵")


@pytest.mark.asyncio
async def test_published_card_labels_actual_sample_in_existing_footer(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json=profile() if request.url.path.endswith(
            "/summary",
        ) else report(106))

    async with AsyncERBSClient(
        ERBSConfig(asset_directory=tmp_path), transport=httpx.MockTransport(handler),
    ) as client:
        card = await ERBSService(client).published_player_summary("宇麟涵")
    labels = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        await renderer.render(card)
    assert "7,919 RP" in labels
    assert "S12 ERCraft 样本 106 场" in labels
    assert "S12 ERCraft 全部" not in labels
