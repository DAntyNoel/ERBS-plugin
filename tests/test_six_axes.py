from __future__ import annotations

import json
from pathlib import Path

import pytest

from erbs_plugin import build_production_axes, score_match
from erbs_plugin.scoring.axes import consistency_score

REFERENCE = json.loads(
    (Path(__file__).parent / "fixtures/ercraft-six-axis-reference.json").read_text()
)


@pytest.mark.parametrize("case", REFERENCE["cases"], ids=lambda case: case["name"])
def test_six_axes_match_unmodified_ercraft_output(case: dict) -> None:
    matches = [score_match(raw, tier_key=case["tierKey"]) for raw in case["raw"]]
    assert build_production_axes(matches, scope=case["scope"]) == case["expected"]


def test_consistency_is_population_standard_deviation_with_minimum_two_games() -> None:
    assert consistency_score([]) is None
    assert consistency_score([70]) is None
    assert consistency_score([70, 70, 70]) == 100
    assert consistency_score([40, 70, 100]) == 51.01
    assert consistency_score([0, 100]) == 0


def test_no_synthetic_comparison_percentile_for_local_historical_axes() -> None:
    case = REFERENCE["cases"][2]
    results = [score_match(raw) for raw in case["raw"]]
    axes = build_production_axes(results)
    assert all("percentile" not in row and "grade" not in row for row in axes["axes"])
    assert axes["axes"][1]["components"][0]["metric"] == "damage"
    assert axes["axes"][1]["components"][1]["metric"] == "combatContribution"
    assert axes["axes"][2]["components"][0]["metric"] == "monster"
    assert axes["axes"][3]["components"][0]["metric"] == "vision"
