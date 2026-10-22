from __future__ import annotations

from copy import deepcopy

import pytest

from erbs_plugin.assets.summary_cards import (
    FIRST_PICK_SKIN_SUFFIXES,
    VERIFIED_CHARACTER_IDS,
    summary_card_url,
)
from erbs_plugin.services.summary_art import build_summary_art_candidates


def match(character: int, skin: int | None, **changes: object) -> dict:
    return {
        "seasonId": 41, "matchingMode": 3, "matchingTeamMode": 3,
        "characterNum": character, "skinCode": skin, **changes,
    }


def metadata() -> dict:
    return {"characters": [
        {"id": 67, "name": "艾比盖尔", "imageUrl": "character.png", "skins": [
            {"id": 1067000, "name": "默认", "grade": 1, "imageUrl": "base.png"},
            {"id": 1067001, "name": "未使用", "grade": 4, "imageUrl": "unused.png"},
            {"id": 1067002, "name": "英雄", "grade": 4, "fullImageUrl": "epic-full.png",
             "imageUrl": "epic.png"},
            {"id": 1067003, "name": "稀有", "grade": 3, "imageUrl": "rare.png"},
        ]},
        {"id": 31, "name": "莉央", "communityImageUrl": "community.png", "skins": [
            {"id": 1031000, "name": "默认", "grade": 1},
            {"id": 1031001, "name": "巫女", "grade": 3, "imageUrl": "rio.png"},
        ]},
    ]}


def overview(*characters: dict, **changes: object) -> dict:
    return {
        "seasonId": 41, "matchingModeId": 3, "teamModeId": 3,
        "characterStats": list(characters), **changes,
    }


@pytest.fixture
def no_ercraft_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("erbs_plugin.services.summary_art.summary_card_url", lambda *_: None)


def test_candidates_use_only_target_ranked_usage_and_deduplicate_used_skins(
    no_ercraft_cards: None,
) -> None:
    profile = {"playerSeasonOverviews": [
        overview({"key": 31, "play": 9999}, seasonId=39),
        overview({"key": 31, "play": 9999}, matchingModeId=2),
        overview({"key": 31, "play": 9999}, teamModeId=0),
        overview(
            {"key": "67", "play": "213", "skinStats": [
                {"key": "1067002", "play": 172}, {"key": 1067002, "play": 1},
                {"key": 1067003, "play": 40}, {"key": 1067001, "play": 0},
                {"key": 1067000, "play": -1}, {"key": 9999999, "play": 20},
            ]},
            {"key": 31, "play": 2, "skinStats": [{"key": 1031001, "play": 2}]},
        ),
    ]}
    chars = metadata()
    original_profile, original_chars = deepcopy(profile), deepcopy(chars)

    candidates, source = build_summary_art_candidates(
        profile, chars, [match(31, 1031001)] * 20, 41,
    )

    assert source == "赛季排位使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 2), (67, 213)]
    skins = candidates[1]["skins"]
    assert [(s["skinId"], s["skinGrade"], s["weight"]) for s in skins] == [
        (1067002, 4, 10), (1067003, 3, 1),
    ]
    assert skins[0]["characterImageUrl"] == "epic-full.png"
    assert skins[1]["characterImageUrl"] == "rare.png"
    assert skins[0]["summaryArtUrl"] is None
    assert skins[1]["summaryArtUrl"] is None
    assert candidates[0]["skins"][0]["skinId"] == 1031001
    assert profile == original_profile
    assert chars == original_chars


def test_missing_skin_usage_uses_only_that_characters_recent_skin_evidence(
    no_ercraft_cards: None,
) -> None:
    profile = {"playerSeasonOverviews": [overview({"key": 67, "play": 20})]}
    candidates, source = build_summary_art_candidates(profile, metadata(), [
        match(67, 1067003), match(67, 1067003),
        match(67, 1067002, seasonId=39), match(67, 1067001, matchingMode=2),
        match(31, 1031001),
    ], 41)

    assert source == "赛季排位使用记录"
    assert candidates[0]["weight"] == 20
    assert [skin["skinId"] for skin in candidates[0]["skins"]] == [1067003]
    assert candidates[0]["skins"][0]["weight"] == 1


