from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass(slots=True)
class FetchMeta:
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_updated_at: datetime | None = None
    cached: bool = False
    source: str = "DAK.GG"


@dataclass(slots=True)
class PlayerProfile:
    nickname: str
    account_level: int
    mmr: int
    tier_id: int | None
    tier_grade_id: int | None
    tier_mmr: int | None
    season_id: int | None
    overview: Mapping[str, Any]
    characters: tuple[Mapping[str, Any], ...]
    teammates: tuple[Mapping[str, Any], ...]
    skins: tuple[Mapping[str, Any], ...]
    raw: Mapping[str, Any]
    meta: FetchMeta = field(default_factory=FetchMeta)

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> PlayerProfile:
        player = data.get("player")
        if not isinstance(player, Mapping) or not player.get("name"):
            raise ValueError("player.name is required")
        seasons = data.get("playerSeasons") or []
        current = next(
            (item for item in seasons if isinstance(item, Mapping) and item.get("mmr")), {}
        )
        overviews = data.get("playerSeasonOverviews") or []
        current_season_id = current.get("seasonId")
        overview = next(
            (
                item
                for item in overviews
                if isinstance(item, Mapping)
                and item.get("seasonId") == current_season_id
                and _number(item.get("matchingModeId")) == 3
                and _number(item.get("teamModeId")) == 3
            ),
            next((item for item in overviews if isinstance(item, Mapping)), {}),
        )
        overview_characters = (
            overview.get("characterStats") if isinstance(overview, Mapping) else ()
        )
        source_time = _datetime(player.get("syncedAt") or overview.get("updatedAt"))
        return cls(
            nickname=str(player["name"]),
            account_level=_number(player.get("accountLevel")),
            mmr=_number(current.get("mmr") or data.get("mmr")),
            tier_id=_number(current.get("tierId")) if current.get("tierId") is not None else None,
            tier_grade_id=(
                _number(current.get("tierGradeId"))
                if current.get("tierGradeId") is not None
                else None
            ),
            tier_mmr=(
                _number(current.get("tierMmr"))
                if current.get("tierMmr") is not None
                else None
            ),
            season_id=(
                _number(current.get("seasonId")) if current.get("seasonId") is not None else None
            ),
            overview=overview,
            characters=tuple(
                data.get("playerCharacterStats")
                or data.get("characters")
                or overview_characters
                or ()
            ),
            teammates=tuple(data.get("playTogether") or data.get("teammates") or ()),
            skins=tuple(data.get("playerSkinStats") or data.get("skins") or ()),
            raw=data,
            meta=FetchMeta(source_updated_at=source_time),
        )


@dataclass(slots=True)
class MatchRecord:
    game_id: int
    season_id: int
    nickname: str
    rank: int
    victory: bool
    character_id: int
    kills: int
    assists: int
    team_kills: int
    damage: int
    mmr_gain: int
    mmr_after: int
    skin_code: int
    route_id: int
    equipment: tuple[int, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> MatchRecord:
        game_id = data.get("gameId")
        if game_id is None:
            raise ValueError("match.gameId is required")
        return cls(
            game_id=_number(game_id),
            season_id=_number(data.get("seasonId")),
            nickname=str(data.get("nickname") or ""),
            rank=_number(data.get("gameRank"), 999),
            victory=bool(data.get("victory") or _number(data.get("gameRank")) == 1),
            character_id=_number(data.get("characterNum")),
            kills=_number(data.get("playerKill")),
            assists=_number(data.get("playerAssistant")),
            team_kills=_number(data.get("teamKill")),
            damage=_number(data.get("damageToPlayer")),
            mmr_gain=_number(data.get("mmrGain")),
            mmr_after=_number(data.get("mmrAfter")),
            skin_code=_number(data.get("skinCode")),
            route_id=_number(data.get("routeIdOfStart")),
            equipment=tuple(_number(item) for item in (data.get("equipment") or ())),
            raw=data,
        )


@dataclass(slots=True)
class CardPayload:
    kind: str
    title: str
    subtitle: str = ""
    sections: tuple[Mapping[str, Any], ...] = ()
    footer: Mapping[str, Any] = field(default_factory=dict)
