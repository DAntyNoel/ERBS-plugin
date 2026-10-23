from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest

from erbs_plugin import compute_match_grade, score_match
from erbs_plugin.scoring.core import document, js_round

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures" / "ercraft-scoring-reference.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", REFERENCE["matches"] + REFERENCE["boundaries"])
def test_numerical_core_matches_unmodified_typescript(case: dict) -> None:
    # Includes the full intermediate evidence, rounding, missing fields, and fallback metadata.
    assert compute_match_grade(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", REFERENCE["matches"])
def test_raw_dak_adapter_matches_online_numeric_score(case: dict) -> None:
    actual = score_match(case["raw"])
    assert actual["score"] == case["onlineScore"]
    assert actual["baselineTierKey"] == case["input"]["tierKey"]
    assert actual["roleScoreDetail"] == case["expected"]["roleScoreDetail"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"mmrAfter": None}, "missing-pre-match-rp"),
        ({"mmrGain": None}, "missing-pre-match-rp"),
        ({"mmrAfter": 0, "mmrGain": 0}, "missing-pre-match-rp"),
        ({"mmrAfter": float("nan")}, "missing-pre-match-rp"),
        ({"bestWeapon": None}, "missing-weapon"),
        ({"bestWeapon": 0}, "missing-weapon"),
        ({"characterNum": 9999}, "unsupported-character-weapon"),
        ({"seasonId": 43}, "unsupported-or-missing-season"),
        ({"seasonId": None}, "unsupported-or-missing-season"),
        ({"matchingMode": 2}, "unsupported-or-missing-mode"),
        ({"matchingTeamMode": None}, "unsupported-or-missing-mode"),
        ({"gameRank": 9}, "missing-or-invalid-placement"),
    ],
)
def test_adapter_preserves_unknowns(change: dict, reason: str) -> None:
    result = score_match({**REFERENCE["matches"][0]["raw"], **change})
    assert result["score"] is None
    assert result["missingReason"] == reason
    json.dumps(result, allow_nan=False)


def test_zero_team_kills_removes_combat_and_renormalizes() -> None:
    result = score_match({**REFERENCE["matches"][0]["raw"], "teamKill": 0})
    detail = result["roleScoreDetail"]
    assert detail["missingMetrics"] == ["combatContribution"]
    assert detail["effectiveWeight"] == 71
    assert result["score"] is not None


def test_missing_statistic_is_distinct_from_zero() -> None:
    match = REFERENCE["matches"][0]["raw"]
    missing = score_match({**match, "playerDeaths": None})
    zero = score_match({**match, "playerDeaths": 0})
    assert "survival" in missing["roleScoreDetail"]["missingMetrics"]
    assert zero["roleScoreDetail"]["metricScores"]["survival"] == 95


def test_pre_match_rp_selects_tier_before_promotion() -> None:
    result = score_match({**REFERENCE["matches"][0]["raw"], "mmrAfter": 3650, "mmrGain": 100})
    assert result["baselineTierKey"] == "gold"
    assert result["preMatchRp"] == 3550


def test_explicit_baseline_tier_allows_unknown_season_without_guessing_ladder() -> None:
    result = score_match({**REFERENCE["matches"][0]["raw"], "seasonId": 43}, tier_key="gold")
    assert result["score"] is not None
    assert result["baselineTierKey"] == "gold"


def test_normal_fill_requires_opt_in_and_explicit_baseline_without_using_hidden_mmr() -> None:
    normal = {
        **REFERENCE["matches"][0]["raw"], "matchingMode": 2, "seasonId": 0,
        "mmrAfter": 0, "mmrGain": 0,
    }
    assert score_match(normal, tier_key="gold")["score"] is None
    assert score_match(normal, allow_normal=True)["score"] is None
    actual = score_match(normal, tier_key="gold", allow_normal=True)
    assert actual["score"] is not None
    assert actual["baselineTierKey"] == "gold"
    assert "preMatchRp" not in actual
    assert score_match(
        {**normal, "matchingMode": 4}, tier_key="gold", allow_normal=True,
    )["score"] is None
    assert score_match(
        {**normal, "matchingTeamMode": 4}, tier_key="gold", allow_normal=True,
    )["score"] is None


def test_js_round_uses_positive_infinity_at_half_ties() -> None:
    assert js_round(2.5, 0) == 3
    assert js_round(-2.5, 0) == -2
    assert js_round(0.49999999999999994, 0) == 0


def test_bundled_baselines_are_unchanged_upstream_artifacts() -> None:
    provenance = document("provenance.json")
    root = files("erbs_plugin.scoring").joinpath("data")
    for path, digest in provenance["sourceFiles"].items():
        data = root.joinpath(path.split("/")[-1]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
    assert "Copyright (c) 2026 MINE9289" in root.joinpath("LICENSE.txt").read_text(encoding="utf-8")
