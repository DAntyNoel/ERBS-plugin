from __future__ import annotations

import json

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService, InvalidQuery, execute_command
from erbs_plugin.cache import query_cache_spec
from erbs_plugin.client.page import extract_character_analysis
from erbs_plugin.commands import parse_command


def page(data: object, *, script_id: str = "__NEXT_DATA__") -> str:
    payload = {
        "props": {
            "pageProps": {
                "characterTitle": "魔术师",
                "dehydratedState": {
                    "queries": [
                        {"state": {"data": {"unrelated": True}}},
                        {"state": {"data": data}},
                    ],
                },
            }
        }
    }
    return f"<script id='{script_id}' type='application/json'>{json.dumps(payload)}</script>"


@pytest.mark.parametrize("script_id", ["__NEXT_DATA__", "changed-during-migration"])
def test_character_page_selects_snapshot_query(script_id: str) -> None:
    data = {"characterDetailStatSnapshot": {"tier": "diamond_plus"}, "patches": [1234]}
    result = extract_character_analysis(page(data, script_id=script_id))
    assert result["patches"] == [1234]
    assert result["characterTitle"] == "魔术师"
    assert result["characterDetailStatSnapshot"] == data["characterDetailStatSnapshot"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"props": None},
        {
            "props": {
                "pageProps": {
                    "dehydratedState": {"queries": [{"state": None}, {"state": {"data": []}}]},
                }
            }
        },
    ],
)
def test_malformed_page_has_a_controlled_parse_error(payload: object) -> None:
    with pytest.raises(ValueError, match="统计快照"):
        extract_character_analysis(
            '<script id="__NEXT_DATA__">' + json.dumps(payload) + "</script>"
        )


@pytest.mark.parametrize(
    ("text", "operation", "arguments", "mode", "tier", "server"),
    [
        ('/查询玩家 "有 空格" 钴协议', "search", ("有 空格",), "COBALT", "diamond_plus", "seoul"),
        ("/查询角色 席琳 排位 星陨", "character", ("席琳",), "RANK", "meteorite_plus", "seoul"),
        (
            "/查询角色装备 艾玛 钴协议",
            "character-equipment",
            ("艾玛",),
            "COBALT",
            "diamond_plus",
            "seoul",
        ),
        ("/角色数据 无暇", "character-stats", (), "RANK", "mithril_plus", "seoul"),
        ("/段位统计 国服", "tier-stats", (), "RANK", "diamond_plus", "asia2"),
        ("/永恒多少分 欧服", "tier-cutoffs", (), "RANK", "diamond_plus", "frankfurt"),
        ("/查询装备 军刀", "item", ("军刀",), "RANK", "diamond_plus", "seoul"),
    ],
)
def test_command_contract(text, operation, arguments, mode, tier, server) -> None:
    parsed = parse_command(text)
    assert (parsed.operation, parsed.arguments, parsed.mode, parsed.tier, parsed.server) == (
        operation,
        arguments,
        mode,
        tier,
        server,
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "/查询玩家",
        "/查询玩家 a 胡说",
        "/段位统计 不存在",
        "/角色数据 不存在",
        "/查询角色 艾玛 排位 不存在",
        '/查询玩家 "a',
    ],
)
def test_bad_commands_are_rejected(text: str) -> None:
    with pytest.raises(InvalidQuery):
        parse_command(text)


@pytest.mark.asyncio
async def test_help_works_without_network() -> None:
    async def handler(request):
        raise AssertionError(request.url)

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        result = json.loads(await execute_command("/帮助", client=client))
    assert result["kind"] == "help"
    assert len(result["sections"][0]["items"]) == 7


