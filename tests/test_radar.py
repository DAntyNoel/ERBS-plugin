from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from erbs_plugin import AXES_VERSION, InvalidQuery
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


def test_radar_uses_upstream_six_axes_without_sample_shrinkage() -> None:
    reference = json.loads(
        (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text(
            encoding="utf-8"
        )
    )
    raw = reference["matches"][0]["raw"]
    small = RadarScorer().score(RadarSample("Kanami", (raw,)))
    full = RadarScorer().score(RadarSample("Kanami", tuple(raw for _ in range(20))))
    assert small.confidence == "insufficient"
    assert full.confidence == "medium"
    assert full.calibration_version == AXES_VERSION
    assert len(full.dimensions) == 6
    assert [d.score for d in full.dimensions[:5]] == [d.score for d in small.dimensions[:5]]
    assert small.dimensions[5].score is None
    assert full.dimensions[5].score == 100
    assert small.overall_score == reference["matches"][0]["onlineScore"]


def test_result_axis_uses_every_scored_match_as_upstream_does() -> None:
    reference = json.loads(
        (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text(
            encoding="utf-8"
        )
    )
    sample = RadarSample("sample", tuple(c["raw"] for c in reference["matches"][:210]))
    profile = RadarScorer().score(sample)
    assert profile.scored_matches == 210
    assert profile.complete_matches == 202
    from erbs_plugin.scoring.core import js_round

    expected = js_round(sum(c["onlineScore"] for c in reference["matches"][:210]) / 210, 2)
    assert profile.overall_score == expected
    assert profile.analysis_axes["aggregationPolicy"] == "production-overall-direct-match-mean"


def test_radar_does_not_turn_missing_data_into_neutral_or_zero_scores() -> None:
    profile = RadarScorer().score(RadarSample("missing", ({},)))
    assert profile.overall_score is None
    assert profile.scored_matches == 0
    assert all(item.score is None for item in profile.dimensions)
    section = build_radar_section(profile)
    assert all(axis["score"] is None for axis in section["axes"])
    assert section["topStyles"] == []
    assert section["matchScores"][0]["missingReason"] == "unsupported-or-missing-mode"


def test_radar_presentation_keeps_semantic_scores_without_svg_geometry() -> None:
    reference = json.loads(
        (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text(
            encoding="utf-8"
        )
    )
    profile = RadarScorer().score(
        RadarSample("sample", tuple(c["raw"] for c in reference["matches"][:2]))
    )
    section = build_radar_section(profile)
    assert len(section["axes"]) == 6
    assert "rings" not in section
    assert "scorePoints" not in section
    assert all("outerX" not in axis for axis in section["axes"])
    assert [axis["label"] for axis in section["axes"]] == [
        "生存",
        "交战",
        "运营",
        "支援",
        "结果",
        "稳定性",
    ]
    from erbs_plugin.legacy.radar import with_radar_geometry

    legacy = with_radar_geometry(section)
    assert len(legacy["rings"]) == 4
    assert all(len(ring["points"].split()) == 6 for ring in legacy["rings"])
    assert len(legacy["scorePoints"].split()) == 6
    assert legacy["axes"][1]["outerX"] == pytest.approx(340.4, abs=0.1)
    assert "outerX" not in section["axes"][1]
