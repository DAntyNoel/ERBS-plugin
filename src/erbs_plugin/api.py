from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, overload

from .cache import QueryCacheDatabase, annotate_query_payload, query_cache_spec
from .client import AsyncERBSClient
from .commands import (
    normalize_mode,
    normalize_operation,
    normalize_server,
    normalize_tier,
    parse_command,
)
from .config import ERBSConfig
from .exceptions import InvalidQuery
from .models import CardPayload
from .rendering import CardRenderer, SkiaCardRenderer, TextRenderer
from .services import ERBSService
from .summary_art import select_summary_art

type OutputFormat = Literal["json", "bytes", "path"]
type QueryOutput = str | bytes | Path
type QueryOperation = Literal[
    "overview",
    "rank",
    "stats",
    "matches",
    "recent",
    "radar",
    "summary",
    "characters",
    "skins",
    "teammates",
    "multi",
    "compare",
    "best-match",
    "hero-pool",
    "equipment",
    "leaderboard",
    "character",
    "item",
    "routes",
    "search",
    "character-stats",
    "character-equipment",
    "tier-stats",
    "tier-cutoffs",
    "help",
]


def _normalize_operation(operation: str) -> str:
    return normalize_operation(operation)


def _require_arguments(operation: str, arguments: tuple[str, ...], count: int) -> None:
    if len(arguments) != count:
        suffix = "argument" if count == 1 else "arguments"
        raise InvalidQuery(f"{operation} requires {count} {suffix}")


async def _payload_for(
    service: ERBSService,
    operation: str,
    arguments: tuple[str, ...],
    *,
    count: int,
    page: int,
    season: str | None,
    weapon: str | None,
    mode: str,
    tier: str,
    server: str,
) -> CardPayload:
    operation = _normalize_operation(operation)
    if operation == "help":
        _require_arguments(operation, arguments, 0)
        return service.help_card()
    if operation == "search":
        _require_arguments(operation, arguments, 1)
        return await service.search_player_card(arguments[0], mode=mode, count=count, season=season)
    if operation == "character-equipment":
        _require_arguments(operation, arguments, 1)
        return await service.character_analysis_card(
            arguments[0], weapon=weapon, mode=mode, tier=tier, equipment_only=True
        )
    if operation == "character-stats":
        _require_arguments(operation, arguments, 0)
        return await service.character_stats_card(mode=mode, tier=tier)
    if operation in {"tier-stats", "tier-cutoffs"}:
        _require_arguments(operation, arguments, 0)
        return await service.tier_statistics_card(
            server=server, cutoffs_only=operation == "tier-cutoffs"
        )
    if operation == "overview":
        _require_arguments(operation, arguments, 1)
        return await service.player_overview(arguments[0])
    if operation == "rank":
        _require_arguments(operation, arguments, 1)
        return await service.rank_card(arguments[0], season=season)
    if operation == "stats":
        _require_arguments(operation, arguments, 1)
        return await service.stats_card(arguments[0], season=season)
    if operation == "matches":
        _require_arguments(operation, arguments, 1)
        return await service.matches_card(arguments[0], count=count)
    if operation == "recent":
        _require_arguments(operation, arguments, 1)
        return await service.recent_card(arguments[0])
    if operation == "radar":
        _require_arguments(operation, arguments, 1)
        return await service.radar_card(arguments[0], count=count)
    if operation == "summary":
        _require_arguments(operation, arguments, 1)
        return await service.player_summary(arguments[0], count=count, season=season)
    if operation == "characters":
        _require_arguments(operation, arguments, 1)
        return await service.characters_card(arguments[0])
    if operation == "skins":
        _require_arguments(operation, arguments, 1)
        return await service.skins_card(arguments[0])
    if operation == "teammates":
        _require_arguments(operation, arguments, 1)
        return await service.teammates_card(arguments[0])
    if operation == "multi":
        return await service.multi_card(list(arguments))
    if operation == "compare":
        _require_arguments(operation, arguments, 2)
        return await service.compare_card(arguments[0], arguments[1])
    if operation == "best-match":
        _require_arguments(operation, arguments, 1)
        return await service.best_match_card(arguments[0])
    if operation == "hero-pool":
        _require_arguments(operation, arguments, 1)
        return await service.hero_pool_card(arguments[0])
    if operation == "equipment":
        _require_arguments(operation, arguments, 1)
        return await service.equipment_card(arguments[0])
    if operation == "leaderboard":
        _require_arguments(operation, arguments, 0)
        return await service.leaderboard_card(page=page)
    if operation == "character":
        _require_arguments(operation, arguments, 1)
        return await service.character_card(arguments[0], weapon=weapon, mode=mode, tier=tier)
    if operation == "item":
        _require_arguments(operation, arguments, 1)
        return await service.item_card(arguments[0])
    if operation == "routes":
        _require_arguments(operation, arguments, 1)
        return await service.routes_card(arguments[0], weapon=weapon)
    raise InvalidQuery(f"unsupported operation: {operation}")