WEAPON = {
    "key": 24,
    "count": 20,
    "win": 5,
    "tier": "S",
    "tierScore": 88,
    "rank": {"count": 2, "size": 100},
    "place": 60,
    "damageToPlayer": 200000,
    "itemBuildStats": [
        {
            "key": [1, 2, 3, 4, 5],
            "count": 12,
            "win": 3,
            "orderStats": [{"key": "53124", "count": 10}],
        },
        {"key": [1, 6, 3, 4, 5], "count": 8, "win": 2},
    ],
    "skillBuildStats": [
        {"key": "QWE", "count": 10, "win": 3, "orderStats": [{"key": "QWQER", "count": 8}]}
    ],
    "tacticalSkillStats": [{"key": 100, "count": 20, "win": 5}],
    "traitCoreStats": [
        {"key": 200, "count": 20, "win": 5, "stats": [{"key": 201, "count": 10, "win": 3}]}
    ],
    "infusionStats": [{"key": 200, "count": 20, "win": 5}],
}
ANALYSIS = {
    "characterDetailStatSnapshot": {
        "tierGameCount": 200,
        "characterDetailStat": {"weaponStats": [WEAPON]},
    },
    "players": [{"userNum": 8, "name": "强者"}],
    "playerTiers": [{"userNum": 8, "mmr": 9000, "tierId": 8}],
}
CHARACTER = {"id": 19, "key": "Emma", "name": "艾玛", "weaponTypes": [{"id": 24, "key": "Arcana"}]}


def analysis_handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/characters/Emma"):
            return httpx.Response(200, text=page(ANALYSIS))
        data = {
            "characters": {"characters": [CHARACTER]},
            "items": {"items": [{"id": i, "name": f"装备{i}"} for i in range(1, 7)]},
            "masteries": {"masteries": [{"id": 24, "name": "阿尔卡纳"}]},
            "skills": {"skills": [{"id": 9, "characterId": 19, "slot": "Q", "name": "技能Q"}]},
            "trait-skills": {
                "traitSkills": [{"id": 200, "name": "核心"}, {"id": 201, "name": "副系"}]
            },
            "tactical-skills": {"tacticalSkills": [{"id": 100, "name": "战术"}]},
            "tiers": {"tiers": [{"id": 8, "name": "永恒"}]},
            "character-stats": {
                "characterStatSnapshot": {
                    "tierGameCount": 200,
                    "characterStats": [{"key": 19, "weaponStats": [WEAPON]}],
                }
            },
        }
        if path.rsplit("/", 1)[-1] in data:
            return httpx.Response(200, json=data[path.rsplit("/", 1)[-1]])
        raise AssertionError(request.url)

    return handler


@pytest.mark.asyncio
async def test_character_builds_join_metadata_and_weight_slot_statistics() -> None:
    seen = []
    async with AsyncERBSClient(
        ERBSConfig(query_cache_enabled=False), transport=httpx.MockTransport(analysis_handler(seen))
    ) as client:
        card = await ERBSService(client).character_card("aima")
        equipment = await ERBSService(client).character_analysis_card("19", equipment_only=True)
    sections = {section["title"]: section["items"] for section in card.sections}
    summary = sections["武器流派"][0]
    assert (summary["games"], summary["winRate"], summary["avgDamage"], summary["pickRate"]) == (
        20,
        25.0,
        10000.0,
        10.0,
    )
    build = sections["推荐出装 / 合成顺序"][0]
    assert [row["id"] for row in build["order"]] == [5, 3, 1, 2, 4]
    slot = next(row for row in sections["各部位装备"] if row["slot"] == "武器")
    assert (slot["games"], slot["pickRate"], slot["winRate"]) == (20, 100.0, 25.0)
    assert sections["技能加点"][0]["order"] == list("QWQER")
    assert sections["潜能"][0]["choices"][0]["name"] == "副系"
    assert sections["灌注"][0]["name"] == "核心"
    assert sections["高分玩家"][0]["name"] == "强者"
    assert len(equipment.sections) == 3
    assert sum(request.url.path.endswith("/characters/Emma") for request in seen) == 1


@pytest.mark.asyncio
async def test_character_modes_and_filters_reach_the_real_request() -> None:
    seen = []
    async with AsyncERBSClient(
        ERBSConfig(query_cache_enabled=False), transport=httpx.MockTransport(analysis_handler(seen))
    ) as client:
        service = ERBSService(client)
        card = await service.character_stats_card(tier="星陨")
        await service.character_card("艾玛", mode="钴协议")
    assert card.sections[0]["items"][0]["name"] == "艾玛"
    stats = next(request for request in seen if request.url.path.endswith("/character-stats"))
    assert dict(stats.url.params) == {
        "dt": "7",
        "matchingMode": "RANK",
        "teamMode": "SQUAD",
        "tier": "meteorite_plus",
    }
    cobalt = next(request for request in seen if request.url.path.endswith("/characters/Emma"))
    assert cobalt.url.params["teamMode"] == "COBALT"
    assert "tier" not in cobalt.url.params


