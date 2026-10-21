"""Port of ERCraft productionAnalysisAxes.ts at 93dd2a1 (MIT, MINE9289)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .core import js_round, number

AXES_VERSION = "production-analysis-axes.v1.1"
AXES_METRIC_PRESET = "dtg-v1+asym-v1+charrobust10-v1+overallraw-v1"
AXIS_ORDER = ("survival", "combat", "macro", "support", "finish", "consistency")
AXIS_LABELS = dict(zip(AXIS_ORDER, ("生存", "交战", "运营", "支援", "结果", "稳定性"), strict=True))
_KO_LABELS = dict(
    zip(AXIS_ORDER, ("생존", "교전", "운영", "지원", "마무리", "일관성"), strict=True)
)
_DESCRIPTIONS = {
    "survival": "production 생존 지표 기준입니다.",
    "combat": "production 피해와 교전 기여 지표를 기존 가중치로 합산합니다.",
    "macro": "production 야생동물/운영 지표 기준입니다.",
    "support": "production 시야 지표 기준입니다.",
    "finish": "production 경기 결과 성과 기준입니다.",
    "consistency": "production 경기점수 안정성 기준입니다.",
}
AXIS_DESCRIPTIONS = {
    "survival": "按当局基准比较死亡表现",
    "combat": "按定位权重合成对人伤害与团战贡献",
    "macro": "按当局基准比较野怪击杀表现",
    "support": "按当局基准比较视野贡献",
    "finish": "逐局结果分的加权平均；v3 使用最终单局分",
    "consistency": "100 减去逐局分数总体标准差的两倍，截断到 0—100",
}
_METRIC_LABELS = {
    "damage": "피해",
    "combatContribution": "교전 기여",
    "survival": "생존",
    "vision": "시야",
    "monster": "야생동물",
    "matchGradeOutcomeScore": "경기 결과",
    "matchGradeScore": "경기 성과",
    "consistency": "경기점수 안정성",
}


def _round(value: float | None, digits: int = 2) -> float | None:
    return js_round(value, digits) if value is not None else None


def _mean(entries: Sequence[tuple[object, float]]) -> float | None:
    total, weight_sum = 0.0, 0.0
    for value, weight in entries:
        numeric = number(value)
        if numeric is not None and weight > 0:
            total += numeric * weight
            weight_sum += weight
    return total / weight_sum if weight_sum else None


def consistency_score(scores: Sequence[object]) -> float | None:
    values = [v for score in scores if (v := number(score)) is not None]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return js_round(max(0, min(100, 100 - math.sqrt(variance) * 2)), 2)


def build_production_axes(
    results: Sequence[Mapping[str, Any]],
    *,
    scope: str = "overall",
) -> dict[str, Any]:
    """Consume local v3 results; reproduce the upstream six-axis contract.

    `overall` uses direct match means. `character` preserves the public source's
    >=10 match, ceil(10%) tail weights .15/.75 and its unweighted consistency.
    """
    if scope not in ("overall", "character"):
        raise ValueError("scope must be overall or character")
    matches = [result for result in results if number(result.get("score")) is not None]
    weights = [1.0] * len(matches)
    robust = scope == "character" and len(matches) >= 10
    if robust:
        ordered = sorted(range(len(matches)), key=lambda i: matches[i]["score"])
        tail = math.ceil(len(matches) * 0.1)
        for index, match_index in enumerate(ordered):
            weights[match_index] = (
                0.15 if index < tail else (0.75 if index >= len(matches) - tail else 1.0)
            )

    def component(metric: str) -> dict[str, Any] | None:
        entries = []
        for match, weight in zip(matches, weights, strict=True):
            evidence = next(
                (
                    row
                    for row in match["roleScoreDetail"]["metricDetails"]
                    if row["metric"] == metric
                ),
                None,
            )
            if evidence is not None:
                entries.append((evidence, weight))
        if not entries:
            return None

        # compute.ts rounds evidence before productionAnalysisAxes consumes it.
        def average(key: str, digits: int) -> float | None:
            values = [(_round(number(row.get(key)), 4), w) for row, w in entries]
            return _round(_mean(values), digits)

        return {
            "metric": metric,
            "label": _METRIC_LABELS[metric],
            "score": average("adjustedMetricScore", 2),
            "weight": average("weight", 2),
            "contribution": None,
            "actualValue": average("actual", 4),
            "expectedValue": average("expected", 4),
            "ratio": average("ratio", 4),
        }

    def axis_row(
        axis: str, score: float | None, count: int, components: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "axis": axis,
            "label": _KO_LABELS[axis],
            "score": _round(score),
            "referenceScore": 65,
            "status": "unavailable"
            if count <= 0
            else ("ready" if count >= len(matches) else "partial"),
            "sampleCount": count,
            "components": components,
            "description": _DESCRIPTIONS[axis],
        }

    axes = []
    for axis, metrics in (
        ("survival", ("survival",)),
        ("combat", ("damage", "combatContribution")),
        ("macro", ("monster",)),
        ("support", ("vision",)),
    ):
        components = [c for metric in metrics if (c := component(metric)) is not None]
        total_weight = sum(c["weight"] or 0 for c in components)
        score = (
            sum((c["score"] or 0) * ((c["weight"] or 0) / total_weight) for c in components)
            if total_weight > 0
            else None
        )
        for c in components:
            c["contribution"] = (
                _round(c["score"] * (c["weight"] / total_weight))
                if score is not None and total_weight > 0
                else None
            )
        count = sum(
            any(e["metric"] in metrics for e in m["roleScoreDetail"]["metricDetails"])
            for m in matches
        )
        axes.append(axis_row(axis, score, count, components))

    # v3-direct sets matchGradeOutcomeScore=null, so upstream falls back to matchGradeScore.
    finish = _round(_mean([(m["score"], w) for m, w in zip(matches, weights, strict=True)]))
    finish_components = (
        []
        if finish is None
        else [
            {
                "metric": "matchGradeScore",
                "label": _METRIC_LABELS["matchGradeScore"],
                "score": finish,
                "weight": 100,
                "contribution": finish,
                "actualValue": None,
                "expectedValue": None,
                "ratio": None,
            }
        ]
    )
    axes.append(axis_row("finish", finish, len(matches), finish_components))
    values = [m["score"] for m in matches]
    consistency = consistency_score(values)
    consistency_components = (
        []
        if consistency is None
        else [
            {
                "metric": "consistency",
                "label": _METRIC_LABELS["consistency"],
                "score": consistency,
                "weight": 100,
                "contribution": consistency,
                "actualValue": _round(_mean([(v, 1) for v in values])),
                "expectedValue": 65,
                "ratio": None,
            }
        ]
    )
    last = axis_row("consistency", consistency, len(values), consistency_components)
    last["status"] = "ready" if consistency is not None else "unavailable"
    axes.append(last)
    policy = (
        "production-character-robust-weighted-10pct"
        if robust
        else (
            "production-character-plain-mean"
            if scope == "character"
            else "production-overall-direct-match-mean"
        )
    )
    return {
        "version": AXES_VERSION,
        "metricPresetVersion": AXES_METRIC_PRESET,
        "scope": scope,
        "sampleCount": len(matches),
        "aggregationPolicy": policy,
        "axes": axes,
    }
