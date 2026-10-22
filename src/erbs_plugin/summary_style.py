"""ERCraft play-card-percentile.v4 selection with the configured Chinese titles.

Rules verified against the public PlayCardDialog-s8kz-wDg.js on 2026-10-22.
Only published percentiles are classified; local scores are never substituted.
"""

from __future__ import annotations

from collections.abc import Mapping

from .published_summary import published_summary_grade
from .scoring.axes import AXIS_ORDER

SUMMARY_STYLE_VERSION = "play-card-percentile.v4"
SUMMARY_STYLE_TITLES = {
    "01": "至尊的六边形战士",
    "02": "可靠的带队老司机",
    "03": "莽撞的铁头战士",
    "04": "不稳定的蹦蹦炸弹",
    "05": "稳健的可靠战友",
    "06": "无情的上分机器",
    "07": "从容的均衡主义者",
    "08": "顽强的生存能手",
    "09": "精明的操盘运营手",
    "10": "无私的团队后盾",
    "11": "努力上分的萌新",
    "12": "倒霉的复活点常客",
    "13": "帅就完了的嘉豪",
}


def select_summary_style(axes: object) -> str | None:
    """Match the website's thresholds, precedence and ties on six valid API axes."""
    if not isinstance(axes, (list, tuple)) or len(axes) != len(AXIS_ORDER):
        return None
    percentiles = {}
    for row in axes:
        if not isinstance(row, Mapping):
            return None
        key = row.get("axis", row.get("key"))
        if (
            not isinstance(key, str) or key not in AXIS_ORDER or key in percentiles
            or published_summary_grade(row) is None
        ):
            return None
        percentiles[key] = row["percentile"]
    values = [percentiles[key] for key in AXIS_ORDER]
    survival, combat, macro, support, finish, consistency = values
    # Accumulate in the same order as JavaScript reduce, including threshold boundaries.
    total = 0
    for value in values:
        total += value
    diagnostic_rules = (
        ("01", min(values) >= 70),
        ("11", len([value for value in values if value < 40]) >= 4
         and total / len(values) < 40 and max(values) < 70),
        ("13", combat >= 70 and finish < 40),
        ("03", combat >= 70 and survival < 40),
        ("02", combat >= 85 and finish >= 70),
        ("12", survival < 25),
        ("04", consistency < 40 and max(values) >= 70),
    )
    for style_id, matches in diagnostic_rules:
        if matches:
            return style_id

    # Survival, macro and support can dominate the four action axes. Combat has
    # already had its diagnostic rules; finish and consistency do not enter this pool.
    specialties = (
        ("08", survival, (combat, macro, support)),
        ("09", macro, (survival, combat, support)),
        ("10", support, (survival, combat, macro)),
    )
    for style_id, value, others in specialties:
        if value >= 60 and value - max(others) >= 15:
            return style_id
    if survival >= 70 and support >= 60 and consistency >= 70:
        return "05"
    # max() keeps the first tied item: survival -> macro -> support, as on the site.
    strongest = max(specialties, key=lambda item: item[1])
    if strongest[1] >= 70 and strongest[1] >= combat:
        return strongest[0]
    if finish >= 70 and consistency >= 70:
        return "06"
    return "07"
