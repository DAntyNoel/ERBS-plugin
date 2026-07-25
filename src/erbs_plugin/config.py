from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_path


def _default_query_cache_seconds() -> dict[str, int]:
    return {
        "overview": 300,
        "rank": 180,
        "stats": 600,
        "matches": 120,
        "recent": 120,
        "radar": 180,
        "characters": 900,
        "skins": 1800,
        "teammates": 300,
        "multi": 300,
        "compare": 300,
        "best-match": 120,
        "hero-pool": 900,
        "equipment": 900,
        "leaderboard": 60,
        "character": 1800,
        "item": 86400,
        "routes": 600,
    }


@dataclass(slots=True)
class ERBSConfig:
    api_base_url: str = "https://er.dakgg.io"
    language: str = "zh-CN"
    timeout_seconds: float = 8.0
    retry_count: int = 2
    retry_backoff_seconds: float = 0.25
    retry_max_delay_seconds: float = 4.0
    request_concurrency: int = 3
    player_cache_seconds: int = 300
    match_cache_seconds: int = 180
    metadata_cache_seconds: int = 1800
    negative_cache_seconds: int = 600
    stale_cache_seconds: int = 900
    query_cache_enabled: bool = True
    query_cache_seconds: Mapping[str, int] = field(default_factory=_default_query_cache_seconds)
    query_cache_max_entries: int = 512
    private_database_path: Path | None = None
    asset_directory: Path | None = None
    browser_path: Path | None = None
    render_timeout_seconds: float = 30.0
    render_restart_after: int = 100
    render_scale: float = 1.0
    render_timezone_name: str = "CST"
    render_timezone_offset_hours: int = 8

    def __post_init__(self) -> None:
        self.api_base_url = self.api_base_url.rstrip("/")
        self.query_cache_seconds = {
            key.strip().casefold().replace("_", "-"): max(0, int(value))
            for key, value in self.query_cache_seconds.items()
        }
        self.query_cache_max_entries = max(1, self.query_cache_max_entries)
        if self.private_database_path is None:
            self.private_database_path = (
                user_data_path("erbs-plugin", appauthor=False) / "private-query-cache.sqlite3"
            )
        else:
            self.private_database_path = Path(self.private_database_path).expanduser()
        if self.asset_directory is not None:
            self.asset_directory = Path(self.asset_directory)
        if self.browser_path is not None:
            self.browser_path = Path(self.browser_path)
        self.request_concurrency = max(1, self.request_concurrency)
        self.retry_count = max(0, self.retry_count)
        self.retry_backoff_seconds = max(0.0, self.retry_backoff_seconds)
        self.retry_max_delay_seconds = max(0.0, self.retry_max_delay_seconds)
        self.stale_cache_seconds = max(0, self.stale_cache_seconds)
        self.render_scale = min(2.0, max(0.5, self.render_scale))
        self.render_timezone_name = self.render_timezone_name.strip() or "GMT"
        self.render_timezone_offset_hours = min(
            23, max(-23, int(self.render_timezone_offset_hours))
        )

    def query_cache_ttl(self, operation: str) -> int:
        if not self.query_cache_enabled:
            return 0
        normalized = operation.strip().casefold().replace("_", "-")
        return int(self.query_cache_seconds.get(normalized, 0))
