from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal

from .config import ERBSConfig
from .models import CardPayload
from .rendering import HtmlCardRenderer


@dataclass(frozen=True, slots=True)
class CardPreview:
    operation: str
    description: str
    payload: CardPayload


@dataclass(frozen=True, slots=True)
class DebugQuery:
    operation: str
    arguments: tuple[str, ...] = ()
    count: int = 5
    page: int = 1
    season: str | None = None
    weapon: str | None = None


@dataclass(frozen=True, slots=True)
class PreviewBuild:
    output_directory: Path
    index: Path
    manifest: Path
    images: tuple[Path, ...]
    primary_image: Path | None = None
    gallery_count: int = 0
    result: str | bytes | Path | None = None


_EMMA_CHARACTER_IMAGE = "asset://CharProfile_Emma_S000.png"
_NICKY_CHARACTER_IMAGE = "asset://CharProfile_Nicky_S000.png"
_KARLA_CHARACTER_IMAGE = "asset://CharProfile_Karla_S000.png"
_SUN_ITEM_IMAGE = "asset://ItemIcon_130503.png"
_ELVEN_DRESS_ITEM_IMAGE = "asset://ItemIcon_202516.png"
_WHITE_NIGHT_CROWN_ITEM_IMAGE = "asset://ItemIcon_201536.png"
DEFAULT_DEBUG_PLAYERS = ("B站丨咕咕禽OC", "Preme", "페이블")
_PRIMARY_PLAYER, _SECONDARY_PLAYER, _TERTIARY_PLAYER = DEFAULT_DEBUG_PLAYERS

DEFAULT_DEBUG_QUERIES = (
    DebugQuery("overview", (_PRIMARY_PLAYER,)),
    DebugQuery("rank", (_PRIMARY_PLAYER,)),
    DebugQuery("stats", (_PRIMARY_PLAYER,)),
    DebugQuery("matches", (_PRIMARY_PLAYER,), count=5),
    DebugQuery("recent", (_PRIMARY_PLAYER,)),
    DebugQuery("characters", (_PRIMARY_PLAYER,)),
    DebugQuery("skins", (_PRIMARY_PLAYER,)),
    DebugQuery("teammates", (_PRIMARY_PLAYER,)),
    DebugQuery("multi", DEFAULT_DEBUG_PLAYERS),
    DebugQuery("compare", (_PRIMARY_PLAYER, _SECONDARY_PLAYER)),
    DebugQuery("best-match", (_PRIMARY_PLAYER,)),
    DebugQuery("hero-pool", (_PRIMARY_PLAYER,)),
    DebugQuery("equipment", (_PRIMARY_PLAYER,)),
    DebugQuery("leaderboard"),
    DebugQuery("character", ("艾玛",), weapon="Arcana"),
    DebugQuery("item", ("烈阳",)),
    DebugQuery("routes", ("艾玛",), weapon="Arcana"),
)


