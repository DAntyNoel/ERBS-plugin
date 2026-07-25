from __future__ import annotations

import math
from collections.abc import Mapping

from .models import RadarProfile

_CENTER_X = 220.0
_CENTER_Y = 186.0
_RADIUS = 139.0
_LABEL_RADIUS = 154.0
_AXIS_LABELS = {
    "aggression": "进攻",
    "pressure": "承伤",
    "teamwork": "团队",
    "support": "支援",
    "development": "运营",
    "vision": "控图",
    "investment": "资源",
    "stability": "稳健",
}


def _point(index: int, radius: float) -> tuple[float, float]:
    angle = math.radians(-90 + index * 45)
    return (
        _CENTER_X + math.cos(angle) * radius,
        _CENTER_Y + math.sin(angle) * radius,
    )


def _points(radii: list[float]) -> str:
    return " ".join(
        f"{x:.1f},{y:.1f}" for index, radius in enumerate(radii) for x, y in [_point(index, radius)]
    )


def build_radar_section(profile: RadarProfile) -> Mapping[str, object]:
    axes: list[dict[str, object]] = []
    for index, dimension in enumerate(profile.dimensions):
        outer_x, outer_y = _point(index, _RADIUS)
        label_x, label_y = _point(index, _LABEL_RADIUS)
        score_x, score_y = _point(index, _RADIUS * dimension.score / 100)
        if label_x < _CENTER_X - 18:
            anchor = "end"
        elif label_x > _CENTER_X + 18:
            anchor = "start"
        else:
            anchor = "middle"
        compact_label_x = label_x
        compact_anchor = anchor
        if index == 2:
            compact_label_x = 390.0
            compact_anchor = "end"
        elif index == 6:
            compact_label_x = 50.0
            compact_anchor = "start"
        axes.append(
            {
                "key": dimension.key,
                "label": _AXIS_LABELS.get(dimension.key, dimension.label),
                "description": dimension.description,
                "score": dimension.score,
                "outerX": round(outer_x, 1),
                "outerY": round(outer_y, 1),
                "labelX": round(label_x, 1),
                "labelY": round(label_y, 1),
                "scoreX": round(score_x, 1),
                "scoreY": round(score_y, 1),
                "anchor": anchor,
                "compactLabelX": round(compact_label_x, 1),
                "compactAnchor": compact_anchor,
            }
        )

    confidence_labels = {"high": "高", "medium": "中", "low": "低"}
    top_styles = sorted(profile.dimensions, key=lambda item: item.score, reverse=True)[:3]
    return {
        "title": "八维实战风格",
        "type": "radar",
        "centerX": _CENTER_X,
        "centerY": _CENTER_Y,
        "rings": [
            {"value": value, "points": _points([_RADIUS * value / 100] * 8)}
            for value in (25, 50, 75, 100)
        ],
        "axes": axes,
        "scorePoints": _points(
            [_RADIUS * dimension.score / 100 for dimension in profile.dimensions]
        ),
        "sampleSize": profile.sample_size,
        "totalMinutes": round(profile.total_minutes),
        "confidence": profile.confidence,
        "confidenceLabel": confidence_labels.get(profile.confidence, profile.confidence),
        "calibrationVersion": profile.calibration_version,
        "topStyles": [
            {"label": dimension.label, "score": dimension.score}
            for dimension in top_styles
        ],
        "items": [
            {
                "key": dimension.key,
                "label": dimension.label,
                "score": dimension.score,
                "description": dimension.description,
                "coverage": round(dimension.coverage * 100),
                "components": [
                    {
                        "label": component.label,
                        "value": round(component.value, 2),
                        "score": round(component.score),
                    }
                    for component in dimension.components
                ],
            }
            for dimension in profile.dimensions
        ],
    }


__all__ = ["build_radar_section"]
