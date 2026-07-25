from __future__ import annotations

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService


@pytest.mark.asyncio
async def test_player_overview_card() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(
                200,
                json={
                    "matches": [
                        {
                            "gameId": 101,
                            "gameRank": 1,
                            "characterNum": 31,
                            "playerKill": 5,
                        },
                        {
                            "gameId": 102,
                            "gameRank": 4,
                            "characterNum": 31,
                            "playerKill": 2,
                        },
                    ]
                },
            )
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(
                200,
                json={"characters": [{"id": 31, "name": "艾玛", "imageUrl": "asset://emma"}]},
            )
        return httpx.Response(
            200,
            json={
                "player": {"name": "Kanami", "accountLevel": 88},
                "playerSeasons": [
                    {
                        "seasonId": 39,
                        "mmr": 8123,
                        "tierId": 7,
                        "tierGradeId": 2,
                        "tierMmr": 123,
                    }
                ],
                "playerSeasonOverviews": [
                    {
                        "seasonId": 39,
                        "matchingModeId": 3,
                        "teamModeId": 3,
                        "play": 20,
                        "win": 4,
                        "top3": 9,
                        "playerKill": 33,
                        "playerAssistant": 41,
                        "characterStats": [{"key": 31, "play": 12, "win": 3}],
                    }
                ],
            },
        )

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).player_overview("Kanami")
    finally:
        await client.aclose()

    assert card.kind == "player"
    assert card.title == "Kanami"
    assert [section["title"] for section in card.sections] == [
        "赛季概览",
        "当前段位",
        "最近 20 场摘要",
        "名次走势",
        "常用实验体 / 英雄池",
    ]
    assert card.sections[0]["items"][4]["value"] == "20.0%"
    assert card.sections[1]["items"][0]["value"] == 8123
    assert card.sections[2]["items"][3]["value"] == "#2.5"
    assert [item["rank"] for item in card.sections[3]["items"]] == [1, 4]
    assert card.sections[4]["type"] == "hero-pool"
    assert card.sections[4]["items"][0]["name"] == "艾玛"
    assert card.sections[4]["items"][0]["winRate"] == "25.0%"


@pytest.mark.asyncio
async def test_character_and_routes_cards_use_real_character_key_and_weapon() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(
                200,
                json={
                    "characters": [
                        {
                            "id": 19,
                            "key": "Emma",
                            "name": "艾玛",
                            "weaponTypes": [{"id": 24, "key": "Arcana"}],
                        }
                    ]
                },
            )
        if request.url.path.endswith("/character-stats"):
            return httpx.Response(
                200,
                json={
                    "characterDetailStatSnapshot": {
                        "characterDetailStat": {
                            "weaponStats": [
                                {
                                    "key": 24,
                                    "count": 10,
                                    "win": 2,
                                    "top3": 5,
                                    "place": 37,
                                    "teamKill": 80,
                                    "playerKill": 30,
                                    "playerDeaths": 20,
                                    "damageToPlayer": 120000,
                                }
                            ]
                        }
                    }
                },
            )
        if request.url.path.endswith("/routes"):
            return httpx.Response(200, json={"weaponRoutes": [{"id": 2582, "title": "route"}]})
        raise AssertionError(request.url.path)

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        character = await ERBSService(client).character_card("艾玛", weapon="Arcana")
        routes = await ERBSService(client).routes_card("艾玛", weapon="Arcana")
    finally:
        await client.aclose()

    assert character.subtitle == "角色强度 · Arcana"
    assert [item["value"] for item in character.sections[0]["items"]] == [
        10,
        "20.0%",
        "50.0%",
        "#3.70",
        "8.00",
        "3.00",
        "2.00",
        "12000.00",
    ]
    assert routes.sections[0]["items"] == [{"id": 2582, "title": "route"}]
    route_request = next(request for request in requests if request.url.path.endswith("/routes"))
    assert "character=Emma" in route_request.url.query.decode()
    assert "weaponType=Arcana" in route_request.url.query.decode()
