from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import erbs_plugin.api as api_module
from erbs_plugin import ERBSConfig, InvalidQuery, PlayerNotFound
from erbs_plugin.models import CardPayload


class FakeClient:
    def __init__(self) -> None:
        self.config = ERBSConfig()
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


class FakeRenderer:
    def __init__(self, image: bytes = b"\x89PNG\r\n\x1a\nimage") -> None:
        self.image = image
        self.rendered: list[CardPayload] = []
        self.close_calls = 0

    async def render(self, payload: CardPayload) -> bytes:
        self.rendered.append(payload)
        return self.image

    async def close(self) -> None:
        self.close_calls += 1


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        async def method(*args: Any, **kwargs: Any) -> CardPayload:
            self.calls.append((name, args, kwargs))
            return CardPayload(kind="test", title=name)

        return method


@pytest.mark.parametrize(
    ("operation", "arguments", "options", "expected"),
    [
        ("overview", ("player",), {}, ("player_overview", ("player",), {})),
        ("rank", ("player",), {"season": "S1"}, ("rank_card", ("player",), {"season": "S1"})),
        ("stats", ("player",), {}, ("stats_card", ("player",), {"season": None})),
        ("matches", ("player",), {"count": 7}, ("matches_card", ("player",), {"count": 7})),
        ("recent", ("player",), {}, ("recent_card", ("player",), {})),
        ("characters", ("player",), {}, ("characters_card", ("player",), {})),
        ("skins", ("player",), {}, ("skins_card", ("player",), {})),
        ("teammates", ("player",), {}, ("teammates_card", ("player",), {})),
        ("multi", ("one", "two"), {}, ("multi_card", (["one", "two"],), {})),
        ("compare", ("one", "two"), {}, ("compare_card", ("one", "two"), {})),
        ("best-match", ("player",), {}, ("best_match_card", ("player",), {})),
        ("hero-pool", ("player",), {}, ("hero_pool_card", ("player",), {})),
        ("equipment", ("player",), {}, ("equipment_card", ("player",), {})),
        ("leaderboard", (), {"page": 3}, ("leaderboard_card", (), {"page": 3})),
        (
            "character",
            ("Abigail",),
            {"weapon": "Axe"},
            ("character_card", ("Abigail",), {"weapon": "Axe"}),
        ),
        ("item", ("Mithril Armor",), {}, ("item_card", ("Mithril Armor",), {})),
        (
            "routes",
            ("Abigail",),
            {"weapon": "Axe"},
            ("routes_card", ("Abigail",), {"weapon": "Axe"}),
        ),
    ],
)
def test_query_dispatches_every_operation(
    monkeypatch,
    operation: str,
    arguments: tuple[str, ...],
    options: dict[str, Any],
    expected: tuple[str, tuple[Any, ...], dict[str, Any]],
) -> None:
    service = FakeService()
    client = FakeClient()
    monkeypatch.setattr(api_module, "ERBSService", lambda _: service)

    result = asyncio.run(api_module.query(operation, *arguments, client=client, **options))

    assert json.loads(result)["title"] == expected[0]
    assert service.calls == [expected]
    assert client.close_calls == 0


def test_query_owns_client_and_renderer_when_not_supplied(monkeypatch) -> None:
    client = FakeClient()
    renderer = FakeRenderer()
    service = FakeService()
    monkeypatch.setattr(api_module, "AsyncERBSClient", lambda _: client)
    monkeypatch.setattr(api_module, "HtmlCardRenderer", lambda _: renderer)
    monkeypatch.setattr(api_module, "ERBSService", lambda _: service)

    result = asyncio.run(api_module.query("overview", "player", format="bytes"))

    assert result == renderer.image
    assert client.close_calls == 1
    assert renderer.close_calls == 1


def test_query_does_not_close_caller_resources(monkeypatch) -> None:
    client = FakeClient()
    renderer = FakeRenderer()
    service = FakeService()
    monkeypatch.setattr(api_module, "ERBSService", lambda _: service)

    result = asyncio.run(
        api_module.query(
            "overview",
            "player",
            format="bytes",
            client=client,
            renderer=renderer,
        )
    )

    assert result == renderer.image
    assert client.close_calls == 0
    assert renderer.close_calls == 0


def test_path_output_is_written_and_returned(monkeypatch, tmp_path: Path) -> None:
    client = FakeClient()
    renderer = FakeRenderer()
    service = FakeService()
    destination = tmp_path / "nested" / "card.png"
    monkeypatch.setattr(api_module, "ERBSService", lambda _: service)

    result = asyncio.run(
        api_module.query(
            "overview",
            "player",
            format="path",
            output=destination,
            client=client,
            renderer=renderer,
        )
    )

    assert result == destination
    assert destination.read_bytes() == renderer.image
    assert list(destination.parent.glob("*.tmp")) == []


def test_path_output_requires_destination() -> None:
    with pytest.raises(InvalidQuery, match="output is required"):
        asyncio.run(api_module.query("overview", "player", format="path"))


def test_invalid_format_fails_before_client_creation(monkeypatch) -> None:
    created = False

    def client_factory(config: ERBSConfig):
        nonlocal created
        created = True
        return FakeClient()

    monkeypatch.setattr(api_module, "AsyncERBSClient", client_factory)

    with pytest.raises(InvalidQuery, match="unsupported output format"):
        asyncio.run(api_module.query("overview", "player", format="invalid"))
    assert created is False


def test_typed_exceptions_are_not_converted(monkeypatch) -> None:
    class MissingPlayerService:
        async def player_overview(self, nickname: str) -> CardPayload:
            raise PlayerNotFound(nickname)

    client = FakeClient()
    monkeypatch.setattr(api_module, "ERBSService", lambda _: MissingPlayerService())

    with pytest.raises(PlayerNotFound, match="missing"):
        asyncio.run(api_module.query("overview", "missing", client=client))
    assert client.close_calls == 0


def test_named_function_uses_unified_query(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    async def fake_query(*args: object, **kwargs: object) -> str:
        calls.append((*args, kwargs))
        return "result"

    monkeypatch.setattr(api_module, "query", fake_query)

    result = asyncio.run(api_module.player_overview("player", format="json"))

    assert result == "result"
    assert calls == [("overview", "player", {"format": "json"})]
