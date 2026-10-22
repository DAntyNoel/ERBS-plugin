from __future__ import annotations

import pytest

from erbs_plugin.exceptions import UpstreamUnavailable
from erbs_plugin.services.summary_data import fetch_summary_sample


def match(game_id: int, **changes: object) -> dict:
    return {
        "gameId": game_id, "seasonId": 41, "matchingMode": 3,
        "matchingTeamMode": 3, **changes,
    }


@pytest.mark.asyncio
async def test_fill_deduplicates_and_filters_season_mode_and_team_before_stopping() -> None:
    calls = []

    class Client:
        async def player_matches(self, nickname: str, **options):
            assert nickname == "Kanami"
            calls.append(options)
            if options["matching_mode"] == "RANK":
                return {"matches": [match(1), match(1), match(2, seasonId=39)]}
            return {"meta": {"season": "SEASON_12"}, "_erbs_cached": True, "matches": [
                match(1, matchingMode=2),
                match(2, matchingMode=2, seasonId=39),
                match(3, matchingMode=4),
                match(4, matchingMode=2, matchingTeamMode=4),
                match(5, matchingMode=2, seasonId=0),
                match(6, matchingMode=2),
            ]}

    sample = await fetch_summary_sample(
        Client(), " Kanami ", season="SEASON_12", season_id=41,
    )

    assert [row["gameId"] for row in sample.matches] == [1, 5, 6]
    assert sample.cached is True
    assert sample.page_count == 2
    assert [call["matching_mode"] for call in calls] == ["RANK", "NORMAL"]


@pytest.mark.asyncio
async def test_zero_season_normal_games_require_the_server_season_marker() -> None:
    class Client:
        async def player_matches(self, nickname: str, **options):
            return {"matches": [match(1, matchingMode=2, seasonId=0)]}

    sample = await fetch_summary_sample(Client(), "Kanami", season="SEASON_12", season_id=41)
    assert sample.matches == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 21, 60])
async def test_configurable_cap_keeps_original_total_and_stops_at_requested_sample(limit) -> None:
    pages = []

    class Client:
        async def player_matches(self, nickname: str, **options):
            assert options["matching_mode"] == "RANK"
            page = options["page"]
            pages.append(page)
            return {"meta": {"count": 85}, "matches": [
                match(i) for i in range((page-1)*20+1, min(page*20, 85)+1)
            ]}

    sample = await fetch_summary_sample(
        Client(), "Kanami", season="SEASON_12", season_id=41, max_ranked_matches=limit,
    )
    count = 85 if limit is None else limit
    assert len(sample.matches) == count
    assert sample.ranked_total == 85
    assert sample.truncated is (limit is not None)
    assert pages == list(range(1, (count+19)//20+1))


@pytest.mark.asyncio
async def test_fill_continues_past_duplicates_until_it_reaches_20() -> None:
    class Client:
        async def player_matches(self, nickname: str, **options):
            if options["matching_mode"] == "RANK":
                return {"matches": [match(i) for i in range(1, 8)]}
            ids = list(range(1, 21)) if options["page"] == 1 else [21, 22]
            # First page has seven already-seen ids and one invalid team, so another page is needed.
            return {"matches": [
                match(i, matchingMode=2, matchingTeamMode=4 if i == 20 else 3) for i in ids
            ]}

    sample = await fetch_summary_sample(Client(), "Kanami", season="SEASON_12", season_id=41)
    assert [row["gameId"] for row in sample.matches] == [*range(1, 20), 21]
    assert sample.page_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["repeat", "empty", "short", "season", "failure", "overlap", "count-change"],
)
async def test_incomplete_ranked_pages_raise_instead_of_becoming_a_partial_season(problem) -> None:
    class Client:
        async def player_matches(self, nickname: str, **options):
            assert options["matching_mode"] == "RANK"
            if options["page"] == 1:
                return {"meta": {"count": 40}, "matches": [match(i) for i in range(1, 21)]}
            if problem == "failure":
                raise UpstreamUnavailable("offline")
            rows = [match(i) for i in range(1, 21)] if problem == "repeat" else []
            if problem == "short":
                rows = [match(21)]
            if problem in {"overlap", "count-change"}:
                rows = [match(i) for i in range(20, 40)]
            return {"meta": {
                "count": 41 if problem == "count-change" else 40,
                "season": "SEASON_11" if problem == "season" else "SEASON_12",
            }, "matches": rows}

    with pytest.raises(UpstreamUnavailable):
        await fetch_summary_sample(Client(), "Kanami", season="SEASON_12", season_id=41)
