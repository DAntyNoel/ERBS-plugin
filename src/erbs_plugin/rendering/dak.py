"""DAK.GG desktop query layouts drawn from the shared, inspectable query payload.

No website navigation, ads or character-selection sidebar are included in cards.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..exceptions import RenderFailed

PAGE = 0xFFF4F4F4
WHITE = 0xFFFFFFFF
INK = 0xFF292C33
MUTED = 0xFF888A8E
LINE = 0xFFE6E6E8
DARK = 0xFF2C2F37
TAN = 0xFFBA947A
GREEN = 0xFF27A78F
BLUE = 0xFF3287C4
RED = 0xFFE36E73
GOLD = 0xFFD99A00


def num(value: Any, digits: int = 1, suffix: str = "") -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return "—"
    rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"{rounded:,.{digits}f}{suffix}"


def divided(row: Mapping, key: str, total_key: str = "plays", digits: int = 1) -> str:
    value, total = row.get(key), row.get(total_key)
    return num(value / total, digits) if isinstance(value, (int, float)) and total else "—"


class Drawing:
    def __init__(self, renderer, width: int, height: int):
        self.r = renderer
        self.sk = renderer._skia
        scale = renderer.config.render_scale
        if height * scale > 32760 or width * height * scale**2 > 48_000_000:
            raise RenderFailed("图片内容超出绘图尺寸限制，请缩小查询范围")
        self.surface = self.sk.Surface.MakeRasterN32Premul(
            math.ceil(width * scale), math.ceil(height * scale)
        )
        if self.surface is None:
            raise RenderFailed("无法分配 Skia 绘图画布")
        self.c = self.surface.getCanvas()
        self.c.scale(scale, scale)
        self.c.clear(PAGE)

    def rect(self, x, y, w, h, color=WHITE, radius=0):
        self.r._rect(self.c, x, y, w, h, color, radius)

    def line(self, x, y, w):
        self.c.drawLine(x, y, x + w, y, self.r._paint(LINE))

    def text(self, value, x, y, size=15, color=INK, bold=False, width=None):
        self.r._label(self.c, value, x, y, size=size, color=color, bold=bold, width=width)

    def center(self, value, x, y, w, size=15, color=INK, bold=False):
        measured = min(w, self.r._measure(value, size, bold))
        self.text(value, x + (w - measured) / 2, y, size, color, bold, w)

    def image(self, source, x, y, w, h, *, circle=False, cover=False, bg=WHITE):
        self.c.save()
        if circle:
            self.c.clipRRect(self.sk.RRect.MakeOval(self.sk.Rect.MakeXYWH(x, y, w, h)), True)
        self.r._image(self.c, source, x, y, w, h, cover=cover, background=bg)
        self.c.restore()

    def heading(self, title, x, y, w):
        self.text(title, x, y + 23, 20, bold=True, width=w)

    def table_head(self, title, x, y, w, columns=()):
        self.rect(x, y, w, 38, DARK, 3)
        self.text(title, x + 14, y + 25, 14, WHITE, width=w * 0.56)
        for name, fraction in columns:
            self.center(name, x + w * fraction, y + 25, w * 0.15, 13, WHITE)

    def item(self, item, x, y, w=43, h=29):
        grades = {
            "Common": 0xFFAAAAAA,
            "Uncommon": 0xFF6E965C,
            "Rare": 0xFF4E9AC2,
            "Epic": 0xFF8C6BB5,
            "Legend": 0xFFD0AE57,
            "Legendary": 0xFFD0AE57,
            "Mythic": 0xFFA94449,
        }
        grade = item.get("grade")
        if isinstance(grade, int):
            grade = {
                1: "Common",
                2: "Uncommon",
                3: "Rare",
                4: "Epic",
                5: "Legend",
                6: "Mythic",
            }.get(grade)
        self.image(item.get("imageUrl"), x, y, w, h, bg=grades.get(grade, LINE))

    def finish(self):
        encoded = self.surface.makeImageSnapshot().encodeToData(self.sk.kPNG, 100)
        if encoded is None:
            raise RenderFailed("Skia PNG 编码失败")
        return bytes(encoded)

    def footer(self, payload, x, y, w):
        self.line(x, y, w)
        for i, line in enumerate(self.r._footer_lines(payload, w)):
            self.text(line, x, y + 25 + 22 * i, 13, MUTED, width=w)


def render_player(renderer, payload) -> bytes:
    sections = {row.get("type"): row for row in payload.sections}
    overview = payload.sections[0]
    profile = overview["profile"]
    stats = {row.get("label"): row.get("value") for row in overview.get("items", [])}
    rank = sections.get("rank", {})
    rank_stats = {row.get("label"): row.get("value") for row in rank.get("items", [])}
    matches = next(
        (s.get("items", []) for s in payload.sections if s.get("title") == "最近对局"), []
    )
    heroes = sections.get("hero-pool", {}).get("items", [])
    teammates = overview.get("teammates", [])
    left_end = 850 + len(heroes) * 70 + 90 + len(teammates) * 70
    right_end = 490 + max(1, len(matches)) * 110
    bottom = max(left_end, right_end) + 28
    footer_height = 45 + 22 * len(renderer._footer_lines(payload, 1250))
    d = Drawing(renderer, 1290, bottom + footer_height)
    d.image(profile.get("bannerUrl"), 20, 20, 1250, 205, cover=True, bg=DARK)
    d.image(profile.get("imageUrl"), 20, 20, 260, 205, cover=True, bg=DARK)
    d.rect(300, 43, 62, 24, 0xB0000000, 12)
    d.text(f"Lv.{profile.get('level', '—')}", 309, 60, 14, WHITE)
    d.text(payload.title, 300, 108, 34, WHITE, True, 650)
    d.text(profile.get("seasonName") or "赛季未知", 1120, 188, 18, WHITE, width=130)
    d.rect(300, 135, 105, 40, GREEN, 3)
    d.center("玩家战绩", 300, 161, 105, 17, WHITE, True)
    d.rect(20, 225, 1250, 48, 0xFF353844)
    for i, name in enumerate(("总览", "实验体", "历史对局", "皮肤统计")):
        d.rect(30 + i * 115, 225, 115, 48, WHITE if i == 0 else 0xFF353844)
        d.center(name, 30 + i * 115, 255, 115, 17, INK if i == 0 else WHITE, i == 0)

    # Left: rank, twelve season metrics and the daily RP history.
    x, y, w = 20, 295, 380
    d.rect(x, y, w, 525)
    d.center(
        f"排位 · {profile.get('seasonName') or '—'}",
        x,
        y + 32,
        w,
        19,
        bold=True,
    )
    d.line(x, y + 50, w)
    d.image(rank.get("imageUrl"), x + 28, y + 66, 100, 100)
    d.text(f"{num(rank_stats.get('MMR'), 0)} RP", x + 145, y + 90, 25, TAN, True)
    d.text(f"{rank.get('tierName', '未定级')} {rank_stats.get('小段', '')}", x + 145, y + 119, 16)
    d.text(f"{rank_stats.get('小段 RP', '—')} RP", x + 145, y + 144, 14, MUTED)
    labels = [
        ("平均TK", "平均 TK", 2, ""),
        ("胜率", "胜率 %", 1, "%"),
        ("游戏场次", "场次", 0, ""),
        ("平均击杀", "平均击杀", 2, ""),
        ("TOP 2", "TOP 2 %", 1, "%"),
        ("平均伤害", "平均伤害", 0, ""),
        ("平均助攻", "平均助攻", 1, ""),
        ("TOP 3", "TOP 3 %", 1, "%"),
        ("平均排名", "平均排名", 1, ""),
        ("平均野怪击杀", "平均野怪击杀", 1, ""),
        ("平均Credit获得", "平均Credit获得", 0, ""),
        ("平均视野贡献", "平均视野贡献", 2, ""),
    ]
    for i, (label, key, digits, suffix) in enumerate(labels):
        cx, cy = x + 16 + i % 3 * 122, y + 180 + i // 3 * 48
        d.text(label, cx, cy + 14, 12, MUTED, width=116)
        d.rect(cx, cy + 21, 106, 3, LINE)
        d.text(num(stats.get(key), digits, suffix), cx, cy + 43, 16, bold=True)
    _history(d, profile.get("mmrHistory") or [], x + 10, y + 395, w - 20, 116)
    y += 550
    d.table_head("实验体", x, y, w, (("胜率", 0.38), ("RP", 0.56), ("均伤", 0.76)))
    for i, hero in enumerate(heroes):
        cy = y + 38 + i * 70
        d.rect(x, cy, w, 70)
        d.image(hero.get("imageUrl"), x + 8, cy + 14, 38, 38, circle=True)
        d.text(hero.get("name"), x + 52, cy + 26, 13, width=92)
        d.text(f"{hero.get('plays', '—')} 场", x + 52, cy + 47, 12, MUTED)
        d.center(hero.get("winRate", "—"), x + 142, cy + 35, 62, 13)
        d.center(num(hero.get("mmrGain"), 0), x + 207, cy + 35, 68, 13, TAN)
        d.center(divided(hero, "damageToPlayer", digits=0), x + 278, cy + 35, 94, 13)
        d.line(x, cy + 69, w)
    y += 38 + len(heroes) * 70 + 25
    d.table_head("一起游戏的玩家", x, y, w, (("胜率", 0.55), ("均排", 0.77)))
    for i, mate in enumerate(teammates):
        cy = y + 38 + i * 70
        d.rect(x, cy, w, 70)
        d.image(mate.get("imageUrl"), x + 8, cy + 15, 38, 38, circle=True)
        d.text(mate.get("name"), x + 55, cy + 27, 14, width=142)
        d.text(f"{mate.get('plays', '—')} 场", x + 55, cy + 49, 12, MUTED)
        d.center(num(mate.get("winRate"), 1, "%"), x + 205, cy + 37, 76, 14)
        d.center(num(mate.get("avgRank")), x + 291, cy + 37, 78, 14)
    if not teammates:
        d.rect(x, y + 38, w, 60)
        d.text("暂无一起游戏的玩家", x + 20, y + 73, 14, MUTED)

    # Right: mode tabs, recent summary and compact match rows.
    x, y, w = 420, 295, 850
    mode_name = profile.get("modeName", "排位")
    for i, name in enumerate(("全部", "排位", "匹配", "钴协议")):
        d.rect(x + i * w / 4, y, w / 4 - 1, 44, GOLD if name == mode_name else WHITE)
        d.center(name, x + i * w / 4, y + 28, w / 4, 17, WHITE if name == mode_name else INK)
    y += 56
    d.rect(x, y, w, 126)
    d.text(f"最近 {len(matches)} 场对局（{mode_name}）", x + 16, y + 27, 16, bold=True)
    metrics = [
        (
            "平均排名",
            num(sum(m.get("rank", 0) for m in matches) / len(matches)) if matches else "—",
        ),
        ("胜利次数", str(sum(m.get("rank") == 1 for m in matches))),
        ("TOP 3", str(sum((m.get("rank") or 999) <= 3 for m in matches))),
        (
            "平均TK",
            num(sum(m.get("teamKills", 0) for m in matches) / len(matches), 2) if matches else "—",
        ),
    ]
    for i, (label, value) in enumerate(metrics):
        d.center(label, x + 80 + i * 175, y + 56, 175, 13, MUTED)
        d.center(value, x + 80 + i * 175, y + 80, 175, 19, GREEN if i == 1 else INK, True)
    rank_size, rank_gap = 24, 5
    ranks_width = len(matches) * (rank_size + rank_gap) - rank_gap
    for i, match in enumerate(reversed(matches)):
        color = (
            GREEN if match.get("rank") == 1 else BLUE if match.get("rank") in {2, 3} else 0xFFD9D9D9
        )
        tx = x + (w - ranks_width) / 2 + i * (rank_size + rank_gap)
        d.rect(tx, y + 94, rank_size, rank_size, color, 4)
        d.center(
            match.get("rank"),
            tx,
            y + 111,
            rank_size,
            13,
            WHITE if match.get("rank", 9) <= 3 else MUTED,
            True,
        )
    y = 490
    for i, match in enumerate(matches):
        _player_match(d, match, x, y + i * 110, w)
    if not matches:
        d.rect(x, y, w, 110)
        d.center("当前筛选条件暂无对局", x, y + 64, w, 20, MUTED)
    d.footer(payload, 20, bottom, 1250)
    return d.finish()


def _history(d, items, x, y, w, h):
    values = [row.get("mmr") for row in items]
    if not values or any(not isinstance(v, (int, float)) for v in values):
        d.center("暂无段位走势", x, y + 50, w, 14, MUTED)
        return
    low, high = min(values), max(values)
    span = max(100, high - low)
    path = d.sk.Path()
    for i, value in enumerate(values):
        px = x + 45 + i * (w - 60) / max(1, len(values) - 1)
        py = y + h - 25 - (value - low) / span * (h - 42)
        if i:
            path.lineTo(px, py)
        else:
            path.moveTo(px, py)
        d.c.drawCircle(px, py, 3, d.r._paint(GOLD))
        stamp = str(items[i].get("date", ""))
        d.center(f"{stamp[4:6]}/{stamp[6:8]}", px - 22, y + h - 2, 44, 10, MUTED)
    d.text(num(high, 0), x, y + 15, 11, MUTED)
    d.text(num(low, 0), x, y + h - 25, 11, MUTED)
    d.c.drawPath(path, d.r._paint(GOLD, stroke=2))


def _player_match(d, row, x, y, w):
    rank = row.get("rank")
    color = GREEN if rank == 1 else BLUE if rank in {2, 3} else 0xFF555D67
    d.rect(x, y, w, 100, WHITE, 4)
    d.rect(x, y, 7, 100, color, 3)
    d.text(f"#{rank or '—'}", x + 18, y + 24, 18, color, True)
    d.text(row.get("modeName"), x + 18, y + 46, 13, MUTED)
    try:
        stamp = datetime.fromisoformat(str(row.get("startedAt"))).astimezone(
            timezone(timedelta(hours=d.r.config.render_timezone_offset_hours))
        )
        date, time = stamp.strftime("%m/%d"), stamp.strftime("%H:%M")
    except (ValueError, TypeError):
        date, time = "—", "—"
    d.text(time, x + 18, y + 66, 12, MUTED)
    d.text(date, x + 18, y + 84, 12, MUTED)
    d.image(row.get("imageUrl"), x + 89, y + 13, 57, 57, circle=True)
    d.rect(x + 128, y + 53, 22, 19, DARK, 9)
    d.center(row.get("level"), x + 128, y + 67, 22, 11, WHITE)
    d.center(row.get("characterName"), x + 77, y + 88, 90, 12)
    icons = [row.get("tacticalSkill") or {}, *(row.get("traitSkills") or [])]
    for i, icon in enumerate(icons[:6]):
        d.image(
            icon.get("imageUrl"), x + 159 + i % 2 * 25, y + 12 + i // 2 * 24, 22, 22, circle=True
        )
    server = str(row.get("serverName") or "").strip()
    server_name = {
        "asia": "亚一",
        "seoul": "亚一",
        "asia2": "亚二",
        "asia3": "亚三",
        "ohio": "美服",
        "frankfurt": "欧服",
        "saopaulo": "南美",
    }.get(server.casefold(), server or "未知区服")
    game_id = row.get("gameId")
    d.center(
        f"{server_name}—{game_id if game_id is not None else '—'}",
        x + 218,
        y + 18,
        464,
        12,
        0xFF555555 if server_name == "亚一" else 0xFFAAAAAA,
        True,
    )
    d.center(
        f"{row.get('teamKills', '—')} / {row.get('kills', '—')} / {row.get('assists', '—')}",
        x + 218,
        y + 46,
        128,
        16,
    )
    d.center("TK / K / A", x + 218, y + 69, 128, 12, MUTED)
    d.center(num(row.get("damage"), 0), x + 355, y + 46, 102, 16)
    d.center("伤害", x + 355, y + 69, 102, 12, MUTED)
    gain = row.get("mmrGain")
    ranked = row.get("matchingMode") == 3
    if ranked:
        value = num(row.get("mmrAfter"), 0)
        if isinstance(gain, (int, float)):
            value += f" ({gain:+g})"
    else:
        deaths = row.get("deaths")
        value = (
            num((row.get("kills", 0) + row.get("assists", 0)) / max(1, deaths), 2)
            if isinstance(deaths, int)
            else "—"
        )
    d.center(
        value,
        x + 464,
        y + 46,
        132,
        15,
        GREEN if ranked and gain and gain > 0 else RED if ranked and gain and gain < 0 else INK,
    )
    d.center("RP" if ranked else "KDA", x + 464, y + 69, 132, 12, MUTED)
    d.center(row.get("routeId"), x + 600, y + 46, 82, 15)
    d.center("路径ID", x + 600, y + 69, 82, 12, MUTED)
    equipment = row.get("equipmentItems", [])[:5]
    for start in range(0, len(equipment), 3):
        equipment_row = equipment[start:start + 3]
        row_x = x + 695 + (3 - len(equipment_row)) * 47 / 2
        for i, item in enumerate(equipment_row):
            d.item(item, row_x + i * 47, y + 20 + start // 3 * 32)


def render_character(renderer, payload) -> bytes:
    groups = {s.get("title"): s.get("items", []) for s in payload.sections}
    info = payload.sections[0]["character"]
    weapons = groups.get("武器流派", [])
    main = weapons[0] if weapons else {}
    skills, tacticals = groups.get("技能加点", []), groups.get("战术技能", [])
    augments = groups.get("潜能", [])[:3]
    builds = groups.get("推荐出装 / 合成顺序", [])
    slots = groups.get("各部位装备", [])
    equipment_only = not any(s.get("title") == "技能加点" for s in payload.sections)
    # Keep the desktop content width, with no all-character selection column.
    y = 390
    skills_y = y
    if not equipment_only:
        y += 60 + max(1, len(skills), len(tacticals)) * 70 + 25
    augments_y = y
    augment_height = max(
        [0, *(110 + max(1, len(a.get("builds") or a.get("choices") or [])) * 52 for a in augments)]
    )
    if not equipment_only:
        y += 52 + max(100, augment_height) + 35
    builds_y = y
    y += 88 + sum(
        68 + (len(builds[0].get("orders", [])) * 43 if i == 0 else 0) for i in range(len(builds))
    )
    slots_y = y + 25
    slot_groups = [
        (name, [r for r in slots if r.get("slot") == name])
        for name in ("武器", "胸甲", "头部", "手臂", "腿部")
    ]
    # Desktop DAK puts the weapon alone, then chest/head and arm/legs in pairs.
    slot_rows = (slot_groups[:1], slot_groups[1:3], slot_groups[3:])
    row_heights = [max(38 + max(1, len(rows)) * 52 for _, rows in row) for row in slot_rows]
    bottom = slots_y + 52 + sum(row_heights) + 65
    d = Drawing(renderer, 1000, bottom + 45 + 22 * len(renderer._footer_lines(payload, 960)))
    d.image(info.get("imageUrl"), 20, 20, 100, 100)
    d.rect(138, 27, 34, 34, TAN, 6)
    d.center(main.get("tier") or "—", 138, 51, 34, 24, WHITE, True)
    d.text(f"{main.get('name', '')} {payload.title}", 184, 56, 27, bold=True, width=760)
    for i, skill in enumerate(info.get("skills", [])):
        d.image(skill.get("imageUrl"), 138 + i * 45, 77, 38, 38, bg=DARK)
        d.text(skill.get("name"), 164 + i * 45, 111, 12, WHITE, True)
    mode = "钴协议" if payload.footer.get("mode") == "COBALT" else "排位"
    d.rect(20, 144, 76, 40, DARK)
    d.center(mode, 20, 170, 76, 17, WHITE, True)
    for i, weapon in enumerate(weapons):
        d.rect(112 + i * 155, 144, 147, 40, WHITE if i else DARK)
        total = sum(w.get("games") or 0 for w in weapons)
        rate = (weapon.get("games") or 0) / total * 100 if total else None
        d.center(
            f"{weapon.get('name', '—')} {num(rate, 1, '%')}",
            112 + i * 155,
            170,
            147,
            14,
            INK if i else WHITE,
        )
    tier = {
        "diamond_plus": "灭钻+",
        "meteorite_plus": "星陨+",
        "mithril_plus": "无瑕+",
        "immortal": "永恒",
    }.get(payload.footer.get("tier"), payload.footer.get("tier") or mode)
    d.rect(668, 144, 145, 40)
    d.center(tier, 668, 170, 145, 16)
    d.rect(825, 144, 155, 40)
    patch = info.get("patch")
    patch_name = f"{patch // 1000}.{patch % 1000 // 10}" if isinstance(patch, int) else patch
    d.center(f"最近7日  v{patch_name or '—'}", 825, 170, 155, 14)
    d.rect(20, 203, 960, 44, 0xFFE8E8ED)
    for i, name in enumerate(("大纲", "物品", "路径", "潜能", "战术技能", "技能", "介绍")):
        d.center(name, 24 + i * 100, 231, 100, 16, TAN if i == 0 else INK, i == 0)
    keys = [
        ("胜率", "winRate", "win", "%"),
        ("TOP 3", "top3Rate", "top3", "%"),
        ("获得RP", "rpChange", "mmrGain", ""),
        ("选择率", "pickRate", "count", "%"),
        ("平均排名", "avgRank", "place", ""),
        ("平均击杀", "avgKills", "playerKill", ""),
    ]
    for i, (label, key, rank_key, suffix) in enumerate(keys):
        x = 20 + i * 162
        d.rect(x, 275, 150, 94, WHITE, 3)
        d.center(label, x, 300, 150, 14)
        d.center(
            num(main.get(key), 2 if key in {"pickRate", "avgKills"} else 1, suffix),
            x,
            329,
            150,
            22,
            bold=True,
        )
        rank = (main.get("metricRanks") or {}).get(rank_key)
        d.center(f"#{rank} / {main.get('rankSize')}" if rank else "—", x, 352, 150, 12, MUTED)
    if not equipment_only:
        _skills(d, skills, tacticals, skills_y)
        _augments(d, augments, augments_y)
    _builds(d, builds, builds_y)
    d.heading("物品统计", 20, slots_y, 960)
    row_y = slots_y + 52
    for row, row_height in zip(slot_rows, row_heights, strict=True):
        for j, (name, rows) in enumerate(row):
            x = 20 + j * 490
            _slot_table(d, name, rows, x, row_y, 470)
        row_y += row_height + 20
    d.footer(payload, 20, bottom, 960)
    return d.finish()


def _skills(d, skills, tacticals, y):
    d.heading("推荐技能", 20, y, 620)
    d.heading("推荐战术技能", 655, y, 325)
    y += 48
    d.table_head("技能构建", 20, y, 620)
    d.table_head("战术技能", 655, y, 325)
    for i in range(max(1, len(skills), len(tacticals))):
        cy = y + 38 + i * 70
        d.rect(20, cy, 620, 70)
        d.rect(655, cy, 325, 70)
        if i < len(skills):
            row = skills[i]
            for j, skill in enumerate(row.get("priority", [])):
                d.image(skill.get("imageUrl"), 30 + j * 40, cy + 18, 32, 32, bg=DARK)
                d.text(skill.get("name"), 51 + j * 40, cy + 47, 11, WHITE, True)
            for j, slot in enumerate(row.get("order", [])[:15]):
                d.rect(202 + j * 20, cy + 25, 18, 22, TAN if slot == "Q" else LINE, 3)
                d.center(slot, 202 + j * 20, cy + 41, 18, 12, WHITE if slot == "Q" else INK)
            d.text(f"选择率 {num(row.get('pickRate'), 1, '%')}", 514, cy + 29, 12, TAN)
            d.text(f"胜率 {num(row.get('winRate'), 1, '%')}", 514, cy + 50, 12)
        if i < len(tacticals):
            row = tacticals[i]
            d.image(row.get("imageUrl"), 668, cy + 18, 34, 34, circle=True)
            d.text(row.get("name"), 714, cy + 41, 15, width=130)
            d.text(f"选择率 {num(row.get('pickRate'), 1, '%')}", 849, cy + 29, 12, TAN)
            d.text(f"胜率 {num(row.get('winRate'), 1, '%')}", 849, cy + 50, 12)
        d.line(20, cy + 69, 620)
        d.line(655, cy + 69, 325)


def _augments(d, augments, y):
    d.heading("推荐潜能", 20, y, 960)
    y += 52
    for i, row in enumerate(augments):
        x, w = 20 + i * 325, 310
        builds = row.get("builds") or []
        if not builds:
            builds = [{"choices": [choice], **choice} for choice in row.get("choices", [])[:4]]
        d.rect(x, y, w, 110 + max(1, len(builds)) * 52)
        d.image(row.get("imageUrl"), x + 14, y + 17, 40, 40, circle=True)
        d.text(row.get("name"), x + 67, y + 32, 16, width=w - 80)
        d.text(
            f"选择率 {num(row.get('pickRate'), 1, '%')}  |  胜率 {num(row.get('winRate'), 1, '%')}",
            x + 67,
            y + 57,
            12,
            TAN,
            width=w - 80,
        )
        d.rect(x, y + 75, w, 35, 0xFFE8E8ED)
        d.text("潜能", x + 14, y + 98, 13, MUTED)
        d.text("选择率", x + 196, y + 98, 13, MUTED)
        d.text("胜率", x + 260, y + 98, 13, MUTED)
        for j, build in enumerate(builds):
            cy = y + 110 + j * 52
            for k, choice in enumerate(build.get("choices", [])[:4]):
                d.image(choice.get("imageUrl"), x + 12 + k * 39, cy + 12, 28, 28, circle=True)
            d.text(num(build.get("pickRate"), 1, "%"), x + 194, cy + 32, 13, TAN)
            d.text(num(build.get("winRate"), 1, "%"), x + 259, cy + 32, 13)
            d.line(x, cy + 51, w)
    if not augments:
        d.text("当前条件暂无潜能数据", 20, y + 42, 16, MUTED)


def _builds(d, builds, y):
    d.heading("最终装备", 20, y, 960)
    y += 50
    d.table_head(
        "最终项目构建 / 合成顺序",
        20,
        y,
        960,
        (("选择率", 0.62), ("胜率", 0.75), ("平均排名", 0.86)),
    )
    y += 38
    for i, row in enumerate(builds):
        d.rect(20, y, 960, 68)
        for j, item in enumerate(row.get("equipmentItems", [])):
            d.item(item, 35 + j * 61, y + 17, 53, 34)
        d.center(num(row.get("pickRate"), 1, "%"), 615, y + 42, 110, 15, TAN)
        d.center(num(row.get("winRate"), 1, "%"), 735, y + 42, 110, 15)
        d.center(num(row.get("avgRank"), 2), 855, y + 42, 110, 15)
        d.line(20, y + 67, 960)
        y += 68
        if i == 0:
            for order in row.get("orders", []):
                d.rect(20, y, 960, 43, 0xFFEDEDEF)
                for j, item in enumerate(order.get("equipmentItems", [])):
                    d.item(item, 48 + j * 68, y + 8, 42, 27)
                    if j < 4:
                        d.text("›", 96 + j * 68, y + 28, 18, MUTED)
                d.center(num(order.get("pickRate"), 1, "%"), 615, y + 28, 110, 14, TAN)
                y += 43
    if not builds:
        d.rect(20, y, 960, 68)
        d.text("当前条件暂无装备数据", 36, y + 40, 16, MUTED)


def _slot_table(d, name, rows, x, y, w):
    d.table_head(name, x, y, w, (("选择率", 0.59), ("平均排名", 0.79)))
    y += 38
    for i, row in enumerate(rows):
        cy = y + i * 52
        d.rect(x, cy, w, 52)
        d.item(row, x + 12, cy + 10, 44, 30)
        d.text(row.get("name"), x + 68, cy + 32, 14, width=w * 0.43)
        d.center(num(row.get("pickRate"), 1, "%"), x + w * 0.57, cy + 32, 90, 14, TAN)
        d.center(num(row.get("avgRank"), 2), x + w * 0.79, cy + 32, 85, 14)
        d.line(x, cy + 51, w)
    if not rows:
        d.rect(x, y, w, 52)
        d.text("暂无数据", x + 16, y + 33, 14, MUTED)
