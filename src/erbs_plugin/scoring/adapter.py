"""Adapt DAK.GG records without treating absent statistics as zero."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .core import ROLE_LABELS, SCORING_VERSION, compute_match_grade, lookup_role, number


def _read(match: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        value = number(match.get(key))
        if value is not None:
            return value
    return None


def score_match(
    match: Mapping[str, object], *, tier_key: str | None = None, allow_normal: bool = False,
) -> dict[str, Any]:
    """Score a ranked squad record; explicit tier_key is the pre-match baseline tier.

    Automatic RP classification covers verified DAK season IDs 39 (S11) and 41 (S12).
    Unknown seasons need an explicit tier; a future ladder must not be silently assumed.
    Normal squad games require both allow_normal and an explicit baseline tier.
    """
    result: dict[str, Any] = {
        "version": SCORING_VERSION,
        "gameId": match.get("gameId"),
        "score": None,
        "missingReason": None,
        "gradeVersion": "ercraft-public-fine-cuts.v1",
    }

    def missing(reason: str) -> dict[str, Any]:
        result["missingReason"] = reason
        return result

    mode = match.get("matchingMode")
    team_mode = match.get("matchingTeamMode", match.get("teamMode"))
    normal = allow_normal and tier_key is not None and mode in (2, "NORMAL")
    if (mode not in (3, "RANK") and not normal) or team_mode not in (3, "SQUAD"):
        return missing("unsupported-or-missing-mode")
    if tier_key is None:
        if match.get("seasonId") not in (39, 41):
            return missing("unsupported-or-missing-season")
        after = _read(match, "mmrAfter", "rpAfter")
        delta = _read(match, "mmrGain", "rpDelta")
        if after is None or delta is None or after - delta <= 0:
            return missing("missing-pre-match-rp")
        before = after - delta
        result["preMatchRp"] = before
        tier_key = next(
            tier
            for minimum, tier in (
                (7600, "mithril_plus"),
                (6400, "meteorite_plus"),
                (5000, "diamond_plus"),
                (3600, "platinum"),
                (2400, "gold"),
                (1400, "silver"),
                (600, "bronze"),
                (0, "iron"),
            )
            if before >= minimum
        )
    result["baselineTierKey"] = tier_key
    character = _read(match, "characterNum")
    weapon = _read(match, "bestWeapon", "weaponTypeId")
    if character is None or character <= 0 or not character.is_integer():
        return missing("missing-character")
    if weapon is None or weapon <= 0 or not weapon.is_integer():
        return missing("missing-weapon")
    role = lookup_role(int(character), int(weapon))
    if role is None:
        return missing("unsupported-character-weapon")
    result.update(role=role, roleLabel=ROLE_LABELS[role])
    placement = _read(match, "gameRank", "placement")
    if placement not in range(1, 9):
        return missing("missing-or-invalid-placement")
    computed = compute_match_grade(
        {
            "tierKey": tier_key,
            "characterNum": int(character),
            "weaponTypeId": int(weapon),
            "role": role,
            "placement": placement,
            "durationSeconds": _read(match, "playTime", "gameDuration"),
            "damageToPlayer": _read(match, "damageToPlayer", "damageToPlayers"),
            "kills": _read(match, "playerKill", "kills"),
            "assists": _read(match, "playerAssistant", "assists"),
            "teamKills": _read(match, "teamKill", "teamKills"),
            "deaths": _read(match, "playerDeaths", "deaths"),
            "visionScore": _read(match, "viewContribution", "visionScore"),
            "monsterKill": _read(match, "monsterKill"),
        }
    )
    if computed is None:
        return missing("missing-baseline-or-metrics")
    result.update(computed)
    return result
