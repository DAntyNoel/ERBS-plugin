from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path

from .config import ERBSConfig
from .models import CardPayload
from .rendering import HtmlCardRenderer


@dataclass(frozen=True, slots=True)
class CardPreview:
    operation: str
    description: str
    payload: CardPayload


@dataclass(frozen=True, slots=True)
class PreviewBuild:
    output_directory: Path
    index: Path
    manifest: Path
    images: tuple[Path, ...]


def _icon(label: str, start: str, end: str) -> str:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/>
</linearGradient></defs>
<rect width="128" height="128" rx="24" fill="url(#g)"/>
<text x="64" y="73" text-anchor="middle" fill="white"
 font-family="Arial, sans-serif" font-size="34" font-weight="700">{label}</text>
</svg>"""
    encoded = base64.b64encode(svg.encode()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


_PLAYER_ICON = _icon("ER", "#19b99a", "#1474a8")
_CHARACTER_ICON = _icon("C", "#7848db", "#d74a8b")
_ITEM_ICON = _icon("I", "#d49a22", "#ce4f2d")
_ROUTE_ICON = _icon("R", "#2b7f5f", "#59b54b")


def _card(
    operation: str,
    subtitle: str,
    sections: tuple[dict[str, object], ...],
    *,
    kind: str = "player",
    title: str = "预览玩家",
) -> CardPreview:
    return CardPreview(
        operation=operation,
        description=subtitle,
        payload=CardPayload(
            kind=kind,
            title=title,
            subtitle=subtitle,
            sections=sections,
            footer={"source": "DAK.GG", "cached": operation in {"rank", "skins"}},
        ),
    )


CARD_PREVIEWS = (
    _card(
        "overview",
        "玩家综合资料",
        (
            {
                "title": "赛季概览",
                "type": "stats",
                "items": [
                    {"label": "等级", "value": 87},
                    {"label": "MMR", "value": 8123},
                    {"label": "场次", "value": 339},
                    {"label": "胜场", "value": 54},
                    {"label": "TOP 3", "value": 126},
                    {"label": "击杀", "value": 918},
                ],
            },
        ),
    ),
    _card(
        "rank",
        "段位信息",
        (
            {
                "title": "当前段位",
                "type": "stats",
                "items": [
                    {"label": "MMR", "value": 8123},
                    {"label": "Tier ID", "value": 9},
                    {"label": "小段", "value": 1},
                    {"label": "小段 RP", "value": 83},
                ],
            },
        ),
    ),
    _card(
        "stats",
        "赛季统计",
        (
            {
                "title": "表现",
                "type": "stats",
                "items": [
                    {"label": "场次", "value": 339},
                    {"label": "胜率", "value": "15.9%"},
                    {"label": "TOP 2", "value": 91},
                    {"label": "TOP 3", "value": 126},
                    {"label": "平均击杀", "value": "2.71"},
                    {"label": "平均助攻", "value": "4.82"},
                    {"label": "平均伤害", "value": "18,642"},
                    {"label": "平均 TK", "value": "7.53"},
                ],
            },
        ),
    ),
    _card(
        "matches",
        "最近 5 场",
        (
            {
                "title": "战绩",
                "type": "items",
                "items": [
                    {
                        "name": "#1 · 艾玛",
                        "imageUrl": _CHARACTER_ICON,
                        "kills": 8,
                        "assists": 7,
                        "damage": 27841,
                        "mmrGain": 34,
                        "equipment": "秘银装甲 · 智能手环 · 圣法衣",
                    },
                    {
                        "name": "#4 · 妮琪",
                        "imageUrl": _PLAYER_ICON,
                        "kills": 3,
                        "assists": 5,
                        "damage": 16402,
                        "mmrGain": -7,
                        "equipment": "龙鳞 · 运动手表 · 战斗服",
                    },
                ],
            },
        ),
        kind="matches",
    ),
    _card(
        "recent",
        "近期状态",
        (
            {
                "title": "最近 20 场摘要",
                "type": "stats",
                "items": [
                    {"label": "场次", "value": 20},
                    {"label": "胜场", "value": 4},
                    {"label": "TOP 3", "value": 11},
                    {"label": "平均排名", "value": "#3.2"},
                ],
            },
            {
                "title": "名次序列",
                "type": "items",
                "items": [{"name": rank} for rank in ("#1", "#2", "#6", "#3", "#4")],
            },
        ),
        kind="matches",
    ),
    _card(
        "characters",
        "实验体统计",
        (
            {
                "title": "常用实验体",
                "type": "items",
                "items": [
                    {"name": "艾玛", "imageUrl": _CHARACTER_ICON, "play": 72, "win": 18},
                    {"name": "妮琪", "imageUrl": _PLAYER_ICON, "play": 48, "win": 9},
                ],
            },
        ),
        kind="characters",
    ),
    _card(
        "skins",
        "皮肤使用统计",
        (
            {
                "title": "最近战绩中的皮肤",
                "type": "items",
                "items": [
                    {"name": "午夜魔术师 艾玛", "imageUrl": _CHARACTER_ICON, "count": 12},
                    {"name": "冠军 妮琪", "imageUrl": _PLAYER_ICON, "count": 7},
                ],
            },
        ),
        kind="characters",
    ),
    _card(
        "teammates",
        "近期队友",
        (
            {
                "title": "最近共同游戏",
                "type": "items",
                "items": [
                    {"name": "队友 Alpha", "games": 4},
                    {"name": "队友 Beta", "games": 2},
                    {"name": "队友 Gamma", "games": 1},
                ],
            },
        ),
    ),
    _card(
        "multi",
        "多人查询",
        (
            {
                "title": "玩家",
                "type": "items",
                "items": [
                    {"name": "玩家 Alpha", "mmr": 8123, "level": 87, "plays": 339},
                    {"name": "玩家 Beta", "mmr": 7760, "level": 64, "plays": 205},
                    {"name": "玩家 Gamma", "mmr": 7421, "level": 52, "plays": 188},
                ],
            },
        ),
        kind="comparison",
        title="玩家 Alpha / 玩家 Beta / 玩家 Gamma",
    ),
    _card(
        "compare",
        "玩家对比",
        (
            {
                "title": "核心数据",
                "type": "comparison",
                "left": "玩家 Alpha",
                "right": "玩家 Beta",
                "rows": [
                    {"label": "场次", "left": 339, "right": 205},
                    {"label": "胜场", "left": 54, "right": 39},
                    {"label": "TOP 3", "left": 126, "right": 82},
                    {"label": "击杀", "left": 918, "right": 604},
                    {"label": "伤害", "left": 6321138, "right": 3924510},
                ],
            },
        ),
        kind="comparison",
        title="玩家 Alpha VS 玩家 Beta",
    ),
    _card(
        "best-match",
        "近期最佳局",
        (
            {
                "title": "最佳表现",
                "type": "items",
                "items": [
                    {
                        "name": "#1 · 艾玛",
                        "imageUrl": _CHARACTER_ICON,
                        "kills": 11,
                        "assists": 9,
                        "teamKills": 20,
                        "damage": 32140,
                        "mmrGain": 42,
                    }
                ],
            },
        ),
        kind="matches",
    ),
    _card(
        "hero-pool",
        "英雄池",
        (
            {
                "title": "常用实验体",
                "type": "items",
                "items": [
                    {"name": "艾玛", "imageUrl": _CHARACTER_ICON, "play": 72, "win": 18},
                    {"name": "妮琪", "imageUrl": _PLAYER_ICON, "play": 48, "win": 9},
                    {"name": "卡拉", "imageUrl": _ROUTE_ICON, "play": 31, "win": 6},
                ],
            },
        ),
        kind="characters",
    ),
    _card(
        "equipment",
        "出装习惯",
        (
            {
                "title": "装备频率",
                "type": "items",
                "items": [
                    {"name": "秘银装甲", "imageUrl": _ITEM_ICON, "count": 16},
                    {"name": "智能手环", "imageUrl": _PLAYER_ICON, "count": 12},
                    {"name": "圣法衣", "imageUrl": _CHARACTER_ICON, "count": 9},
                ],
            },
        ),
        kind="characters",
    ),
    _card(
        "leaderboard",
        "第 1 页",
        (
            {
                "title": "排名",
                "type": "items",
                "items": [
                    {"name": "Rank One", "rank": 1, "mmr": 11842, "tier": "Immortal"},
                    {"name": "Rank Two", "rank": 2, "mmr": 11690, "tier": "Immortal"},
                    {"name": "Rank Three", "rank": 3, "mmr": 11571, "tier": "Immortal"},
                ],
            },
        ),
        kind="global",
        title="排行榜",
    ),
    _card(
        "character",
        "角色强度",
        (
            {
                "title": "统计",
                "type": "items",
                "items": [
                    {
                        "name": "艾玛 · 暗器",
                        "imageUrl": _CHARACTER_ICON,
                        "pickRate": "4.8%",
                        "winRate": "12.6%",
                        "averageRank": 3.4,
                    }
                ],
            },
        ),
        kind="global",
        title="艾玛",
    ),
    _card(
        "item",
        "物品详情",
        (
            {
                "title": "属性",
                "type": "items",
                "items": [
                    {
                        "name": "秘银装甲",
                        "imageUrl": _ITEM_ICON,
                        "rarity": "Legend",
                        "defense": 38,
                        "moveSpeed": "0.08",
                    }
                ],
            },
        ),
        kind="global",
        title="秘银装甲",
    ),
    _card(
        "routes",
        "路线",
        (
            {
                "title": "推荐路线",
                "type": "items",
                "items": [
                    {
                        "name": "港口 → 仓库 → 消防局",
                        "imageUrl": _ROUTE_ICON,
                        "routeId": 10421,
                        "weapon": "暗器",
                        "votes": 284,
                    },
                    {
                        "name": "寺庙 → 森林 → 池塘",
                        "imageUrl": _PLAYER_ICON,
                        "routeId": 10608,
                        "weapon": "暗器",
                        "votes": 167,
                    },
                ],
            },
        ),
        kind="global",
        title="艾玛",
    ),
)


def preview_operations() -> tuple[str, ...]:
    return tuple(preview.operation for preview in CARD_PREVIEWS)


def _select_previews(operations: Iterable[str] | None) -> tuple[CardPreview, ...]:
    if operations is None:
        return CARD_PREVIEWS
    requested = tuple(dict.fromkeys(operations))
    unknown = sorted(set(requested) - set(preview_operations()))
    if unknown:
        raise ValueError(f"unknown preview operation: {', '.join(unknown)}")
    requested_set = set(requested)
    return tuple(preview for preview in CARD_PREVIEWS if preview.operation in requested_set)


def _gallery_html(previews: tuple[CardPreview, ...]) -> str:
    cards = "\n".join(
        f"""<article>
  <header><code>{escape(preview.operation)}</code><span>{escape(preview.description)}</span></header>
  <a href="{escape(preview.operation)}.png">
    <img src="{escape(preview.operation)}.png" alt="{escape(preview.operation)} preview">
  </a>
