from __future__ import annotations

import json
from copy import deepcopy

import pytest

from erbs_plugin.assets import AssetManager
from erbs_plugin.cache import QueryCacheDatabase, query_cache_spec
from erbs_plugin.config import ERBSConfig
from erbs_plugin.debug import DebugQuery, render_query_preview
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import SkiaCardRenderer


@pytest.mark.asyncio
async def test_summary_debug_json_preview_and_manifest_share_one_draw_on_cache_hit(
    monkeypatch, tmp_path,
) -> None:
    config = ERBSConfig(
        asset_directory=tmp_path / "assets",
        private_database_path=tmp_path / "queries.sqlite3",
        summary_match_limit=100,
    )
    source = CardPayload(kind="summary", title="player", sections=({
        "type": "player-summary",
        "artCandidates": [{
            "characterId": 67, "characterName": "艾比盖尔", "weight": 213,
            "skins": [
                {"skinId": 1067000, "skinName": "默认", "weight": 1,
                 "characterImageUrl": "https://cdn.dak.gg/base.png"},
                {"skinId": 1067003, "skinName": "英雄", "weight": 10,
                 "characterImageUrl": "https://cdn.dak.gg/epic.png"},
            ],
        }],
    },))
    snapshot = deepcopy(source)
    service_calls = 0
    closed_clients = 0
    choices_calls: list[list[int]] = []
    rendered_skins: list[int] = []
    next_skin = iter((0, 1))

    class FakeClient:
        def __init__(self, active_config: ERBSConfig) -> None:
            assert active_config is config

        async def aclose(self) -> None:
            nonlocal closed_clients
            closed_clients += 1

    class FakeService:
        def __init__(self, client: FakeClient) -> None:
            assert isinstance(client, FakeClient)

        async def player_summary(self, nickname: str, *, count: int, season: str | None):
            nonlocal service_calls
            service_calls += 1
            assert nickname == "player" and count == 20 and season is None
            return source

    async def gallery_payload(query: DebugQuery) -> CardPayload:
        return CardPayload(kind="player", title=query.operation)

    async def prepare_assets(value, active_config):
        assert active_config is config
        for section in value["sections"]:
            assert "artCandidates" not in section
        return AssetManager(config.asset_directory)

    def choices(population, *, weights, k):
        assert k == 1
        choices_calls.append(weights)
        if "skins" in population[0]:
            return [population[0]]
        return [population[next(next_skin)]]

    def render_png(card: CardPayload) -> bytes:
        if card.kind == "summary":
            section = card.sections[0]
            assert "artCandidates" not in section
            rendered_skins.append(section["skinId"])
            return b"\x89PNG\r\n\x1a\n" + str(section["skinId"]).encode()
        return b"\x89PNG\r\n\x1a\ngallery"

    monkeypatch.setattr("erbs_plugin.client.AsyncERBSClient", FakeClient)
    monkeypatch.setattr("erbs_plugin.services.ERBSService", FakeService)
    monkeypatch.setattr("erbs_plugin.summary_art.random.choices", choices)
    monkeypatch.setattr("erbs_plugin.rendering.skia.prepare_assets", prepare_assets)
    async with SkiaCardRenderer(config) as renderer:
        monkeypatch.setattr(renderer, "_render", render_png)
        for index, skin_id in enumerate((1067000, 1067003)):
            build = await render_query_preview(
                "summary", "player", count=20, format="json",
                output_directory=tmp_path / "cards", config=config, renderer=renderer,
                gallery_payload_provider=gallery_payload,
            )
            result = json.loads(build.result)
            manifest = json.loads(build.manifest.read_text(encoding="utf-8"))
            record = next(row for row in manifest if row["source"] == "query")
            assert result["sections"][0]["skinId"] == skin_id
            assert result["footer"]["cached"] is bool(index)
            assert record["payload"] == result
            assert build.primary_image.read_bytes() == (
                b"\x89PNG\r\n\x1a\n" + str(skin_id).encode()
            )
            assert choices_calls == [[213], [1, 10]] * (index + 1)
            assert rendered_skins == [1067000, 1067003][:index + 1]

    assert service_calls == 1 and closed_clients == 1
    assert source == snapshot
    spec = query_cache_spec(
        "summary", ("player",), api_base_url=config.api_base_url,
        language=config.language, count=20, page=1, season=None, weapon=None,
        summary_match_limit=100,
    )
    cached = await QueryCacheDatabase(config.private_database_path).get(spec)
    assert cached is not None
    assert cached.sections[0] == source.sections[0]
