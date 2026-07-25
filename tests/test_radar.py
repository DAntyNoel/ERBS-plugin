from __future__ import annotations

from collections.abc import Mapping

import pytest

from erbs_plugin import InvalidQuery
from erbs_plugin.radar import (
    RadarDataSource,
    RadarSample,
    RadarScorer,
    aggregate_radar_metrics,
    build_radar_section,
)


def match(game_id: int, *, deaths: int = 0) -> dict[str, object]:
    return {
        "gameId": game_id,
        "matchingMode": 3,
        "matchingTeamMode": 3,
        "playTime": 600,
        "damageToPlayer": 10000,
        "damageFromPlayer": 8000,
        "damageToMonster": 20000,
        "playerKill": 2,
        "playerAssistant": 3,
        "teamKill": 6,
        "playerDeaths": deaths,
        "healAmount": 2000,
        "damageOffsetedByShield_Player": 1000,
        "creditRevivedOthersCount": 1,
        "ccTimeToPlayer": 30,
        "teamRecover": 500,
        "protectAbsorb": 500,
        "tacticalSkillUseCount": 2,
        "monsterKill": 30,
        "crGetAnimal": 200,
        "crGetMutant": 100,
        "totalGainVFCredit": 1000,
        "totalUseVFCredit": 700,
        "viewContribution": 20,
        "addSurveillanceCamera": 1,
        "addTelephotoCamera": 3,
        "removeSurveillanceCamera": 1,
        "removeTelephotoCamera": 2,
        "useSecurityConsole": 2,
        "useReconDrone": 1,
        "useEmpDrone": 1,
        "craftLegend": 2,
        "craftMythic": 1,
    }


def test_aggregate_radar_metrics_uses_rates_ratios_and_style_fields() -> None:
    sample = RadarSample("Kanami", (match(1), match(2, deaths=2)))

    metrics = aggregate_radar_metrics(sample)

    assert metrics.sample_size == 2
    assert metrics.total_minutes == 20
    assert metrics.values["damage_to_player_per_min"] == 1000
    assert metrics.values["kills_per_10_min"] == 2
    assert metrics.values["pvp_damage_share"] == pytest.approx(1 / 3)
    assert metrics.values["kill_participation"] == pytest.approx(10 / 12)
    assert metrics.values["camera_actions_per_10_min"] == 7
    assert metrics.values["credit_turnover"] == pytest.approx(0.7)
    assert metrics.values["deathless_rate"] == 0.5
    assert metrics.values["multi_death_rate"] == 0.5
    assert set(metrics.coverage) == {
        "aggression",
        "pressure",
        "teamwork",
        "support",
        "development",
        "vision",
        "investment",
        "stability",
    }


class FakeRadarClient:
    def __init__(self, pages: Mapping[int, Mapping[str, object]]) -> None:
        self.pages = pages
        self.requested_pages: list[int] = []

    async def player_matches(self, nickname: str, **options: object) -> Mapping[str, object]:
        page = int(options["page"])
        self.requested_pages.append(page)
        assert nickname == "Kanami"
        assert options["matching_mode"] == "RANK"
        assert options["team_mode"] == "SQUAD"
        return self.pages.get(page, {"matches": []})


@pytest.mark.asyncio
async def test_radar_data_source_fetches_pages_filters_modes_and_deduplicates() -> None:
    wrong_mode = {**match(3), "matchingMode": 2}
    client = FakeRadarClient(
        {
            1: {"matches": [match(1), match(2)], "_erbs_cached": True},
            2: {"matches": [match(2), wrong_mode, match(4)]},
        }
    )

    sample = await RadarDataSource(client).fetch(" Kanami ", count=25)  # type: ignore[arg-type]

    assert sorted(client.requested_pages) == [1, 2]
    assert [item["gameId"] for item in sample.matches] == [1, 2, 4]
    assert sample.cached is True
    assert sample.page_count == 2


@pytest.mark.asyncio
async def test_radar_data_source_rejects_invalid_count_before_fetch() -> None:
    client = FakeRadarClient({})

    with pytest.raises(InvalidQuery, match="1 到 60"):
        await RadarDataSource(client).fetch("Kanami", count=0)  # type: ignore[arg-type]

    assert client.requested_pages == []


def test_radar_scorer_returns_eight_bounded_scores_and_confidence() -> None:
    sample = RadarSample("Kanami", tuple(match(index) for index in range(20)))

    profile = RadarScorer().score(sample)

    assert profile.confidence == "high"
    assert profile.calibration_version == "style-v1"
    assert len(profile.dimensions) == 8
    assert [item.key for item in profile.dimensions] == [
        "aggression",
        "pressure",
        "teamwork",
        "support",
        "development",
        "vision",
        "investment",
        "stability",
    ]
    assert all(0 <= item.score <= 100 for item in profile.dimensions)
    assert all(len(item.components) >= 2 for item in profile.dimensions)


def test_small_sample_scores_are_shrunk_toward_neutral() -> None:
    scorer = RadarScorer()
    small = scorer.score(RadarSample("Kanami", (match(1),)))
    full = scorer.score(RadarSample("Kanami", tuple(match(index) for index in range(20))))

    for small_dimension, full_dimension in zip(
        small.dimensions, full.dimensions, strict=True
    ):
        assert abs(small_dimension.score - 50) <= abs(full_dimension.score - 50)


def test_stability_rewards_lower_death_frequency() -> None:
    scorer = RadarScorer()
    stable = scorer.score(RadarSample("stable", tuple(match(index) for index in range(20))))
    risky = scorer.score(
        RadarSample("risky", tuple(match(index, deaths=3) for index in range(20)))
    )

    stable_score = next(item.score for item in stable.dimensions if item.key == "stability")
    risky_score = next(item.score for item in risky.dimensions if item.key == "stability")
    assert stable_score > risky_score


def test_radar_presentation_builds_eight_axis_svg_geometry() -> None:
    profile = RadarScorer().score(
        RadarSample("Kanami", tuple(match(index) for index in range(20)))
    )

    section = build_radar_section(profile)

    assert section["type"] == "radar"
    assert len(section["axes"]) == 8
    assert len(section["rings"]) == 4
    assert len(str(section["scorePoints"]).split()) == 8
    assert len(section["topStyles"]) == 3
    assert section["axes"][2]["compactAnchor"] == "end"
    assert section["axes"][6]["compactAnchor"] == "start"
    assert [axis["label"] for axis in section["axes"]] == [
        "进攻",
        "承伤",
        "团队",
        "支援",
        "运营",
        "控图",
        "资源",
        "稳健",
    ]