</article>"""
        for preview in previews
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ERBS command card previews</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 28px; background: #070b10; color: #edf5ff;
      font-family: "Microsoft YaHei", sans-serif;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    p {{ margin: 8px 0 24px; color: #8fa8bb; }}
    main {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 20px; align-items: start;
    }}
    article {{
      overflow: hidden; background: #101923; border: 1px solid #263c4c;
      border-radius: 14px;
    }}
    header {{ display: flex; gap: 12px; align-items: center; padding: 12px 14px; }}
    code {{ color: #62f4d4; font-size: 14px; }}
    header span {{ color: #8fa8bb; font-size: 13px; }}
    a {{ display: block; padding: 0 10px 10px; }}
    img {{ display: block; width: 100%; height: auto; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>ERBS command card previews</h1>
  <p>{len(previews)} 个离线样例 · 修改 card.html 或 card.css 后重新运行生成命令</p>
  <main>{cards}</main>
</body>
</html>
"""


async def render_card_previews(
    output_directory: str | Path,
    *,
    operations: Iterable[str] | None = None,
    config: ERBSConfig | None = None,
    renderer: HtmlCardRenderer | None = None,
) -> PreviewBuild:
    selected = _select_previews(operations)
    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    owned_renderer = renderer is None
    active_renderer = renderer or HtmlCardRenderer(config)
    images: list[Path] = []
    try:
        for preview in selected:
            image_path = destination / f"{preview.operation}.png"
            image_path.write_bytes(await active_renderer.render(preview.payload))
            images.append(image_path)
    finally:
        if owned_renderer:
            await active_renderer.close()

    index = destination / "index.html"
    manifest = destination / "manifest.json"
    index.write_text(_gallery_html(selected), encoding="utf-8")
    manifest.write_text(
        json.dumps(
            [
                {
                    "operation": preview.operation,
                    "description": preview.description,
                    "image": f"{preview.operation}.png",
                    "payload": asdict(preview.payload),
                }
                for preview in selected
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return PreviewBuild(destination, index, manifest, tuple(images))


__all__ = [
    "CARD_PREVIEWS",
    "CardPreview",
    "PreviewBuild",
    "preview_operations",
    "render_card_previews",
]
