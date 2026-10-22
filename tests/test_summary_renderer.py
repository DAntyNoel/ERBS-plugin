from __future__ import annotations

import hashlib
from dataclasses import replace

import httpx
import pytest

from erbs_plugin import ERBSConfig, RenderFailed
from erbs_plugin.assets import AssetManager
from erbs_plugin.assets.manager import AssetEntry
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import SkiaCardRenderer

skia = pytest.importorskip("skia")
SUMMARY_ART_URL = "https://ercraft.net/assets/play-cards/67/10.webp"
DAK_ART_URL = "https://cdn.dak.gg/selected-skin.png"


def colored_image(width: int, height: int, color: int) -> bytes:
    surface = skia.Surface(width, height)
    surface.getCanvas().clear(color)
    return bytes(surface.makeImageSnapshot().encodeToData())


def cache_asset(directory, key: str, source: str, content: bytes) -> None:
    manager = AssetManager(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.png"
    path.write_bytes(content)
    entries = manager.load_manifest()
    entries[key] = AssetEntry(
        key=key, path=path.name, source=source,
        sha256=hashlib.sha256(content).hexdigest(), size=len(content),
        downloaded_at="2026-10-22T00:00:00+00:00",
    )
    manager.save_manifest(entries)


def portrait_payload() -> CardPayload:
    card = payload()
    card.sections[0].update(
        summaryArtUrl=SUMMARY_ART_URL, characterImageUrl=DAK_ART_URL,
        skinName="热带次元 艾比盖尔",
    )
    return card


def payload() -> CardPayload:
    return CardPayload(
        kind="summary",
        title="长昵称 Player <测试> " * 4,
        sections=({
            "type": "player-summary",
            "displayTitle": "六维实战档案",
            "rp": 4445,
            "scopeLabel": "最近 20 场排位三排",
            "sampleSize": 20,
            "seasonId": 41,
            "seasonName": "赛季 S12",
            "axes": [
                {"key": "survival", "score": 0, "sampleCount": 20},
                {"key": "combat", "score": 75.25, "sampleCount": 18, "grade": "C"},
                {"key": "macro", "score": None, "sampleCount": 0},
                {"key": "support", "score": 100, "sampleCount": 20},
                {"key": "finish", "score": 60, "sampleCount": 20},
                {"key": "consistency", "score": float("nan"), "sampleCount": 1},
            ],
        },),
        footer={"cached": True, "source": "DAK.GG"},
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
    assert "E" in labels and labels.count("S") == 2 and "A" in labels
    assert "75.25% · 18场" in labels and "0% · 20场" in labels
    assert labels.count("—") == 2
    assert "100% · 20场" in labels and "0场" in labels and "1场" in labels
    assert "S12 ERCraft 全部" in labels
    assert "战绩" in labels and "结果" not in labels
    assert not any(
        word in text
        for text in labels
        for word in ("最近", "本地", "评级", "来源", "公式", "缓存", "DAK.GG", "六维", "数据不足")
    )
    assert not any(text.startswith("P75") or text in {"SS", "SSS", "C"} for text in labels)


@pytest.mark.asyncio
async def test_published_summary_displays_api_percentiles_and_grades(tmp_path, monkeypatch):
    card = payload()
    section = card.sections[0]
    section["source"] = "ercraft-api"
    for axis, percentile, grade in zip(
        section["axes"], (0, 65.56, 95, 85, 70, 69.99999999),
        ("E", "A", "SSS", "SS", "S", "A"), strict=True,
    ):
        axis.update(score=1, percentile=percentile, grade=grade, status="partial",
                    sourceGames=20, eligibleGames=18, sampleCount=18)
    labels = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        image = skia.Image.MakeFromEncoded(await renderer.render(card))
        assert (image.width(), image.height()) == (1024, 1536)
        assert labels.count("A") == 2
        assert all(grade in labels for grade in ("E", "S", "SS", "SSS"))
        assert "P0 · 18场" in labels and "P65.6 · 18场" in labels
        assert "P95 · 18场" in labels and labels.count("P70 · 18场") == 2
        assert not any("%" in label for label in labels)
        labels.clear()
        section["axes"][0]["grade"] = None
        await renderer.render(card)
        assert "—" in labels and "E" not in labels and "P0 · 18场" not in labels


@pytest.mark.asyncio
@pytest.mark.parametrize("truncated,sample_size,ranked_count,ranked_total", [
    (False, 216, 216, 216),
    (False, 20, 7, 7),
    (True, 500, 500, 1168),
])
async def test_summary_preserves_axis_counts_without_adding_scope_notes(
    tmp_path, monkeypatch, truncated, sample_size, ranked_count, ranked_total,
):
    card = payload()
    card.sections[0].update(
        truncated=truncated, sampleSize=sample_size,
        rankedCount=ranked_count, rankedTotal=ranked_total,
    )
    card.sections[0]["axes"][0].update(score=68.41, percentile=99.9, sampleCount=215)
    labels = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        await renderer.render(card)

    assert "68.41% · 215场" in labels
    assert "S12 ERCraft 全部" in labels
    assert not any("1168" in label or "216场" == label or "20场" == label for label in labels)
    assert not any("99.9" in label or label.startswith("P") for label in labels)
    assert card.sections[0]["axes"][0]["percentile"] == 99.9


@pytest.mark.asyncio
@pytest.mark.parametrize("summary_title,expected_title", [
    (None, "光与盐"),
    ("冠军之路", "冠军之路"),
])
async def test_summary_restores_original_ribbon_and_rp_layout(
    tmp_path, monkeypatch, summary_title, expected_title,
):
    art = tmp_path / "background.png"
    art.write_bytes(colored_image(1024, 1536, skia.ColorRED))
    cache_asset(tmp_path, "tier", DAK_ART_URL, colored_image(16, 16, skia.ColorBLUE))
    card = payload()
    card.sections[0]["tierImageUrl"] = DAK_ART_URL
    labels = []
    tier_positions = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
        summary_art_path=art, summary_title=summary_title,
    )) as renderer:
        original = renderer._label
        original_image = renderer._image

        def record(canvas, value, *args, **kwargs):
            labels.append((str(value), args[1]))
            return original(canvas, value, *args, **kwargs)

        def record_image(canvas, source, x, y, *args, **kwargs):
            if source == DAK_ART_URL:
                tier_positions.append(y)
            return original_image(canvas, source, x, y, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        monkeypatch.setattr(renderer, "_image", record_image)
        image = skia.Image.MakeFromEncoded(await renderer.render(card))
    assert (expected_title, 1201) in labels
    assert not any(label == "六维实战档案" for label, _ in labels)
    assert ("4,445 RP", 1249) in labels
    assert tier_positions == [1215]
    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    assert tuple(pixels[1185, 400]) == (50, 55, 70, 255)
    assert tuple(pixels[1248, 450]) == (247, 234, 216, 255)


@pytest.mark.asyncio
@pytest.mark.parametrize("season_name,expected", [
    ("赛季 S12", "S12 ERCraft 全部"),
    ("Season s13", "S13 ERCraft 全部"),
    (None, "ERCraft 全部"),
    ("SEASON_21", "ERCraft 全部"),
])
async def test_summary_translates_original_footer_without_inventing_display_season(
    tmp_path, monkeypatch, season_name, expected,
):
    card = payload()
    card.sections[0]["seasonName"] = season_name
    labels = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        await renderer.render(card)
    assert expected in labels
    assert not any("S41" in label or "S21" in label for label in labels)


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


@pytest.mark.asyncio
async def test_summary_uses_complete_cached_ercraft_background_and_keeps_labels_clean(
    tmp_path, monkeypatch,
):
    cache_asset(tmp_path, "card", SUMMARY_ART_URL, colored_image(1024, 1536, skia.ColorRED))
    cache_asset(tmp_path, "dak", DAK_ART_URL, colored_image(16, 16, skia.ColorBLUE))
    labels = []

    async def get(*args, **kwargs):
        raise AssertionError("cached summary assets must not request the network")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        image = skia.Image.MakeFromEncoded(await renderer.render(portrait_payload()))

    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    assert tuple(pixels[10, 10]) == (255, 0, 0, 255)
    assert tuple(pixels[500, 500]) == (255, 0, 0, 255)
    assert "热带次元 艾比盖尔" not in labels
    assert "S12 ERCraft 全部" in labels
    assert not any("DAK.GG" in label for label in labels)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_asset", ["bytes", "dimensions", "missing"])
async def test_invalid_cached_ercraft_card_falls_back_to_selected_dak_skin(
    tmp_path, monkeypatch, bad_asset,
):
    if bad_asset != "missing":
        content = (b"invalid image" if bad_asset == "bytes"
                   else colored_image(32, 32, skia.ColorRED))
        cache_asset(tmp_path, "card", SUMMARY_ART_URL, content)
    cache_asset(tmp_path, "dak", DAK_ART_URL, colored_image(16, 16, skia.ColorBLUE))
    labels = []
    async with SkiaCardRenderer(ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False,
    )) as renderer:
        original = renderer._label

        def record(canvas, value, *args, **kwargs):
            labels.append(str(value))
            return original(canvas, value, *args, **kwargs)

        monkeypatch.setattr(renderer, "_label", record)
        image = skia.Image.MakeFromEncoded(await renderer.render(portrait_payload()))

    pixels = image.toarray(colorType=skia.kRGBA_8888_ColorType)
    assert tuple(pixels[500, 500]) == (0, 0, 255, 255)
    assert "热带次元 艾比盖尔" not in labels
    assert not any("卡面 ERCraft" in label for label in labels)


@pytest.mark.asyncio
async def test_explicit_art_overrides_cached_ercraft_card_and_keeps_strict_errors(tmp_path):
    cache_asset(tmp_path, "card", SUMMARY_ART_URL, colored_image(1024, 1536, skia.ColorBLUE))
    art = tmp_path / "explicit.png"
    art.write_bytes(colored_image(1024, 1536, skia.ColorRED))
    config = ERBSConfig(
        asset_directory=tmp_path, download_render_assets=False, summary_art_path=art,
    )
    async with SkiaCardRenderer(config) as renderer:
        image = skia.Image.MakeFromEncoded(await renderer.render(portrait_payload()))
    assert tuple(image.toarray(colorType=skia.kRGBA_8888_ColorType)[500, 500]) == (255, 0, 0, 255)

    art.write_bytes(colored_image(32, 32, skia.ColorRED))
    async with SkiaCardRenderer(config) as renderer:
        with pytest.raises(RenderFailed, match="1024×1536"):
            await renderer.render(portrait_payload())
    async with SkiaCardRenderer(replace(config, summary_art_path=tmp_path / "missing")) as renderer:
        with pytest.raises(RenderFailed, match="无法读取总结卡底图"):
            await renderer.render(portrait_payload())
