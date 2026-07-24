from .analysis import ERBSAnalysisService
from .api import (
    OutputFormat,
    QueryOperation,
    QueryOutput,
    best_match,
    character,
    characters,
    compare,
    equipment,
    hero_pool,
    item,
    leaderboard,
    matches,
    multi,
    player_overview,
    query,
    rank,
    recent,
    routes,
    skins,
    stats,
    teammates,
)
from .assets import AssetManager
from .client import AsyncERBSClient
from .config import ERBSConfig
from .exceptions import (
    AssetMissing,
    ERBSError,
    InvalidQuery,
    PlayerNotFound,
    RateLimited,
    RenderFailed,
    UpstreamUnavailable,
)
from .models import CardPayload, FetchMeta, MatchRecord, PlayerProfile
from .rendering import HtmlCardRenderer, TextRenderer
from .services import ERBSService

__all__ = [
    "AssetManager",
    "AssetMissing",
    "AsyncERBSClient",
    "CardPayload",
    "ERBSAnalysisService",
    "ERBSConfig",
    "ERBSError",
    "ERBSService",
    "FetchMeta",
    "HtmlCardRenderer",
    "InvalidQuery",
    "MatchRecord",
    "OutputFormat",
    "PlayerNotFound",
    "PlayerProfile",
    "QueryOperation",
    "QueryOutput",
    "RateLimited",
    "RenderFailed",
    "TextRenderer",
    "UpstreamUnavailable",
    "best_match",
    "character",
    "characters",
    "compare",
    "equipment",
    "hero_pool",
    "item",
    "leaderboard",
    "matches",
    "multi",
    "player_overview",
    "query",
    "rank",
    "recent",
    "routes",
    "skins",
    "stats",
    "teammates",
]

__version__ = "0.1.0"
API_VERSION = 1