@pytest.mark.asyncio
async def test_tiers_use_explicit_cutoff_types_and_sum_grades() -> None:
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("current-season"):
            return httpx.Response(200, json={"type": "SEASON_11", "name": "S11"})
        if request.url.path.endswith("leaderboard"):
            return httpx.Response(
                200, json={"cutoffs": [{"tierType": 8, "mmr": 9000}, {"tierType": 7, "mmr": 8000}]}
            )
        return httpx.Response(
            200,
            json={
                "distributions": [
                    {"tierType": 6, "count": 20, "rate": 0.2},
                    {"tierType": 6, "count": 30, "rate": 0.3},
                    {"tierType": 63, "count": 10, "rate": 0.1},
                ]
            },
        )

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        card = await ERBSService(client).tier_statistics_card(server="国服")
    assert [row["value"] for row in card.sections[0]["items"]] == [9000, 8000]
    assert card.sections[1]["items"][0] == {"name": "灭钻", "count": 50, "rate": 50}
    assert card.footer["distributionScope"] == "all-servers"
    board = next(request for request in seen if request.url.path.endswith("leaderboard"))
    assert board.url.params["serverName"] == "asia2"
    assert board.url.params["seasonKey"] == "SEASON_11"


@pytest.mark.asyncio
async def test_player_query_uses_latest_played_season_and_mode_not_today() -> None:
    seen = []

    def handler(request):
        seen.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        data = {
            "profile": {
                "player": {"name": "sample", "accountLevel": 50},
                "playerSeasons": [{"seasonId": 39, "mmr": 0}],
                "playerSeasonOverviews": [
                    {"seasonId": 39, "matchingModeId": 6, "teamModeId": 4, "play": 10, "win": 3}
                ],
            },
            "seasons": {"seasons": [{"id": 39, "key": "SEASON_11"}]},
            "matches": {"matches": []},
            "items": {"items": []},
            "characters": {"characters": []},
        }
        return httpx.Response(200, json=data.get(name, {}))

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        result = json.loads(
            await execute_command(
                "/查询玩家 sample 钴协议",
                client=client,
                config=ERBSConfig(query_cache_enabled=False),
            )
        )
    # Cobalt history must not fill the missing ranked sidebar with cobalt statistics.
    assert result["sections"][0]["items"][1]["value"] is None
    assert result["sections"][0]["profile"]["mmrHistory"] == []
    assert next(s for s in result["sections"] if s.get("type") == "hero-pool")["items"] == []
    assert any(s.get("type") == "rank" for s in result["sections"])
    request = next(request for request in seen if request.url.path.endswith("/matches"))
    assert request.url.params["season"] == "SEASON_11"
    assert request.url.params["matchingMode"] == "COBALT"
    assert request.url.params["teamMode"] == "COBALT"
    assert not any("sync" in str(request.url) for request in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "label", "mode_ids"),
    [("ALL", "全部", [3, 2, 6]), ("RANK", "排位", [3]),
     ("NORMAL", "匹配", [2]), ("COBALT", "钴协议", [6])],
)
async def test_player_sidebar_stays_ranked_in_selected_season_while_history_filters(
    mode, label, mode_ids,
):
    seen = []

    def handler(request):
        seen.append(request)
        data = {
            "profile": {
                "player": {"name": "sample"},
                "playerSeasons": [{"seasonId": 41, "mmr": 9000}, {"seasonId": 39, "mmr": 0}],
                "playerSeasonOverviews": [
                    {"seasonId": 41, "play": 999},
                    {"seasonId": 39, "matchingModeId": 3, "teamModeId": 2, "play": 99},
                    {
                        "seasonId": 39,
                        "matchingModeId": 3,
                        "teamModeId": 3,
                        "play": 10,
                        "win": 3,
                        "characterStats": [{"key": 19, "play": 10}],
                        "mmrStats": [["2026-10-20", 0]],
                        "duoStats": [{"nickname": "ranked teammate", "play": 4, "win": 1}],
                    },
                    {
                        "seasonId": 39,
                        "matchingModeId": 2,
                        "teamModeId": 3,
                        "play": 20,
                        "win": 7,
                        "characterStats": [{"key": 19, "play": 20}],
                    },
                    {
                        "seasonId": 39, "matchingModeId": 6, "teamModeId": 4,
                        "play": 50, "win": 25,
                        "characterStats": [{"key": 19, "play": 50}],
                    },
                ],
            },
            "seasons": {"seasons": [{"id": 39, "key": "SEASON_11"}]},
            "matches": {"matches": [
                {"gameId": mode_id, "matchingMode": mode_id, "gameRank": 2,
                 "seasonId": 39, "characterNum": 19}
                for mode_id in mode_ids
            ]},
            "items": {"items": []},
            "characters": {"characters": [CHARACTER]},
        }
        return httpx.Response(200, json=data.get(request.url.path.rsplit("/", 1)[-1], {}))

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        card = await ERBSService(client).search_player_card(
            "sample",
            mode=mode,
            season="SEASON_11",
        )
    assert card.sections[0]["items"][1]["value"] == 10
    assert card.sections[0]["items"][2]["value"] == 3
    assert card.sections[0]["profile"]["mmrHistory"] == [{"date": "2026-10-20", "mmr": 0}]
    assert card.sections[0]["teammates"][0]["name"] == "ranked teammate"
    assert card.sections[0]["profile"]["modeName"] == label
    assert card.sections[-2]["items"][0]["plays"] == 10
    rank = next(s for s in card.sections if s.get("type") == "rank")
    assert rank["items"][0]["value"] == 0  # Keep this season's placement RP, not season 41's.
    matches = next(s["items"] for s in card.sections if s.get("title") == "最近对局")
    assert [match["matchingMode"] for match in matches] == mode_ids
    request = next(request for request in seen if request.url.path.endswith("/matches"))
    assert request.url.params["season"] == "SEASON_11"
    assert request.url.params["matchingMode"] == mode
    assert request.url.params["teamMode"] == {"ALL": "ALL", "COBALT": "COBALT"}.get(mode, "SQUAD")


