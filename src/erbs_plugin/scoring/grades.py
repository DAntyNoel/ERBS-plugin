"""Display bands for local summary scores, independent of population percentiles."""

from __future__ import annotations

import math

SUMMARY_GRADE_VERSION = "local-six-axis-bands.v1"
_SUMMARY_CUTS = ((70, "S"), (55, "A"), (40, "B"), (25, "C"), (10, "D"), (0, "E"))


def summary_grade(score: object) -> str | None:
    """Classify a valid local 0–100 score without changing or rounding it."""
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not 0 <= score <= 100
        or not math.isfinite(score)
    ):
        return None
    return next(grade for lower, grade in _SUMMARY_CUTS if score >= lower)