def test_missing_skin_evidence_falls_back_to_base_without_adding_other_skins(
    no_ercraft_cards: None,
) -> None:
    profile = {"playerSeasonOverviews": [overview(
        {"key": 67, "play": 20, "skinStats": [{"key": 99999, "play": 20}]},
        {"key": 31, "play": 3},
    )]}
    candidates, _ = build_summary_art_candidates(profile, metadata(), [], 41)

    assert [skin["skinId"] for skin in candidates[1]["skins"]] == [1067000]
    assert candidates[1]["skins"][0]["characterImageUrl"] == "base.png"
    assert candidates[0]["skins"] == [{
        "skinId": 1031000, "skinName": "默认", "skinGrade": 1,
        "weight": 1, "characterImageUrl": "community.png",
        "summaryArtUrl": None,
    }]


def test_recent_usage_fallback_does_not_use_other_seasons_modes_or_profile_characters(
    no_ercraft_cards: None,
) -> None:
    profile = {
        "characters": [{"key": 31, "play": 9999}],
        "playerCharacterStats": [{"key": 31, "play": 9999}],
        "playerSeasonOverviews": [
            overview({"key": 31, "play": 9999}, seasonId=39),
            overview({"key": 31, "play": 9999}, matchingModeId=2),
            overview({"key": 31, "play": 9999}, teamModeId=0),
            overview({"key": 31, "play": 0}, {"key": None, "play": 500}),
        ],
    }
    candidates, source = build_summary_art_candidates(profile, metadata(), [
        match(67, 1067002), match(67, 1067003), match(31, 1031001),
        match(31, 1031000, seasonId=39), match(31, 1031000, matchingMode=2),
        match(31, 1031000, matchingTeamMode=4), match(0, 0),
    ], 41)

    assert source == "最近场次使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 1), (67, 2)]
    assert [s["skinId"] for s in candidates[1]["skins"]] == [1067002, 1067003]


def test_base_skin_code_fallback_and_character_image_preserve_partial_metadata(
    no_ercraft_cards: None,
) -> None:
    chars = {"characters": [
        {"id": "67", "name": "艾比盖尔", "imageUrl": "character.png", "skins": [
            {"id": 1067000, "name": "默认"},
            {"id": 1067002, "name": "未使用", "grade": 4},
        ]},
    ]}
    candidates, _ = build_summary_art_candidates(
        {"playerSeasonOverviews": [overview({"key": 67, "play": 3})]}, chars, [], 41,
    )

    assert candidates[0]["skins"] == [{
        "skinId": 1067000, "skinName": "默认", "skinGrade": None,
        "weight": 1, "characterImageUrl": "character.png",
        "summaryArtUrl": None,
    }]


def test_unknown_character_keeps_usage_without_inventing_a_skin_or_image() -> None:
    candidates, source = build_summary_art_candidates(
        {"playerSeasonOverviews": [overview({"key": 999, "play": 7})]}, {}, [], 41,
    )

    assert source == "赛季排位使用记录"
    assert candidates == [{
        "characterId": 999, "characterName": "实验体 999", "weight": 7,
        "skins": [{"skinId": None, "skinName": None, "skinGrade": None,
                   "weight": 1, "characterImageUrl": None, "summaryArtUrl": None}],
    }]


def test_malformed_or_nonpositive_usage_does_not_make_weighted_candidates() -> None:
    profile = {"playerSeasonOverviews": [overview(
        {"key": 67, "play": True}, {"key": 31, "play": 1.5},
        {"key": 67, "play": "invalid"}, {"key": 31, "play": -1},
    )]}
    candidates, source = build_summary_art_candidates(profile, metadata(), [], 41)

    assert candidates == []
    assert source == "本赛季匹配使用记录"


def test_ranked_sample_usage_takes_priority_over_many_normal_samples(
    no_ercraft_cards: None,
) -> None:
    candidates, source = build_summary_art_candidates({}, metadata(), [
        match(67, 1067002), match(31, 1031001),
        *[match(31, 1031000, seasonId=0, matchingMode=2) for _ in range(20)],
    ], 41)

    assert source == "最近场次使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 1), (67, 1)]
    assert [s["skinId"] for s in candidates[0]["skins"]] == [1031001]


def test_normal_samples_supply_usage_when_no_ranked_usage_exists(no_ercraft_cards: None) -> None:
    profile = {"playerSeasonOverviews": [
        overview({"key": 31, "play": 9999}, seasonId=0, matchingModeId=2),
    ]}
    candidates, source = build_summary_art_candidates(profile, metadata(), [
        match(67, 1067003, seasonId=0, matchingMode=2),
        match(67, 1067002, matchingMode=2),
        match(31, 1031001, seasonId="0", matchingMode=2),
        match(31, 1031000, seasonId=39, matchingMode=2),
        match(31, 1031000, seasonId=0, matchingMode=6),
        match(31, 1031000, seasonId=0, matchingMode=2, matchingTeamMode=4),
    ], 41)

    assert source == "本赛季匹配使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 1), (67, 2)]
    assert [s["skinId"] for s in candidates[1]["skins"]] == [1067002, 1067003]


