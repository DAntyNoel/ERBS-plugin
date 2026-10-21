from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..scoring import AXES_VERSION, build_production_axes, score_match
from ..scoring.axes import AXIS_DESCRIPTIONS, AXIS_LABELS, AXIS_ORDER
from ..scoring.core import number
from .models import RadarComponentScore, RadarDimensionScore, RadarProfile, RadarSample

SOURCE_COMMIT = "93dd2a13345c53e5a6fb271c92d42b9fb62c7761"


def _dimension(
    row: Mapping[str, Any],
    total: int,
    *,
    published: bool = False,
) -> RadarDimensionScore:
    key = row["axis"]
    value = number(row.get("score"))
    components = tuple(
        RadarComponentScore(
            key=c.get("metric", c.get("key", "")),
            label=c.get("label", ""),
            value=number(c.get("actualValue")),
            score=number(c.get("score")),
        )
        for c in row.get("components", ())
    )
    count = int(row.get("sampleCount", 0))
    return RadarDimensionScore(
        key=key,
        label=AXIS_LABELS[key],
        description="ERCraft 发布报告：" + str(row.get("label", AXIS_LABELS[key]))
        if published
        else AXIS_DESCRIPTIONS[key],
        score=value,
        raw_score=value,
        coverage=count / total if total else 0,
        components=components,
        sample_count=count,
        status=row.get("status", "unavailable"),
        evidence=dict(row),
    )


class RadarScorer:
    """Local ERCraft production-analysis-axes.v1.1, including its aggregation rules."""

    def score(
        self, sample: RadarSample, *, scope: str = "overall", tier_key: str | None = None
    ) -> RadarProfile:
        results = tuple(score_match(match, tier_key=tier_key) for match in sample.matches)
        analysis = build_production_axes(results, scope=scope)
        eligible = [result for result in results if result["score"] is not None]
        complete = [r for r in eligible if not r["roleScoreDetail"]["missingMetrics"]]
        count = len(eligible)
        # These are ERCraft config.ts resolveGradeConfidence cutoffs.
        confidence = next(
            label
            for cutoff, label in (
                (5, "insufficient"),
                (10, "provisional"),
                (20, "low"),
                (40, "medium"),
                (float("inf"), "high"),
            )
            if count < cutoff
        )
        return RadarProfile(
            nickname=sample.nickname,
            sample_size=len(sample.matches),
            total_minutes=sum(max(0, number(m.get("playTime")) or 0) for m in sample.matches) / 60,
            confidence=confidence,
            cached=sample.cached,
            calibration_version=AXES_VERSION,
            dimensions=tuple(_dimension(row, len(sample.matches)) for row in analysis["axes"]),
            # The header shows the upstream finish axis; it is not an average of six axes.
            overall_score=analysis["axes"][4]["score"],
            scored_matches=count,
            complete_matches=len(complete),
            match_scores=results,
            analysis_axes=analysis,
            source_meta={
                "commit": SOURCE_COMMIT,
                "scope": "recent-matches",
                "aggregationScope": scope,
                "requestedMatches": len(sample.matches),
            },
        )


def published_profile(nickname: str, payload: Mapping[str, Any]) -> RadarProfile:
    """Use one complete published report as a fallback; never mix it with local axes."""
    report = payload["report"]
    rows = {row["axis"]: row for row in report["target"]["overallAxes"]}
    dimensions = []
    for key in AXIS_ORDER:
        published = rows[key]
        row = {
            **published,
            "score": published["combinedScore"],
            "sampleCount": published.get("eligibleGames", 0),
        }
        dimension = _dimension(row, int(published.get("sourceGames", 0)), published=True)
        dimensions.append(dimension)
    count = max(int(row.get("sourceGames", 0)) for row in rows.values())
    return RadarProfile(
        nickname=nickname,
        sample_size=count,
        total_minutes=0,
        confidence="upstream",
        cached=True,
        calibration_version=report["axisFormulaVersion"],
        dimensions=tuple(dimensions),
        overall_score=rows["finish"]["combinedScore"],
        scored_matches=count,
        analysis_axes=dict(report),
        source="ercraft-api-fallback",
        source_meta={
            "scope": dict(payload["scope"]),
            "version": report["version"],
            "sourceContract": report.get("sourceContract"),
            "authority": report.get("authority"),
        },
        fallback_reason="local-six-axis-data-incomplete",
    )


__all__ = ["RadarScorer", "published_profile"]
