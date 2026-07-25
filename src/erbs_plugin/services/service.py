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
from ..radar import RadarDataSource, RadarScorer, build_radar_section

_MMR_CHART_MATCH_COUNT = 20
_TIER_NAMES = {
    0: "段位未鉴定",
    1: "铁阎",
    2: "铜魂",
    3: "银烙",
    4: "金魄",
    5: "修罗",
    6: "灭钻",
    7: "半神",
    8: "永恒",
    63: "星陨",
    66: "无瑕",
}


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
        profile, matches, metadata, radar_sample = await asyncio.gather(
            self.profile(nickname),
            self.matches(nickname, count=20),
            self.client.metadata("characters"),
            RadarDataSource(self.client).fetch(nickname, count=20),
        )
        overview = profile.overview
        stats = [
            {"label": "等级", "value": profile.account_level},
            {"label": "赛季", "value": profile.season_id or "-"},
            {"label": "场次", "value": overview.get("play", 0)},
            {"label": "胜场", "value": overview.get("win", 0)},
            {
                "label": "胜率",
                "value": self._rate(overview.get("win"), overview.get("play")),
            },
            {"label": "TOP 3", "value": overview.get("top3", 0)},
            {"label": "击杀", "value": overview.get("playerKill", 0)},
            {"label": "助攻", "value": overview.get("playerAssistant", 0)},
        ]
        heroes = self._hero_pool_items(profile, metadata)
        recent_sections = list(self._recent_sections(matches, metadata))
        season_section: dict[str, Any] = {
            "title": "赛季概览",
            "type": "stats",
            "items": stats,
        }
        overview_sections: list[Mapping[str, Any]] = [season_section]
        if radar_sample.matches:
            radar_profile = RadarScorer().score(radar_sample)
            season_section["radar"] = {
                **build_radar_section(radar_profile),
                "compact": True,
            }
        rank_section = {**self._rank_section(profile), "layout": "half"}
        recent_sections[0] = {**recent_sections[0], "layout": "half"}
        overview_sections.extend(
            (rank_section, *recent_sections, self._hero_pool_section(heroes))
        )
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle="玩家综合资料",
            sections=tuple(overview_sections),
            footer=self._footer(profile),
        )

    async def rank_card(self, nickname: str, *, season: str | None = None) -> CardPayload:
        profile = await self.profile(nickname, season=season)
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle="段位信息",
            sections=(self._rank_section(profile),),
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
        if not 1 <= count <= 20:
            raise InvalidQuery("战绩数量必须在 1 到 20 之间")
        matches, character_map, item_map = await self._matches_with_names(
            nickname, count=count
        )
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
        matches, metadata = await asyncio.gather(
            self.matches(nickname, count=20),
            self.client.metadata("characters"),
        )
        return CardPayload(
            kind="matches",
            title=nickname,
            subtitle="近期状态",
            sections=self._recent_sections(matches, metadata),
            footer=self._plain_footer(),
        )

    async def radar_card(self, nickname: str, *, count: int = 20) -> CardPayload:
        sample = await RadarDataSource(self.client).fetch(nickname, count=count)
        if not sample.matches:
            raise InvalidQuery("没有可用于风格雷达的排位三排记录")
        profile = RadarScorer().score(sample)
        return CardPayload(
            kind="radar",
            title=profile.nickname,
            subtitle="排位风格",
            sections=(build_radar_section(profile),),
            footer=self._plain_footer(cached=profile.cached),
        )

    async def characters_card(self, nickname: str) -> CardPayload:
        profile, metadata = await asyncio.gather(
            self.profile(nickname), self.client.metadata("characters")
        )
        heroes = self._hero_pool_items(profile, metadata)
        return CardPayload(
            kind="characters",
            title=nickname,
            subtitle="实验体统计",
            sections=(self._hero_pool_section(heroes),),
            footer=self._footer(profile),
        )

    async def skins_card(self, nickname: str) -> CardPayload:
        data, metadata = await asyncio.gather(
            self.client.player_matches(
                nickname.strip(), matching_mode="RANK", team_mode="SQUAD", page=1
            ),
            self.client.metadata("characters"),
        )
        skin_map = {
            int(skin["id"]): skin
            for character in metadata.get("characters") or ()
            if isinstance(character, Mapping)
            for skin in character.get("skins") or ()
            if isinstance(skin, Mapping) and skin.get("id") is not None
        }
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
                        {
                            "name": skin_map.get(skin_code, {}).get("name")
                            or f"Skin {skin_code}",
                            "imageUrl": skin_map.get(skin_code, {}).get("imageUrl"),
                            "skinCode": skin_code,
                            "count": count,
                        }
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
            metadata = item_map.get(int(item["itemId"]), {})
            item["name"] = metadata.get("name") or f"Item {item['itemId']}"
            item["imageUrl"] = metadata.get("imageUrl")
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
        weapon_key, weapon_id = self._resolve_weapon(character, weapon)
        detail = await self.client.character_detail(
            str(character.get("key") or character["id"]),
            weapon_type=weapon_key,
        )
        snapshot = detail.get("characterDetailStatSnapshot") or {}
        character_stats = (
            snapshot.get("characterDetailStat")
            if isinstance(snapshot, Mapping)
            else {}
        ) or {}
        weapon_stats = (
            character_stats.get("weaponStats")
            if isinstance(character_stats, Mapping)
            else ()
        ) or ()
        selected = next(
            (
                item
                for item in weapon_stats
                if isinstance(item, Mapping) and int(item.get("key") or 0) == weapon_id
            ),
            {},
        )
        play = int(selected.get("count") or 0)

        def average(key: str) -> str:
            return f"{float(selected.get(key) or 0) / play:.2f}" if play else "-"

        return CardPayload(
            kind="global",
            title=str(character.get("name") or query),
            subtitle=f"角色强度 · {weapon_key}",
            sections=(
                {
                    "title": "当前版本统计",
                    "type": "stats",
                    "items": [
                        {"label": "场次", "value": play},
                        {
                            "label": "胜率",
                            "value": f"{int(selected.get('win') or 0) / play * 100:.1f}%"
                            if play
                            else "-",
                        },
                        {
                            "label": "TOP 3",
                            "value": f"{int(selected.get('top3') or 0) / play * 100:.1f}%"
                            if play
                            else "-",
                        },
                        {"label": "平均排名", "value": f"#{average('place')}"},
                        {"label": "平均 TK", "value": average("teamKill")},
                        {"label": "平均 K", "value": average("playerKill")},
                        {"label": "平均 D", "value": average("playerDeaths")},
                        {"label": "平均伤害", "value": average("damageToPlayer")},
                    ],
                },
            ),
            footer=self._plain_footer(cached=bool(detail.get("_erbs_cached"))),
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
        weapon_key, _ = self._resolve_weapon(character, weapon)
        data = await self.client.routes(
            character=str(character.get("key") or character["id"]),
            weaponType=weapon_key,
        )
        routes = data.get("weaponRoutes") or data.get("routes") or data.get("items") or []
        return CardPayload(
            kind="global",
            title=str(character.get("name") or character_query),
            subtitle=f"路线 · {weapon_key}",
            sections=(_items_section("推荐路线", [dict(item) for item in routes[:10]]),),
            footer=self._plain_footer(cached=bool(data.get("_erbs_cached"))),
        )

    @staticmethod
    def _resolve_weapon(
        character: Mapping[str, Any], weapon: str | None
    ) -> tuple[str, int]:
        weapon_types = [
            item
            for item in character.get("weaponTypes") or ()
            if isinstance(item, Mapping) and item.get("key") and item.get("id") is not None
        ]
        if not weapon_types:
            if weapon is None:
                raise InvalidQuery("该角色缺少武器类型元数据")
            return weapon, 0
        selected = next(
            (
                item
                for item in weapon_types
                if weapon is None
                or str(item.get("key", "")).casefold() == weapon.casefold()
                or str(item.get("id")) == weapon
            ),
            None,
        )
        if selected is None:
            choices = " / ".join(str(item["key"]) for item in weapon_types)
            raise InvalidQuery(f"不支持的武器类型：{weapon}（可选：{choices}）")
        return str(selected["key"]), int(selected["id"])

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

    @staticmethod
    def _rate(numerator: Any, denominator: Any) -> str:
        total = int(denominator or 0)
        return f"{int(numerator or 0) / total * 100:.1f}%" if total else "-"

    @staticmethod
    def _rank_section(profile: PlayerProfile) -> Mapping[str, Any]:
        tier_name = _TIER_NAMES.get(profile.tier_id)
        if tier_name is None and profile.tier_id is not None:
            tier_name = f"Tier {profile.tier_id}"
        section: dict[str, Any] = {
            "title": "当前段位",
            "type": "rank",
            "tierId": profile.tier_id,
            "tierName": tier_name or "-",
            "items": [
                {"label": "MMR", "value": profile.mmr},
                {"label": "段位", "value": tier_name or "-"},
                {"label": "小段", "value": profile.tier_grade_id or "-"},
                {"label": "小段 RP", "value": profile.tier_mmr or "-"},
            ],
        }
        if profile.tier_id in {0, 1, 2, 3, 4, 5, 6, 7, 8, 63, 66}:
            suffix = "?1" if profile.tier_id == 63 else ""
            section["imageUrl"] = (
                f"//cdn.dak.gg/assets/er/images/rank/full/{profile.tier_id}.png{suffix}"
            )
        return section

    @classmethod
    def _recent_sections(
        cls,
        matches: list[MatchRecord],
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        wins = sum(item.victory for item in matches)
        top3 = sum(item.rank <= 3 for item in matches)
        avg_rank = sum(item.rank for item in matches) / len(matches) if matches else 0
        character_map = {
            int(item["id"]): item
            for item in (metadata or {}).get("characters") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        character_counts = Counter(item.character_id for item in matches if item.character_id)
        most_used_id = character_counts.most_common(1)[0][0] if character_counts else None
        most_used = character_map.get(most_used_id, {}) if most_used_id is not None else {}
        summary: dict[str, Any] = {
            "title": "最近 20 场摘要",
            "type": "recent-summary",
            "items": [
                {"label": "场次", "value": len(matches)},
                {"label": "胜场", "value": wins},
                {"label": "TOP 3", "value": top3},
                {"label": "平均排名", "value": f"#{avg_rank:.1f}" if matches else "-"},
            ],
        }
        if most_used_id is not None:
            summary.update(
                {
                    "characterId": most_used_id,
                    "characterName": most_used.get("name") or f"角色 {most_used_id}",
                    "imageUrl": most_used.get("imageUrl") or most_used.get("communityImageUrl"),
                }
            )
        sections: list[Mapping[str, Any]] = [
            summary,
        ]
        mmr_chart = cls._mmr_chart_section(matches)
        if mmr_chart is not None:
            sections.append(mmr_chart)
        sections.append(
            {
                "title": "名次走势",
                "type": "placements",
                "maxRank": 8,
                "items": [
                    {"rank": item.rank, "victory": item.victory, "podium": item.rank <= 3}
                    for item in matches
                ],
            },
        )
        return tuple(sections)

    @staticmethod
    def _mmr_chart_section(matches: list[MatchRecord]) -> Mapping[str, Any] | None:
        chart_matches = [
            match for match in matches[:_MMR_CHART_MATCH_COUNT] if match.mmr_after > 0
        ]
        if not chart_matches:
            return None

        chronological = list(reversed(chart_matches))
        start_mmr = chronological[0].mmr_after - chronological[0].mmr_gain
        mmr_values = [start_mmr, *(match.mmr_after for match in chronological)]
        minimum = min(mmr_values)
        maximum = max(mmr_values)
        span = maximum - minimum
        rough_step = max(1, (span + 3) // 4)
        magnitude = 10 ** max(0, len(str(rough_step)) - 1)
        rough_factor = (rough_step + magnitude - 1) // magnitude
        nice_factor = next(factor for factor in (1, 2, 5, 10) if rough_factor <= factor)
        tick_step = nice_factor * magnitude
        chart_min = minimum // tick_step * tick_step
        chart_max = (maximum + tick_step - 1) // tick_step * tick_step
        if chart_min == minimum:
            chart_min -= tick_step
        if chart_max == maximum:
            chart_max += tick_step

        return {
            "title": "段位分",
            "type": "mmr-chart",
            "chartMin": chart_min,
            "chartMax": chart_max,
            "ticks": list(range(chart_min, chart_max + 1, tick_step)),
            "startMmr": start_mmr,
            "currentMmr": chronological[-1].mmr_after,
            "netChange": chronological[-1].mmr_after - start_mmr,
            "peakMmr": maximum,
            "items": [
                {
                    "gameId": match.game_id,
                    "mmr": match.mmr_after,
                    "gain": match.mmr_gain,
                }
                for match in chronological
            ],
        }

    def _hero_pool_items(
        self,
        profile: PlayerProfile,
        metadata: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        character_map = {
            int(item["id"]): item
            for item in metadata.get("characters") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        heroes = self.analysis.hero_pool(profile)
        for index, hero in enumerate(heroes, start=1):
            character_id = int(hero.get("key") or hero.get("characterNum") or 0)
            character = character_map.get(character_id, {})
            plays = int(hero.get("plays") or hero.get("play") or 0)
            hero["name"] = character.get("name") or f"角色 {character_id}"
            hero["imageUrl"] = character.get("imageUrl")
            hero["poolRank"] = index
            hero["winRate"] = self._rate(hero.get("win"), plays)
            hero["usagePercent"] = f"{float(hero.get('usageRate') or 0) * 100:.1f}%"
        return heroes

    @staticmethod
    def _hero_pool_section(heroes: list[dict[str, Any]]) -> Mapping[str, Any]:
        return {"title": "常用实验体 / 英雄池", "type": "hero-pool", "items": heroes}

    async def _matches_with_names(
        self, nickname: str, *, count: int
    ) -> tuple[
        list[MatchRecord], dict[int, Mapping[str, Any]], dict[int, Mapping[str, Any]]
    ]:
        matches, characters, items = await asyncio.gather(
            self.matches(nickname, count=count, matching_mode="RANK"),
            self.client.metadata("characters"),
            self.client.metadata("items"),
        )
        character_map = {
            int(item["id"]): item
            for item in characters.get("characters") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        item_map = {
            int(item["id"]): item
            for item in items.get("items") or ()
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        return matches, character_map, item_map

    @staticmethod
    def _match_item(
        match: MatchRecord | None,
        character_map: Mapping[int, Mapping[str, Any]] | None = None,
        item_map: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if match is None:
            return {}
        character_map = character_map or {}
        item_map = item_map or {}
        character = character_map.get(match.character_id, {})
        character_name = character.get("name") or f"角色 {match.character_id}"
        equipment_items = [
            {
                "itemId": item_id,
                "name": item_map.get(item_id, {}).get("name") or f"Item {item_id}",
                "imageUrl": item_map.get(item_id, {}).get("imageUrl"),
                "grade": item_map.get(item_id, {}).get("grade") or "Common",
            }
            for item_id in match.equipment[:5]
        ]
        return {
            "layout": "match",
            "name": f"#{match.rank} · {character_name}",
            "characterName": character_name,
            "rank": match.rank,
            "imageUrl": character.get("imageUrl"),
            "gameId": match.game_id,
            "characterId": match.character_id,
            "skinCode": match.skin_code,
            "kills": match.kills,
            "assists": match.assists,
            "deaths": match.deaths,
            "teamKills": match.team_kills,
            "damage": match.damage,
            "mmrGain": match.mmr_gain,
            "mmrAfter": match.mmr_after,
            "routeId": match.route_id or "Private",
            "equipment": " · ".join(str(item["name"]) for item in equipment_items),
            "equipmentItems": equipment_items,
        }

    @staticmethod
    def _footer(profile: PlayerProfile) -> dict[str, Any]:
        return {
            "source": "DAK.GG",
            "cached": profile.meta.cached,
            "sourceUpdatedAt": (
                profile.meta.source_updated_at.isoformat()
                if profile.meta.source_updated_at
                else None
            ),
        }

    @staticmethod
    def _plain_footer(*, cached: bool = False) -> dict[str, Any]:
        return {"source": "DAK.GG", "cached": cached}
