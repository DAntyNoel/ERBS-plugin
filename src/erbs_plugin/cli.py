from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .api import query
from .assets import cli as assets_cli
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
    parser.add_argument("--browser-path", type=Path)


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


def _add_debug_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    debug = subparsers.add_parser("debug", help="render real command results for visual review")
    debug.add_argument("--output-directory", type=Path, default=Path(".debug/cards"))
    debug.add_argument("--browser-path", type=Path)
    debug.add_argument("--scale", type=float, default=1.0)
    debug.add_argument("--refresh-data", action="store_true")
    commands = debug.add_subparsers(dest="debug_command")
    cards = commands.add_parser(
        "cards", help="run and render all default live commands (compatibility alias)"
    )
    cards.add_argument("--output-directory", type=Path, default=Path(".debug/cards"))
    cards.add_argument("--browser-path", type=Path)
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
    radar = add_player_command("radar", "render a live eight-dimension player style radar")
    radar.add_argument("--count", type=int, default=20)
    add_player_command("characters", "render live player character statistics")
    add_player_command("teammates", "render live recent teammates")
    add_player_command("best-match", "render a live best recent match")
    add_player_command("hero-pool", "render a live player hero pool")
    add_player_command("equipment", "render live player equipment habits")

    leaderboard = commands.add_parser("leaderboard", help="render the live leaderboard")
    leaderboard.add_argument("--page", type=int, default=1)
    add_query_options(leaderboard)

    character = commands.add_parser("character", help="render live character statistics")
    character.add_argument("query", nargs="+")
    character.add_argument("--weapon")
    add_query_options(character)

    item = commands.add_parser("item", help="render live item details")
    item.add_argument("query", nargs="+")
    add_query_options(item)

    routes = commands.add_parser("routes", help="render live saved routes")
    routes.add_argument("query", nargs="+")
    routes.add_argument("--weapon")
    add_query_options(routes)


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
    radar = _add_player_command(subparsers, "radar", "eight-dimension player style radar")
    radar.add_argument("--count", type=int, default=20)
    _add_player_command(subparsers, "characters", "player character statistics")
    _add_player_command(subparsers, "teammates", "recent teammates")
    _add_player_command(subparsers, "best-match", "best recent match")
    _add_player_command(subparsers, "hero-pool", "player hero pool")
    _add_player_command(subparsers, "equipment", "player equipment habits")

    leaderboard = subparsers.add_parser("leaderboard", help="global leaderboard")
    leaderboard.add_argument("--page", type=int, default=1)
    _add_output_options(leaderboard)

    character = subparsers.add_parser("character", help="character statistics")
    character.add_argument("query", nargs="+")
    character.add_argument("--weapon")
    _add_output_options(character)

    item = subparsers.add_parser("item", help="item details")
    item.add_argument("query", nargs="+")
    _add_output_options(item)

    routes = subparsers.add_parser("routes", help="saved routes")
    routes.add_argument("query", nargs="+")
    routes.add_argument("--weapon")
    _add_output_options(routes)

    _add_assets_commands(subparsers)
    _add_debug_commands(subparsers)
    return result


def _config(args: argparse.Namespace) -> ERBSConfig:
    values: dict[str, object] = {
        "api_base_url": args.api_base_url,
        "language": args.language,
    }
    if args.browser_path is not None:
        values["browser_path"] = args.browser_path
    if getattr(args, "asset_directory", None) is not None:
        values["asset_directory"] = args.asset_directory
    if hasattr(args, "scale"):
        values["render_scale"] = args.scale
    return ERBSConfig(**values)


def _query_arguments(args: argparse.Namespace) -> tuple[str, ...]:
    if hasattr(args, "nickname"):
        return (args.nickname,)
    if args.operation in {"character", "item", "routes"}:
        return (" ".join(args.query),)
    return ()


def _debug_query_arguments(args: argparse.Namespace) -> tuple[str, ...]:
    if hasattr(args, "nickname"):
        return (args.nickname,)
    if args.debug_command in {"character", "item", "routes"}:
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
            if args.debug_command in {None, "cards"}:
                build = await render_card_previews(
                    args.output_directory,
                    refresh_data=args.refresh_data,
                    config=ERBSConfig(browser_path=args.browser_path, render_scale=args.scale),
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
