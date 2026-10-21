from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from erbs_plugin.config import ERBSConfig
from erbs_plugin.debug import CARD_PREVIEWS
from erbs_plugin.exceptions import RenderFailed
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import SkiaCardRenderer

skia = pytest.importorskip("skia")


@pytest.mark.asyncio
async def test_every_card_layout_renders_native_png_offline(tmp_path, monkeypatch):
    async def get(*args, **kwargs):
        raise AssertionError("offline rendering must not request network")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    async with SkiaCardRenderer(
        ERBSConfig(
            asset_directory=tmp_path,
            download_render_assets=False,
        )
    ) as renderer:
        for preview in CARD_PREVIEWS:
            png = await renderer.render(preview.payload)
            image = skia.Image.MakeFromEncoded(png)
            assert png.startswith(b"\x89PNG\r\n\x1a\n"), preview.operation
            assert image.width() == (1000 if preview.payload.kind == "character" else 1290)
            assert 250 < image.height() < 32760, preview.operation


@pytest.mark.asyncio
async def test_downloaded_image_pixels_are_present_and_download_is_reused(tmp_path, monkeypatch):
    surface = skia.Surface(16, 32)
    surface.getCanvas().clear(skia.ColorRED)
    surface.getCanvas().drawRect(
        skia.Rect.MakeXYWH(0, 16, 16, 16), skia.Paint(Color=skia.ColorGREEN)
    )
    red_png = bytes(surface.makeImageSnapshot().encodeToData())
    calls = []

    async def get(self, url):
        calls.append(url)
        return httpx.Response(200, content=red_png, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    payload = CardPayload(
        kind="global",
        title="原生图片测试",
        sections=(
            {
                "title": "图片",
                "type": "items",
                "items": [
                    {
                        "name": "测试图片",
                        "imageUrl": "http://cdn.dak.gg/red.png",
                    }
                ],
            },
        ),
    )
    async with SkiaCardRenderer(ERBSConfig(asset_directory=tmp_path)) as renderer:
        first = await renderer.render(payload)
        second = await renderer.render(payload)
    assert calls == ["https://cdn.dak.gg/red.png"]
    assert first == second
    pixels = skia.Image.MakeFromEncoded(first).toarray(colorType=skia.kRGBA_8888_ColorType)
    red_count = ((pixels[:, :, 0] > 240) & (pixels[:, :, 1] < 20) & (pixels[:, :, 2] < 20)).sum()
    green_count = ((pixels[:, :, 0] < 20) & (pixels[:, :, 1] > 240) & (pixels[:, :, 2] < 20)).sum()
    assert red_count > 300
    assert green_count > 300


@pytest.mark.asyncio
async def test_scale_and_layout_limits(tmp_path):
    config = ERBSConfig(asset_directory=tmp_path, download_render_assets=False)
    payload = CardPayload(kind="help", title="帮助")
    async with SkiaCardRenderer(config) as renderer:
        normal = skia.Image.MakeFromEncoded(await renderer.render(payload))
    async with SkiaCardRenderer(replace(config, render_scale=0.5)) as renderer:
        half = skia.Image.MakeFromEncoded(await renderer.render(payload))
        assert half.width() == normal.width() // 2
        assert abs(half.height() * 2 - normal.height()) <= 1
        excessive = replace(
            payload,
            sections=(
                {
                    "type": "items",
                    "items": [{"name": "row"}] * 1000,
                },
            ),
        )
        with pytest.raises(RenderFailed, match="尺寸限制"):
            await renderer.render(excessive)


def test_wrapping_keeps_normal_numbers_whole_and_bounds_long_tokens():
    renderer = SkiaCardRenderer(ERBSConfig(download_render_assets=False))
    renderer._initialize()
    lines = renderer._wrap("平均伤害 18688.15 胜率 15.17% " + "X" * 120, 240)
    assert any("18688.15" in line for line in lines)
    assert any("15.17%" in line for line in lines)
    assert all(renderer._measure(line, 17) <= 240 for line in lines)
