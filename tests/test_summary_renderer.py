from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from erbs_plugin import ERBSConfig, RenderFailed
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import SkiaCardRenderer

skia = pytest.importorskip("skia")


def payload() -> CardPayload:
    return CardPayload(
        kind="summary",
        title="长昵称 Player <测试> " * 4,
        sections=({
            "type": "player-summary",
            "displayTitle": "六维实战档案",
            "rp": 4445,
            "scopeLabel": "最近 20 场排位三排",
            "axes": [
                {"key": "survival", "score": 0, "sampleCount": 20},
                {"key": "combat", "score": 75.25, "sampleCount": 18},
                {"key": "macro", "score": None, "sampleCount": 0},
                {"key": "support", "score": 100, "sampleCount": 20},
                {"key": "finish", "score": 60, "sampleCount": 20},
                {"key": "consistency", "score": float("nan"), "sampleCount": 1},
            ],
        },),
    )


@pytest.mark.asyncio
async def test_summary_preserves_zero_missing_and_local_score_semantics(tmp_path, monkeypatch):
    async def get(*args, **kwargs):
        raise AssertionError("offline summary rendering must not request the network")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        labels = []
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        png = await renderer.render(payload())
    image = skia.Image.MakeFromEncoded(png)
    assert (image.width(), image.height()) == (1024, 1536)
    assert "0.0" in labels and "100.0" in labels and "75.2" in labels
    assert labels.count("—") == 2
    assert "18 场 · / 100" in labels and "1 场 · 数据不足" in labels
    assert "最近 20 场排位三排 · 本地评分" in labels
    assert not any(text.startswith("P75") or text in {"S", "SS", "SSS", "A"} for text in labels)


@pytest.mark.asyncio
async def test_summary_uses_explicit_local_art_and_render_scale(tmp_path):
    surface = skia.Surface(1024, 1536)
    surface.getCanvas().clear(skia.ColorRED)
    art = tmp_path / "art.png"
    art.write_bytes(bytes(surface.makeImageSnapshot().encodeToData()))
    config = ERBSConfig(asset_directory=tmp_path, download_render_assets=False,
                        summary_art_path=art, render_scale=0.5)
    async with SkiaCardRenderer(config) as renderer:
        image = skia.Image.MakeFromEncoded(await renderer.render(payload()))
    assert (image.width(), image.height()) == (512, 768)
    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    assert tuple(pixels[100, 100]) == (255, 0, 0, 255)
    async with SkiaCardRenderer(replace(config, summary_art_path=tmp_path / "missing")) as renderer:
        with pytest.raises(RenderFailed, match="无法读取总结卡底图"):
            await renderer.render(payload())
    art.write_bytes(b"invalid image")
    async with SkiaCardRenderer(config) as renderer:
        with pytest.raises(RenderFailed, match="1024×1536"):
            await renderer.render(payload())
