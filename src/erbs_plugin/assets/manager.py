from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..exceptions import AssetMissing


@dataclass(slots=True)
class AssetEntry:
    key: str
    path: str
    source: str
    sha256: str
    size: int
    downloaded_at: str
    version: str = "unknown"


class AssetManager:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.manifest_path = self.directory / "manifest.json"

    def load_manifest(self) -> dict[str, AssetEntry]:
        if not self.manifest_path.exists():
            return {}
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {key: AssetEntry(**value) for key, value in raw.get("assets", {}).items()}

    def save_manifest(self, entries: dict[str, AssetEntry], *, version: str = "unknown") -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": version,
            "updatedAt": datetime.now(UTC).isoformat(),
            "assets": {key: asdict(value) for key, value in sorted(entries.items())},
        }
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.manifest_path)

    def resolve(self, key: str) -> Path:
        entry = self.load_manifest().get(key)
        if entry is None:
            raise AssetMissing(key)
        path = self.directory / entry.path
        if not path.is_file():
            raise AssetMissing(key)
        return path

    @staticmethod
    def placeholder_path() -> Path:
        return Path(__file__).with_name("placeholder.svg")

    def check(self) -> list[str]:
        if not self.manifest_path.is_file():
            return ["manifest.json"]
        missing: list[str] = []
        for key, entry in self.load_manifest().items():
            path = self.directory / entry.path
            if not path.is_file() or self._sha256(path) != entry.sha256:
                missing.append(key)
        return missing

    async def download(
        self,
        assets: dict[str, str],
        *,
        concurrency: int = 4,
        force: bool = False,
        version: str = "unknown",
    ) -> dict[str, AssetEntry]:
        self.directory.mkdir(parents=True, exist_ok=True)
        entries = self.load_manifest()
        semaphore = __import__("asyncio").Semaphore(max(1, concurrency))
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            async def fetch(key: str, url: str) -> None:
                parsed = urlparse(url if "://" in url else f"https:{url}")
                normalized_url = parsed.geturl()
                suffix = Path(parsed.path).suffix or ".bin"
                relative = Path(key.replace(":", "/")).with_suffix(suffix)
                destination = self.directory / relative
                if not force and key in entries and destination.is_file():
                    return
                destination.parent.mkdir(parents=True, exist_ok=True)
                async with semaphore:
                    response = await client.get(normalized_url)
                    response.raise_for_status()
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(response.content)
                temporary.replace(destination)
                entries[key] = AssetEntry(
                    key=key,
                    path=relative.as_posix(),
                    source=normalized_url,
                    sha256=self._sha256(destination),
                    size=destination.stat().st_size,
                    downloaded_at=datetime.now(UTC).isoformat(),
                    version=version,
                )

            import asyncio

            await asyncio.gather(*(fetch(key, url) for key, url in assets.items()))
        self.save_manifest(entries, version=version)
        return entries

    def prune(self, valid_keys: set[str]) -> list[str]:
        entries = self.load_manifest()
        removed: list[str] = []
        for key in list(entries):
            if key in valid_keys:
                continue
            path = self.directory / entries[key].path
            if path.is_file():
                path.unlink()
            entries.pop(key)
            removed.append(key)
        self.save_manifest(entries)
        return removed

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
