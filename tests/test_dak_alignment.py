from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService
from erbs_plugin.models import PlayerProfile

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "bilibili_gugugin_oc.json").read_text(
        encoding="utf-8"
    )
)


def test_ranked_squad_profile_matches_dak_page() -> None:
    profile = PlayerProfile.from_api(FIXTURE["profile"])

    assert profile.nickname == "B站丨咕咕禽OC"
    assert profile.account_level == 307
    assert profile.mmr == 8906
    assert profile.tier_mmr == 606
    assert profile.overview["play"] == 339
    assert profile.overview["matchingModeId"] == 3
    assert profile.characters[0]["key"] == 31
    assert profile.characters[0]["play"] == 156


@pytest.mark.asyncio
async def test_latest_match_and_equipment_names_match_dak_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/matches"):
            return httpx.Response(200, json={"matches": FIXTURE["matches"]})
        if path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": FIXTURE["characters"]})
        if path.endswith("/data/items"):
            return httpx.Response(200, json={"items": FIXTURE["items"]})
        raise AssertionError(path)

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).matches_card("B站丨咕咕禽OC", count=1)
    finally:
        await client.aclose()

    item = card.sections[0]["items"][0]
    assert item["name"] == "#1 · 夏洛特"
    assert item["teamKills"] == 28
    assert item["kills"] == 3
    assert item["assists"] == 20
    assert item["deaths"] == 4
    assert item["damage"] == 8410
    assert item["mmrAfter"] == 9096
    assert item["mmrGain"] == 190
    assert item["routeId"] == "Private"
    assert item["equipment"] == "烈阳 · 精灵舞裙 · 白夜王冠 · 克拉达戒指 · 风火轮"
    assert [equipment["name"] for equipment in item["equipmentItems"]] == [
        "烈阳",
        "精灵舞裙",
        "白夜王冠",
        "克拉达戒指",
        "风火轮",
    ]
    assert len(item["equipmentItems"]) == 5
    assert [equipment["grade"] for equipment in item["equipmentItems"]] == [
        "Legend",
        "Legend",
        "Legend",
        "Legend",
        "Epic",
    ]
    assert all(equipment["imageUrl"].endswith(".png") for equipment in item["equipmentItems"])
