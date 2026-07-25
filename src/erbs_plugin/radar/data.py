from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from math import ceil

from ..client import AsyncERBSClient
from ..exceptions import InvalidQuery
from .models import RadarMetrics, RadarSample

_PAGE_SIZE = 20
_MAX_MATCHES = 60

_DIMENSION_FIELDS: dict[str, tuple[str, ...]] = {
    "aggression": ("damageToPlayer", "playerKill", "damageToMonster", "playTime"),
    "pressure": (
        "damageFromPlayer",
        "healAmount",
        "damageOffsetedByShield_Player",
        "playTime",
    ),
    "teamwork": (
        "playerKill",
        "playerAssistant",
        "teamKill",
        "creditRevivedOthersCount",
    ),
    "support": (
        "ccTimeToPlayer",
        "teamRecover",
        "protectAbsorb",
        "tacticalSkillUseCount",
    ),
    "development": (
        "monsterKill",
        "damageToMonster",
        "crGetAnimal",
        "crGetMutant",
        "totalGainVFCredit",
    ),
    "vision": (
        "viewContribution",
        "addTelephotoCamera",
        "removeTelephotoCamera",
        "useSecurityConsole",
    ),
    "investment": (
        "totalGainVFCredit",
        "totalUseVFCredit",
        "craftLegend",
        "craftMythic",
    ),
    "stability": ("playerDeaths", "playTime"),
}


def _number(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: object, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _sum(matches: Iterable[Mapping[str, object]], *keys: str) -> float:
    return sum(_number(match, key) for match in matches for key in keys)


def _coverage(matches: tuple[Mapping[str, object], ...], fields: tuple[str, ...]) -> float:
    if not matches or not fields:
        return 0.0
    present = sum(field in match for match in matches for field in fields)
    return present / (len(matches) * len(fields))


class RadarDataSource:
    """Fetch and aggregate ranked squad match data used by the style radar."""

    def __init__(self, client: AsyncERBSClient) -> None:
        self.client = client

    async def fetch(self, nickname: str, *, count: int = 20) -> RadarSample:
        if not 1 <= count <= _MAX_MATCHES:
            raise InvalidQuery(f"雷达图样本数量必须在 1 到 {_MAX_MATCHES} 之间")

        clean_nickname = nickname.strip()
        if not clean_nickname:
            raise InvalidQuery("玩家昵称不能为空")

        page_count = ceil(count / _PAGE_SIZE)
        payloads = await asyncio.gather(
            *(
                self.client.player_matches(
                    clean_nickname,
                    matching_mode="RANK",
                    team_mode="SQUAD",
                    page=page,
                )
                for page in range(1, page_count + 1)
            )
        )

        matches: list[Mapping[str, object]] = []
        seen_game_ids: set[int] = set()
        cached = False
        for payload in payloads:
            cached = cached or bool(payload.get("_erbs_cached"))
            for item in payload.get("matches") or ():
                if not isinstance(item, Mapping):
                    continue
                matching_mode = _integer(item.get("matchingMode"), 3)
                team_mode = _integer(
                    item.get("matchingTeamMode", item.get("teamMode")), 3
                )
                if matching_mode != 3 or team_mode != 3:
                    continue
                game_id = _integer(item.get("gameId"), 0)
                if game_id and game_id in seen_game_ids:
                    continue
                if game_id:
                    seen_game_ids.add(game_id)
                matches.append(dict(item))
                if len(matches) >= count:
                    break
            if len(matches) >= count:
                break

        return RadarSample(
            nickname=clean_nickname,
            matches=tuple(matches),
            cached=cached,
            page_count=page_count,
        )


def aggregate_radar_metrics(sample: RadarSample) -> RadarMetrics:
    matches = sample.matches
    sample_size = len(matches)
    total_minutes = max(_sum(matches, "playTime") / 60.0, 0.0)
    safe_minutes = max(total_minutes, 1.0)
    safe_games = max(sample_size, 1)

    damage_to_player = _sum(matches, "damageToPlayer")
    damage_to_monster = _sum(matches, "damageToMonster")
    total_gain_credit = _sum(matches, "totalGainVFCredit")
    total_use_credit = sum(
        _number(match, "totalUseVFCredit") or _number(match, "sumUsedVFCredits")
        for match in matches
    )
    team_kills = _sum(matches, "teamKill")
    kills = _sum(matches, "playerKill")
    assists = _sum(matches, "playerAssistant")
    deaths = [_number(match, "playerDeaths") for match in matches]

    values = {
        "damage_to_player_per_min": damage_to_player / safe_minutes,
        "kills_per_10_min": kills / safe_minutes * 10,
        "pvp_damage_share": damage_to_player
        / max(1.0, damage_to_player + damage_to_monster),
        "damage_from_player_per_min": _sum(matches, "damageFromPlayer") / safe_minutes,
        "self_sustain_per_min": _sum(
            matches, "healAmount", "damageOffsetedByShield_Player"
        )
        / safe_minutes,
        "kill_participation": (kills + assists) / max(1.0, team_kills),
        "assists_per_10_min": assists / safe_minutes * 10,
        "ally_revives_per_10_games": _sum(matches, "creditRevivedOthersCount")
        / safe_games
        * 10,
        "cc_seconds_per_min": _sum(matches, "ccTimeToPlayer") / safe_minutes,
        "team_support_per_min": _sum(matches, "teamRecover", "protectAbsorb")
        / safe_minutes,
        "tactical_uses_per_10_min": _sum(matches, "tacticalSkillUseCount")
        / safe_minutes
        * 10,
        "animals_per_min": _sum(matches, "monsterKill") / safe_minutes,
        "monster_damage_per_min": damage_to_monster / safe_minutes,
        "farm_credit_share": _sum(matches, "crGetAnimal", "crGetMutant")
        / max(1.0, total_gain_credit),
        "view_contribution_per_min": _sum(matches, "viewContribution") / safe_minutes,
        "camera_actions_per_10_min": _sum(
            matches,
            "addSurveillanceCamera",
            "addTelephotoCamera",
            "removeSurveillanceCamera",
            "removeTelephotoCamera",
        )
        / safe_minutes
        * 10,
        "intel_actions_per_10_min": _sum(
            matches, "useSecurityConsole", "useReconDrone", "useEmpDrone"
        )
        / safe_minutes
        * 10,
        "credit_turnover": total_use_credit / max(1.0, total_gain_credit),
        "credit_spend_per_min": total_use_credit / safe_minutes,
        "high_grade_crafts_per_game": _sum(matches, "craftLegend", "craftMythic")
        / safe_games,
        "deaths_per_10_min": sum(deaths) / safe_minutes * 10,
        "deathless_rate": sum(death == 0 for death in deaths) / safe_games,
        "multi_death_rate": sum(death >= 2 for death in deaths) / safe_games,
    }
    coverage = {
        dimension: _coverage(matches, fields)
        for dimension, fields in _DIMENSION_FIELDS.items()
    }
    return RadarMetrics(
        sample_size=sample_size,
        total_minutes=total_minutes,
        values=values,
        coverage=coverage,
    )


__all__ = ["RadarDataSource", "aggregate_radar_metrics"]