def _card(
    operation: str,
    subtitle: str,
    sections: tuple[dict[str, object], ...],
    *,
    kind: str = "player",
    title: str = _PRIMARY_PLAYER,
) -> CardPreview:
    return CardPreview(
        operation=operation,
        description=subtitle,
        payload=CardPayload(
            kind=kind,
            title=title,
            subtitle=subtitle,
            sections=sections,
            footer={"source": "DAK.GG", "cached": operation == "rank"},
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
                    {"label": "赛季", "value": 39},
                    {"label": "场次", "value": 339},
                    {"label": "胜场", "value": 54},
                    {"label": "胜率", "value": "15.9%"},
                    {"label": "TOP 3", "value": 126},
                    {"label": "击杀", "value": 918},
                    {"label": "助攻", "value": 1634},
                ],
            },
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
                "title": "名次走势",
                "type": "placements",
                "items": [
                    {"rank": rank, "victory": rank == 1, "podium": rank <= 3}
                    for rank in (1, 2, 6, 3, 4, 5, 2, 1, 7, 3)
                ],
            },
            {
                "title": "常用实验体 / 英雄池",
                "type": "hero-pool",
                "items": [
                    {
                        "name": "艾玛",
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
                        "poolRank": 1,
                        "plays": 72,
                        "winRate": "25.0%",
                        "usagePercent": "47.7%",
                    },
                    {
                        "name": "妮琪",
                        "imageUrl": _NICKY_CHARACTER_IMAGE,
                        "poolRank": 2,
                        "plays": 48,
                        "winRate": "18.8%",
                        "usagePercent": "31.8%",
                    },
                    {
                        "name": "卡拉",
                        "imageUrl": _KARLA_CHARACTER_IMAGE,
                        "poolRank": 3,
                        "plays": 31,
                        "winRate": "19.4%",
                        "usagePercent": "20.5%",
                    },
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
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
                        "kills": 8,
                        "assists": 7,
                        "damage": 27841,
                        "mmrGain": 34,
                        "equipment": "秘银装甲 · 智能手环 · 圣法衣",
                    },
                    {
                        "name": "#4 · 妮琪",
                        "imageUrl": _NICKY_CHARACTER_IMAGE,
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
                "title": "名次走势",
                "type": "placements",
                "items": [
                    {"rank": rank, "victory": rank == 1, "podium": rank <= 3}
                    for rank in (1, 2, 6, 3, 4, 5, 2, 1, 7, 3)
                ],
            },
        ),
        kind="matches",
    ),
    _card(
        "characters",
        "实验体统计",
        (
            {
                "title": "常用实验体 / 英雄池",
                "type": "hero-pool",
                "items": [
                    {
                        "name": "艾玛",
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
                        "poolRank": 1,
                        "plays": 72,
                        "winRate": "25.0%",
                        "usagePercent": "60.0%",
                    },
                    {
                        "name": "妮琪",
                        "imageUrl": _NICKY_CHARACTER_IMAGE,
                        "poolRank": 2,
                        "plays": 48,
                        "winRate": "18.8%",
                        "usagePercent": "40.0%",
                    },
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
                    {"name": "午夜魔术师 艾玛", "imageUrl": _EMMA_CHARACTER_IMAGE, "count": 12},
                    {"name": "冠军 妮琪", "imageUrl": _NICKY_CHARACTER_IMAGE, "count": 7},
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
                    {"name": _SECONDARY_PLAYER, "games": 4},
                    {"name": _TERTIARY_PLAYER, "games": 2},
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
                    {"name": _PRIMARY_PLAYER, "mmr": 8123, "level": 87, "plays": 339},
                    {"name": _SECONDARY_PLAYER, "mmr": 7760, "level": 64, "plays": 205},
                    {"name": _TERTIARY_PLAYER, "mmr": 7421, "level": 52, "plays": 188},
                ],
            },
        ),
        kind="comparison",
        title=" / ".join(DEFAULT_DEBUG_PLAYERS),
    ),
    _card(
        "compare",
        "玩家对比",
        (
            {
                "title": "核心数据",
                "type": "comparison",
                "left": _PRIMARY_PLAYER,
                "right": _SECONDARY_PLAYER,
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
        title=f"{_PRIMARY_PLAYER} VS {_SECONDARY_PLAYER}",
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
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
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
                "title": "常用实验体 / 英雄池",
                "type": "hero-pool",
                "items": [
                    {
                        "name": "艾玛",
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
                        "poolRank": 1,
                        "plays": 72,
                        "winRate": "25.0%",
                        "usagePercent": "47.7%",
                    },
                    {
                        "name": "妮琪",
                        "imageUrl": _NICKY_CHARACTER_IMAGE,
                        "poolRank": 2,
                        "plays": 48,
                        "winRate": "18.8%",
                        "usagePercent": "31.8%",
                    },
                    {
                        "name": "卡拉",
                        "imageUrl": _KARLA_CHARACTER_IMAGE,
                        "poolRank": 3,
                        "plays": 31,
                        "winRate": "19.4%",
                        "usagePercent": "20.5%",
                    },
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
                    {"name": "烈阳", "imageUrl": _SUN_ITEM_IMAGE, "count": 16},
                    {"name": "精灵舞裙", "imageUrl": _ELVEN_DRESS_ITEM_IMAGE, "count": 12},
                    {"name": "白夜王冠", "imageUrl": _WHITE_NIGHT_CROWN_ITEM_IMAGE, "count": 9},
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
                    {"name": _PRIMARY_PLAYER, "rank": 1, "mmr": 11842, "tier": "Immortal"},
                    {"name": _SECONDARY_PLAYER, "rank": 2, "mmr": 11690, "tier": "Immortal"},
                    {"name": _TERTIARY_PLAYER, "rank": 3, "mmr": 11571, "tier": "Immortal"},
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
                        "imageUrl": _EMMA_CHARACTER_IMAGE,
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
                        "name": "烈阳",
                        "imageUrl": _SUN_ITEM_IMAGE,
                        "rarity": "Legend",
                        "defense": 38,
                        "moveSpeed": "0.08",
                    }
                ],
            },
        ),
        kind="global",
        title="烈阳",
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
                        "imageUrl": _SUN_ITEM_IMAGE,
                        "routeId": 10421,
                        "weapon": "暗器",
                        "votes": 284,
                    },
                    {
                        "name": "寺庙 → 森林 → 池塘",
                        "imageUrl": _ELVEN_DRESS_ITEM_IMAGE,
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
    return tuple(query.operation for query in DEFAULT_DEBUG_QUERIES)


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _quoted(value: str) -> str:
    return f'"{value}"' if any(character.isspace() for character in value) else value


def _debug_query_command(query: DebugQuery) -> str:
    parts = ["erbs", query.operation, *query.arguments]
    if query.operation == "matches":
        parts.extend(("--count", str(query.count)))
    if query.operation == "leaderboard":
        parts.extend(("--page", str(query.page)))
    if query.season is not None:
        parts.extend(("--season", query.season))
    if query.weapon is not None:
        parts.extend(("--weapon", query.weapon))
    return " ".join(_quoted(part) for part in parts)


def _live_record(query: DebugQuery, payload: CardPayload) -> dict[str, Any]:
    return {
        "id": f"live:{query.operation}",
        "source": "live",
        "operation": query.operation,
        "description": _debug_query_command(query),
        "image": f"{query.operation}.png",
        "arguments": list(query.arguments),
        "options": {
            "count": query.count,
            "page": query.page,
            "season": query.season,
            "weapon": query.weapon,
        },
        "payload": asdict(payload),
    }


def _image_exists(output_directory: Path, record: dict[str, Any]) -> bool:
    image = record.get("image")
    if not isinstance(image, str) or Path(image).name != image:
        return False
    return (output_directory / image).is_file()


def _gallery_records(
    output_directory: Path,
    *,
    live_records: list[dict[str, Any]] | None = None,
    custom_record: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    manifest = output_directory / "manifest.json"
    existing_records = _read_manifest(manifest)
    if live_records is None:
        live_records = [
            record
            for record in existing_records
            if record.get("source") == "live" and _image_exists(output_directory, record)
        ]
    live_by_operation = {str(record.get("operation")): record for record in live_records}
    default_records = [
        live_by_operation[query.operation]
        for query in DEFAULT_DEBUG_QUERIES
        if query.operation in live_by_operation
        and _image_exists(output_directory, live_by_operation[query.operation])
    ]
    custom_records = [
        record
        for record in existing_records
        if record.get("source") == "query" and _image_exists(output_directory, record)
    ]
    if custom_record is not None:
        custom_records = [
            record for record in custom_records if record.get("id") != custom_record.get("id")
        ]
        custom_records.append(custom_record)
    return [*default_records, *custom_records]


def _gallery_html(records: list[dict[str, Any]]) -> str:
    cards = "\n".join(
        f"""<article>
  <header>
    <code>{escape(str(record['operation']))}</code>
    <span>{escape(str(record['description']))}</span>
    <b>{escape(str(record.get('source', 'live')).upper())}</b>
  </header>
  <a href="{escape(str(record['image']))}">
    <img src="{escape(str(record['image']))}" alt="{escape(str(record['operation']))} preview">
  </a>
</article>"""
        for record in records
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
    header span {{ color: #8fa8bb; font-size: 13px; flex: 1; }}
    header b {{ color: #60778a; font-size: 10px; letter-spacing: 1px; }}
    a {{ display: block; padding: 0 10px 10px; }}
    img {{ display: block; width: 100%; height: auto; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>ERBS command card previews</h1>
  <p>{len(records)} 个预览结果 · 修改 card.html 或 card.css 后重新运行生成命令</p>
  <main>{cards}</main>
</body>
</html>
"""


def _write_gallery(
    output_directory: Path,
    *,
    live_records: list[dict[str, Any]] | None = None,
    custom_record: dict[str, Any] | None = None,
) -> tuple[Path, Path, int]:
    records = _gallery_records(
        output_directory,
        live_records=live_records,
        custom_record=custom_record,
    )
    index = output_directory / "index.html"
    manifest = output_directory / "manifest.json"
    index.write_text(_gallery_html(records), encoding="utf-8")
    manifest.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return index, manifest, len(records)


async def render_card_previews(
    output_directory: str | Path,
    *,
    missing_only: bool = False,
    config: ERBSConfig | None = None,
    renderer: HtmlCardRenderer | None = None,
    payload_provider: Callable[[DebugQuery], Awaitable[CardPayload]] | None = None,
) -> PreviewBuild:
    from .api import _payload_for
    from .client import AsyncERBSClient
    from .services import ERBSService

    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    existing_live_records = [
        record
        for record in _read_manifest(destination / "manifest.json")
        if record.get("source") == "live" and _image_exists(destination, record)
    ]
    existing_live_by_operation = {
        str(record.get("operation")): record for record in existing_live_records
    }
    queries_to_render = tuple(
        query
        for query in DEFAULT_DEBUG_QUERIES
        if not missing_only or query.operation not in existing_live_by_operation
    )

    active_config = config or ERBSConfig()
    owned_renderer = renderer is None
    active_renderer = renderer or HtmlCardRenderer(active_config)
    client: AsyncERBSClient | None = None
    if payload_provider is None:
        client = AsyncERBSClient(active_config)
        service = ERBSService(client)

        async def load_payload(query: DebugQuery) -> CardPayload:
            return await _payload_for(
                service,
                query.operation,
                query.arguments,
                count=query.count,
                page=query.page,
                season=query.season,
                weapon=query.weapon,
            )

        active_payload_provider = load_payload
    else:
        active_payload_provider = payload_provider

    live_by_operation = existing_live_by_operation if missing_only else {}
    images: list[Path] = []
    try:
        for query in queries_to_render:
            payload = await active_payload_provider(query)
            image_path = destination / f"{query.operation}.png"
            image_path.write_bytes(await active_renderer.render(payload))
            images.append(image_path)
            live_by_operation[query.operation] = _live_record(query, payload)
    finally:
        if client is not None:
            await client.aclose()
        if owned_renderer:
            await active_renderer.close()

    live_records = [
        live_by_operation[query.operation]
        for query in DEFAULT_DEBUG_QUERIES
        if query.operation in live_by_operation
    ]
    index, manifest, gallery_count = _write_gallery(
        destination,
        live_records=live_records,
    )
    return PreviewBuild(
        destination,
        index,
        manifest,
        tuple(images),
        gallery_count=gallery_count,
    )

async def render_query_preview(
    operation: str,
    *arguments: str,
    output_directory: str | Path,
    config: ERBSConfig | None = None,
    renderer: HtmlCardRenderer | None = None,
    gallery_payload_provider: Callable[[DebugQuery], Awaitable[CardPayload]] | None = None,
    format: Literal["json", "bytes", "path"] = "json",
    output: str | Path | None = None,
    count: int = 5,
    page: int = 1,
    season: str | None = None,
    weapon: str | None = None,
) -> PreviewBuild:
    from .api import _payload_for, _render_output
    from .client import AsyncERBSClient
    from .services import ERBSService

    destination = Path(output_directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    active_config = config or ERBSConfig()
    spec = {
        "operation": operation,
        "arguments": list(arguments),
        "count": count,
        "page": page,
        "season": season,
        "weapon": weapon,
        "language": active_config.language,
    }
    digest = hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    image_path = destination / f"custom-{operation}-{digest}.png"

    owned_renderer = renderer is None
    active_renderer = renderer or HtmlCardRenderer(active_config)
    client = AsyncERBSClient(active_config)
    try:
        payload = await _payload_for(
            ERBSService(client),
            operation,
            arguments,
            count=count,
            page=page,
            season=season,
            weapon=weapon,
        )
        result = await _render_output(
            payload,
            format=format,
            output=output,
            config=active_config,
            renderer=active_renderer,
        )
        if isinstance(result, bytes):
            image = result
        elif isinstance(result, Path):
            image = result.read_bytes()
        else:
            image = await active_renderer.render(payload)
        bootstrap = await render_card_previews(
            destination,
            missing_only=True,
            config=active_config,
            renderer=active_renderer,
            payload_provider=gallery_payload_provider,
        )
        image_path.write_bytes(image)
    finally:
        await client.aclose()
        if owned_renderer:
            await active_renderer.close()

    option_parts = []
    if count != 5:
        option_parts.extend(("--count", str(count)))
    if page != 1:
        option_parts.extend(("--page", str(page)))
    if season is not None:
        option_parts.extend(("--season", season))
    if weapon is not None:
        option_parts.extend(("--weapon", weapon))
    command = " ".join(
        _quoted(part)
        for part in ("erbs", "debug", operation, *arguments, *option_parts)
    )
    custom_record = {
        "id": f"query:{digest}",
        "source": "query",
        "operation": operation,
        "description": command,
        "image": image_path.name,
        "arguments": list(arguments),
        "options": {
            "count": count,
            "page": page,
            "season": season,
            "weapon": weapon,
            "language": active_config.language,
        },
        "payload": asdict(payload),
    }
    index, manifest, gallery_count = _write_gallery(
        destination,
        custom_record=custom_record,
    )
    return PreviewBuild(
        destination,
        index,
        manifest,
        (*bootstrap.images, image_path),
        primary_image=image_path,
        gallery_count=gallery_count,
        result=result,
    )


__all__ = [
    "CARD_PREVIEWS",
    "DEFAULT_DEBUG_PLAYERS",
    "DEFAULT_DEBUG_QUERIES",
    "CardPreview",
    "DebugQuery",
    "PreviewBuild",
    "preview_operations",
    "render_card_previews",
    "render_query_preview",
]
