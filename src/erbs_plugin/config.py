from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_path


@dataclass(slots=True)
class ERBSConfig:
    api_base_url: str = "https://er.dakgg.io"
    language: str = "zh-CN"
    timeout_seconds: float = 8.0
    retry_count: int = 2
    request_concurrency: int = 3
    player_cache_seconds: int = 300
    match_cache_seconds: int = 180
    metadata_cache_seconds: int = 1800
    negative_cache_seconds: int = 600
    asset_directory: Path = field(
        default_factory=lambda: user_data_path("erbs-plugin", appauthor=False) / "assets"
    )
    browser_path: Path | None = None
    render_timeout_seconds: float = 30.0
    render_restart_after: int = 100
    render_scale: float = 1.0

    def __post_init__(self) -> None:
        self.api_base_url = self.api_base_url.rstrip("/")
        self.asset_directory = Path(self.asset_directory)
        if self.browser_path is not None:
            self.browser_path = Path(self.browser_path)
        self.request_concurrency = max(1, self.request_concurrency)
        self.retry_count = max(0, self.retry_count)
        self.render_scale = min(2.0, max(0.5, self.render_scale))
