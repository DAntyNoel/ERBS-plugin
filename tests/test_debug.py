from __future__ import annotations

import json

import pytest

from erbs_plugin import cli as cli_module
from erbs_plugin.debug import preview_operations, render_card_previews
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


def test_parser_accepts_card_debug_command() -> None:
    args = cli_module.parser().parse_args(
        ["debug", "cards", "--only", "overview", "compare", "--scale", "1.25"]
    )

    assert args.operation == "debug"
    assert args.debug_command == "cards"
    assert args.only == ["overview", "compare"]
    assert args.scale == 1.25


@pytest.mark.asyncio
async def test_render_card_previews_writes_gallery_and_manifest(tmp_path) -> None:
    renderer = FakeRenderer()

    build = await render_card_previews(
        tmp_path / "cards",
        operations=["overview", "compare"],
        renderer=renderer,
    )

    assert [path.name for path in build.images] == ["overview.png", "compare.png"]
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in build.images)
    assert "overview.png" in build.index.read_text(encoding="utf-8")
    manifest = json.loads(build.manifest.read_text(encoding="utf-8"))
    assert [item["operation"] for item in manifest] == ["overview", "compare"]
    assert [payload.subtitle for payload in renderer.rendered] == ["玩家综合资料", "玩家对比"]
    assert renderer.close_calls == 0


@pytest.mark.asyncio
async def test_render_card_previews_rejects_unknown_operation(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown preview operation"):
        await render_card_previews(tmp_path, operations=["missing"], renderer=FakeRenderer())
