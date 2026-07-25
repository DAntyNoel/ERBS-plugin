from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


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
    value: float
    score: float


@dataclass(frozen=True, slots=True)
class RadarDimensionScore:
    key: str
    label: str
    description: str
    score: int
    raw_score: float
    coverage: float
    components: tuple[RadarComponentScore, ...]


@dataclass(frozen=True, slots=True)
class RadarProfile:
    nickname: str
    sample_size: int
    total_minutes: float
    confidence: str
    cached: bool
    calibration_version: str
    dimensions: tuple[RadarDimensionScore, ...]


__all__ = [
    "RadarComponentScore",
    "RadarDimensionScore",
    "RadarMetrics",
    "RadarProfile",
    "RadarSample",
]
