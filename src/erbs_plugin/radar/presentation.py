from __future__ import annotations

from collections.abc import Mapping

from .models import RadarProfile

_AXIS_LABELS = {
    "survival": "生存",
    "combat": "交战",
    "macro": "运营",
    "support": "支援",
    "finish": "结果",
    "consistency": "稳定性",
}


def build_radar_section(profile: RadarProfile) -> Mapping[str, object]:
    axes: list[dict[str, object]] = []
    for dimension in profile.dimensions:
        axes.append(
            {
                "key": dimension.key,
                "label": _AXIS_LABELS.get(dimension.key, dimension.label),
                "description": dimension.description,
                "score": dimension.score,
                "status": dimension.status,
                "sampleCount": dimension.sample_count,
                "grade": dimension.evidence.get("grade"),
                "percentile": dimension.evidence.get("percentile"),
            }
        )

    confidence_labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "insufficient": "样本不足",
        "provisional": "暂定",
        "upstream": "上游结果",
    }
    top_styles = sorted(
        (item for item in profile.dimensions if item.score is not None),
        key=lambda item: item.score,
        reverse=True,
    )[:3]
    return {
        "title": "六维实战评分",
        "type": "radar",
        "axes": axes,
        "sampleSize": profile.sample_size,
        "totalMinutes": round(profile.total_minutes),
        "confidence": profile.confidence,
        "confidenceLabel": confidence_labels.get(profile.confidence, profile.confidence),
        "calibrationVersion": profile.calibration_version,
        "source": profile.source,
        "sourceLabel": "本地计算" if profile.source == "local" else "接口备选",
        "sourceMeta": dict(profile.source_meta),
        "fallbackReason": profile.fallback_reason,
        "analysisAxes": dict(profile.analysis_axes),
        "overallScore": profile.overall_score,
        "scoredMatches": profile.scored_matches,
        "completeMatches": profile.complete_matches,
        "matchScores": list(profile.match_scores),
        "topStyles": [
            {"label": dimension.label, "score": dimension.score} for dimension in top_styles
        ],
        "items": [
            {
                "key": dimension.key,
                "label": dimension.label,
                "score": dimension.score,
                "description": dimension.description,
                "coverage": round(dimension.coverage * 100),
                "status": dimension.status,
                "sampleCount": dimension.sample_count,
                "evidence": dict(dimension.evidence),
                "components": [
                    {
                        "label": component.label,
                        "value": round(component.value, 2) if component.value is not None else None,
                        "score": component.score,
                    }
                    for component in dimension.components
                ],
            }
            for dimension in profile.dimensions
        ],
    }


__all__ = ["build_radar_section"]
