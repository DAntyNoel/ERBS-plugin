from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RadarSample:
    nickname: str
    matches: tuple[Mapping[str, object], ...]
    cached: bool = False
    page_count: int = 0


@dataclass(frozen=True, slots=True)
class RadarMetrics:
    sample_size: int
    total_minutes: float
    values: Mapping[str, float]
    coverage: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RadarComponentScore:
    key: str
    label: str
    value: float | None
    score: float | None


@dataclass(frozen=True, slots=True)
class RadarDimensionScore:
    key: str
    label: str
    description: str
    score: float | None
    raw_score: float | None
    coverage: float
    components: tuple[RadarComponentScore, ...]
    sample_count: int = 0
    status: str = "unavailable"
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RadarProfile:
    nickname: str
    sample_size: int
    total_minutes: float
    confidence: str
    cached: bool
    calibration_version: str
    dimensions: tuple[RadarDimensionScore, ...]
    overall_score: float | None = None
    scored_matches: int = 0
    complete_matches: int = 0
    match_scores: tuple[Mapping[str, object], ...] = ()
    analysis_axes: Mapping[str, object] = field(default_factory=dict)
    source: str = "local"
    source_meta: Mapping[str, object] = field(default_factory=dict)
    fallback_reason: str | None = None


__all__ = [
    "RadarComponentScore",
    "RadarDimensionScore",
    "RadarMetrics",
    "RadarProfile",
    "RadarSample",
]
