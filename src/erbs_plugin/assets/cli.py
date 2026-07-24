from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ..client import AsyncERBSClient
from ..config import ERBSConfig
from .manager import AssetManager

METADATA_NAMES = (
    "characters",
    "items",
    "tiers",
    "masteries",
    "skills",
    "tactical-skills",
    "trait-skills",
    "infusions",
)
ASSET_BASE_URL = "https://cdn.dak.gg"


def _collect_urls(value: Any, prefix: str = "metadata") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, Mapping):
        identity = value.get("id") or value.get("key") or value.get("imageName") or "item"
        for key, child in value.items():
            next_prefix = f"{prefix}:{identity}:{key}"
            if isinstance(child, str) and key.lower().endswith(("url", "image")):
                if child.startswith(("http://", "https://", "//", "/")):
                    result[next_prefix] = urljoin(ASSET_BASE_URL, child)
            else:
                result.update(_collect_urls(child, next_prefix))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            result.update(_collect_urls(child, f"{prefix}:{index}"))
    return result


async def discover_assets(config: ERBSConfig) -> tuple[dict[str, str], str]:
    assets: dict[str, str] = {}
    version = "unknown"
    async with AsyncERBSClient(config) as client:
        for name in METADATA_NAMES:
            payload = await client.metadata(name)
            assets.update(_collect_urls(payload, name))
            if version == "unknown":
                for url in assets.values():
                    marker = "/game-assets/"
                    if marker in url:
                        version = url.split(marker, 1)[1].split("/", 1)[0]
                        break
    return assets, version


async def run(args: argparse.Namespace) -> int:
    config = ERBSConfig(asset_directory=Path(args.directory))
    manager = AssetManager(config.asset_directory)
    if args.command == "check":
        missing = manager.check()
        if missing:
            print("Missing or invalid assets:")
            print("\n".join(missing))
            return 1
        print(f"Asset manifest is valid: {manager.manifest_path}")
        return 0

    assets, version = await discover_assets(config)
    if args.command in {"download", "update"}:
        await manager.download(
            assets,
            concurrency=args.concurrency,
            force=args.command == "update" or args.force,
            version=version,
        )
        print(f"Prepared {len(assets)} assets in {manager.directory}")
        return 0
    if args.command == "prune":
        removed = manager.prune(set(assets))
        print(f"Removed {len(removed)} obsolete assets")
        return 0
    return 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="erbs-assets")
    result.add_argument("command", choices=("download", "check", "update", "prune"))
    result.add_argument("--directory", required=True)
    result.add_argument("--concurrency", type=int, default=4)
    result.add_argument("--force", action="store_true")
    return result


def main() -> None:
    raise SystemExit(asyncio.run(run(parser().parse_args())))
