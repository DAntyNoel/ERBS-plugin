from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .api import execute_command, query
from .assets import cli as assets_cli
from .commands import normalize_operation
from .config import ERBSConfig
from .debug import render_card_previews, render_query_preview
from .exceptions import (
    AssetMissing,
    ERBSError,
    InvalidQuery,
    PlayerNotFound,
    RateLimited,
    RenderFailed,
    UpstreamUnavailable,
)

EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_UPSTREAM = 4
EXIT_RENDER = 5


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "bytes", "path"), default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--api-base-url", default="https://er.dakgg.io")
    parser.add_argument("--language", default="zh-CN")
    parser.add_argument("--font-path", type=Path)
    parser.add_argument("--web-base-url", default="https://dak.gg/er")


def _add_player_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
) -> argparse.ArgumentParser:
    command = subparsers.add_parser(name, help=help_text)
    command.add_argument("nickname")
    _add_output_options(command)
    return command


def _add_assets_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    assets = subparsers.add_parser("assets", help="download and validate local image assets")
    commands = assets.add_subparsers(dest="assets_command", required=True)
    for name in ("download", "check", "update", "prune"):
        command = commands.add_parser(name)
        command.add_argument("--directory", type=Path, required=True)
        command.add_argument("--concurrency", type=int, default=4)
        command.add_argument("--force", action="store_true")


def _add_dak_commands(subparsers, output_options) -> None:
    for name, aliases, description in (
        ("search", ["查询玩家", "查玩家"], "player profile and recent matches"),
        ("character-equipment", ["查询角色装备"], "character equipment builds"),
        ("character-stats", ["角色数据", "角色数据统计"], "all character and weapon statistics"),
        ("tier-stats", ["段位统计"], "tier population and cutoffs"),
        ("tier-cutoffs", ["永恒多少分"], "Eternity and Demigod RP cutoffs"),
        ("help", ["帮助"], "query command help"),
    ):
        command = subparsers.add_parser(name, aliases=aliases, help=description)
        if name == "search":
            command.add_argument("nickname")
            command.add_argument("--count", type=int, default=20)
            command.add_argument("--season")
        if name == "character-equipment":
            command.add_argument("query", nargs="+")
            command.add_argument("--weapon")
        if name in {"search", "character-equipment", "character-stats"}:
            command.add_argument("--mode", default="RANK")
        if name in {"character-equipment", "character-stats"}:
            command.add_argument("--tier", default="diamond_plus")
        if name in {"tier-stats", "tier-cutoffs"}:
            command.add_argument("--server", default="seoul")
        output_options(command)


