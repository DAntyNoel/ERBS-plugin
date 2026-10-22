from __future__ import annotations

from copy import deepcopy

import pytest

from erbs_plugin import ERBSConfig
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import SkiaCardRenderer
from erbs_plugin.summary_art import select_summary_art


def portrait_payload() -> CardPayload:
    return CardPayload(kind="summary", title="player", sections=({
        "type": "player-summary",
        "artCandidates": [
            {"characterId": 67, "characterName": "Abigail", "weight": 213, "skins": [
                {"skinId": 1067000, "skinName": "base", "skinGrade": 1, "weight": 1,
                 "characterImageUrl": "https://cdn.dak.gg/base.png"},
                {"skinId": 1067003, "skinName": "Epic", "skinGrade": 4, "weight": 10,
                 "characterImageUrl": "https://cdn.dak.gg/epic.png",
                 "summaryArtUrl": "https://ercraft.net/assets/play-cards/67/first-pick/10.webp"},
            ]},
            {"characterId": 31, "characterName": "Rio", "weight": 2, "skins": [
                {"skinId": 1031000, "skinName": "base", "skinGrade": 1, "weight": 1,
                 "characterImageUrl": "https://cdn.dak.gg/rio.png"},
            ]},
        ],
    },))


def test_draws_character_then_skin_with_exact_weights_without_mutating_pool(monkeypatch):
    original = portrait_payload()
    snapshot = deepcopy(original)
    calls = []

    def choices(items, *, weights, k):
        calls.append((weights, k))
        return [items[0] if len(calls) == 1 else items[-1]]

    monkeypatch.setattr("erbs_plugin.summary_art.random.choices", choices)
    selected = select_summary_art(original)
    assert calls == [([213, 2], 1), ([1, 10], 1)]
    assert selected.sections[0]["characterId"] == 67
    assert selected.sections[0]["skinId"] == 1067003
    assert selected.sections[0]["skinGrade"] == 4
    assert selected.sections[0]["characterImageUrl"] == "https://cdn.dak.gg/epic.png"
    assert selected.sections[0]["summaryArtUrl"].endswith("/67/first-pick/10.webp")
    assert "artCandidates" not in selected.sections[0]
    assert original == snapshot
    assert select_summary_art(selected) is selected


def test_ignores_invalid_weights_and_keeps_legacy_or_other_cards(monkeypatch):
    original = portrait_payload()
    original.sections[0]["artCandidates"] = [
        {"weight": weight, "skins": [{"weight": 1}]}
        for weight in (None, True, -1, 0, float("nan"), float("inf"), "10")
    ] + [{"weight": 1, "skins": [{"weight": 0}]}]
    original.sections[0]["characterImageUrl"] = "https://cdn.dak.gg/legacy.png"

    def choices(*args, **kwargs):
        raise AssertionError("invalid or legacy pools must not draw")

    monkeypatch.setattr("erbs_plugin.summary_art.random.choices", choices)
    selected = select_summary_art(original)
    assert selected.sections[0]["characterImageUrl"] == "https://cdn.dak.gg/legacy.png"
    assert "artCandidates" not in selected.sections[0]
    for kind in ("summary", "radar", "player"):
        card = CardPayload(kind=kind, title="legacy")
        assert select_summary_art(card) is card


@pytest.mark.asyncio
async def test_direct_bot_renderer_selects_before_preparing_only_one_image(tmp_path, monkeypatch):
    from erbs_plugin.rendering.resources import image_sources

    captured = []

    async def prepare(value, config):
        from erbs_plugin.assets import AssetManager
        captured.append(set(image_sources(value).values()))
        return AssetManager(tmp_path)

    monkeypatch.setattr("erbs_plugin.summary_art.random.choices",
                        lambda items, **kwargs: [items[-1]])
    monkeypatch.setattr("erbs_plugin.rendering.skia.prepare_assets", prepare)
    async with SkiaCardRenderer(ERBSConfig(asset_directory=tmp_path)) as renderer:
        monkeypatch.setattr(renderer, "_render", lambda card: card.sections[0]["skinId"])
        assert await renderer.render(portrait_payload()) == 1031000
    assert captured == [{"https://cdn.dak.gg/rio.png"}]
