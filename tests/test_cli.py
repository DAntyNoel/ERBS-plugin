from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest

import erbs_plugin.cli as cli_module
from erbs_plugin import PlayerNotFound, RenderFailed, UpstreamUnavailable


@pytest.mark.parametrize(
    "arguments",
    [
        ["overview", "player"],
        ["rank", "player", "--season", "S1"],
        ["stats", "player"],
        ["matches", "player", "--count", "10"],
        ["recent", "player"],
        ["radar", "player", "--count", "30"],
        ["debug", "radar", "player", "--count", "30"],
        ["characters", "player"],
        ["teammates", "player"],
        ["best-match", "player"],
        ["hero-pool", "player"],
        ["equipment", "player"],
        ["leaderboard", "--page", "2"],
        ["character", "Black", "Mamba", "--weapon", "Pistol"],
        ["item", "Mithril", "Armor"],
        ["routes", "Black", "Mamba", "--weapon", "Pistol"],
        ["assets", "check", "--directory", "assets"],
    ],
)
def test_parser_accepts_every_command(arguments: list[str]) -> None:
    assert cli_module.parser().parse_args(arguments).operation == arguments[0]


@pytest.mark.parametrize(
    "arguments",
    [
        ["skins", "player"],
        ["multi", "one", "two"],
        ["compare", "one", "two"],
        ["debug", "skins", "player"],
        ["debug", "multi", "one", "two"],
        ["debug", "compare", "one", "two"],
    ],
)
def test_retired_commands_are_not_exposed(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli_module.parser().parse_args(arguments)


def test_render_commands_do_not_expose_asset_directory_option() -> None:
    with pytest.raises(SystemExit):
        cli_module.parser().parse_args(
            ["overview", "player", "--asset-directory", "assets"]
        )


def test_cli_json_output(monkeypatch, capsys) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def fake_query(*args: object, **kwargs: object) -> str:
        calls.append((args, kwargs))
        return '{"title": "player"}'

    monkeypatch.setattr(cli_module, "query", fake_query)
    args = cli_module.parser().parse_args(["matches", "player", "--count", "7"])

    assert asyncio.run(cli_module.run(args)) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"title": "player"}\n'
    assert captured.err == ""
    assert calls[0][0] == ("matches", "player")
    assert calls[0][1]["count"] == 7


def test_cli_writes_raw_png_bytes(monkeypatch, capfdbinary) -> None:
    image = b"\x89PNG\r\n\x1a\nimage"

    async def fake_query(*args: object, **kwargs: object) -> bytes:
        return image

    monkeypatch.setattr(cli_module, "query", fake_query)
    args = cli_module.parser().parse_args(["overview", "player", "--format", "bytes"])

    assert asyncio.run(cli_module.run(args)) == 0
    captured = capfdbinary.readouterr()
    assert captured.out == image
    assert captured.err == b""


def test_cli_path_output(monkeypatch, tmp_path: Path, capsys) -> None:
    destination = tmp_path / "card.png"

    async def fake_query(*args: object, **kwargs: object) -> Path:
        assert kwargs["output"] == destination
        return destination

    monkeypatch.setattr(cli_module, "query", fake_query)
    args = cli_module.parser().parse_args(
        ["overview", "player", "--format", "path", "--output", str(destination)]
    )

    assert asyncio.run(cli_module.run(args)) == 0
    assert capsys.readouterr().out == f"{destination}\n"


def test_cli_rejects_invalid_output_combination(capsys) -> None:
    args = cli_module.parser().parse_args(
        ["overview", "player", "--format", "path"]
    )

    assert asyncio.run(cli_module.run(args)) == cli_module.EXIT_USAGE
    assert "--output is required" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (PlayerNotFound("missing"), cli_module.EXIT_NOT_FOUND),
        (UpstreamUnavailable("offline"), cli_module.EXIT_UPSTREAM),
        (RenderFailed("browser"), cli_module.EXIT_RENDER),
    ],
)
def test_cli_maps_typed_errors(monkeypatch, capsys, error: Exception, expected_code: int) -> None:
    async def fake_query(*args: object, **kwargs: object):
        raise error

    monkeypatch.setattr(cli_module, "query", fake_query)
    args = cli_module.parser().parse_args(["overview", "player"])

    assert asyncio.run(cli_module.run(args)) == expected_code
    assert capsys.readouterr().err


def test_cli_assets_reuses_asset_runner(monkeypatch, tmp_path: Path) -> None:
    seen: list[argparse.Namespace] = []

    async def fake_run(args: argparse.Namespace) -> int:
        seen.append(args)
        return 9

    monkeypatch.setattr(cli_module.assets_cli, "run", fake_run)
    args = cli_module.parser().parse_args(
        ["assets", "check", "--directory", str(tmp_path)]
    )

    assert asyncio.run(cli_module.run(args)) == 9
    assert seen[0].command == "check"
    assert seen[0].directory == tmp_path


def test_cli_hides_unexpected_tracebacks(monkeypatch, capsys) -> None:
    async def fake_query(*args: object, **kwargs: object):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_module, "query", fake_query)
    args = cli_module.parser().parse_args(["overview", "player"])

    assert asyncio.run(cli_module.run(args)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "unexpected error: boom\n"
