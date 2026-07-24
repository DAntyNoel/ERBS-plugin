from __future__ import annotations

import hashlib

import httpx
import pytest

from erbs_plugin.assets.manager import AssetEntry, AssetManager


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
    assert manager.prune(set()) == [entry.key]
    assert not image.exists()


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
