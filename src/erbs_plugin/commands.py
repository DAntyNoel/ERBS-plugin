"""Framework-neutral DAK.GG command names and filters shared by API and CLI."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from .exceptions import InvalidQuery

ALIASES = {
    "player": "overview",
    "player-overview": "overview",
    "best_match": "best-match",
    "hero_pool": "hero-pool",
    "查询玩家": "search",
    "查玩家": "search",
    "查询角色": "character",
    "查询角色装备": "character-equipment",
    "角色数据": "character-stats",
    "角色数据统计": "character-stats",
    "段位统计": "tier-stats",
    "永恒多少分": "tier-cutoffs",
    "查询装备": "item",
    "帮助": "help",
}
MODES = {"排位": "RANK", "普通": "NORMAL", "钴协议": "COBALT", "全部": "ALL"}
TIERS = {
    "灭钻": "diamond_plus",
    "钻石": "diamond_plus",
    "无暇": "mithril_plus",
    "无瑕": "mithril_plus",
    "星陨": "meteorite_plus",
    "修罗": "platinum_plus",
    "黄金": "gold",
    "白银": "silver",
    "青铜": "bronze",
    "铁阎": "iron",
    "in1000": "in1000",
}
SERVERS = {
    "亚1": "seoul",
    "亚一": "seoul",
    "国际服": "seoul",
    "亚2": "asia2",
    "亚二": "asia2",
    "国服": "asia2",
    "亚3": "asia3",
    "亚三": "asia3",
    "美服": "ohio",
    "美1": "ohio",
    "欧服": "frankfurt",
    "欧1": "frankfurt",
    "南美": "saopaulo",
    "南1": "saopaulo",
    "全球": "global",
}


def normalize_operation(value: str) -> str:
    key = value.strip().lstrip("/").casefold().replace("_", "-")
    return ALIASES.get(key, key)


def _filter(value: str, aliases: dict[str, str], label: str) -> str:
    key = value.strip().casefold()
    normalized = {
        **{k.casefold(): v for k, v in aliases.items()},
        **{v.casefold(): v for v in aliases.values()},
    }
    if key not in normalized:
        raise InvalidQuery(f"不支持的{label}：{value}")
    return normalized[key]


def normalize_mode(value: str = "RANK") -> str:
    return _filter(value, MODES, "模式")


def normalize_tier(value: str = "diamond_plus") -> str:
    return _filter(value, TIERS, "段位")


def normalize_server(value: str = "seoul") -> str:
    return _filter(value, {**SERVERS, "global": "global"}, "服务器")


def team_mode(mode: str) -> str:
    return {"COBALT": "COBALT", "ALL": "ALL"}.get(normalize_mode(mode), "SQUAD")


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    operation: str
    arguments: tuple[str, ...] = ()
    mode: str = "RANK"
    tier: str = "diamond_plus"
    server: str = "seoul"


def parse_command(text: str) -> ParsedCommand:
    try:
        tokens = shlex.split(text.strip())
    except ValueError as exc:
        raise InvalidQuery(f"命令引号不匹配：{exc}") from exc
    if not tokens:
        raise InvalidQuery("请输入命令，例如 /查询玩家 玩家名称")
    operation = normalize_operation(tokens.pop(0))
    if operation == "help" and not tokens:
        return ParsedCommand(operation)
    if operation == "search" and 1 <= len(tokens) <= 2:
        return ParsedCommand(
            operation, (tokens[0],), mode=normalize_mode(tokens[1]) if len(tokens) == 2 else "RANK"
        )
    if operation in {"character", "character-equipment"} and 1 <= len(tokens) <= 3:
        return ParsedCommand(
            operation,
            (tokens[0],),
            mode=normalize_mode(tokens[1]) if len(tokens) >= 2 else "RANK",
            tier=normalize_tier(tokens[2]) if len(tokens) == 3 else "diamond_plus",
        )
    if operation == "character-stats" and len(tokens) <= 1:
        return ParsedCommand(
            operation, tier=normalize_tier(tokens[0]) if tokens else "diamond_plus"
        )
    if operation in {"tier-stats", "tier-cutoffs"} and len(tokens) <= 1:
        return ParsedCommand(operation, server=normalize_server(tokens[0]) if tokens else "seoul")
    if operation == "item" and tokens:
        return ParsedCommand(operation, (" ".join(tokens),))
    raise InvalidQuery("命令或参数不正确，请使用 /帮助 查看查询命令")


COMMAND_HELP = (
    ("/查询玩家 <昵称> [排位/普通/钴协议/全部]", "玩家资料与最近对局"),
    ("/查询角色 <角色> [排位/钴协议] [段位]", "角色、技能、出装与潜能"),
    ("/查询角色装备 <角色> [排位/钴协议] [段位]", "角色出装与合成顺序"),
    ("/角色数据 [段位]", "全部角色及武器统计"),
    ("/段位统计 [服务器]", "段位分布及分数线"),
    ("/永恒多少分 [服务器]", "永恒与半神分数线"),
    ("/查询装备 <名称/ID/拼音>", "装备属性与合成材料"),
)
