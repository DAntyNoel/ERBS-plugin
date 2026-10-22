"""Validate ERCraft's published card grades without substituting local scores."""

from __future__ import annotations

import math
from collections.abc import Mapping

PUBLISHED_SUMMARY_SOURCE = "ercraft-api"
_CUTS = ((95, "SSS"), (85, "SS"), (70, "S"), (55, "A"),
         (40, "B"), (25, "C"), (10, "D"), (0, "E"))


def published_summary_grade(axis: Mapping) -> str | None:
    """Return the supplied grade only when its percentile and evidence agree.

    Thresholds validate the wire contract; missing grades are never generated.
    ERCraft's card accepts both available and partial axes with at least 10 games.
    """
    percentile = axis.get("percentile")
    if (
        axis.get("status") not in ("available", "partial")
        or not isinstance(percentile, (int, float)) or isinstance(percentile, bool)
        or not 0 <= percentile <= 100 or not math.isfinite(percentile)
    ):
        return None
    for key in ("sourceGames", "eligibleGames"):
        count = axis.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 10:
            return None
    if axis["eligibleGames"] > axis["sourceGames"]:
        return None
    expected = next(grade for lower, grade in _CUTS if percentile >= lower)
    return axis.get("grade") if axis.get("grade") == expected else None
