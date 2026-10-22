from __future__ import annotations

from copy import deepcopy

import pytest

from erbs_plugin.scoring.axes import AXIS_ORDER
from erbs_plugin.summary_style import SUMMARY_STYLE_TITLES, select_summary_style

# Representative cases, in survival/combat/macro/support/finish/consistency order.
STYLE_CASES = [
    ("01", (70, 70, 70, 70, 70, 70), "至尊的六边形战士"),
    ("02", (60, 85, 60, 60, 70, 60), "可靠的带队老司机"),
    ("03", (39, 70, 50, 50, 50, 60), "莽撞的铁头战士"),
    ("04", (60, 60, 75, 60, 50, 39), "不稳定的蹦蹦炸弹"),
    ("05", (75, 70, 70, 65, 60, 75), "稳健的可靠战友"),
    ("06", (55, 65, 55, 55, 70, 70), "无情的上分机器"),
    ("07", (50, 50, 50, 50, 50, 50), "从容的均衡主义者"),
    ("08", (60, 45, 45, 45, 50, 50), "顽强的生存能手"),
    ("09", (45, 45, 60, 45, 50, 50), "精明的操盘运营手"),
    ("10", (45, 45, 45, 60, 50, 50), "无私的团队后盾"),
    ("11", (20, 20, 20, 20, 20, 20), "努力上分的萌新"),
    ("12", (24, 50, 50, 50, 50, 50), "倒霉的复活点常客"),
    ("13", (30, 70, 50, 50, 39, 20), "帅就完了的嘉豪"),
]


def api_axes(values) -> list[dict]:
    cuts = ((95, "SSS"), (85, "SS"), (70, "S"), (55, "A"),
            (40, "B"), (25, "C"), (10, "D"), (0, "E"))
    return [{
        "axis": key, "percentile": value,
        "grade": next(grade for cutoff, grade in cuts if value >= cutoff),
        "status": "partial", "sourceGames": 20, "eligibleGames": 18,
        "combinedScore": 50,
    } for key, value in zip(AXIS_ORDER, values, strict=True)]


@pytest.mark.parametrize("style_id,values,title", STYLE_CASES)
def test_all_thirteen_style_ids_and_exact_user_titles(style_id, values, title):
    assert select_summary_style(api_axes(values)) == style_id
    assert SUMMARY_STYLE_TITLES[style_id] == title


@pytest.mark.parametrize("values,expected", [
    ((90, 90, 90, 90, 90, 90), "01"),  # All-round outranks carrier/stability.
    ((20, 20, 20, 20, 20, 20), "11"),  # Broad weakness outranks respawn.
    ((20, 90, 50, 50, 20, 20), "13"),  # Bad conversion outranks reckless/respawn/random.
    ((20, 90, 50, 50, 75, 20), "03"),  # Reckless outranks carrier/respawn/random.
    ((50, 90, 50, 50, 75, 20), "02"),  # Carrier outranks random.
    ((20, 50, 80, 50, 50, 20), "12"),  # Respawn outranks random/macro dominance.
    ((50, 50, 85, 50, 50, 20), "04"),  # Random outranks action dominance.
    ((85, 60, 60, 60, 60, 75), "08"),  # Clear dominance outranks stable teammate.
    ((75, 70, 70, 65, 60, 75), "05"),  # Stable teammate outranks high specialization.
    ((75, 70, 70, 55, 75, 75), "08"),  # High specialization outranks steady results.
    ((75, 75, 75, 75, 60, 60), "08"),  # Action tie: survival before macro/support.
    ((50, 75, 75, 75, 60, 60), "09"),  # Action tie: macro before support.
    ((50, 75, 74, 75, 60, 60), "10"),  # Support tied with combat is eligible.
    ((50, 75.001, 75, 75, 60, 60), "07"),  # Combat higher prevents specialization.
    ((60, 45, 45, 45, 50, 50), "08"),
    ((59.999, 44.999, 44.999, 44.999, 50, 50), "07"),
    ((60, 45.001, 45, 45, 50, 50), "07"),  # Lead below 15 fails dominance.
    ((50, 70, 50, 50, 39.999, 60), "13"),
    ((50, 70, 50, 50, 40, 60), "07"),
    ((24.999, 50, 50, 50, 50, 50), "12"),
    ((25, 50, 50, 50, 50, 50), "07"),
    ((55, 65, 55, 55, 70, 69.999), "07"),
])
def test_website_precedence_ties_and_unrounded_boundaries(values, expected):
    assert select_summary_style(api_axes(values)) == expected


def test_axis_order_and_raw_scores_do_not_change_classification():
    axes = api_axes((45, 45, 45, 60, 50, 50))
    original = deepcopy(axes)
    assert select_summary_style(axes) == "10"
    for axis in axes:
        axis["combinedScore"] = 100
        axis["score"] = 100
        axis["key"] = axis.pop("axis")
    assert select_summary_style(tuple(reversed(axes))) == "10"
    assert original[0]["combinedScore"] == 50


@pytest.mark.parametrize("invalid", [
    "duplicate", "missing", "unknown", "nan", "boolean", "only-local-scores",
])
def test_invalid_or_local_axes_never_receive_an_evaluation_title(invalid):
    axes = api_axes((50, 50, 50, 50, 50, 50))
    if invalid == "duplicate":
        axes[1]["axis"] = axes[0]["axis"]
    elif invalid == "missing":
        axes.pop()
    elif invalid == "unknown":
        axes[0]["axis"] = "unknown"
    elif invalid == "nan":
        axes[0]["percentile"] = float("nan")
    elif invalid == "boolean":
        axes[0]["percentile"] = True
    else:
        for axis in axes:
            axis["score"] = axis.pop("percentile")
    assert select_summary_style(axes) is None


def test_title_uses_percentiles_without_revalidating_api_grades_or_samples():
    axes = api_axes((50, 50, 50, 50, 50, 50))
    for axis in axes:
        axis.update(grade=None, status="unavailable", sourceGames=6, eligibleGames=6)
    assert select_summary_style(axes) == "07"
