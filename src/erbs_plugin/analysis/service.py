from __future__ import annotations

from collections import Counter
from typing import Any

from ..models import MatchRecord, PlayerProfile


class ERBSAnalysisService:
    def compare(self, left: PlayerProfile, right: PlayerProfile) -> dict[str, Any]:
        fields = {
            "MMR": (left.mmr, right.mmr),
            "场次": (left.overview.get("play", 0), right.overview.get("play", 0)),
            "胜场": (left.overview.get("win", 0), right.overview.get("win", 0)),
            "TOP 3": (left.overview.get("top3", 0), right.overview.get("top3", 0)),
            "击杀": (left.overview.get("playerKill", 0), right.overview.get("playerKill", 0)),
            "伤害": (
                left.overview.get("damageToPlayer", 0),
                right.overview.get("damageToPlayer", 0),
            ),
        }
        return {
            "left": left.nickname,
            "right": right.nickname,
            "rows": [
                {"label": label, "left": values[0], "right": values[1]}
                for label, values in fields.items()
            ],
        }

    def best_match(self, matches: list[MatchRecord]) -> MatchRecord | None:
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                item.victory,
                -item.rank,
                item.mmr_gain,
                item.team_kills,
                item.kills,
                item.damage,
            ),
        )

    def hero_pool(self, profile: PlayerProfile, *, limit: int = 10) -> list[dict[str, Any]]:
        stats = [dict(item) for item in profile.characters]
        stats.sort(key=lambda item: int(item.get("play") or item.get("plays") or 0), reverse=True)
        total = sum(int(item.get("play") or item.get("plays") or 0) for item in stats)
        result: list[dict[str, Any]] = []
        for item in stats[:limit]:
            plays = int(item.get("play") or item.get("plays") or 0)
            result.append({**item, "plays": plays, "usageRate": plays / total if total else 0})
        return result

    def equipment_habits(
        self, matches: list[MatchRecord], *, limit: int = 10
    ) -> list[dict[str, Any]]:
        counts = Counter(item for match in matches for item in match.equipment if item)
        return [
            {"itemId": item_id, "count": count}
            for item_id, count in counts.most_common(limit)
        ]