@pytest.mark.asyncio
async def test_desktop_character_data_uses_population_items_and_trait_builds(monkeypatch):
    monkeypatch.setitem(ANALYSIS["characterDetailStatSnapshot"], "tierCount", 400)
    monkeypatch.setitem(
        WEAPON,
        "itemStats",
        [
            {"key": 0, "count": 50, "stats": [{"key": 1, "count": 25, "win": 5, "place": 100}]},
        ],
    )
    monkeypatch.setitem(
        WEAPON,
        "traitCoreStats",
        [
            {
                "key": 200,
                "count": 20,
                "win": 5,
                "buildStats": [{"key": [200, [201], []], "count": 8, "win": 2}],
            },
        ],
    )
    async with AsyncERBSClient(transport=httpx.MockTransport(analysis_handler([]))) as client:
        card = await ERBSService(client).character_analysis_card("Emma")
    sections = {s["title"]: s["items"] for s in card.sections}
    assert sections["武器流派"][0]["pickRate"] == 5
    item = sections["各部位装备"][0]
    assert (item["slot"], item["pickRate"], item["avgRank"]) == ("武器", 50, 4)
    build = sections["潜能"][0]["builds"][0]
    assert [choice["id"] for choice in build["choices"]] == [201]
    assert (build["pickRate"], build["winRate"]) == (40, 25)


@pytest.mark.asyncio
async def test_metadata_initials_and_ambiguous_names():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": 1, "name": "烈阳"},
                    {"id": 2, "name": "烈焰"},
                ]
            },
        )

    async with AsyncERBSClient(transport=httpx.MockTransport(handler)) as client:
        service = ERBSService(client)
        assert (await service.resolve_metadata("items", "lieyang", "items"))["id"] == 1
        for text in ("ly", "烈", " "):
            with pytest.raises(InvalidQuery):
                await service.resolve_metadata("items", text, "items")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("mode", "COBALT"),
        ("tier", "in1000"),
        ("server", "asia2"),
        ("web_base_url", "https://other.test"),
    ],
)
def test_query_cache_separates_new_filters(key, value) -> None:
    options = dict(
        api_base_url="https://er.dakgg.io",
        language="zh-CN",
        count=20,
        page=1,
        season=None,
        weapon=None,
    )
    baseline = query_cache_spec("character", ("艾玛",), **options)
    changed = query_cache_spec("character", ("艾玛",), **options, **{key: value})
    assert baseline != changed
