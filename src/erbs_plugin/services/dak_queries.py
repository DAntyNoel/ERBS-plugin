"""DAK.GG collectors shared by the command, Python and rendering entry points.

The request contract was verified against EternalReturnLoMu e04e650. This is a
Python implementation using ERBS-plugin's own client, payloads, assets and scoring.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..commands import COMMAND_HELP, normalize_mode, normalize_server, normalize_tier, team_mode
from ..exceptions import InvalidQuery, UpstreamUnavailable
from ..models import CardPayload
from ..scoring.core import number


def rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def index(data: Mapping[str, Any], name: str) -> dict[str, Mapping[str, Any]]:
    return {str(row["id"]): row for row in rows(data.get(name)) if row.get("id") is not None}


def ratio(value: Any, total: Any, scale: float = 1) -> float | None:
    numerator, denominator = number(value), number(total)
    return (
        round(numerator / denominator * scale, 2)
        if (numerator is not None and denominator is not None and denominator > 0)
        else None
    )


def section(title: str, items: list[dict[str, Any]], kind: str = "items") -> dict[str, Any]:
    return {"title": title, "type": kind, "items": items}


def weapon_summary(
    weapon: Mapping[str, Any],
    total: Any,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    rank = weapon.get("rank") or {}
    count = weapon.get("count")
    return {
        "id": weapon.get("key"),
        "name": metadata.get("name", str(weapon.get("key"))),
        "imageUrl": metadata.get("iconUrl"),
        "tier": weapon.get("tier"),
        "tierScore": weapon.get("tierScore"),
        "rank": rank.get("count"),
        "rankSize": rank.get("size"),
        "games": count,
        "pickRate": ratio(count, total, 100),
        "winRate": ratio(weapon.get("win"), count, 100),
        "top3Rate": ratio(weapon.get("top3"), count, 100),
        "avgRank": ratio(weapon.get("place"), count),
        "avgKills": ratio(weapon.get("playerKill"), count),
        "avgDamage": ratio(weapon.get("damageToPlayer"), count),
        "rpChange": ratio(weapon.get("mmrGain"), count),
    }


def pick(raw: Mapping[str, Any], refs: Mapping[str, Mapping[str, Any]], total: Any) -> dict:
    identifier = str(raw.get("key", ""))
    metadata = refs.get(identifier, {})
    return {
        "id": raw.get("key"),
        "name": metadata.get("name", identifier),
        "imageUrl": metadata.get("imageUrl") or metadata.get("iconUrl"),
        "games": raw.get("count"),
        "pickRate": ratio(raw.get("count"), total, 100),
        "winRate": ratio(raw.get("win"), raw.get("count"), 100),
    }


def popular(value: Any, limit: int) -> list[Mapping[str, Any]]:
    return sorted(rows(value), key=lambda row: number(row.get("count")) or 0, reverse=True)[:limit]


class DakQueryMixin:
    """Uses the owning ERBSService's client, normalization and domain helpers."""

    async def search_player_card(
        self,
        nickname: str,
        *,
        mode: str = "RANK",
        count: int = 20,
        season: str | None = None,
    ) -> CardPayload:
        mode = normalize_mode(mode)
        if not 1 <= count <= 20:
            raise InvalidQuery("战绩数量必须在 1 到 20 之间")
        profile, characters, items = await asyncio.gather(
            self.profile(nickname, season=season),
            self.client.metadata("characters"),
            self.client.metadata("items"),
        )
        latest = next(iter(rows(profile.raw.get("playerSeasons"))), None)
        season_key = season
        if season is not None:
            seasons = await self.client.metadata("seasons")
            requested = next(
                (
                    row
                    for row in rows(seasons.get("seasons"))
                    if season in {str(row.get("key")), str(row.get("id"))}
                ),
                None,
            )
            if requested is None or not requested.get("key"):
                raise InvalidQuery(f"未找到赛季：{season}")
            season_key = str(requested["key"])
            latest = next(
                (
                    row
                    for row in rows(profile.raw.get("playerSeasons"))
                    if row.get("seasonId") == requested.get("id")
                ),
                {"seasonId": requested.get("id"), "mmr": 0},
            )
        if latest is not None:
            profile = replace(
                profile,
                season_id=latest.get("seasonId"),
                mmr=latest.get("mmr") or 0,
                tier_id=latest.get("tierId"),
                tier_grade_id=latest.get("tierGradeId"),
                tier_mmr=latest.get("tierMmr"),
            )
        # Inactive players must use the season they last played, not today's season.
        if season_key is None and profile.season_id is not None:
            seasons = await self.client.metadata("seasons")
            latest = next(
                (row for row in rows(seasons.get("seasons")) if row.get("id") == profile.season_id),
                None,
            )
            if latest is None or not latest.get("key"):
                raise UpstreamUnavailable("DAK.GG 缺少玩家最近游玩赛季的映射")
            season_key = str(latest["key"])
        mode_id = {"RANK": 3, "NORMAL": 2, "COBALT": 6, "ALL": None}[mode]
        overviews = [
            row
            for row in rows(profile.raw.get("playerSeasonOverviews"))
            if (profile.season_id is None or row.get("seasonId") == profile.season_id)
            and (
                mode == "ALL"
                or (
                    row.get("matchingModeId") == mode_id
                    and row.get("teamModeId") == (4 if mode == "COBALT" else 3)
                )
            )
        ]
        overview = next(iter(overviews), {})
        if mode == "ALL":
            keys = (
                "play",
                "win",
                "top3",
                "damageToPlayer",
                "teamKill",
                "playerKill",
                "playerAssistant",
                "place",
            )
            overview = {
                key: sum(values)
                if (
                    values := [
                        value for row in overviews if (value := number(row.get(key))) is not None
                    ]
                )
                else None
                for key in keys
            }
            aggregate: dict[str, dict] = {}
            for row in overviews:
                for hero in rows(row.get("characterStats")):
                    identifier = str(hero.get("key"))
                    combined = aggregate.setdefault(identifier, {"key": hero.get("key")})
                    for key in keys:
                        if (value := number(hero.get(key))) is not None:
                            combined[key] = combined.get(key, 0) + value
            overview["characterStats"] = list(aggregate.values())
        profile = replace(
            profile, overview=overview, characters=tuple(rows(overview.get("characterStats")))
        )
        matches = await self.matches(
            nickname, count=count, season=season_key, matching_mode=mode, team_mode=team_mode(mode)
        )
        char_map = {int(key): row for key, row in index(characters, "characters").items()}
        item_map = {int(key): row for key, row in index(items, "items").items()}
        stats = [{"label": "等级", "value": profile.account_level}]
        for label, key in (("场次", "play"), ("胜场", "win"), ("TOP 3", "top3")):
            stats.append({"label": label, "value": overview.get(key)})
        for label, key in (
            ("胜率 %", "win"),
            ("平均伤害", "damageToPlayer"),
            ("平均 TK", "teamKill"),
            ("平均击杀", "playerKill"),
            ("平均助攻", "playerAssistant"),
            ("平均排名", "place"),
        ):
            stats.append(
                {
                    "label": label,
                    "value": ratio(
                        overview.get(key), overview.get("play"), 100 if key == "win" else 1
                    ),
                }
            )
        sections = [section("赛季概览", stats, "stats")]
        if mode == "RANK":
            sections.append(self._rank_section(profile))
        sections.extend(self._recent_sections(matches, characters))
        sections.append(self._hero_pool_section(self._hero_pool_items(profile, characters)))
        sections.append(
            section("最近对局", [self._match_item(row, char_map, item_map) for row in matches])
        )
        footer = {
            **self._footer(profile),
            "mode": mode,
            "season": season_key,
            "sample": len(matches),
        }
        return CardPayload(
            kind="player",
            title=profile.nickname,
            subtitle=f"玩家查询 · {mode} · {season_key or '无赛季'}",
            sections=tuple(sections),
            footer=footer,
        )

    async def character_analysis_card(
        self,
        query: str,
        *,
        weapon: str | None = None,
        mode: str = "RANK",
        tier: str = "diamond_plus",
        equipment_only: bool = False,
    ) -> CardPayload:
        mode, tier = normalize_mode(mode), normalize_tier(tier)
        if mode not in {"RANK", "COBALT"}:
            raise InvalidQuery("角色详情仅支持排位和钴协议")
        character = await self.resolve_metadata("characters", query, "characters")
        names = ("masteries", "items", "skills", "tactical-skills", "trait-skills", "tiers")
        detail, *datasets = await asyncio.gather(
            self.client.character_detail(
                str(character.get("key") or character["id"]),
                matching_mode=mode,
                team_mode=team_mode(mode),
                tier=tier,
            ),
            *(self.client.metadata(name) for name in names),
        )
        references = dict(zip(names, datasets, strict=True))
        weapons = index(references["masteries"], "masteries")
        items = index(references["items"], "items")
        skills = {
            str(row.get("slot")): row
            for row in rows(references["skills"].get("skills"))
            if row.get("characterId") == character["id"]
        }
        tacticals = index(references["tactical-skills"], "tacticalSkills")
        traits = index(references["trait-skills"], "traitSkills")
        tiers = index(references["tiers"], "tiers")
        snapshot = detail.get("characterDetailStatSnapshot") or {}
        candidates = popular((snapshot.get("characterDetailStat") or {}).get("weaponStats"), 100)
        if weapon is not None:
            _, identifier = self._resolve_weapon(character, weapon)
            candidates = [row for row in candidates if str(row.get("key")) == str(identifier)]
        title = str(character.get("name") or query)
        footer = {
            **self._plain_footer(cached=bool(detail.get("_erbs_cached"))),
            "mode": mode,
            "tier": tier if mode == "RANK" else None,
            "patches": detail.get("patches", []),
            "sourceUpdatedAt": (detail.get("meta") or {}).get("updatedAt"),
        }
        if not candidates:
            return CardPayload(
                kind="character",
                title=title,
                subtitle="当前条件暂无统计数据",
                sections=(section("暂无数据", [], "items"),),
                footer={**footer, "missingReason": "no-character-statistics"},
            )
        selected = candidates[0]
        count = selected.get("count")
        summaries = [
            weapon_summary(row, snapshot.get("tierGameCount"), weapons.get(str(row.get("key")), {}))
            for row in candidates
        ]
        sections = [section("武器流派", summaries, "character-stats")]
        builds = []
        all_builds = rows(selected.get("itemBuildStats"))
        for raw in popular(all_builds, 4):
            equipment = [
                pick({"key": identifier}, items, None) for identifier in raw.get("key", [])
            ]
            best_order = popular(raw.get("orderStats"), 1)
            order = str(best_order[0].get("key", "")) if best_order else ""
            sequence = [
                equipment[int(digit) - 1]
                for digit in order
                if digit.isdigit() and 1 <= int(digit) <= len(equipment)
            ]
            builds.append(
                {
                    "name": " · ".join(row["name"] for row in equipment),
                    "equipmentItems": equipment,
                    "order": sequence,
                    "games": raw.get("count"),
                    "pickRate": ratio(raw.get("count"), count, 100),
                    "winRate": ratio(raw.get("win"), raw.get("count"), 100),
                }
            )
        sections.append(section("推荐出装 / 合成顺序", builds, "builds"))
        slot_picks = []
        for position, slot in enumerate(("武器", "胸甲", "头部", "手臂", "腿部")):
            totals: dict[str, list[float]] = defaultdict(lambda: [0, 0])
            for raw in all_builds:
                ids = raw.get("key") or []
                if position < len(ids):
                    value = totals[str(ids[position])]
                    value[0] += number(raw.get("count")) or 0
                    value[1] += number(raw.get("win")) or 0
            for identifier, (games, wins) in sorted(
                totals.items(), key=lambda row: row[1][0], reverse=True
            )[:5]:
                slot_picks.append(
                    {
                        **pick({"key": identifier, "count": games, "win": wins}, items, count),
                        "slot": slot,
                    }
                )
        sections.append(section("各部位装备", slot_picks))
        if not equipment_only:
            skill_builds = []
            for raw in popular(selected.get("skillBuildStats"), 4):
                orders = popular(raw.get("orderStats"), 1)
                order = orders[0].get("key", "") if orders else ""
                skill_builds.append(
                    {
                        "name": " → ".join(raw.get("key") or []),
                        "order": list(order),
                        "skills": [
                            {"name": slot, "imageUrl": skills.get(slot, {}).get("imageUrl")}
                            for slot in list(order)[:15]
                        ],
                        "pickRate": ratio(raw.get("count"), count, 100),
                        "winRate": ratio(raw.get("win"), raw.get("count"), 100),
                    }
                )
            sections.append(section("技能加点", skill_builds, "skills"))
            sections.append(
                section(
                    "战术技能",
                    [
                        pick(row, tacticals, count)
                        for row in popular(selected.get("tacticalSkillStats"), 4)
                    ],
                )
            )
            augments = []
            for raw in popular(selected.get("traitCoreStats"), 4):
                augments.append(
                    {
                        **pick(raw, traits, count),
                        "choices": [
                            pick(row, traits, raw.get("count"))
                            for row in popular(raw.get("stats"), 6)
                        ],
                    }
                )
            sections.append(section("潜能", augments, "augments"))
            sections.append(
                section(
                    "灌注",
                    [
                        pick(row, {**tacticals, **items, **traits}, count)
                        for row in popular(selected.get("infusionStats"), 12)
                    ],
                )
            )
            players = {str(row.get("userNum")): row for row in rows(detail.get("players"))}
            top = sorted(
                rows(detail.get("playerTiers")),
                key=lambda row: number(row.get("mmr")) or 0,
                reverse=True,
            )[:10]
            sections.append(
                section(
                    "高分玩家",
                    [
                        {
                            "name": players.get(str(row.get("userNum")), {}).get("name"),
                            "mmr": row.get("mmr"),
                            "tierName": tiers.get(str(row.get("tierId")), {}).get("name"),
                        }
                        for row in top
                    ],
                )
            )
        return CardPayload(
            kind="character",
            title=title,
            subtitle=(
                f"{'角色出装' if equipment_only else '角色详情'} · {mode} · "
                f"{tier if mode == 'RANK' else 'COBALT'}"
            ),
            sections=tuple(sections),
            footer=footer,
        )

    async def character_stats_card(
        self,
        *,
        tier: str = "diamond_plus",
        mode: str = "RANK",
    ) -> CardPayload:
        mode, tier = normalize_mode(mode), normalize_tier(tier)
        if mode not in {"RANK", "COBALT"}:
            raise InvalidQuery("角色数据仅支持排位和钴协议")
        data, characters, masteries = await asyncio.gather(
            self.client.character_stats(matching_mode=mode, team_mode=team_mode(mode), tier=tier),
            self.client.metadata("characters"),
            self.client.metadata("masteries"),
        )
        snapshot = data.get("characterStatSnapshot") or {}
        chars, weapons = index(characters, "characters"), index(masteries, "masteries")
        entries = []
        for character in rows(snapshot.get("characterStats")):
            metadata = chars.get(str(character.get("key")), {})
            for raw in rows(character.get("weaponStats")):
                entry = weapon_summary(
                    raw, snapshot.get("tierGameCount"), weapons.get(str(raw.get("key")), {})
                )
                entries.append(
                    {
                        **entry,
                        "weapon": entry["name"],
                        "weaponImageUrl": entry["imageUrl"],
                        "characterId": character.get("key"),
                        "name": metadata.get("name"),
                        "imageUrl": metadata.get("imageUrl"),
                    }
                )
        entries.sort(key=lambda row: number(row.get("tierScore")) or 0, reverse=True)
        footer = {
            **self._plain_footer(cached=bool(data.get("_erbs_cached"))),
            "mode": mode,
            "tier": tier if mode == "RANK" else None,
            "patch": snapshot.get("patch"),
            "days": snapshot.get("dt"),
        }
        if not entries:
            footer["missingReason"] = "no-character-statistics"
        return CardPayload(
            kind="global",
            title="角色数据",
            subtitle=f"{mode} · {tier}",
            sections=(section("全部角色 / 武器", entries, "character-stats"),),
            footer=footer,
        )

    async def tier_statistics_card(
        self,
        *,
        server: str = "seoul",
        cutoffs_only: bool = False,
    ) -> CardPayload:
        server = normalize_server(server)
        season = await self.client.current_season()
        season_key = season.get("type") or season.get("key")
        if not season_key:
            raise UpstreamUnavailable("DAK.GG 当前赛季缺少 seasonKey")
        leaderboard = self.client.leaderboard(season_key=str(season_key), server_name=server)
        if cutoffs_only:
            board = await leaderboard
            distribution = {}
        else:
            board, distribution = await asyncio.gather(leaderboard, self.client.tier_distribution())
        cutoffs = rows(board.get("cutoffs"))
        # Explicit tierType is authoritative; tolerate the historical positional payload.
        eternal = next((row for row in cutoffs if row.get("tierType") == 8), None)
        demigod = next((row for row in cutoffs if row.get("tierType") == 7), None)
        if eternal is None and cutoffs and all(not row.get("tierType") for row in cutoffs):
            if len(cutoffs) <= 2:
                eternal, demigod = cutoffs[-1], cutoffs[0]
        cutoff_items = [
            {"label": label, "value": row.get("mmr") if row else None}
            for label, row in (("永恒", eternal), ("半神", demigod))
        ]
        sections = [section("当前分数线", cutoff_items, "stats")]
        if not cutoffs_only:
            totals: dict[int, list[float]] = defaultdict(lambda: [0, 0])
            for row in rows(distribution.get("distributions")):
                identifier = int(row.get("tierType") or 0)
                totals[identifier][0] += number(row.get("count")) or 0
                totals[identifier][1] += number(row.get("rate")) or 0
            names = {
                1: "铁阎",
                2: "青铜",
                3: "白银",
                4: "黄金",
                5: "修罗",
                6: "灭钻",
                63: "星陨",
                66: "无瑕",
                7: "半神",
                8: "永恒",
            }
            sections.append(
                section(
                    "段位分布（全服统计）",
                    [
                        {
                            "name": names.get(key, str(key)),
                            "count": int(values[0]),
                            "rate": round(values[1] * 100, 2),
                        }
                        for key, values in sorted(
                            totals.items(),
                            key=lambda pair: pair[0] * 10 if pair[0] < 10 else pair[0],
                        )
                    ],
                )
            )
        footer = {
            **self._plain_footer(
                cached=any(data.get("_erbs_cached") for data in (season, board, distribution))
            ),
            "server": server,
            "distributionScope": "all-servers",
            "sourceUpdatedAt": board.get("updatedAt"),
        }
        return CardPayload(
            kind="global",
            title="永恒 / 半神分数线" if cutoffs_only else "段位统计",
            subtitle=f"{season.get('name', season_key)} · {server}",
            sections=tuple(sections),
            footer=footer,
        )

    @staticmethod
    def help_card() -> CardPayload:
        return CardPayload(
            kind="help",
            title="永恒轮回查询命令",
            sections=(
                section(
                    "帮助",
                    [
                        {"name": command, "description": description}
                        for command, description in COMMAND_HELP
                    ],
                ),
            ),
        )
