from __future__ import annotations

import hashlib

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
