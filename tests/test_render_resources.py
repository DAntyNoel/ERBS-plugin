from __future__ import annotations

import asyncio

import httpx
import pytest

from erbs_plugin.assets import AssetManager
from erbs_plugin.config import ERBSConfig
from erbs_plugin.rendering.resources import image_sources, prepare_assets


def test_only_referenced_dak_cdn_images_are_download_candidates() -> None:
    sources = image_sources(
        {
            "imageUrl": "//cdn.dak.gg/character.png",
            "nested": [{"iconUrl": "http://cdn.dak.gg/character.png"}],
            "link": "https://cdn.dak.gg/not-an-image",
            "raw": {"imageUrl": "https://example.invalid/blocked.png"},
            "other": {"imageUrl": "asset://downloaded.png"},
        }
    )
    assert list(sources.values()) == ["https://cdn.dak.gg/character.png"]


@pytest.mark.asyncio
async def test_preparation_keeps_partial_success_and_reuses_local_files(tmp_path, monkeypatch):
    calls = []

    async def get(self, url):
        calls.append(str(url))
        await asyncio.sleep(0)
        return httpx.Response(
            503 if str(url).endswith("bad.png") else 200,
            content=b"downloaded-image",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    config = ERBSConfig(asset_directory=tmp_path / "assets")
    payload = {
        "items": [
            {"imageUrl": "https://cdn.dak.gg/ok.png"},
            {"imageUrl": "https://cdn.dak.gg/bad.png"},
        ]
    }
    manager = await prepare_assets(payload, config)
    assert manager.resolve_source("https://cdn.dak.gg/ok.png").read_bytes() == b"downloaded-image"
    assert manager.check() == []
    await prepare_assets(payload, config)
    assert calls.count("https://cdn.dak.gg/ok.png") == 1
    assert calls.count("https://cdn.dak.gg/bad.png") == 2


@pytest.mark.asyncio
async def test_offline_render_preparation_does_not_request_network(tmp_path, monkeypatch):
    async def get(*args, **kwargs):
        raise AssertionError("offline preparation must not request images")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    manager = await prepare_assets(
        {"imageUrl": "https://cdn.dak.gg/test.png"},
        ERBSConfig(asset_directory=tmp_path, download_render_assets=False),
    )
    assert not manager.manifest_path.exists()


@pytest.mark.asyncio
async def test_strict_asset_download_raises_after_saving_successful_downloads(
    tmp_path, monkeypatch
):
    async def get(self, url):
        return httpx.Response(
            500 if "bad" in url else 200, content=b"ok", request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    manager = AssetManager(tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        await manager.download(
            {"ok": "https://cdn.dak.gg/ok.png", "bad": "https://cdn.dak.gg/bad.png"}
        )
    assert manager.resolve("ok").read_bytes() == b"ok"
    assert manager.check() == []
