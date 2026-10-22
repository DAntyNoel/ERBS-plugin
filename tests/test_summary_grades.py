from __future__ import annotations

import pytest

from erbs_plugin.scoring.grades import SUMMARY_GRADE_VERSION, summary_grade


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (0, "E"), (9.999, "E"),
        (10, "D"), (24.999, "D"),
        (25, "C"), (39.999, "C"),
        (40, "B"), (54.999, "B"),
        (55, "A"), (69.999, "A"),
        (70, "S"), (100, "S"),
    ],
)
def test_summary_grades_use_explicit_local_score_bands(score: float, grade: str) -> None:
    assert summary_grade(score) == grade


@pytest.mark.parametrize(
    "score",
    [None, True, False, float("nan"), float("inf"), float("-inf"), -0.001, 100.001,
     "70", "", [], {}, object()],
)
def test_invalid_summary_scores_do_not_receive_a_grade(score: object) -> None:
    assert summary_grade(score) is None


def test_summary_grade_version_identifies_local_bands() -> None:
    assert SUMMARY_GRADE_VERSION == "local-six-axis-bands.v1"
