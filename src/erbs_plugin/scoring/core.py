"""Python port of ERCraft's public role-score.v3 numerical core.

Source: adgjmptw2/ERCraft-main@93dd2a13345c53e5a6fb271c92d42b9fb62c7761.
Copyright (c) 2026 MINE9289, MIT; see data/LICENSE.txt.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from functools import cache
from importlib.resources import files
from typing import Any

SCORING_VERSION = "ercraft-role-score.v3-public-93dd2a1"
METRICS = ("damage", "combatContribution", "survival", "vision", "monster")
ROLE_WEIGHTS = {
    "평타 딜러": (32, 24, 10, 18, 16),
    "스증 딜러": (36, 25, 10, 18, 11),
    "암살자": (30, 32, 10, 18, 10),
    "평타 브루저": (27, 28, 15, 17, 13),
    "스증 브루저": (30, 29, 15, 17, 9),
    "탱커": (12, 35, 20, 30, 3),
    "서포터": (7, 38, 20, 33, 2),
}
ROLE_LABELS = dict(
    zip(
        ROLE_WEIGHTS,
        (
            "普攻输出",
            "技能输出",
            "刺客",
            "普攻斗士",
            "技能斗士",
            "坦克",
            "辅助",
        ),
        strict=True,
    )
)


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def js_round(value: float, digits: int = 4) -> float:
    """Match Math.round, including ties toward +infinity (not Python's ties-to-even)."""
    scale = 10**digits
    scaled = value * scale
    lower = math.floor(scaled)
    return (lower + (scaled - lower >= 0.5)) / scale


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@cache
def document(name: str) -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("data", name).read_text(encoding="utf-8"))


def lookup_role(character: int, weapon: int) -> str | None:
    entry = document("character-weapon-roles.v1.json")["entries"].get(f"{character}:{weapon}")
    return entry["role"] if entry else None


def combat_ratio(kills: object, assists: object, team_kills: object) -> float | None:
    k, a, t = number(kills), number(assists), number(team_kills)
    if k is None or a is None or t is None or t <= 0:
        return None
    return js_round(min((k + a * 0.7) / t, 1), 6)


def asymmetric_adjustment(raw: float) -> tuple[float, str]:
    if raw < 50:
        adjusted, policy = 65 + (50 - 65) * 0.75 + (raw - 50), "severe-low-1.00"
    elif raw < 65:
        adjusted, policy = 65 + (raw - 65) * 0.75, "mild-low-0.75"
    elif raw == 65:
        adjusted, policy = 65.0, "neutral"
    elif raw <= 80:
        adjusted, policy = 65 + (raw - 65) * 1.2, "strength-1.20"
    else:
        adjusted = 65 + (80 - 65) * 1.2 + (raw - 80) * 1.35
        policy = "exceptional-strength-1.35"
    if adjusted < 30:
        policy = "clamped-min-30"
    if adjusted > 95:
        policy = "clamped-max-95"
    return js_round(clamp(adjusted, 30, 95)), policy


def placement_adjustment(placement: object, score: float) -> float | None:
    base = {1: 6, 2: 4, 3: 2, 4: 1, 5: -1, 6: -2, 7: -4, 8: -6}.get(number(placement))
    if base is None:
        return None
    if base > 0:
        factor = 0.2 + 0.8 * clamp((score - 45) / 20, 0, 1)
        bonus = {1: 2, 2: 1.5, 3: 1}.get(placement, 0) * clamp((score - 75) / 15, 0, 1)
        return js_round(base * factor + bonus)
    return js_round(base * (1 - 0.75 * clamp((score - 60) / 25, 0, 1)))


def _baseline(input: Mapping[str, object]) -> tuple[dict[str, Any] | None, str | None, int | None]:
    tier, character, weapon, role = (
        input.get(key) for key in ("tierKey", "characterNum", "weaponTypeId", "role")
    )
    exact = document("tier-baselines.v1.json")["combinations"].get(f"{tier}:{character}:{weapon}")
    if exact:
        return exact, "exact", exact["count"]
    fallback = document("role-score-fallback-baselines.v1.json")
    for group, key, level in (
        ("tierCharacter", f"{tier}:{character}", "tier-character"),
        ("tierRole", f"{tier}:{role}", "tier-role"),
        ("tierOverall", tier, "tier-overall"),
    ):
        row = fallback[group].get(key)
        if row:
            return row["means"], level, row["count"]
    return None, None, None


def _duration(role: str, seconds: float | None) -> tuple[str, dict[str, Any], str, float]:
    bucket = "unknown-duration"
    scalar = 1.0
    if seconds is not None and seconds > 0:
        for limit, key, midpoint in (
            (900, "duration-lt-15m", 750),
            (1200, "duration-15-20m", 1050),
            (1500, "duration-20-25m", 1350),
            (1800, "duration-25-30m", 1650),
            (math.inf, "duration-30m-plus", 1950),
        ):
            if seconds < limit:
                bucket, scalar = key, clamp(seconds / midpoint, 0.75, 1.25)
                break
    doc = document("role-score-duration-adjustments.v1.json")
    record = doc["roleDuration"].get(f"role:{role}|duration:{bucket}")
    if bucket != "unknown-duration" and record:
        return bucket, record, "role-duration", scalar
    record = doc["roleGlobal"].get(f"role:{role}")
    if record:
        return bucket, record, "role-global", scalar
    return bucket, doc["global"], "global", scalar


