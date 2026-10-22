"""Display ERCraft's published values without applying local scoring rules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

PUBLISHED_SUMMARY_SOURCE = "ercraft-api"
SummaryProgressCallback = Callable[[Mapping[str, Any]], Awaitable[None]]


def published_summary_grade(axis: Mapping) -> str | None:
    """Use the supplied grade as-is; absent grades remain absent."""
    grade = axis.get("grade")
    return grade if isinstance(grade, str) and grade else None
