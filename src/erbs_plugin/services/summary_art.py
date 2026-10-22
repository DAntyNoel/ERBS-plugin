from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ..assets.summary_cards import summary_card_url


def _positive_integer(value: object) -> int | None:
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        return None
    try:
        result = int(value) if value is not None else 0
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _rows(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _image_url(*values: object) -> str | None:
    return next((value for value in values if isinstance(value, str) and value.strip()), None)


def build_summary_art_candidates(
    raw_profile: Mapping[str, Any],
    characters_metadata: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
    season_id: int,
) -> tuple[list[dict[str, Any]], str]:
    """Weight characters by usage and prefer their verified ERCraft skin artwork.

    ERCraft skins are eligible regardless of usage; only the fallback uses public
    skin history. Neither pool establishes which skins the player owns.
    The caller must already filter NORMAL samples to the requested season: their
    upstream seasonId can be zero, so it cannot establish that boundary itself.
    """
    characters = {
        character_id: row
        for row in _rows(characters_metadata.get("characters"))
        if (character_id := _positive_integer(row.get("id"))) is not None
    }
    squad_matches = [
        row for row in matches
        if isinstance(row, Mapping)
        and _positive_integer(row.get("matchingTeamMode", row.get("teamMode"))) == 3
    ]
    ranked_matches = [
        row for row in squad_matches
        if _positive_integer(row.get("seasonId")) == season_id
        and _positive_integer(row.get("matchingMode")) == 3
    ]
    normal_matches = [
        row for row in squad_matches
        if str(row.get("seasonId")) in {"0", str(season_id)}
        and _positive_integer(row.get("matchingMode")) == 2
    ]
    overview = next(
        (
            row for row in _rows(raw_profile.get("playerSeasonOverviews"))
            if _positive_integer(row.get("seasonId")) == season_id
            and _positive_integer(row.get("matchingModeId")) == 3
            and _positive_integer(row.get("teamModeId")) == 3
        ),
        {},
    )
    usage: dict[int, int] = {}
    used_skins: dict[int, set[int]] = {}
    for row in _rows(overview.get("characterStats")):
        character_id = _positive_integer(row.get("key"))
        play = _positive_integer(row.get("play"))
        if character_id is None or play is None:
            continue
        usage[character_id] = max(usage.get(character_id, 0), play)
        used_skins.setdefault(character_id, set()).update(
            skin_id for skin in _rows(row.get("skinStats"))
            if _positive_integer(skin.get("play")) is not None
            and (skin_id := _positive_integer(skin.get("key"))) is not None
        )
    source = "赛季排位使用记录"
    if not usage:
        usage = dict(Counter(
            character_id for row in ranked_matches
            if (character_id := _positive_integer(row.get("characterNum"))) is not None
        ))
        source = "最近场次使用记录"
    if not usage:
        usage = dict(Counter(
            character_id for row in normal_matches
            if (character_id := _positive_integer(row.get("characterNum"))) is not None
        ))
        source = "本赛季匹配使用记录"

    candidates = []
    for character_id, play in sorted(usage.items()):
        character = characters.get(character_id, {})
        skin_metadata = {
            skin_id: row
            for row in _rows(character.get("skins"))
            if (skin_id := _positive_integer(row.get("id"))) is not None
        }
        skin_ids = {
            skin_id for skin_id in skin_metadata
            if summary_card_url(character_id, skin_id) is not None
        }
        if not skin_ids:
            skin_ids = used_skins.get(character_id, set()) & skin_metadata.keys()
            skin_ids |= {
                skin_id for row in ranked_matches
                if _positive_integer(row.get("characterNum")) == character_id
                and (skin_id := _positive_integer(row.get("skinCode"))) in skin_metadata
            }
        if not skin_ids:
            skin_ids = {
                skin_id for row in normal_matches
                if _positive_integer(row.get("characterNum")) == character_id
                and (skin_id := _positive_integer(row.get("skinCode"))) in skin_metadata
            }
        if not skin_ids:
            base_skin = next(
                (
                    skin_id for skin_id, row in sorted(skin_metadata.items())
                    if _positive_integer(row.get("grade")) == 1 or skin_id % 1000 == 0
                ),
                None,
            )
            skin_ids = {base_skin} if base_skin is not None else set()
        skins = []
        for skin_id in sorted(skin_ids):
            skin = skin_metadata[skin_id]
            grade = _positive_integer(skin.get("grade"))
            skins.append({
                "skinId": skin_id,
                "skinName": skin.get("name"),
                "skinGrade": grade,
                "weight": 10 if grade == 4 else 1,
                "summaryArtUrl": summary_card_url(character_id, skin_id),
                "characterImageUrl": _image_url(
                    skin.get("fullImageUrl"), skin.get("imageUrl"),
                    character.get("imageUrl"), character.get("communityImageUrl"),
                ),
            })
        if not skins:
            skins.append({
                "skinId": None,
                "skinName": None,
                "skinGrade": None,
                "weight": 1,
                "summaryArtUrl": None,
                "characterImageUrl": _image_url(
                    character.get("imageUrl"), character.get("communityImageUrl"),
                ),
            })
        candidates.append({
            "characterId": character_id,
            "characterName": character.get("name") or f"实验体 {character_id}",
            "weight": play,
            "skins": skins,
        })
    return candidates, source
