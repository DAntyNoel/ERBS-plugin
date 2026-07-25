from __future__ import annotations

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService, InvalidQuery, PlayerProfile


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
                            "mmrAfter": 8123,
                            "mmrGain": 25,
                        },
                        {
                            "gameId": 102,
                            "gameRank": 4,
                            "characterNum": 31,
                            "playerKill": 2,
                            "mmrAfter": 8098,
                            "mmrGain": -12,
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
        "段位分",
        "名次走势",
        "常用实验体 / 英雄池",
    ]
    assert card.sections[0]["items"][4]["value"] == "20.0%"
    assert "layout" not in card.sections[0]
    assert card.sections[0]["radar"]["type"] == "radar"
    assert card.sections[0]["radar"]["compact"] is True
    assert len(card.sections[0]["radar"]["axes"]) == 8
    assert card.sections[1]["type"] == "rank"
    assert card.sections[1]["imageUrl"] == (
        "//cdn.dak.gg/assets/er/images/rank/full/7.png"
    )
    assert card.sections[1]["layout"] == "half"
    assert card.sections[1]["tierId"] == 7
    assert card.sections[1]["tierName"] == "半神"
    assert card.sections[1]["items"][0]["value"] == 8123
    assert card.sections[1]["items"][1] == {"label": "段位", "value": "半神"}
    assert card.sections[2]["layout"] == "half"
    assert card.sections[2]["type"] == "recent-summary"
    assert card.sections[2]["characterId"] == 31
    assert card.sections[2]["characterName"] == "艾玛"
    assert card.sections[2]["imageUrl"] == "asset://emma"
    assert card.sections[2]["items"][3]["value"] == "#2.5"
    assert card.sections[3]["type"] == "mmr-chart"
    assert card.sections[3]["currentMmr"] == 8123
    assert [item["rank"] for item in card.sections[4]["items"]] == [1, 4]
    assert card.sections[4]["type"] == "placements"
    assert card.sections[4]["maxRank"] == 8
    assert card.sections[5]["type"] == "hero-pool"
    assert card.sections[5]["items"][0]["name"] == "艾玛"
    assert card.sections[5]["items"][0]["winRate"] == "25.0%"


@pytest.mark.parametrize(
    ("tier_id", "tier_name"),
    [(1, "铁阎"), (6, "灭钻"), (7, "半神"), (8, "永恒"), (63, "星陨"), (66, "无瑕")],
)
def test_rank_section_uses_localized_tier_name(tier_id: int, tier_name: str) -> None:
    profile = PlayerProfile.from_api(
        {
            "player": {"name": "Kanami"},
            "playerSeasons": [{"mmr": 8000, "tierId": tier_id}],
        }
    )

    section = ERBSService._rank_section(profile)

    assert section["tierName"] == tier_name
    assert section["items"][1] == {"label": "段位", "value": tier_name}


@pytest.mark.asyncio
async def test_matches_card_uses_requested_detail_count_without_mmr_chart() -> None:
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/matches"):
            return httpx.Response(
                200,
                json={
                    "matches": [
                        {
                            "gameId": 100 + index,
                            "gameRank": index % 8 + 1,
                            "characterNum": 31,
                            "mmrAfter": 8200 - index * 10,
                            "mmrGain": 10 if index % 2 == 0 else -5,
                        }
                        for index in range(20)
                    ]
                },
            )
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(200, json={"characters": [{"id": 31, "name": "艾玛"}]})
        if request.url.path.endswith("/data/items"):
            return httpx.Response(200, json={"items": []})
        raise AssertionError(request.url.path)

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).matches_card("Kanami", count=5)
    finally:
        await client.aclose()

    assert [section["type"] for section in card.sections] == ["items"]
    details = card.sections[0]
    assert len(details["items"]) == 5
    assert card.subtitle == "最近 5 场"
    assert requested_paths.count("/api/v1/players/Kanami/matches") == 1


@pytest.mark.asyncio
async def test_recent_card_includes_mmr_chart_between_summary_and_placements() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(
                200,
                json={
                    "matches": [
                        {
                            "gameId": 100 + index,
                            "gameRank": index % 8 + 1,
                            "characterNum": 31,
                            "mmrAfter": 8200 - index * 10,
                            "mmrGain": 10 if index % 2 == 0 else -5,
                        }
                        for index in range(20)
                    ]
                },
            )
        if request.url.path.endswith("/data/characters"):
            return httpx.Response(
                200,
                json={
                    "characters": [
                        {"id": 31, "name": "艾玛", "imageUrl": "asset://emma"}
                    ]
                },
            )
        raise AssertionError(request.url.path)

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).recent_card("Kanami")
    finally:
        await client.aclose()

    assert [section["type"] for section in card.sections] == [
        "recent-summary",
        "mmr-chart",
        "placements",
    ]
    assert card.sections[0]["characterName"] == "艾玛"
    assert card.sections[0]["imageUrl"] == "asset://emma"
    assert len(card.sections[1]["items"]) == 20
    assert card.sections[1]["currentMmr"] == 8200


@pytest.mark.asyncio
async def test_radar_card_uses_ranked_squad_match_style_data() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/matches")
        assert request.url.params["matchingMode"] == "RANK"
        assert request.url.params["teamMode"] == "SQUAD"
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "gameId": 100 + index,
                        "matchingMode": 3,
                        "matchingTeamMode": 3,
                        "playTime": 1200,
                        "damageToPlayer": 18000,
                        "damageFromPlayer": 15000,
                        "damageToMonster": 50000,
                        "playerKill": 4,
                        "playerAssistant": 6,
                        "teamKill": 12,
                        "playerDeaths": 1,
                        "monsterKill": 40,
                        "totalGainVFCredit": 1200,
                        "totalUseVFCredit": 900,
                        "viewContribution": 25,
                    }
                    for index in range(20)
                ]
            },
        )

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).radar_card("Kanami")
    finally:
        await client.aclose()

    assert card.kind == "radar"
    assert card.subtitle == "排位风格"
    assert card.sections[0]["type"] == "radar"
    assert len(card.sections[0]["axes"]) == 8
    assert card.footer["source"] == "DAK.GG"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 21])
async def test_matches_card_rejects_invalid_detail_count_before_fetch(count: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(InvalidQuery, match="1 到 20"):
            await ERBSService(client).matches_card("Kanami", count=count)
    finally:
        await client.aclose()


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