def _add_debug_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    debug = subparsers.add_parser("debug", help="render real command results for visual review")
    debug.add_argument("--output-directory", type=Path, default=Path(".debug/cards"))
    debug.add_argument("--font-path", type=Path)
    debug.add_argument("--scale", type=float, default=1.0)
    debug.add_argument("--refresh-data", action="store_true")
    commands = debug.add_subparsers(dest="debug_command")
    cards = commands.add_parser(
        "cards", help="run and render all default live commands (compatibility alias)"
    )
    cards.add_argument("--output-directory", type=Path, default=Path(".debug/cards"))
    cards.add_argument("--font-path", type=Path)
    cards.add_argument("--scale", type=float, default=1.0)
    cards.add_argument("--refresh-data", action="store_true")

    def add_query_options(command: argparse.ArgumentParser) -> None:
        _add_output_options(command)
        command.add_argument("--output-directory", type=Path, default=Path(".debug/cards"))
        command.add_argument("--asset-directory", type=Path)
        command.add_argument("--scale", type=float, default=1.0)
        command.add_argument("--refresh-data", action="store_true")

    def add_player_command(name: str, help_text: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("nickname")
        add_query_options(command)
        return command

    add_player_command("overview", "render a live player overview")
    rank = add_player_command("rank", "render live player rank")
    rank.add_argument("--season")
    stats = add_player_command("stats", "render live player statistics")
    stats.add_argument("--season")
    matches = add_player_command("matches", "render live recent matches")
    matches.add_argument("--count", type=int, default=5)
    add_player_command("recent", "render a live recent performance summary")
    radar = add_player_command("radar", "render a live six-axis player performance radar")
    radar.add_argument("--count", type=int, default=20)
    add_player_command("characters", "render live player character statistics")
    add_player_command("teammates", "render live recent teammates")
    add_player_command("best-match", "render a live best recent match")
    add_player_command("hero-pool", "render a live player hero pool")
    add_player_command("equipment", "render live player equipment habits")

    leaderboard = commands.add_parser("leaderboard", help="render the live leaderboard")
    leaderboard.add_argument("--page", type=int, default=1)
    add_query_options(leaderboard)

    character = commands.add_parser(
        "character", aliases=["查询角色"], help="render character analysis"
    )
    character.add_argument("query", nargs="+")
    character.add_argument("--weapon")
    character.add_argument("--mode", default="RANK")
    character.add_argument("--tier", default="diamond_plus")
    add_query_options(character)

    item = commands.add_parser("item", aliases=["查询装备"], help="render live item details")
    item.add_argument("query", nargs="+")
    add_query_options(item)

    routes = commands.add_parser("routes", help="render live saved routes")
    routes.add_argument("query", nargs="+")
    routes.add_argument("--weapon")
    add_query_options(routes)
    _add_dak_commands(commands, add_query_options)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="erbs",
        description="Framework-neutral Eternal Return queries and card rendering.",
    )
    subparsers = result.add_subparsers(dest="operation", required=True)

    _add_player_command(subparsers, "overview", "player overview")
    rank = _add_player_command(subparsers, "rank", "player rank")
    rank.add_argument("--season")
    stats = _add_player_command(subparsers, "stats", "player statistics")
    stats.add_argument("--season")
    matches = _add_player_command(subparsers, "matches", "recent matches")
    matches.add_argument("--count", type=int, default=5)
    _add_player_command(subparsers, "recent", "recent performance summary")
    radar = _add_player_command(subparsers, "radar", "six-axis player performance radar")
    radar.add_argument("--count", type=int, default=20)
    summary = _add_player_command(subparsers, "summary", "illustrated local performance summary")
    summary.add_argument(
        "--count", type=int, default=20,
        help="compatibility option (1-60); all season ranked games are always used, filled to 20",
    )
    summary.add_argument("--season")
    summary.add_argument("--max-matches", type=int, help="season ranked sample cap (default: 500)")
    summary.add_argument("--art", type=Path, help="local 1024x1536 raster background image")
    summary.add_argument("--card-title", help="display title; does not affect scores")
    _add_player_command(subparsers, "characters", "player character statistics")
    _add_player_command(subparsers, "teammates", "recent teammates")
    _add_player_command(subparsers, "best-match", "best recent match")
    _add_player_command(subparsers, "hero-pool", "player hero pool")
    _add_player_command(subparsers, "equipment", "player equipment habits")

    leaderboard = subparsers.add_parser("leaderboard", help="global leaderboard")
    leaderboard.add_argument("--page", type=int, default=1)
    _add_output_options(leaderboard)

    character = subparsers.add_parser("character", aliases=["查询角色"], help="character analysis")
    character.add_argument("query", nargs="+")
    character.add_argument("--weapon")
    character.add_argument("--mode", default="RANK")
    character.add_argument("--tier", default="diamond_plus")
    _add_output_options(character)

    item = subparsers.add_parser("item", aliases=["查询装备"], help="item details")
    item.add_argument("query", nargs="+")
    _add_output_options(item)

    routes = subparsers.add_parser("routes", help="saved routes")
    routes.add_argument("query", nargs="+")
    routes.add_argument("--weapon")
    _add_output_options(routes)
    _add_dak_commands(subparsers, _add_output_options)
    command = subparsers.add_parser("command", help="execute a slash command")
    command.add_argument("text")
    _add_output_options(command)

    _add_assets_commands(subparsers)
    _add_debug_commands(subparsers)
    return result


def _config(args: argparse.Namespace) -> ERBSConfig:
    values: dict[str, object] = {
        "api_base_url": args.api_base_url,
        "language": args.language,
    }
    if args.font_path is not None:
        values["render_font_path"] = args.font_path
    if getattr(args, "art", None) is not None:
        values["summary_art_path"] = args.art
    if getattr(args, "card_title", None) is not None:
        values["summary_title"] = args.card_title
    if getattr(args, "max_matches", None) is not None:
        if args.max_matches < 20:
            raise InvalidQuery("--max-matches must be at least 20")
        values["summary_match_limit"] = args.max_matches
    values["web_base_url"] = args.web_base_url
    if getattr(args, "asset_directory", None) is not None:
        values["asset_directory"] = args.asset_directory
    if hasattr(args, "scale"):
        values["render_scale"] = args.scale
    return ERBSConfig(**values)


