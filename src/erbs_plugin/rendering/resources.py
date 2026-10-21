"""Prepare only DAK.GG CDN images referenced by a rendered result."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import httpx
from platformdirs import user_data_path

from ..assets import AssetManager
from ..config import ERBSConfig

_LOCKS: WeakKeyDictionary = WeakKeyDictionary()
_IMAGE_KEYS = {
    "imageUrl", "iconUrl", "weaponImageUrl", "bgUrl", "bannerUrl",
    "tierImageUrl", "characterImageUrl",
}
_log = logging.getLogger(__name__)


def image_sources(value: object) -> dict[str, str]:
    sources = {}

    def visit(node: object, key: str = "") -> None:
        if isinstance(node, Mapping):
            for name, child in node.items():
                visit(child, str(name))
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child, key)
        elif isinstance(node, str) and key in _IMAGE_KEYS:
            normalized = f"https:{node}" if node.startswith("//") else node
            parsed = urlsplit(normalized)
            if parsed.scheme in {"http", "https"} and parsed.hostname == "cdn.dak.gg":
                normalized = parsed._replace(scheme="https").geturl()
                digest = hashlib.sha256(normalized.encode()).hexdigest()[:24]
                sources[f"dak:{digest}"] = normalized

    visit(value)
    return sources


async def prepare_assets(value: object, config: ERBSConfig) -> AssetManager:
    assets = (
        AssetManager(config.asset_directory.expanduser())
        if config.asset_directory is not None
        else AssetManager.discover()
    )
    if not assets.manifest_path.exists() and config.asset_directory is None:
        assets = AssetManager(user_data_path("erbs-plugin", appauthor=False) / "assets")
    if not config.download_render_assets:
        return assets
    sources = image_sources(value)
    if not sources:
        return assets
    loop_locks = _LOCKS.setdefault(asyncio.get_running_loop(), {})
    lock = loop_locks.setdefault(str(assets.directory.resolve()), asyncio.Lock())
    async with lock:
        entries = assets.load_manifest()
        known = {
            entry.source for entry in entries.values() if (assets.directory / entry.path).is_file()
        }
        missing = {key: url for key, url in sources.items() if url not in known}
        if missing:
            try:
                await assets.download(
                    missing, concurrency=min(8, config.request_concurrency), strict=False
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                _log.warning("部分 DAK.GG 素材未下载，将显示占位图：%s", exc)
    return assets
