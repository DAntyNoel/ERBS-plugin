"""Materialize one portrait without freezing randomness in the query cache."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .models import CardPayload

SUMMARY_ART_VERSION = "weighted-used-skins.v1"


def _weighted(items: object) -> list[Mapping[str, Any]]:
    if not isinstance(items, (list, tuple)):
        return []
    return [
        item for item in items
        if isinstance(item, Mapping)
        and isinstance(item.get("weight"), (int, float))
        and not isinstance(item["weight"], bool)
        and math.isfinite(item["weight"])
        and item["weight"] > 0
    ]


def select_summary_art(payload: CardPayload) -> CardPayload:
    """Copy cached candidates and draw once; the resulting payload is idempotent."""
    if payload.kind != "summary":
        return payload
    sections = []
    changed = False
    for section in payload.sections:
        if section.get("type") != "player-summary" or "artCandidates" not in section:
            sections.append(section)
            continue
        selected = {key: value for key, value in section.items() if key != "artCandidates"}
        characters = [item for item in _weighted(section["artCandidates"])
                      if _weighted(item.get("skins"))]
        if characters:
            character = random.choices(
                characters, weights=[c["weight"] for c in characters], k=1,
            )[0]
            skins = _weighted(character["skins"])
            skin = random.choices(skins, weights=[s["weight"] for s in skins], k=1)[0]
            selected.update(
                characterId=character.get("characterId"),
                characterName=character.get("characterName"),
                skinId=skin.get("skinId"),
                skinName=skin.get("skinName"),
                skinGrade=skin.get("skinGrade"),
                characterImageUrl=skin.get("characterImageUrl"),
                summaryArtUrl=skin.get("summaryArtUrl"),
            )
        sections.append(selected)
        changed = True
    return replace(payload, sections=tuple(sections)) if changed else payload
