from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    asset_directory: Path | None = None
    browser_path: Path | None = None
    render_timeout_seconds: float = 30.0
    render_restart_after: int = 100
    render_scale: float = 1.0

    def __post_init__(self) -> None:
        self.api_base_url = self.api_base_url.rstrip("/")
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
