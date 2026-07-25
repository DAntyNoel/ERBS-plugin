from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from erbs_plugin import api as api_module
from erbs_plugin import cli as cli_module
from erbs_plugin.debug import (
    CARD_PREVIEWS,
    DEFAULT_DEBUG_PLAYERS,
    DEFAULT_DEBUG_QUERIES,
    DebugQuery,
    preview_operations,
    render_card_previews,
    render_query_preview,
)
from erbs_plugin.models import CardPayload

EXPECTED_OPERATIONS = (
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
)


class FakeRenderer:
    def __init__(self) -> None:
        self.rendered: list[CardPayload] = []
        self.close_calls = 0

    async def render(self, payload: CardPayload) -> bytes:
        self.rendered.append(payload)
        return b"\x89PNG\r\n\x1a\npreview"

    async def close(self) -> None:
        self.close_calls += 1


def test_card_previews_cover_every_query_command() -> None:
    assert preview_operations() == EXPECTED_OPERATIONS


def test_card_previews_use_default_debug_players() -> None:
    primary, secondary, tertiary = DEFAULT_DEBUG_PLAYERS
    queries = {query.operation: query for query in DEFAULT_DEBUG_QUERIES}

    assert queries["overview"].arguments == (primary,)
    assert queries["matches"].arguments == (primary,)
    assert queries["matches"].count == 5
    assert queries["multi"].arguments == (primary, secondary, tertiary)
    assert queries["compare"].arguments == (primary, secondary)
    assert queries["character"].arguments == ("艾玛",)
    assert queries["character"].weapon == "Arcana"
    assert queries["item"].arguments == ("烈阳",)
    assert queries["routes"].weapon == "Arcana"


def test_default_previews_only_use_downloaded_image_assets() -> None:
    image_urls = [
        item["imageUrl"]
        for preview in CARD_PREVIEWS
        for section in preview.payload.sections
        for item in section.get("items", [])
        if "imageUrl" in item
    ]

    assert image_urls
    assert all(image_url.startswith("asset://") for image_url in image_urls)
    assert not any(image_url.startswith("data:image/svg+xml") for image_url in image_urls)


def test_parser_accepts_card_debug_command() -> None:
    args = cli_module.parser().parse_args(["debug", "cards", "--scale", "1.25"])

    assert args.operation == "debug"
    assert args.debug_command == "cards"
    assert args.scale == 1.25


def test_parser_accepts_bare_debug_command() -> None:
    args = cli_module.parser().parse_args(["debug"])

    assert args.operation == "debug"
    assert args.debug_command is None
    assert args.output_directory == Path(".debug/cards")


def test_only_option_is_removed() -> None:
    with pytest.raises(SystemExit):
        cli_module.parser().parse_args(["debug", "cards", "--only", "overview"])


def test_parser_accepts_live_debug_command() -> None:
    args = cli_module.parser().parse_args(["debug", "overview", DEFAULT_DEBUG_PLAYERS[0]])

    assert args.operation == "debug"
    assert args.debug_command == "overview"
    assert args.nickname == DEFAULT_DEBUG_PLAYERS[0]
    assert args.output_directory == Path(".debug/cards")
    assert args.format == "json"


@pytest.mark.asyncio
async def test_render_card_previews_writes_gallery_and_manifest(tmp_path) -> None:
    renderer = FakeRenderer()
    payloads = {preview.operation: preview.payload for preview in CARD_PREVIEWS}
    queries: list[DebugQuery] = []

    async def fake_payload_provider(query: DebugQuery) -> CardPayload:
        queries.append(query)
        return payloads.get(query.operation) or CardPayload(
            kind="player",
            title=query.operation,
            subtitle="test payload",
        )

    build = await render_card_previews(
        tmp_path / "cards",
        renderer=renderer,
        payload_provider=fake_payload_provider,
    )

    assert [path.stem for path in build.images] == list(EXPECTED_OPERATIONS)
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in build.images)
    index = build.index.read_text(encoding="utf-8")
    assert "overview.png" in index
    assert "routes.png" in index
    manifest = json.loads(build.manifest.read_text(encoding="utf-8"))
    assert [item["operation"] for item in manifest] == list(EXPECTED_OPERATIONS)
    assert all(item["source"] == "live" for item in manifest)
    assert manifest[3]["description"].startswith("erbs matches B站丨咕咕禽OC --count 5")
    assert build.gallery_count == len(EXPECTED_OPERATIONS)
    assert queries == list(DEFAULT_DEBUG_QUERIES)
    assert len(renderer.rendered) == len(EXPECTED_OPERATIONS)
    assert renderer.close_calls == 0


