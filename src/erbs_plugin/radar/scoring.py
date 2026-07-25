from __future__ import annotations

from dataclasses import dataclass

from .data import aggregate_radar_metrics
from .models import (
    RadarComponentScore,
    RadarDimensionScore,
    RadarProfile,
    RadarSample,
)


@dataclass(frozen=True, slots=True)
class MetricRule:
    key: str
    label: str
    midpoint: float
    upper: float
    weight: float
    inverse: bool = False


@dataclass(frozen=True, slots=True)
class DimensionRule:
    key: str
    label: str
    description: str
    metrics: tuple[MetricRule, ...]


@dataclass(frozen=True, slots=True)
class RadarScoringProfile:
    version: str
    dimensions: tuple[DimensionRule, ...]
    full_confidence_matches: int = 20


DEFAULT_SCORING_PROFILE = RadarScoringProfile(
    version="style-v1",
    dimensions=(
        DimensionRule(
            "aggression",
            "进攻性",
            "主动寻找战斗并向敌方施压的倾向",
            (
                MetricRule("damage_to_player_per_min", "玩家伤害/分钟", 950, 1500, 0.50),
                MetricRule("kills_per_10_min", "击杀/10分钟", 2.0, 4.0, 0.30),
                MetricRule("pvp_damage_share", "PVP输出占比", 0.25, 0.50, 0.20),
            ),
        ),
        DimensionRule(
            "pressure",
            "承压性",
            "站在正面吸收伤害并维持自身状态的倾向",
            (
                MetricRule("damage_from_player_per_min", "承伤/分钟", 850, 1400, 0.55),
                MetricRule("self_sustain_per_min", "自我恢复与护盾/分钟", 500, 1200, 0.45),
            ),
        ),
        DimensionRule(
            "teamwork",
            "团队参与",
            "跟随团队行动并参与击杀与复活的倾向",
            (
                MetricRule("kill_participation", "参团率", 0.75, 1.0, 0.60),
                MetricRule("assists_per_10_min", "助攻/10分钟", 3.5, 7.0, 0.30),
                MetricRule("ally_revives_per_10_games", "队友复活/10场", 3.0, 8.0, 0.10),
            ),
        ),
        DimensionRule(
            "support",
            "控制支援",
            "通过控制、治疗、护盾和战术技能创造价值的倾向",
            (
                MetricRule("cc_seconds_per_min", "控制秒数/分钟", 3.0, 7.0, 0.45),
                MetricRule("team_support_per_min", "治疗护盾/分钟", 150, 500, 0.40),
                MetricRule("tactical_uses_per_10_min", "战术技能/10分钟", 2.0, 5.0, 0.15),
            ),
        ),
        DimensionRule(
            "development",
            "发育运营",
            "通过刷野和信用币积累建立资源优势的倾向",
            (
                MetricRule("animals_per_min", "动物击杀/分钟", 3.0, 5.5, 0.50),
                MetricRule("monster_damage_per_min", "野怪伤害/分钟", 3000, 5500, 0.30),
                MetricRule("farm_credit_share", "刷野信用币占比", 0.30, 0.55, 0.20),
            ),
        ),
        DimensionRule(
            "vision",
            "视野控图",
            "布置视野、使用控制台与侦察工具的倾向",
            (
                MetricRule("view_contribution_per_min", "视野贡献/分钟", 1.5, 3.5, 0.50),
                MetricRule("camera_actions_per_10_min", "摄像头行为/10分钟", 8, 20, 0.30),
                MetricRule("intel_actions_per_10_min", "地图信息行为/10分钟", 2.5, 7, 0.20),
            ),
        ),
        DimensionRule(
            "investment",
            "资源投入",
            "将获得的信用币和材料转化为即时战力的倾向",
            (
                MetricRule("credit_turnover", "信用币周转率", 0.70, 1.0, 0.45),
                MetricRule("credit_spend_per_min", "信用币消费/分钟", 50, 100, 0.35),
                MetricRule("high_grade_crafts_per_game", "高阶制造/场", 3.0, 6.0, 0.20),
            ),
        ),
        DimensionRule(
            "stability",
            "稳健性",
            "控制死亡频率并避免反复倒下的倾向",
            (
                MetricRule("deaths_per_10_min", "死亡/10分钟", 1.3, 2.5, 0.50, True),
                MetricRule("multi_death_rate", "多次死亡对局率", 0.65, 1.0, 0.25, True),
                MetricRule("deathless_rate", "无死亡对局率", 0.15, 0.45, 0.25),
            ),
        ),
    ),
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return min(maximum, max(minimum, value))


def _metric_score(value: float, rule: MetricRule) -> float:
    midpoint = max(rule.midpoint, 0.000001)
    upper = max(rule.upper, midpoint + 0.000001)
    if value <= midpoint:
        score = value / midpoint * 50
    else:
        score = 50 + (value - midpoint) / (upper - midpoint) * 50
    score = _clamp(score)
    return 100 - score if rule.inverse else score


class RadarScorer:
    """Convert aggregated behavior into eight 0-100 style tendency scores."""

    def __init__(self, profile: RadarScoringProfile = DEFAULT_SCORING_PROFILE) -> None:
        self.profile = profile

    def score(self, sample: RadarSample) -> RadarProfile:
        metrics = aggregate_radar_metrics(sample)
        sample_reliability = min(
            1.0,
            metrics.sample_size / max(1, self.profile.full_confidence_matches),
        )
        dimensions: list[RadarDimensionScore] = []
        for rule in self.profile.dimensions:
            components = tuple(
                RadarComponentScore(
                    key=metric.key,
                    label=metric.label,
                    value=float(metrics.values.get(metric.key, 0.0)),
                    score=_metric_score(float(metrics.values.get(metric.key, 0.0)), metric),
                )
                for metric in rule.metrics
            )
            total_weight = sum(metric.weight for metric in rule.metrics) or 1.0
            raw_score = sum(
                component.score * metric.weight
                for component, metric in zip(components, rule.metrics, strict=True)
            ) / total_weight
            coverage = float(metrics.coverage.get(rule.key, 0.0))
            reliability = sample_reliability * coverage
            adjusted_score = 50 + (raw_score - 50) * reliability
            dimensions.append(
                RadarDimensionScore(
                    key=rule.key,
                    label=rule.label,
                    description=rule.description,
                    score=round(_clamp(adjusted_score)),
                    raw_score=raw_score,
                    coverage=coverage,
                    components=components,
                )
            )

        minimum_coverage = min((item.coverage for item in dimensions), default=0.0)
        if metrics.sample_size >= 20 and minimum_coverage >= 0.8:
            confidence = "high"
        elif metrics.sample_size >= 10 and minimum_coverage >= 0.6:
            confidence = "medium"
        else:
            confidence = "low"
        return RadarProfile(
            nickname=sample.nickname,
            sample_size=metrics.sample_size,
            total_minutes=metrics.total_minutes,
            confidence=confidence,
            cached=sample.cached,
            calibration_version=self.profile.version,
            dimensions=tuple(dimensions),
        )


__all__ = [
    "DEFAULT_SCORING_PROFILE",
    "DimensionRule",
    "MetricRule",
    "RadarScorer",
    "RadarScoringProfile",
]
