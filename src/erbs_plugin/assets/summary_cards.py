"""Verified play-cards.v1 assets from https://ercraft.net/assets/play-cards/manifest.json.

The 2026-10-21 audit checked all 1,885 manifest URLs. Only exact base and
firstPickSkin matches use these illustrations; other skins retain their own art.
"""

from __future__ import annotations

VERIFIED_CHARACTER_IDS = frozenset(range(1, 92))
FIRST_PICK_SKIN_SUFFIXES = {
    2: 2, 4: 5, 6: 4, 9: 3, 10: 7, 13: 4, 15: 4, 16: 5, 17: 5, 18: 5,
    19: 4, 20: 5, 21: 5, 22: 6, 24: 3, 25: 3, 26: 3, 27: 3, 28: 3, 29: 2,
    31: 6, 33: 6, 34: 3, 35: 2, 37: 1, 41: 1, 42: 5, 43: 5, 44: 3, 45: 4,
    46: 3, 47: 4, 48: 3, 50: 3, 52: 3, 53: 3, 55: 3, 57: 2, 59: 1, 64: 3,
    65: 3, 66: 2, 67: 3, 68: 2, 69: 3, 73: 1, 74: 1, 75: 2, 76: 2, 81: 2,
    82: 2, 84: 1, 85: 1, 88: 1,
}


def summary_card_url(character_id: int, skin_id: int | None) -> str | None:
    """Return a verified illustration only when both character and skin match."""
    if (
        not isinstance(character_id, int) or isinstance(character_id, bool)
        or character_id not in VERIFIED_CHARACTER_IDS
        or not isinstance(skin_id, int) or isinstance(skin_id, bool)
    ):
        return None
    base_skin_id = 1_000_000 + character_id * 1_000
    prefix = f"https://ercraft.net/assets/play-cards/{character_id}"
    if skin_id == base_skin_id:
        return f"{prefix}/10.webp"
    suffix = FIRST_PICK_SKIN_SUFFIXES.get(character_id)
    if suffix is not None and skin_id == base_skin_id + suffix:
        return f"{prefix}/first-pick/10.webp"
    return None