def _query_arguments(args: argparse.Namespace) -> tuple[str, ...]:
    if hasattr(args, "nickname"):
        return (args.nickname,)
    if args.operation in {"character", "character-equipment", "item", "routes"}:
        return (" ".join(args.query),)
    return ()


def _debug_query_arguments(args: argparse.Namespace) -> tuple[str, ...]:
    if hasattr(args, "nickname"):
        return (args.nickname,)
    if args.debug_command in {"character", "character-equipment", "item", "routes"}:
        return (" ".join(args.query),)
    return ()


def _emit_result(result: str | bytes | Path) -> None:
    if isinstance(result, bytes):
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    else:
        print(result)


async def run(args: argparse.Namespace) -> int:
    try:
        if args.operation == "assets":
            asset_args = argparse.Namespace(
                command=args.assets_command,
                directory=args.directory,
                concurrency=args.concurrency,
                force=args.force,
            )
            return await assets_cli.run(asset_args)

        if args.operation == "debug":
            if args.debug_command:
                args.debug_command = normalize_operation(args.debug_command)
            if args.debug_command in {None, "cards"}:
                build = await render_card_previews(
                    args.output_directory,
                    refresh_data=args.refresh_data,
                    config=ERBSConfig(render_font_path=args.font_path, render_scale=args.scale),
                )
                print(
                    f"refreshed {len(build.images)} card previews; "
                    f"gallery contains {build.gallery_count} results: {build.index}"
                )
                return 0
            if args.format == "path" and args.output is None:
                raise InvalidQuery("--output is required when --format path is used")
            if args.format != "path" and args.output is not None:
                raise InvalidQuery("--output is only valid with --format path")
            if getattr(args, "page", 1) < 1:
                raise InvalidQuery("--page must be greater than zero")
            build = await render_query_preview(
                args.debug_command,
                *_debug_query_arguments(args),
                output_directory=args.output_directory,
                refresh_data=args.refresh_data,
                config=_config(args),
                format=args.format,
                output=args.output,
                count=getattr(args, "count", 5),
                page=getattr(args, "page", 1),
                season=getattr(args, "season", None),
                weapon=getattr(args, "weapon", None),
                mode=getattr(args, "mode", "RANK"),
                tier=getattr(args, "tier", "diamond_plus"),
                server=getattr(args, "server", "seoul"),
            )
            if build.result is None:
                raise RuntimeError("debug query did not return a result")
            _emit_result(build.result)
            print(
                f"debug preview saved: {build.primary_image}; "
                f"gallery contains {build.gallery_count} results: {build.index}",
                file=sys.stderr,
            )
            return 0

        if args.format == "path" and args.output is None:
            raise InvalidQuery("--output is required when --format path is used")
        if args.format != "path" and args.output is not None:
            raise InvalidQuery("--output is only valid with --format path")
        if getattr(args, "page", 1) < 1:
            raise InvalidQuery("--page must be greater than zero")

        args.operation = normalize_operation(args.operation)
        if args.operation == "command":
            result = await execute_command(
                args.text, format=args.format, output=args.output, config=_config(args)
            )
            _emit_result(result)
            return 0
        result = await query(
            args.operation,
            *_query_arguments(args),
            format=args.format,
            output=args.output,
            config=_config(args),
            count=getattr(args, "count", 5),
            page=getattr(args, "page", 1),
            season=getattr(args, "season", None),
            weapon=getattr(args, "weapon", None),
            mode=getattr(args, "mode", "RANK"),
            tier=getattr(args, "tier", "diamond_plus"),
            server=getattr(args, "server", "seoul"),
        )
    except (InvalidQuery, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except PlayerNotFound as exc:
        print(f"player not found: {exc}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except (RateLimited, UpstreamUnavailable) as exc:
        print(f"upstream error: {exc}", file=sys.stderr)
        return EXIT_UPSTREAM
    except (AssetMissing, RenderFailed) as exc:
        print(f"render error: {exc}", file=sys.stderr)
        return EXIT_RENDER
    except ERBSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 1

    _emit_result(result)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run(parser().parse_args())))


__all__ = ["main", "parser", "run"]