def damage_time(seconds: float | None, legacy: float) -> dict[str, Any]:
    result = {
        "presetVersion": "damage-time-global.v1",
        "policy": "legacy-duration-multiplier",
        "multiplier": js_round(legacy, 6),
        "legacyMultiplier": js_round(legacy, 6),
        "globalMultiplier": None,
        "sampleCount": None,
    }
    if seconds is None or seconds <= 0 or seconds < 480 or seconds >= 1500:
        return result
    minutes = seconds / 60
    points = sorted(document("damage-time-global.v1.json")["points"], key=lambda p: p["minute"])
    global_value, count = points[0]["multiplier"], points[0]["sampleCount"]
    for left, right in zip(points, points[1:], strict=False):
        if left["minute"] <= minutes <= right["minute"]:
            progress = (minutes - left["minute"]) / (right["minute"] - left["minute"])
            global_value = js_round(
                left["multiplier"] + (right["multiplier"] - left["multiplier"]) * progress, 6
            )
            count = int(
                js_round(
                    left["sampleCount"] + (right["sampleCount"] - left["sampleCount"]) * progress, 0
                )
            )
            break
    if minutes < 10:
        weight = (minutes - 8) / 2
        multiplier = js_round(legacy * (1 - weight) + global_value * weight, 6)
        policy = "blend-legacy-to-global"
    elif minutes <= 20:
        multiplier, policy = global_value, "global"
    else:
        weight = (25 - minutes) / 5
        multiplier = js_round(global_value * weight + legacy * (1 - weight), 6)
        policy = "blend-global-to-legacy"
    result.update(
        multiplier=multiplier, policy=policy, globalMultiplier=global_value, sampleCount=count
    )
    return result


def compute_match_grade(input: Mapping[str, object]) -> dict[str, Any] | None:
    """Accept the public TypeScript RoleScoreV3Input shape; return its numerical result."""
    role = input.get("role")
    if role not in ROLE_WEIGHTS:
        return None
    baseline, level, count = _baseline(input)
    if baseline is None:
        return None
    seconds = number(input.get("durationSeconds"))
    bucket, record, duration_level, scalar = _duration(role, seconds)
    multipliers = record["multipliers"]
    time = damage_time(seconds, js_round(multipliers.get("damageToPlayer", 1) * scalar, 6))
    expected = {
        "damageToPlayer": js_round(baseline["averageDamageToPlayer"] * time["multiplier"]),
        "combatContribution": combat_ratio(
            baseline["averagePlayerKill"],
            baseline["averagePlayerAssistant"],
            baseline["averageTeamKill"],
        ),
        **{
            key: js_round(baseline[source] * multipliers.get(key, 1) * scalar)
            for key, source in (
                ("deaths", "averageDeaths"),
                ("viewContribution", "averageViewContribution"),
                ("monsterKill", "averageMonsterKill"),
            )
        },
    }
    actuals = (
        number(input.get("damageToPlayer")),
        combat_ratio(input.get("kills"), input.get("assists"), input.get("teamKills")),
        number(input.get("deaths")),
        number(input.get("visionScore")),
        number(input.get("monsterKill")),
    )
    expected_values = [
        expected[key]
        for key in (
            "damageToPlayer",
            "combatContribution",
            "deaths",
            "viewContribution",
            "monsterKill",
        )
    ]
    details, missing, scores = [], [], {}
    weighted, effective_weight = 0.0, 0
    for metric, weight, actual, target in zip(
        METRICS,
        ROLE_WEIGHTS[role],
        actuals,
        expected_values,
        strict=True,
    ):
        if actual is None or target is None:
            missing.append(metric)
            continue
        relative = target - actual if metric == "survival" else actual - target
        relative /= max(abs(target), 1e-6)
        raw = js_round(clamp(65 + 45 * relative, 20, 100))
        adjusted, policy = asymmetric_adjustment(raw)
        if input.get("applyMetricAdjustment") is False:
            adjusted, policy = raw, "unadjusted"
        ratio = None
        if target != 0 and (metric != "survival" or actual != 0):
            ratio = js_round(target / actual if metric == "survival" else actual / target)
        scores[metric] = adjusted
        details.append(
            {
                "metric": metric,
                "score": adjusted,
                "rawMetricScore": raw,
                "adjustedMetricScore": adjusted,
                "adjustmentPolicy": policy,
                "weight": weight,
                "contribution": js_round(adjusted * weight / 100),
                "rawContribution": js_round(raw * weight / 100),
                "actual": actual,
                "expected": target,
                "ratio": ratio,
                "metricPresetVersion": "metric-adjust-asym-v1",
            }
        )
        weighted += adjusted * weight
        effective_weight += weight
    if not effective_weight:
        return None
    role_score = js_round(weighted / effective_weight)
    adjustment = placement_adjustment(input.get("placement"), role_score)
    if adjustment is None:
        return None
    score = js_round(clamp(role_score + adjustment, 0, 100), 2)
    cuts = (
        (95, "S+"),
        (88, "S"),
        (84, "S-"),
        (80, "A+"),
        (76, "A"),
        (72, "A-"),
        (68, "B+"),
        (62, "B"),
        (56, "B-"),
        (50, "C+"),
        (44, "C"),
        (38, "C-"),
        (32, "D+"),
        (24, "D"),
        (-math.inf, "D-"),
    )
    return {
        "roleScore": role_score,
        "placementAdjustment": adjustment,
        "score": score,
        "grade": next(grade for lower, grade in cuts if score >= lower),
        "roleScoreDetail": {
            "score": role_score,
            "baselineLevel": level,
            "baselineSampleCount": count,
            "durationBucket": bucket,
            "durationFallbackLevel": duration_level,
            "metricScores": scores,
            "metricDetails": details,
            "missingMetrics": missing,
            "effectiveWeight": effective_weight,
            "expectedMetrics": expected,
            "damageTime": time,
        },
    }
