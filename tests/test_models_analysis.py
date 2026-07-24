from __future__ import annotations

from erbs_plugin import ERBSAnalysisService
from erbs_plugin.models import MatchRecord, PlayerProfile


def profile(name: str, mmr: int) -> PlayerProfile:
    return PlayerProfile.from_api(
        {
            "player": {"name": name, "accountLevel": 100},
            "playerSeasons": [
                {"seasonId": 39, "mmr": mmr, "tierId": 7, "tierGradeId": 1}
            ],
            "playerSeasonOverviews": [
                {
                    "play": 10,
                    "win": 2,
                    "top3": 5,
                    "playerKill": 20,
                    "damageToPlayer": 5000,
                    "characterStats": [
                        {"characterNum": 1, "play": 7},
                        {"characterNum": 2, "play": 3},
                    ],
                }
            ],
        }
    )


def match(rank: int, gain: int, game_id: int) -> MatchRecord:
    return MatchRecord.from_api(
        {
            "gameId": game_id,
            "seasonId": 39,
            "nickname": "test",
            "gameRank": rank,
            "mmrGain": gain,
            "playerKill": 3,
            "playerAssistant": 5,
            "teamKill": 8,
            "damageToPlayer": 10000,
            "equipment": [1, 2, 3],
        }
    )


def test_compare_and_hero_pool() -> None:
    service = ERBSAnalysisService()
    left = profile("left", 8000)
    right = profile("right", 7000)

    result = service.compare(left, right)
    heroes = service.hero_pool(left)

    assert result["rows"][0] == {"label": "MMR", "left": 8000, "right": 7000}
    assert heroes[0]["characterNum"] == 1
    assert heroes[0]["usageRate"] == 0.7


def test_best_match_and_equipment_habits() -> None:
    service = ERBSAnalysisService()
    matches = [match(2, 10, 1), match(1, 5, 2), match(1, 20, 3)]

    assert service.best_match(matches).game_id == 3
    assert service.equipment_habits(matches)[0] == {"itemId": 1, "count": 3}
