from __future__ import annotations

import hashlib

import httpx
import pytest

from erbs_plugin.assets.manager import AssetEntry, AssetManager
from erbs_plugin.exceptions import AssetMissing


def test_manifest_check_and_prune(tmp_path) -> None:
    manager = AssetManager(tmp_path)
    assert manager.check() == ["manifest.json"]
    assert manager.placeholder_path().is_file()
    image = tmp_path / "characters" / "one.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    entry = AssetEntry(
        key="characters:one",
        path="characters/one.png",
        source="https://example.invalid/one.png",
        sha256=hashlib.sha256(b"image").hexdigest(),
        size=5,
        downloaded_at="2026-07-24T00:00:00+00:00",
    )
    manager.save_manifest({entry.key: entry}, version="test")

    assert manager.check() == []
    assert manager.resolve_source(entry.source) == image
    assert manager.resolve_filename("one.png") == image
    with pytest.raises(AssetMissing, match="missing.png"):
        manager.resolve_filename("missing.png")
    missing = manager.resolve_source("https://example.invalid/missing.png")
    assert missing == manager.placeholder_path()
    assert manager.prune(set()) == [entry.key]
    assert not image.exists()


def test_discover_reuses_downloaded_assets_from_parent_directory(tmp_path, monkeypatch) -> None:
    source = "https://example.invalid/one.png"
    asset_directory = tmp_path / "assets"
    manager = AssetManager(asset_directory)
    image = asset_directory / "characters" / "one.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    entry = AssetEntry(
        key="characters:one",
        path="characters/one.png",
        source=source,
        sha256=hashlib.sha256(b"image").hexdigest(),
        size=5,
        downloaded_at="2026-07-24T00:00:00+00:00",
    )
    manager.save_manifest({entry.key: entry}, version="test")
    working_directory = tmp_path / "consumer" / "nested"
    working_directory.mkdir(parents=True)
    (working_directory / "manifest.json").write_text("[]", encoding="utf-8")
    monkeypatch.chdir(working_directory)

    discovered = AssetManager.discover()

    assert discovered.directory == asset_directory
    assert discovered.resolve_source(source) == image


def test_discover_falls_back_to_placeholder_when_no_asset_exists(tmp_path) -> None:
    manager = AssetManager.discover(search_from=tmp_path)

    assert (
        manager.resolve_source("https://example.invalid/missing.png")
        == manager.placeholder_path()
    )


@pytest.mark.asyncio
async def test_download_uses_placeholder_for_unavailable_asset(tmp_path, monkeypatch) -> None:
    async def fake_get(self, url):
        request = httpx.Request("GET", str(url))
        return httpx.Response(403, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    manager = AssetManager(tmp_path)
    entries = await manager.download(
        {"skills:missing": "https://cdn.example.invalid/missing.png"}, version="test"
    )

    entry = entries["skills:missing"]
    assert entry.placeholder is True
    assert (tmp_path / entry.path).is_file()
    assert manager.check() == []
