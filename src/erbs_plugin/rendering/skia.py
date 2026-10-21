"""Prepare CDN assets, then rasterize query payloads locally without a browser."""

from __future__ import annotations

import asyncio
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urlsplit

from ..assets import AssetManager
from ..config import ERBSConfig
from ..exceptions import AssetMissing, RenderFailed
from ..models import CardPayload
from .resources import prepare_assets

BG = 0xFFF3F5F8
WHITE = 0xFFFFFFFF
INK = 0xFF202733
MUTED = 0xFF6D7889
LINE = 0xFFE4E8EF
NAVY = 0xFF202B40
ORANGE = 0xFFF97840
BLUE = 0xFF4266D5
GREEN = 0xFF169779


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}" if math.isfinite(value) else "—"
    return unescape(re.sub(r"<[^>]*>", "", str(value))).replace("\r", "")


class SkiaCardRenderer:
    """Reusable async renderer. Assets and fonts are resolved locally and cached."""

    def __init__(self, config: ERBSConfig | None = None) -> None:
        self.config = config or ERBSConfig()
        self.assets = AssetManager.discover(self.config.asset_directory)
        self._lock = asyncio.Lock()
        self._images: OrderedDict[str, Any] = OrderedDict()
        self._fonts: dict[tuple[str, bool], Any] = {}
        self._skia: Any = None
        self._manager: Any = None
        self._primary: Any = None
        self._asset_revision: tuple | None = None

    async def __aenter__(self) -> SkiaCardRenderer:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        async with self._lock:
            self._images.clear()
            self._fonts.clear()

    async def render(self, payload: CardPayload) -> bytes:
        async with self._lock:
            try:
                self.assets = await prepare_assets(asdict(payload), self.config)
                manifest = self.assets.manifest_path
                revision = (
                    (str(manifest), manifest.stat().st_mtime_ns) if manifest.exists() else None
                )
                if revision != self._asset_revision:
                    self._images.clear()
                    self._asset_revision = revision
                # Keep the lock until the worker finishes even if the caller is cancelled.
                task = asyncio.create_task(asyncio.to_thread(self._render, payload))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            except RenderFailed:
                raise
            except Exception as exc:
                raise RenderFailed(f"Skia 图片渲染失败：{exc}") from exc

    def _initialize(self) -> None:
        if self._skia is not None:
            return
        try:
            import skia
        except ImportError as exc:
            raise RenderFailed("请安装 erbs-plugin[render]，原生绘图需要 skia-python") from exc
        self._skia = skia
        self._manager = skia.FontMgr.RefDefault()
        if self.config.render_font_path is not None:
            self._primary = skia.Typeface.MakeFromFile(str(self.config.render_font_path))
            if self._primary is None:
                raise RenderFailed(f"无法加载字体：{self.config.render_font_path}")

    def _runs(self, text: str, size: float, bold: bool = False) -> list[tuple[str, Any]]:
        sk = self._skia
        runs = []
        current = ""
        previous = None
        for char in text:
            key = (char, bold)
            face = self._fonts.get(key)
            if face is None:
                style = sk.FontStyle.Bold() if bold else sk.FontStyle.Normal()
                if self._primary is not None and self._primary.unicharToGlyph(ord(char)):
                    face = self._primary
                else:
                    face = self._manager.matchFamilyStyleCharacter(
                        "sans-serif", style, ["en", "ko", "zh-Hans"], ord(char)
                    )
                if face is None:
                    raise RenderFailed("缺少文字字体，请安装 Noto Sans CJK 或配置 render_font_path")
                self._fonts[key] = face
            if previous is not None and face.uniqueID() != previous.uniqueID():
                runs.append((current, sk.Font(previous, size)))
                current = ""
            current += char
            previous = face
        if current:
            runs.append((current, sk.Font(previous, size)))
        return runs

    def _measure(self, value: Any, size: float, bold: bool = False) -> float:
        return sum(font.measureText(text) for text, font in self._runs(_text(value), size, bold))

    def _label(
        self,
        canvas: Any,
        value: Any,
        x: float,
        y: float,
        *,
        size: float = 18,
        color: int = INK,
        bold: bool = False,
        width: float | None = None,
    ) -> None:
        text = _text(value).replace("\n", " ")
        if width is not None:
            if self._measure(text, size, bold) > width:
                left, right = 0, len(text)
                while left < right:
                    middle = (left + right + 1) // 2
                    if self._measure(text[:middle] + "…", size, bold) <= width:
                        left = middle
                    else:
                        right = middle - 1
                text = text[:left] + "…"
        for part, font in self._runs(text, size, bold):
            canvas.drawString(part, x, y, font, self._paint(color))
            x += font.measureText(part)

    def _wrap(self, value: Any, width: float, size: float = 17) -> list[str]:
        result = []
        for paragraph in _text(value).splitlines() or [""]:
            line = ""
            for token in re.findall(r"[A-Za-z0-9_.,%+/:—-]+|\s+|.", paragraph):
                if line and self._measure(line + token, size) > width:
                    result.append(line)
                    line = ""
                # Ordinary numbers/words stay together; exceptionally long tokens can wrap.
                if self._measure(token, size) > width:
                    for char in token:
                        if line and self._measure(line + char, size) > width:
                            result.append(line)
                            line = ""
                        line += char
                else:
                    line += token
            result.append(line)
        return result

    def _paint(self, color: int, *, stroke: float = 0) -> Any:
        paint = self._skia.Paint(Color=color, AntiAlias=True)
        if stroke:
            paint.setStyle(self._skia.Paint.kStroke_Style)
            paint.setStrokeWidth(stroke)
        return paint

    def _rect(
        self,
        canvas: Any,
        x: float,
        y: float,
        w: float,
        h: float,
        color: int = WHITE,
        radius: float = 10,
    ) -> None:
        canvas.drawRoundRect(
            self._skia.Rect.MakeXYWH(x, y, w, h), radius, radius, self._paint(color)
        )

    def _image(
        self,
        canvas: Any,
        source: Any,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        cover: bool = False,
        background: int = BG,
    ) -> None:
        if not isinstance(source, str) or not source:
            return
        if source.startswith(("https://", "http://", "//")):
            parsed = urlsplit(f"https:{source}" if source.startswith("//") else source)
            if parsed.hostname == "cdn.dak.gg":
                source = parsed._replace(scheme="https").geturl()
        image = self._images.get(source)
        if source not in self._images:
            try:
                if source.startswith("asset://"):
                    path = self.assets.resolve_filename(source.removeprefix("asset://"))
                elif source.startswith(("https://", "http://", "//")):
                    path = self.assets.resolve_source(source)
                else:
                    path = None  # Only manifest assets are accepted, not arbitrary file paths.
                # Skia may decode lazily: own the encoded buffer until raster pixels exist.
                image = (
                    self._skia.Image.MakeFromEncoded(
                        self._skia.Data.MakeWithCopy(path.read_bytes())
                    )
                    if path
                    else None
                )
                if image is not None:
                    image = image.makeRasterImage()
                if image is None and path and path.suffix.casefold() == ".svg":
                    dom = self._skia.SVGDOM.MakeFromStream(
                        self._skia.MemoryStream(path.read_bytes())
                    )
                    if dom:
                        dom.setContainerSize(self._skia.Size(128, 128))
                        surface = self._skia.Surface.MakeRasterN32Premul(128, 128)
                        surface.getCanvas().clear(0)
                        dom.render(surface.getCanvas())
                        image = surface.makeImageSnapshot()
            except (AssetMissing, OSError, ValueError, RuntimeError):
                image = None
            self._images[source] = image
            if len(self._images) > 256:
                self._images.popitem(last=False)
        else:
            self._images.move_to_end(source)
        self._rect(canvas, x, y, w, h, background, 3)
        if image is not None:
            scale = (max if cover else min)(w / image.width(), h / image.height())
            iw, ih = image.width() * scale, image.height() * scale
            canvas.save()
            canvas.clipRect(self._skia.Rect.MakeXYWH(x, y, w, h))
            canvas.drawImageRect(
                image, self._skia.Rect.MakeXYWH(x + (w - iw) / 2, y + (h - ih) / 2, iw, ih)
            )
            canvas.restore()

    @staticmethod
    def _items(section: Mapping) -> list[Mapping]:
        return [item for item in section.get("items", []) if isinstance(item, Mapping)]

    def _summary(self, item: Mapping) -> str:
        labels = {
            "games": "场次",
            "count": "数量",
            "play": "场次",
            "plays": "场次",
            "wins": "胜场",
            "winRate": "胜率 %",
            "pickRate": "登场 %",
            "top3Rate": "前三 %",
            "avgRank": "平均名次",
            "avgKills": "平均击杀",
            "avgDamage": "平均伤害",
            "mmr": "RP",
            "rpChange": "平均 RP",
            "rate": "占比 %",
            "tier": "评级",
            "rank": "排名",
            "tierName": "段位",
            "slot": "部位",
            "grade": "品质",
            "weapon": "武器",
            "value": "值",
            "tierScore": "评分",
            "usagePercent": "使用率",
            "level": "等级",
            "kills": "击杀",
            "assists": "助攻",
            "damage": "伤害",
            "rarity": "品质",
            "attackPower": "攻击力",
            "defense": "防御力",
            "moveSpeed": "移动速度",
            "votes": "推荐数",
            "score": "评分",
        }
        percentages = {"winRate", "pickRate", "top3Rate", "rate"}
        return "   ".join(
            f"{label.replace(' %', '')} {_text(item[key])}"
            + (
                "%"
                if key in percentages and item[key] is not None and not str(item[key]).endswith("%")
                else ""
            )
            for key, label in labels.items()
            if key in item
        )

    def _row_lines(self, item: Mapping, width: float) -> list[str]:
        details = []
        if summary := self._summary(item):
            details.append(summary)
        for key in ("description", "tooltip", "equipment", "content", "effect"):
            if item.get(key):
                details.append(_text(item[key]))
        for key in ("attributes", "stats"):
            if isinstance(item.get(key), Mapping):
                details.extend(
                    f"{name} {_text(value)}"
                    for name, value in item[key].items()
                    if isinstance(value, (str, int, float))
                )
        order = item.get("order")
        if isinstance(order, list) and order:
            details.append(
                "顺序："
                + " → ".join(
                    _text(row.get("name")) if isinstance(row, Mapping) else _text(row)
                    for row in order
                )
            )
        choices = item.get("choices")
        if isinstance(choices, list) and choices:
            details.append("搭配：" + " · ".join(_text(row.get("name")) for row in choices))
        return [line for detail in details for line in self._wrap(detail, width)]

    def _row_height(self, item: Mapping, width: float) -> int:
        if item.get("layout") == "match":
            return 158
        lines = self._row_lines(item, width - 100)
        has_icons = any(item.get(key) for key in ("equipmentItems", "skills", "choices"))
        return max(80, 54 + 25 * len(lines) + (54 if has_icons else 0))

    def _height(self, section: Mapping, width: float) -> int:
        kind = section.get("type")
        items = self._items(section)
        if kind in {"stats", "rank", "recent-summary"}:
            height = 66 + math.ceil(len(items) / 4) * 80
            if section.get("imageUrl") or section.get("iconUrl"):
                height += 76
            return height + (370 if section.get("radar") else 0)
        if kind == "comparison":
            return 122 + len(section.get("rows", [])) * 46
        if kind == "radar":
            return 420
        if kind in {"mmr-chart", "placements"}:
            return 300
        return 70 + sum(self._row_height(item, width - 44) + 8 for item in items) if items else 120

    def _render(self, payload: CardPayload) -> bytes:
        self._initialize()
        from .dak import render_character, render_player

        if payload.kind == "player" and payload.sections and payload.sections[0].get("profile"):
            return render_player(self, payload)
        if (
            payload.kind == "character"
            and payload.sections
            and payload.sections[0].get("character")
        ):
            return render_character(self, payload)
        width = 1000 if payload.kind == "character" else 1290
        panel_width = width - 64
        heights = [self._height(section, panel_width) for section in payload.sections]
        header_lines = self._wrap(payload.title, width - 110, 34)
        header_height = 124 + max(0, len(header_lines) - 1) * 42
        footer_lines = self._footer_lines(payload, width - 80)
        footer_height = 30 + len(footer_lines) * 25
        height = header_height + 32 + sum(heights) + len(heights) * 20 + footer_height
        scale = self.config.render_scale
        if height * scale > 32760 or width * height * scale * scale > 48_000_000:
            raise RenderFailed("图片内容超出绘图尺寸限制，请缩小查询范围")
        surface = self._skia.Surface.MakeRasterN32Premul(
            math.ceil(width * scale), math.ceil(height * scale)
        )
        if surface is None:
            raise RenderFailed("无法分配 Skia 绘图画布")
        canvas = surface.getCanvas()
        canvas.scale(scale, scale)
        canvas.clear(BG)
        self._rect(canvas, 0, 0, width, header_height, NAVY, 0)
        self._label(canvas, "ERBS  /  ETERNAL RETURN", 36, 31, size=14, color=ORANGE, bold=True)
        for position, line in enumerate(header_lines):
            self._label(canvas, line, 36, 77 + position * 42, size=34, color=WHITE, bold=True)
        self._label(
            canvas,
            payload.subtitle,
            36,
            header_height - 16,
            size=18,
            color=0xFFBFCBDD,
            width=width - 72,
        )
        y = header_height + 24
        for section, panel_height in zip(payload.sections, heights, strict=True):
            self._rect(canvas, 32, y, panel_width, panel_height)
            self._label(
                canvas,
                section.get("title", ""),
                54,
                y + 36,
                size=22,
                bold=True,
                width=panel_width - 44,
            )
            self._section(canvas, section, 54, y + 58, panel_width - 44)
            y += panel_height + 20
        for position, line in enumerate(footer_lines):
            self._label(canvas, line, 40, y + 18 + position * 25, size=15, color=MUTED)
        encoded = surface.makeImageSnapshot().encodeToData(self._skia.kPNG, 100)
        if encoded is None:
            raise RenderFailed("Skia PNG 编码失败")
        return bytes(encoded)

    def _footer_lines(self, payload: CardPayload, width: float) -> list[str]:
        footer = payload.footer
        text = f"Data source: {footer.get('source', 'DAK.GG')}  ·  ERBS-plugin"
        if footer.get("updatedAt"):
            try:
                stamp = datetime.fromisoformat(str(footer["updatedAt"]).replace("Z", "+00:00"))
                local = (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).astimezone(
                    timezone(timedelta(hours=self.config.render_timezone_offset_hours))
                )
                text += f"  ·  {local:%Y-%m-%d %H:%M} {self.config.render_timezone_name}"
            except ValueError:
                pass
        lines = self._wrap(text, width, 15)
        for key in ("notice", "missingReason", "rule"):
            if footer.get(key):
                lines.extend(self._wrap(footer[key], width, 15))
        return lines

    def _section(self, canvas: Any, section: Mapping, x: float, y: float, width: float) -> None:
        kind = section.get("type")
        items = self._items(section)
        if kind in {"stats", "rank", "recent-summary"}:
            if section.get("imageUrl") or section.get("iconUrl"):
                self._image(canvas, section.get("imageUrl") or section.get("iconUrl"), x, y, 60, 60)
                self._label(
                    canvas,
                    section.get("characterName") or section.get("tierName") or "",
                    x + 76,
                    y + 36,
                    size=22,
                    bold=True,
                    width=width - 90,
                )
                y += 76
            for position, item in enumerate(items):
                cx, cy = x + position % 4 * (width / 4), y + position // 4 * 80
                self._rect(canvas, cx, cy, width / 4 - 10, 68, BG, 6)
                self._label(
                    canvas,
                    item.get("label", ""),
                    cx + 12,
                    cy + 23,
                    size=15,
                    color=MUTED,
                    width=width / 4 - 34,
                )
                self._label(
                    canvas,
                    item.get("value"),
                    cx + 12,
                    cy + 52,
                    size=23,
                    color=BLUE,
                    bold=True,
                    width=width / 4 - 34,
                )
            if section.get("radar"):
                self._radar(canvas, section["radar"], x, y + math.ceil(len(items) / 4) * 80, width)
        elif kind == "radar":
            self._radar(canvas, section, x, y, width)
        elif kind in {"mmr-chart", "placements"}:
            self._chart(canvas, section, x, y, width)
        elif kind == "comparison":
            self._label(
                canvas,
                section.get("left"),
                x + width / 3,
                y + 24,
                color=BLUE,
                bold=True,
                width=width / 3 - 12,
            )
            self._label(
                canvas,
                section.get("right"),
                x + width * 2 / 3,
                y + 24,
                color=BLUE,
                bold=True,
                width=width / 3 - 12,
            )
            for position, row in enumerate(section.get("rows", [])):
                if isinstance(row, Mapping):
                    cy = y + 74 + position * 46
                    for column, key in enumerate(("label", "left", "right")):
                        self._label(
                            canvas, row.get(key), x + column * width / 3, cy, width=width / 3 - 12
                        )
        elif not items:
            self._label(canvas, "当前条件暂无数据", x, y + 27, color=MUTED)
        else:
            for item in items:
                height = self._row_height(item, width)
                self._rect(canvas, x, y, width, height, BG, 8)
                if item.get("layout") == "match":
                    self._match(canvas, item, x, y, width)
                else:
                    self._image(
                        canvas, item.get("imageUrl") or item.get("iconUrl"), x + 12, y + 12, 46, 46
                    )
                    self._label(
                        canvas,
                        item.get("name")
                        or item.get("nickname")
                        or item.get("title")
                        or item.get("label")
                        or "详情",
                        x + 72,
                        y + 28,
                        size=19,
                        bold=True,
                        width=width - 94,
                    )
                    for position, line in enumerate(self._row_lines(item, width - 100)):
                        self._label(
                            canvas, line, x + 72, y + 55 + position * 25, size=17, color=MUTED
                        )
                    icons = (
                        item.get("equipmentItems")
                        or item.get("skills")
                        or item.get("choices")
                        or []
                    )
                    for position, icon in enumerate(icons):
                        if isinstance(icon, Mapping) and position * 50 + 120 < width:
                            self._image(
                                canvas,
                                icon.get("imageUrl"),
                                x + 72 + position * 50,
                                y + height - 52,
                                44,
                                44,
                            )
                y += height + 8

    def _match(self, canvas: Any, item: Mapping, x: float, y: float, width: float) -> None:
        color = GREEN if item.get("rank") == 1 else BLUE
        self._rect(canvas, x, y, 7, 158, color, 3)
        self._image(canvas, item.get("imageUrl"), x + 18, y + 16, 64, 64)
        self._label(
            canvas, item.get("name"), x + 100, y + 35, size=22, bold=True, width=width - 120
        )
        self._label(
            canvas,
            f"TK / K / A   {_text(item.get('teamKills'))} / {_text(item.get('kills'))} / "
            f"{_text(item.get('assists'))}     D {_text(item.get('deaths'))}"
            f"     DMG  {_text(item.get('damage'))}"
            f"     RP  {_text(item.get('mmrAfter'))} ({_text(item.get('mmrGain'))})",
            x + 100,
            y + 65,
            size=18,
            color=color,
            width=width - 120,
        )
        for position, icon in enumerate(item.get("equipmentItems", [])):
            self._image(canvas, icon.get("imageUrl"), x + 100 + position * 51, y + 85, 46, 40)
        self._label(
            canvas,
            f"Game {_text(item.get('gameId'))}  ·  路线 {_text(item.get('routeId'))}",
            x + 18,
            y + 146,
            size=14,
            color=MUTED,
            width=width - 36,
        )
        performance = item.get("performance") or {}
        score = performance.get("score")
        if score is not None:
            self._label(
                canvas, f"实战评分 {_text(score)}", x + 410, y + 113, color=ORANGE, bold=True
            )

    def _chart(self, canvas: Any, section: Mapping, x: float, y: float, width: float) -> None:
        items = self._items(section)
        is_mmr = section.get("type") == "mmr-chart"
        values = [item.get("mmr" if is_mmr else "rank") for item in items]
        numeric = [
            float(value)
            for value in values
            if isinstance(value, (int, float)) and math.isfinite(value)
        ]
        if not numeric:
            self._label(canvas, "暂无走势数据", x, y + 30, color=MUTED)
            return
        low, high = min(numeric), max(numeric)
        if not is_mmr:
            low, high = 1, max(2, section.get("maxRank") or 8)
        if low == high:
            low, high = low - 1, high + 1
        left, top, w, h = x + 65, y + 15, width - 100, 155
        for position in range(4):
            py = top + position * h / 3
            canvas.drawLine(left, py, left + w, py, self._paint(LINE))
            value = (
                (high - position * (high - low) / 3)
                if is_mmr
                else (low + position * (high - low) / 3)
            )
            self._label(canvas, f"{value:.0f}", x, py + 6, size=14, color=MUTED)
        path = self._skia.Path()
        started = False
        for position, value in enumerate(values):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                started = False
                continue
            px = left + position * w / max(1, len(values) - 1)
            py = top + h - (value - low) / (high - low) * h
            if not is_mmr:
                py = top + (value - low) / (high - low) * h
            if started:
                path.lineTo(px, py)
            else:
                path.moveTo(px, py)
            started = True
            canvas.drawCircle(px, py, 4, self._paint(BLUE))
        canvas.drawPath(path, self._paint(BLUE, stroke=3))
        description = f"最近 {len(values)} 场"
        if is_mmr:
            description += (
                f"   当前 RP {_text(section.get('currentMmr'))}"
                f"   净变化 {_text(section.get('netChange'))}"
            )
        self._label(canvas, description, x, y + 215, color=MUTED)

    def _radar(self, canvas: Any, section: Mapping, x: float, y: float, width: float) -> None:
        axes = [axis for axis in section.get("axes", []) if isinstance(axis, Mapping)]
        if not axes:
            self._label(canvas, "暂无评分数据", x, y + 30, color=MUTED)
            return
        cx, cy, radius = x + 210, y + 173, 125

        def point(position: int, fraction: float) -> tuple[float, float]:
            angle = -math.pi / 2 + position * 2 * math.pi / len(axes)
            return cx + math.cos(angle) * radius * fraction, cy + math.sin(
                angle
            ) * radius * fraction

        def polygon(fractions: list[float]) -> Any:
            path = self._skia.Path()
            for position, fraction in enumerate(fractions):
                px, py = point(position, fraction)
                (path.moveTo if position == 0 else path.lineTo)(px, py)
            path.close()
            return path

        for fraction in (0.25, 0.5, 0.75, 1):
            canvas.drawPath(polygon([fraction] * len(axes)), self._paint(LINE, stroke=1))
        complete = all(isinstance(axis.get("score"), (int, float)) for axis in axes)
        if complete:
            path = polygon([max(0, min(100, axis["score"])) / 100 for axis in axes])
            canvas.drawPath(path, self._paint(0x384266D5))
            canvas.drawPath(path, self._paint(BLUE, stroke=3))
        for position, axis in enumerate(axes):
            px, py = point(position, 1.23)
            label = _text(axis.get("label"))
            self._label(canvas, label, px - self._measure(label, 17) / 2, py + 5, size=17)
            self._label(
                canvas,
                f"{label}  {_text(axis.get('score'))}",
                x + 455,
                y + 45 + position * 39,
                size=20,
                color=BLUE if axis.get("score") is not None else MUTED,
                width=width - 470,
            )
        self._label(
            canvas,
            f"样本 {section.get('sampleSize', 0)} 场 · {section.get('confidenceLabel', '')}"
            f" · {section.get('sourceLabel', '本地计算')}",
            x + 455,
            y + 310,
            size=16,
            color=MUTED,
            width=width - 470,
        )
