from dataclasses import replace

import pytest

from erbs_plugin import ERBSConfig, SkiaCardRenderer
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering.dak import num

skia = pytest.importorskip("skia")


def test_display_rounding_and_unavailable_values():
    assert num(9.95, 1, "%") == "10.0%"
    assert num(None) == "—"
    assert num(float("nan")) == "—"
    assert num(0, 0) == "0"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 20])
async def test_player_layout_keeps_two_desktop_columns_and_bounded_height(tmp_path, count):
    payload = CardPayload(
        kind="player",
        title="long-player-name-" * 30,
        sections=(
            {
                "type": "stats",
                "profile": {"modeName": "排位", "seasonName": "赛季 S12"},
                "items": [],
                "teammates": [],
            },
            {"type": "rank", "items": []},
            {
                "title": "最近对局",
                "items": [
                    {
                        "rank": 2,
                        "characterName": "测试角色",
                        "matchingMode": 3,
                        "mmrAfter": 4400,
                        "mmrGain": 0,
                    }
                    for _ in range(count)
                ],
            },
        ),
    )
    config = ERBSConfig(asset_directory=tmp_path, download_render_assets=False)
    async with SkiaCardRenderer(config) as renderer:
        image = skia.Image.MakeFromEncoded(await renderer.render(payload))
    assert image.width() == 1290
    assert 900 <= image.height() < 3000
    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    # Both columns have white cards in the same vertical band, separated by the page gutter.
    assert tuple(pixels[340, 45, :3]) == (255, 255, 255)
    assert tuple(pixels[380, 460, :3]) == (255, 255, 255)
    assert tuple(pixels[340, 410, :3]) == (244, 244, 244)
    async with SkiaCardRenderer(replace(config, render_scale=0.5)) as renderer:
        half = skia.Image.MakeFromEncoded(await renderer.render(payload))
    assert half.width() == 645
    assert abs(half.height() * 2 - image.height()) <= 1


@pytest.mark.asyncio
async def test_character_layout_renders_without_selection_sidebar_and_empty_tables(tmp_path):
    payload = CardPayload(
        kind="character",
        title="马库斯",
        sections=(
            {
                "title": "武器流派",
                "character": {"patch": 12060},
                "items": [
                    {"name": "斧子", "tier": "C", "pickRate": 1.08, "games": 100},
                ],
            },
            {"title": "技能加点", "items": []},
        ),
        footer={"mode": "RANK", "tier": "diamond_plus"},
    )
    async with SkiaCardRenderer(
        ERBSConfig(
            asset_directory=tmp_path,
            download_render_assets=False,
        )
    ) as renderer:
        image = skia.Image.MakeFromEncoded(await renderer.render(payload))
    assert image.width() == 1000
    assert 1200 < image.height() < 3000
    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    # The desktop weapon table occupies the left column; chest/head share the next row.
    assert tuple(pixels[950, 700, :3]) == (244, 244, 244)
    assert tuple(pixels[1060, 200, :3]) == (255, 255, 255)
    assert tuple(pixels[1060, 700, :3]) == (255, 255, 255)