async def _render_output(
    payload: CardPayload,
    *,
    format: OutputFormat,
    output: str | Path | None,
    config: ERBSConfig,
    renderer: CardRenderer | None,
) -> QueryOutput:
    if format == "json":
        if output is not None:
            raise InvalidQuery("output is only supported when format='path'")
        return TextRenderer().render(select_summary_art(payload))
    if format not in {"bytes", "path"}:
        raise InvalidQuery(f"unsupported output format: {format}")
    if format == "bytes" and output is not None:
        raise InvalidQuery("output is only supported when format='path'")
    if format == "path" and output is None:
        raise InvalidQuery("output is required when format='path'")

    owned_renderer = renderer is None
    active_renderer = renderer or SkiaCardRenderer(config)
    try:
        image = await active_renderer.render(select_summary_art(payload))
    finally:
        if owned_renderer:
            await active_renderer.close()

    if format == "bytes":
        return image

    destination = Path(output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            file.write(image)
            temporary = Path(file.name)
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


@overload
async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: Literal["json"] = "json",
    output: None = None,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: CardRenderer | None = None,
    count: int | None = None,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
    mode: str = "RANK",
    tier: str = "diamond_plus",
    server: str = "seoul",
) -> str: ...


@overload
async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: Literal["bytes"],
    output: None = None,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: CardRenderer | None = None,
    count: int | None = None,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
    mode: str = "RANK",
    tier: str = "diamond_plus",
    server: str = "seoul",
) -> bytes: ...


@overload
async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: Literal["path"],
    output: str | Path,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: CardRenderer | None = None,
    count: int | None = None,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
    mode: str = "RANK",
    tier: str = "diamond_plus",
    server: str = "seoul",
) -> Path: ...


async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: OutputFormat = "json",
    output: str | Path | None = None,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: CardRenderer | None = None,
    count: int | None = None,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
    mode: str = "RANK",
    tier: str = "diamond_plus",
    server: str = "seoul",
) -> QueryOutput:
    """Run one ERBS query and return JSON text, PNG bytes, or a PNG path."""

    if format not in {"json", "bytes", "path"}:
        raise InvalidQuery(f"unsupported output format: {format}")
    if format == "path" and output is None:
        raise InvalidQuery("output is required when format='path'")
    if format != "path" and output is not None:
        raise InvalidQuery("output is only supported when format='path'")

    normalized_operation = _normalize_operation(operation)
    if count is None:
        count = 20 if normalized_operation == "summary" else 5
    mode, tier, server = normalize_mode(mode), normalize_tier(tier), normalize_server(server)
    active_config = config or (client.config if client is not None else ERBSConfig())
    cache_ttl = active_config.query_cache_ttl(normalized_operation)
    query_database: QueryCacheDatabase | None = None
    cache_spec: dict[str, object] | None = None
    payload: CardPayload | None = None
    if cache_ttl > 0:
        query_database = QueryCacheDatabase(
            active_config.private_database_path,
            max_entries=active_config.query_cache_max_entries,
        )
        cache_spec = query_cache_spec(
            normalized_operation,
            arguments,
            api_base_url=active_config.api_base_url,
            language=active_config.language,
            count=count,
            page=page,
            season=season,
            weapon=weapon,
            mode=mode,
            tier=tier,
            server=server,
            web_base_url=active_config.web_base_url,
            ercraft_api_fallback=active_config.ercraft_api_fallback,
            ercraft_api_base_url=active_config.ercraft_api_base_url,
            summary_match_limit=active_config.summary_match_limit,
        )
        payload = await query_database.get(cache_spec)

    owned_client = client is None
    active_client = client
    try:
        if payload is None:
            active_client = active_client or AsyncERBSClient(active_config)
            payload = await _payload_for(
                ERBSService(active_client),
                normalized_operation,
                arguments,
                count=count,
                page=page,
                season=season,
                weapon=weapon,
                mode=mode,
                tier=tier,
                server=server,
            )
            payload = annotate_query_payload(payload)
            if query_database is not None and cache_spec is not None:
                await query_database.set(cache_spec, payload, ttl=cache_ttl)
        return await _render_output(
            payload,
            format=format,
            output=output,
            config=active_config,
            renderer=renderer,
        )
    finally:
        if owned_client and active_client is not None:
            await active_client.aclose()


