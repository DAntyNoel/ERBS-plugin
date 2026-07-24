from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from typing import Any

from rapidfuzz import fuzz, process

from ..analysis import ERBSAnalysisService
from ..client import AsyncERBSClient
from ..exceptions import InvalidQuery
from ..models import CardPayload, MatchRecord, PlayerProfile


def _items_section(title: str, items: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    return {"title": title, "type": "items", "items": items}


class ERBSService:
    def __init__(self, client: AsyncERBSClient) -> None:
        self.client = client
        self.analysis = ERBSAnalysisService()

    async def profile(self, nickname: str, *, season: str | None = None) -> PlayerProfile:
        data = await self.client.player_profile(nickname.strip(), season=season)
        try:
            profile = PlayerProfile.from_api(data)
        except ValueError as exc:
            raise InvalidQuery(f"无法解析玩家资料：{exc}") from exc
        profile.meta.cached = bool(data.get("_erbs_cached"))
        return profile

    async def matches(
        self,
        nickname: str,
        *,
        count: int = 5,
        season: str | None = None,
        matching_mode: str | None = None,
        team_mode: str | None = "SQUAD",
        character: int | None = None,
    ) -> list[MatchRecord]:
        if not 1 <= count <= 20:
            raise InvalidQuery("战绩数量必须在 1 到 20 之间")
        data = await self.client.player_matches(
            nickname.strip(),
            season=season,
            matching_mode=matching_mode,
            team_mode=team_mode,
            character=character,
        )
        result: list[MatchRecord] = []
        for item in data.get("matches") or ():
            if not isinstance(item, Mapping):
                continue
            try:
                result.append(MatchRecord.from_api(item))
            except ValueError:
                continue
            if len(result) >= count:
                break
        return result

    async def player_overview(self, nickname: str) -> CardPayload:
        profile = await self.profile(nickname)
        overview = profile.overview
        stats = [
            {"label": "等级", "value": profile.account_level},
            {"label": "MMR", "value": profile.mmr},
            {"label": "场次", "value": overview.get("play", 0)},
            {"label": "胜场", "value": overview.get("win", 0)},
            {"label": "TOP 3", "value": overview.get("top3", 0)},
            {"label": "击杀", "value": overview.get("playerKill", 0)},
        ]
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle="玩家综合资料",
            sections=({"title": "赛季概览", "type": "stats", "items": stats},),
            footer=self._footer(profile),
        )

    async def rank_card(self, nickname: str, *, season: str | None = None) -> CardPayload:
        profile = await self.profile(nickname, season=season)
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle="段位信息",
            sections=(
                {
                    "title": "当前段位",
                    "type": "stats",
                    "items": [
                        {"label": "MMR", "value": profile.mmr},
                        {"label": "Tier ID", "value": profile.tier_id or "-"},
                        {"label": "小段", "value": profile.tier_grade_id or "-"},
                        {"label": "小段 RP", "value": profile.tier_mmr or "-"},
                    ],
                },
            ),
            footer=self._footer(profile),
        )

    async def stats_card(self, nickname: str, *, season: str | None = None) -> CardPayload:
        profile = await self.profile(nickname, season=season)
        overview = profile.overview
        play = int(overview.get("play") or 0)
        win = int(overview.get("win") or 0)
        items = [
            {"label": "场次", "value": play},
            {"label": "胜率", "value": f"{win / play * 100:.1f}%" if play else "-"},
            {"label": "TOP 2", "value": overview.get("top2", 0)},
            {"label": "TOP 3", "value": overview.get("top3", 0)},
            {"label": "平均击杀", "value": self._average(overview, "playerKill", play)},
            {"label": "平均助攻", "value": self._average(overview, "playerAssistant", play)},
            {"label": "平均伤害", "value": self._average(overview, "damageToPlayer", play)},
            {"label": "平均 TK", "value": self._average(overview, "teamKill", play)},
        ]
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle="赛季统计",
            sections=({"title": "表现", "type": "stats", "items": items},),
            footer=self._footer(profile),
        )

    async def matches_card(self, nickname: str, *, count: int = 5) -> CardPayload:
        matches, character_map, item_map = await self._matches_with_names(nickname, count=count)
        return CardPayload(
            kind="matches",
            title=nickname,
            subtitle=f"最近 {len(matches)} 场",
            sections=(
                _items_section(
                    "战绩",
                    [self._match_item(item, character_map, item_map) for item in matches],
                ),
            ),
            footer=self._plain_footer(),
        )

    async def recent_card(self, nickname: str) -> CardPayload:
        matches = await self.matches(nickname, count=20)
        wins = sum(item.victory for item in matches)
        top3 = sum(item.rank <= 3 for item in matches)
        avg_rank = sum(item.rank for item in matches) / len(matches) if matches else 0
        return CardPayload(
            kind="matches",
            title=nickname,
            subtitle="近期状态",
            sections=(
                {
                    "title": "最近 20 场摘要",
                    "type": "stats",
                    "items": [
                        {"label": "场次", "value": len(matches)},
                        {"label": "胜场", "value": wins},
                        {"label": "TOP 3", "value": top3},
                        {"label": "平均排名", "value": f"#{avg_rank:.1f}" if matches else "-"},
                    ],
                },
                _items_section("名次序列", [{"name": f"#{item.rank}"} for item in matches]),
            ),
            footer=self._plain_footer(),
        )

    async def characters_card(self, nickname: str) -> CardPayload:
        profile = await self.profile(nickname)
        heroes = self.analysis.hero_pool(profile)
        return CardPayload(
            kind="characters",
            title=nickname,
            subtitle="实验体统计",
            sections=(_items_section("常用实验体", heroes),),
            footer=self._footer(profile),
        )

    async def skins_card(self, nickname: str) -> CardPayload:
        data = await self.client.player_matches(
            nickname.strip(), matching_mode="RANK", team_mode="SQUAD", page=1
        )
        skins = Counter(
            int(item.get("skinCode") or 0)
            for item in data.get("matches") or ()
            if isinstance(item, Mapping) and item.get("skinCode")
        )
        return CardPayload(
            kind="characters",
            title=nickname,
            subtitle="皮肤使用统计",
            sections=(
                _items_section(
                    "最近战绩中的皮肤",
                    [
                        {"name": f"Skin {skin_code}", "skinCode": skin_code, "count": count}
                        for skin_code, count in skins.most_common(20)
                    ],
                ),
            ),
            footer=self._plain_footer(cached=bool(data.get("_erbs_cached"))),
        )

    async def teammates_card(self, nickname: str) -> CardPayload:
        data = await self.client.player_matches(
            nickname.strip(), matching_mode="RANK", team_mode="SQUAD", page=1
        )
        matches = [item for item in data.get("matches") or () if isinstance(item, Mapping)][:5]
        details = await asyncio.gather(
            *(
                self.client.match_detail(
                    nickname,
                    int(match.get("seasonId") or 0),
                    int(match.get("gameId") or 0),
                )
                for match in matches
            ),
            return_exceptions=True,
        )
        teammates: Counter[str] = Counter()
        for detail in details:
            if isinstance(detail, Exception):
                continue
            players = detail.get("matches") or detail.get("players") or ()
            own = next(
                (
                    item
                    for item in players
                    if isinstance(item, Mapping)
                    and str(item.get("nickname", "")).casefold() == nickname.casefold()
                ),
                None,
            )
            if not own:
                continue
            team_number = own.get("teamNumber")
            for player in players:
                if not isinstance(player, Mapping) or player.get("teamNumber") != team_number:
                    continue
                name = str(player.get("nickname") or "")
                if name and name.casefold() != nickname.casefold():
                    teammates[name] += 1
        return CardPayload(
            kind="player",
            title=nickname,
            subtitle="近期队友",
            sections=(
                _items_section(
                    "最近共同游戏",
                    [
                        {"name": name, "games": games}
                        for name, games in teammates.most_common(20)
                    ],
                ),
            ),
            footer=self._plain_footer(cached=bool(data.get("_erbs_cached"))),
        )

    async def multi_card(self, nicknames: list[str]) -> CardPayload:
        if not 2 <= len(nicknames) <= 3:
            raise InvalidQuery("多查必须提供 2 到 3 个昵称")
        profiles = await asyncio.gather(*(self.profile(name) for name in nicknames))
        return CardPayload(
            kind="comparison",
            title=" / ".join(profile.nickname for profile in profiles),
            subtitle="多人查询",
            sections=(
                _items_section(
                    "玩家",
                    [
                        {
                            "name": profile.nickname,
                            "mmr": profile.mmr,
                            "level": profile.account_level,
                            "plays": profile.overview.get("play", 0),
                            "wins": profile.overview.get("win", 0),
                        }
                        for profile in profiles
                    ],
                ),
            ),
            footer=self._plain_footer(),
        )

    async def compare_card(self, left: str, right: str) -> CardPayload:
        left_profile, right_profile = await asyncio.gather(self.profile(left), self.profile(right))
        comparison = self.analysis.compare(left_profile, right_profile)
        return CardPayload(
            kind="comparison",
            title=f"{left_profile.nickname} VS {right_profile.nickname}",
            subtitle="玩家对比",
            sections=({"title": "核心数据", "type": "comparison", **comparison},),
            footer=self._plain_footer(),
        )

    async def best_match_card(self, nickname: str) -> CardPayload:
        matches, character_map, item_map = await self._matches_with_names(nickname, count=20)
        best = self.analysis.best_match(matches)
        return CardPayload(
            kind="matches",
            title=nickname,
            subtitle="近期最佳局",
            sections=(
                _items_section(
                    "最佳表现",
                    [self._match_item(best, character_map, item_map)] if best else [],
                ),
            ),
            footer={**self._plain_footer(), "rule": "胜利/名次 → RP → TK → 击杀 → 伤害"},
        )

    async def hero_pool_card(self, nickname: str) -> CardPayload:
        return await self.characters_card(nickname)

    async def equipment_card(self, nickname: str) -> CardPayload:
        matches, _, item_map = await self._matches_with_names(nickname, count=20)
        habits = self.analysis.equipment_habits(matches)
        for item in habits:
            item["name"] = item_map.get(int(item["itemId"]), f"Item {item['itemId']}")
        return CardPayload(
            kind="characters",
            title=nickname,
            subtitle="出装习惯",
            sections=(_items_section("装备频率", habits),),
            footer={**self._plain_footer(), "sample": len(matches)},
        )

    async def leaderboard_card(self, *, page: int = 1) -> CardPayload:
        data = await self.client.leaderboard(page=page)
        entries = (
            data.get("ranks")
            or data.get("leaderboard")
            or data.get("leaderboards")
            or data.get("players")
            or []
        )
        return CardPayload(
            kind="global",
            title="排行榜",
            subtitle=f"第 {page} 页",
            sections=(_items_section("排名", [dict(item) for item in entries[:20]]),),
            footer=self._plain_footer(cached=bool(data.get("_erbs_cached"))),
        )

    async def character_card(self, query: str, *, weapon: str | None = None) -> CardPayload:
        character = await self.resolve_metadata("characters", query, "characters")
        detail = await self.client.character_detail(int(character["id"]), weapon_type=weapon)
        return CardPayload(
            kind="global",
            title=str(character.get("name") or query),
            subtitle="角色强度",
            sections=(_items_section("统计", [dict(detail)]),),
            footer=self._plain_footer(),
        )

    async def item_card(self, query: str) -> CardPayload:
        item = await self.resolve_metadata("items", query, "items")
        return CardPayload(
            kind="global",
            title=str(item.get("name") or query),
            subtitle="物品详情",
            sections=(_items_section("属性", [item]),),
            footer=self._plain_footer(),
        )

    async def routes_card(self, character_query: str, *, weapon: str | None = None) -> CardPayload:
        character = await self.resolve_metadata("characters", character_query, "characters")
        data = await self.client.routes(character=int(character["id"]), weaponType=weapon)
        routes = data.get("routes") or data.get("items") or []
        return CardPayload(
            kind="global",
            title=str(character.get("name") or character_query),
            subtitle="路线",
            sections=(_items_section("推荐路线", [dict(item) for item in routes[:10]]),),
            footer=self._plain_footer(cached=bool(data.get("_erbs_cached"))),
        )

    async def resolve_metadata(
        self, metadata_name: str, query: str, collection_name: str
    ) -> dict[str, Any]:
        data = await self.client.metadata(metadata_name)
        collection = [
            dict(item)
            for item in data.get(collection_name, ())
            if isinstance(item, Mapping)
        ]
        exact = next(
            (
                item
                for item in collection
                if query.casefold()
                in {str(item.get("name", "")).casefold(), str(item.get("key", "")).casefold()}
            ),
            None,
        )
        if exact:
            return exact
        names = {str(item.get("name") or item.get("key")): item for item in collection}
        matched = process.extractOne(query, names.keys(), scorer=fuzz.WRatio, score_cutoff=55)
        if not matched:
            raise InvalidQuery(f"未找到：{query}")
        return names[matched[0]]

    @staticmethod
    def _average(data: Mapping[str, Any], key: str, count: int) -> str:
        return f"{float(data.get(key) or 0) / count:.2f}" if count else "-"

    async def _matches_with_names(
        self, nickname: str, *, count: int
    ) -> tuple[list[MatchRecord], dict[int, str], dict[int, str]]:
        matches, characters, items = await asyncio.gather(
            self.matches(nickname, count=count, matching_mode="RANK"),
            self.client.metadata("characters"),
            self.client.metadata("items"),
        )
        character_map = {
            int(item["id"]): str(item.get("name") or item.get("key") or item["id"])
            for item in characters.get("characters") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        item_map = {
            int(item["id"]): str(item.get("name") or item.get("key") or item["id"])
            for item in items.get("items") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        return matches, character_map, item_map

    @staticmethod
    def _match_item(
        match: MatchRecord | None,
        character_map: Mapping[int, str] | None = None,
        item_map: Mapping[int, str] | None = None,
    ) -> dict[str, Any]:
        if match is None:
            return {}
        character_map = character_map or {}
        item_map = item_map or {}
        character_name = character_map.get(match.character_id, f"角色 {match.character_id}")
        return {
            "name": f"#{match.rank} · {character_name}",
            "gameId": match.game_id,
            "characterId": match.character_id,
            "skinCode": match.skin_code,
            "kills": match.kills,
            "assists": match.assists,
            "teamKills": match.team_kills,
            "damage": match.damage,
            "mmrGain": match.mmr_gain,
            "mmrAfter": match.mmr_after,
            "routeId": match.route_id or "Private",
            "equipment": " · ".join(
                item_map.get(item_id, f"Item {item_id}") for item_id in match.equipment
            ),
        }

    @staticmethod
    def _footer(profile: PlayerProfile) -> dict[str, Any]:
        return {
            "source": "DAK.GG",
            "cached": profile.meta.cached,
            "updatedAt": (
                profile.meta.source_updated_at.isoformat()
                if profile.meta.source_updated_at
                else None
            ),
        }

    @staticmethod
    def _plain_footer(*, cached: bool = False) -> dict[str, Any]:
        return {"source": "DAK.GG", "cached": cached}