@pytest.mark.asyncio
async def test_live_query_returns_original_result_and_survives_full_refresh(
    monkeypatch, tmp_path
) -> None:
    payload = CardPayload(kind="player", title="自定义玩家", subtitle="玩家综合资料")

    async def fake_payload(service: object, operation: str, arguments: tuple[str, ...], **options):
        assert operation == "overview"
        assert arguments == ("自定义玩家",)
        return payload

    async def fake_output(card: CardPayload, **options: object) -> str:
        assert card is payload
        assert options["format"] == "json"
        return '{"title":"自定义玩家"}'

    payloads = {preview.operation: preview.payload for preview in CARD_PREVIEWS}

    async def fake_gallery_payload(query: DebugQuery) -> CardPayload:
        return payloads.get(query.operation) or CardPayload(
            kind="player",
            title=query.operation,
            subtitle="test payload",
        )

    monkeypatch.setattr(api_module, "_payload_for", fake_payload)
    monkeypatch.setattr(api_module, "_render_output", fake_output)
    build = await render_query_preview(
        "overview",
        "自定义玩家",
        output_directory=tmp_path / "cards",
        renderer=FakeRenderer(),
        gallery_payload_provider=fake_gallery_payload,
    )

    assert build.primary_image is not None
    assert build.primary_image.name.startswith("custom-overview-")
    assert build.result == '{"title":"自定义玩家"}'
    manifest = json.loads(build.manifest.read_text(encoding="utf-8"))
    assert len(manifest) == len(EXPECTED_OPERATIONS) + 1
    assert build.gallery_count == len(EXPECTED_OPERATIONS) + 1
    assert manifest[-1]["source"] == "query"
    assert manifest[-1]["description"] == "erbs debug overview 自定义玩家"

    refreshed = await render_card_previews(
        tmp_path / "cards",
        renderer=FakeRenderer(),
        payload_provider=fake_gallery_payload,
    )
    refreshed_manifest = json.loads(refreshed.manifest.read_text(encoding="utf-8"))
    assert refreshed_manifest[-1]["source"] == "query"
    assert build.primary_image.name in refreshed.index.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_cli_runs_live_debug_query(monkeypatch, capsys, tmp_path) -> None:
    calls: list[tuple[str, tuple[str, ...], dict[str, object]]] = []
    image = tmp_path / "custom.png"
    index = tmp_path / "index.html"

    async def fake_render(operation: str, *arguments: str, **options: object) -> object:
        calls.append((operation, arguments, options))
        return SimpleNamespace(
            primary_image=image,
            index=index,
            gallery_count=18,
            result='{"title":"自定义玩家"}',
        )

    monkeypatch.setattr(cli_module, "render_query_preview", fake_render)
    args = cli_module.parser().parse_args(["debug", "overview", "自定义玩家"])

    assert await cli_module.run(args) == 0
    assert calls[0][0:2] == ("overview", ("自定义玩家",))
    captured = capsys.readouterr()
    assert captured.out == '{"title":"自定义玩家"}\n'
    assert "debug preview saved" in captured.err


@pytest.mark.asyncio
async def test_cli_live_debug_bytes_are_not_polluted(monkeypatch, capfdbinary, tmp_path) -> None:
    image = b"\x89PNG\r\n\x1a\ndebug-image"

    async def fake_render(operation: str, *arguments: str, **options: object) -> object:
        return SimpleNamespace(
            primary_image=tmp_path / "custom.png",
            index=tmp_path / "index.html",
            gallery_count=18,
            result=image,
        )

    monkeypatch.setattr(cli_module, "render_query_preview", fake_render)
    args = cli_module.parser().parse_args(
        ["debug", "overview", "自定义玩家", "--format", "bytes"]
    )

    assert await cli_module.run(args) == 0
    captured = capfdbinary.readouterr()
    assert captured.out == image
    assert b"debug preview saved" in captured.err


@pytest.mark.asyncio
async def test_cli_bare_debug_renders_every_default(monkeypatch, capsys, tmp_path) -> None:
    index = tmp_path / "index.html"

    async def fake_render(*args: object, **options: object) -> object:
        return SimpleNamespace(images=tuple(range(17)), gallery_count=17, index=index)

    monkeypatch.setattr(cli_module, "render_card_previews", fake_render)

    assert await cli_module.run(cli_module.parser().parse_args(["debug"])) == 0
    assert "refreshed 17 card previews" in capsys.readouterr().out