async def player_overview(nickname: str, **options: object) -> QueryOutput:
    return await query("overview", nickname, **options)  # type: ignore[arg-type]


async def rank(nickname: str, **options: object) -> QueryOutput:
    return await query("rank", nickname, **options)  # type: ignore[arg-type]


async def stats(nickname: str, **options: object) -> QueryOutput:
    return await query("stats", nickname, **options)  # type: ignore[arg-type]


async def matches(nickname: str, **options: object) -> QueryOutput:
    return await query("matches", nickname, **options)  # type: ignore[arg-type]


async def recent(nickname: str, **options: object) -> QueryOutput:
    return await query("recent", nickname, **options)  # type: ignore[arg-type]


async def radar(nickname: str, **options: object) -> QueryOutput:
    options.setdefault("count", 20)
    return await query("radar", nickname, **options)  # type: ignore[arg-type]


async def player_summary(nickname: str, **options: object) -> QueryOutput:
    options.setdefault("count", 20)
    return await query("summary", nickname, **options)  # type: ignore[arg-type]


async def characters(nickname: str, **options: object) -> QueryOutput:
    return await query("characters", nickname, **options)  # type: ignore[arg-type]


async def skins(nickname: str, **options: object) -> QueryOutput:
    return await query("skins", nickname, **options)  # type: ignore[arg-type]


async def teammates(nickname: str, **options: object) -> QueryOutput:
    return await query("teammates", nickname, **options)  # type: ignore[arg-type]


async def multi(*nicknames: str, **options: object) -> QueryOutput:
    return await query("multi", *nicknames, **options)  # type: ignore[arg-type]


async def compare(left: str, right: str, **options: object) -> QueryOutput:
    return await query("compare", left, right, **options)  # type: ignore[arg-type]


async def best_match(nickname: str, **options: object) -> QueryOutput:
    return await query("best-match", nickname, **options)  # type: ignore[arg-type]


async def hero_pool(nickname: str, **options: object) -> QueryOutput:
    return await query("hero-pool", nickname, **options)  # type: ignore[arg-type]


async def equipment(nickname: str, **options: object) -> QueryOutput:
    return await query("equipment", nickname, **options)  # type: ignore[arg-type]


async def leaderboard(**options: object) -> QueryOutput:
    return await query("leaderboard", **options)  # type: ignore[arg-type]


async def character(query_text: str, **options: object) -> QueryOutput:
    return await query("character", query_text, **options)  # type: ignore[arg-type]


async def item(query_text: str, **options: object) -> QueryOutput:
    return await query("item", query_text, **options)  # type: ignore[arg-type]


async def routes(character_query: str, **options: object) -> QueryOutput:
    return await query("routes", character_query, **options)  # type: ignore[arg-type]


async def search(nickname: str, **options: object) -> QueryOutput:
    options.setdefault("count", 20)
    return await query("search", nickname, **options)  # type: ignore[arg-type]


async def character_stats(**options: object) -> QueryOutput:
    return await query("character-stats", **options)  # type: ignore[arg-type]


async def character_equipment(query_text: str, **options: object) -> QueryOutput:
    return await query("character-equipment", query_text, **options)  # type: ignore[arg-type]


async def tier_stats(**options: object) -> QueryOutput:
    return await query("tier-stats", **options)  # type: ignore[arg-type]


async def tier_cutoffs(**options: object) -> QueryOutput:
    return await query("tier-cutoffs", **options)  # type: ignore[arg-type]


async def execute_command(text: str, **options: object) -> QueryOutput:
    """Execute a slash command without coupling the library to a chat framework."""
    command = parse_command(text)
    filters = {"mode": command.mode, "tier": command.tier, "server": command.server}
    filters.update(options)
    if command.operation == "search":
        filters.setdefault("count", 20)
    return await query(command.operation, *command.arguments, **filters)  # type: ignore[arg-type]


__all__ = [
    "search",
    "character_stats",
    "character_equipment",
    "tier_stats",
    "tier_cutoffs",
    "execute_command",
    "OutputFormat",
    "QueryOperation",
    "QueryOutput",
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
    "player_summary",
    "query",
    "radar",
    "rank",
    "recent",
    "routes",
    "skins",
    "stats",
    "teammates",
]
