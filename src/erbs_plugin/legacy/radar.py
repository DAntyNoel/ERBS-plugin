"""SVG geometry used exclusively by the archived HTML renderer."""

from __future__ import annotations

import math
from typing import Any


def with_radar_geometry(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [with_radar_geometry(child) for child in value]
    if not isinstance(value, dict):
        return value
    result = {key: with_radar_geometry(child) for key, child in value.items()}
    if result.get("type") != "radar":
        return result
    axes = result.get("axes", [])
    count = len(axes)
    cx, cy, radius = 220.0, 186.0, 139.0

    def point(position: int, distance: float) -> tuple[float, float]:
        angle = math.radians(-90 + position * 360 / max(1, count))
        return cx + math.cos(angle) * distance, cy + math.sin(angle) * distance

    def points(radii: list[float]) -> str:
        return " ".join(
            f"{x:.1f},{y:.1f}"
            for position, distance in enumerate(radii)
            for x, y in [point(position, distance)]
        )

    for position, axis in enumerate(axes):
        outer_x, outer_y = point(position, radius)
        label_x, label_y = point(position, 154.0)
        score_x, score_y = point(position, radius * (axis.get("score") or 0) / 100)
        anchor = "end" if label_x < cx - 18 else "start" if label_x > cx + 18 else "middle"
        compact_x, compact_anchor = label_x, anchor
        if label_x > cx + 120:
            compact_x, compact_anchor = 390.0, "end"
        elif label_x < cx - 120:
            compact_x, compact_anchor = 50.0, "start"
        axis.update(
            outerX=round(outer_x, 1),
            outerY=round(outer_y, 1),
            labelX=round(label_x, 1),
            labelY=round(label_y, 1),
            scoreX=round(score_x, 1),
            scoreY=round(score_y, 1),
            anchor=anchor,
            compactLabelX=round(compact_x, 1),
            compactAnchor=compact_anchor,
        )
    result.update(
        centerX=cx,
        centerY=cy,
        rings=[
            {"value": v, "points": points([radius * v / 100] * count)} for v in (25, 50, 75, 100)
        ],
        scorePoints=points([radius * (axis.get("score") or 0) / 100 for axis in axes])
        if axes and all(axis.get("score") is not None for axis in axes)
        else "",
    )
    return result
