from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal, overload

from .client import AsyncERBSClient
from .config import ERBSConfig
from .exceptions import InvalidQuery
from .models import CardPayload
from .rendering import HtmlCardRenderer, TextRenderer
from .services import ERBSService

type OutputFormat = Literal["json", "bytes", "path"]
type QueryOutput = str | bytes | Path
type QueryOperation = Literal[
    "overview",
    "rank",
    "stats",
    "matches",
    "recent",
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
]

_OPERATION_ALIASES = {
    "player": "overview",
    "player-overview": "overview",
    "best_match": "best-match",
    "hero_pool": "hero-pool",
}


def _normalize_operation(operation: str) -> str:
    normalized = operation.strip().casefold().replace("_", "-")
    return _OPERATION_ALIASES.get(normalized, normalized)


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
) -> CardPayload:
    operation = _normalize_operation(operation)
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
        return await service.character_card(arguments[0], weapon=weapon)
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
    renderer: HtmlCardRenderer | None,
) -> QueryOutput:
    if format == "json":
        if output is not None:
            raise InvalidQuery("output is only supported when format='path'")
        return TextRenderer().render(payload)
    if format not in {"bytes", "path"}:
        raise InvalidQuery(f"unsupported output format: {format}")
    if format == "bytes" and output is not None:
        raise InvalidQuery("output is only supported when format='path'")
    if format == "path" and output is None:
        raise InvalidQuery("output is required when format='path'")

    owned_renderer = renderer is None
    active_renderer = renderer or HtmlCardRenderer(config)
    try:
        image = await active_renderer.render(payload)
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
    renderer: HtmlCardRenderer | None = None,
    count: int = 5,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
) -> str: ...


@overload
async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: Literal["bytes"],
    output: None = None,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: HtmlCardRenderer | None = None,
    count: int = 5,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
) -> bytes: ...


@overload
async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: Literal["path"],
    output: str | Path,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: HtmlCardRenderer | None = None,
    count: int = 5,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
) -> Path: ...


async def query(
    operation: QueryOperation | str,
    *arguments: str,
    format: OutputFormat = "json",
    output: str | Path | None = None,
    config: ERBSConfig | None = None,
    client: AsyncERBSClient | None = None,
    renderer: HtmlCardRenderer | None = None,
    count: int = 5,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
) -> QueryOutput:
    """Run one ERBS query and return JSON text, PNG bytes, or a PNG path."""

    if format not in {"json", "bytes", "path"}:
        raise InvalidQuery(f"unsupported output format: {format}")
    if format == "path" and output is None:
        raise InvalidQuery("output is required when format='path'")
    if format != "path" and output is not None:
        raise InvalidQuery("output is only supported when format='path'")

    active_config = config or (client.config if client is not None else ERBSConfig())
    owned_client = client is None
    active_client = client or AsyncERBSClient(active_config)
    try:
        payload = await _payload_for(
            ERBSService(active_client),
            operation,
            arguments,
            count=count,
            page=page,
            season=season,
            weapon=weapon,
        )
        return await _render_output(
            payload,
            format=format,
            output=output,
            config=active_config,
            renderer=renderer,
        )
    finally:
        if owned_client:
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


__all__ = [
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
    "query",
    "rank",
    "recent",
    "routes",
    "skins",
    "stats",
    "teammates",
]