def test_ranked_skin_stats_and_samples_are_combined_before_normal_skin_fallback(
    no_ercraft_cards: None,
) -> None:
    profile = {"playerSeasonOverviews": [overview(
        {"key": 67, "play": 213, "skinStats": [{"key": 1067002, "play": 172}]},
        {"key": 31, "play": 2},
    )]}
    candidates, source = build_summary_art_candidates(profile, metadata(), [
        match(67, 1067003),
        match(67, 1067000, seasonId=0, matchingMode=2),
        match(31, 1031001, seasonId=0, matchingMode=2),
    ], 41)

    assert source == "赛季排位使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 2), (67, 213)]
    assert [s["skinId"] for s in candidates[1]["skins"]] == [1067002, 1067003]
    assert [s["skinId"] for s in candidates[0]["skins"]] == [1031001]


def test_ercraft_skins_replace_used_unmapped_skins_and_preserve_usage_weights() -> None:
    chars = metadata()
    chars["characters"][0]["skins"][-1].update(name="热带次元", grade=4)
    profile = {"playerSeasonOverviews": [overview(
        {"key": 67, "play": 213, "skinStats": [{"key": 1067002, "play": 213}]},
        {"key": 31, "play": 2, "skinStats": [{"key": 1031001, "play": 2}]},
    )]}
    original_chars, original_profile = deepcopy(chars), deepcopy(profile)

    candidates, source = build_summary_art_candidates(
        profile, chars, [match(67, 1067002), match(31, 1031001)], 41,
    )

    assert source == "赛季排位使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(31, 2), (67, 213)]
    assert [s["skinId"] for s in candidates[0]["skins"]] == [1031000]
    assert [(s["skinId"], s["weight"]) for s in candidates[1]["skins"]] == [
        (1067000, 1), (1067003, 10),
    ]
    assert all(s["summaryArtUrl"] for c in candidates for s in c["skins"])
    assert chars == original_chars
    assert profile == original_profile


def test_new_character_without_ercraft_assets_keeps_usage_and_used_skin_fallback() -> None:
    chars = metadata()
    chars["characters"].append({
        "id": 92, "name": "新实验体", "imageUrl": "new-character.png", "skins": [
            {"id": 1092000, "name": "默认", "grade": 1},
            {"id": 1092001, "name": "已使用英雄", "grade": 4, "imageUrl": "new-epic.png"},
            {"id": 1092002, "name": "未使用英雄", "grade": 4, "imageUrl": "unused.png"},
        ],
    })
    profile = {"playerSeasonOverviews": [overview(
        {"key": 67, "play": 9},
        {"key": 92, "play": 3, "skinStats": [{"key": 1092001, "play": 3}]},
    )]}

    candidates, source = build_summary_art_candidates(profile, chars, [], 41)

    assert source == "赛季排位使用记录"
    assert [(c["characterId"], c["weight"]) for c in candidates] == [(67, 9), (92, 3)]
    assert candidates[1]["skins"] == [{
        "skinId": 1092001, "skinName": "已使用英雄", "skinGrade": 4, "weight": 10,
        "summaryArtUrl": None, "characterImageUrl": "new-epic.png",
    }]


@pytest.mark.parametrize(("character_id", "skin_id", "expected"), [
    (67, 1067000, "https://ercraft.net/assets/play-cards/67/10.webp"),
    (67, 1067003, "https://ercraft.net/assets/play-cards/67/first-pick/10.webp"),
    (31, 1031006, "https://ercraft.net/assets/play-cards/31/first-pick/10.webp"),
    (1, 1001000, "https://ercraft.net/assets/play-cards/1/10.webp"),
    (91, 1091000, "https://ercraft.net/assets/play-cards/91/10.webp"),
    (67, 1067002, None),
    (67, 1031000, None),
    (1, 1001001, None),
    (92, 1092000, None),
    (999, 1999000, None),
    (67, None, None),
])
def test_verified_summary_cards_never_replace_an_unmapped_skin(
    character_id: int, skin_id: int | None, expected: str | None,
) -> None:
    assert summary_card_url(character_id, skin_id) == expected


def test_verified_manifest_snapshot_has_complete_base_and_first_pick_counts() -> None:
    assert len(VERIFIED_CHARACTER_IDS) == 91
    assert len(FIRST_PICK_SKIN_SUFFIXES) == 54
    assert set(FIRST_PICK_SKIN_SUFFIXES) <= VERIFIED_CHARACTER_IDS
