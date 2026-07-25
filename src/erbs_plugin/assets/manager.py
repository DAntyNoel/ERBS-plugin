from __future__ import annotations

import hashlib
import json
from base64 import b64decode
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from platformdirs import user_data_path

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
    placeholder: bool = False


PLACEHOLDER_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class AssetManager:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.manifest_path = self.directory / "manifest.json"

    @classmethod
    def discover(
        cls,
        preferred: str | Path | None = None,
        *,
        search_from: str | Path | None = None,
    ) -> AssetManager:
        """Find a downloaded local asset manifest for rendering."""

        start = Path(search_from or Path.cwd()).resolve()
        candidates: list[Path] = []
        if preferred is not None:
            candidates.append(Path(preferred).expanduser())
        for root in (start, *start.parents):
            candidates.extend(
                (
                    root,
                    root / "assets",
                    root / "data" / "erbs-assets",
                    root / "erbs-assets",
                )
            )
        candidates.append(user_data_path("erbs-plugin", appauthor=False) / "assets")

        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            manifest = resolved / "manifest.json"
            if not manifest.is_file():
                continue
            try:
                raw = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(raw, dict) and isinstance(raw.get("assets"), dict):
                return cls(resolved)

        fallback = Path(preferred).expanduser() if preferred is not None else start / "assets"
        return cls(fallback)

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

    def resolve_source(self, source: str) -> Path:
        normalized = source if not source.startswith("//") else f"https:{source}"
        for entry in self.load_manifest().values():
            if entry.source != normalized:
                continue
            path = self.directory / entry.path
            if path.is_file():
                return path
        return self.placeholder_path()

    def resolve_filename(self, filename: str) -> Path:
        """Resolve a downloaded asset by its source filename."""

        if not filename or Path(filename).name != filename:
            raise AssetMissing(filename)
        for entry in self.load_manifest().values():
            if Path(urlparse(entry.source).path).name != filename:
                continue
            path = self.directory / entry.path
            if path.is_file() and not entry.placeholder:
                return path
        raise AssetMissing(filename)

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
                if not force and destination.is_file():
                    if key not in entries:
                        entries[key] = AssetEntry(
                            key=key,
                            path=relative.as_posix(),
                            source=normalized_url,
                            sha256=self._sha256(destination),
                            size=destination.stat().st_size,
                            downloaded_at=datetime.now(UTC).isoformat(),
                            version=version,
                        )
                    return
                destination.parent.mkdir(parents=True, exist_ok=True)
                async with semaphore:
                    response = await client.get(normalized_url)
                    if response.status_code not in {403, 404}:
                        response.raise_for_status()
                placeholder = response.status_code in {403, 404}
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(PLACEHOLDER_PNG if placeholder else response.content)
                temporary.replace(destination)
                entries[key] = AssetEntry(
                    key=key,
                    path=relative.as_posix(),
                    source=normalized_url,
                    sha256=self._sha256(destination),
                    size=destination.stat().st_size,
                    downloaded_at=datetime.now(UTC).isoformat(),
                    version=version,
                    placeholder=placeholder,
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
