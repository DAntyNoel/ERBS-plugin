"""Local six-axis portrait cards, inspired by ERCraft's public play-card layout."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ..exceptions import RenderFailed
from ..models import CardPayload
from ..scoring.axes import AXIS_ORDER

PAPER = 0xFFFFFCF2
INK = 0xFF323746
ACCENT = 0xFF4A7BB2
BORDER = 0xFF705449
MUTED = 0xFF857B70
LABELS = ("生存", "交战", "运营", "支援", "结果", "稳定性")


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def render_summary(renderer: Any, payload: CardPayload) -> bytes:
    """Draw locally; an optional explicit art file supplies the full background."""
    sk = renderer._skia
    section = next((s for s in payload.sections if s.get("type") == "player-summary"), None)
    if section is None:
        raise RenderFailed("总结卡缺少 player-summary 数据")
    scale = renderer.config.render_scale
    surface = sk.Surface.MakeRasterN32Premul(math.ceil(1024 * scale), math.ceil(1536 * scale))
    if surface is None:
        raise RenderFailed("无法分配总结卡画布")
    canvas = surface.getCanvas()
    canvas.scale(scale, scale)
    canvas.clear(PAPER)

    def line(points: list[tuple[float, float]], color: int, stroke: float = 1.5) -> None:
        path = sk.Path()
        for i, (x, y) in enumerate(points):
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        canvas.drawPath(path, renderer._paint(color, stroke=stroke))

    def polygon(points: list[tuple[float, float]], fill: int, edge: int, stroke=1.5) -> None:
        path = sk.Path()
        for i, (x, y) in enumerate(points):
            (path.moveTo if i == 0 else path.lineTo)(x, y)
        path.close()
        canvas.drawPath(path, renderer._paint(fill))
        canvas.drawPath(path, renderer._paint(edge, stroke=stroke))

    def diamond(x: float, y: float, radius: float, color: int) -> None:
        polygon([(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)], color, color)

    def center(value: object, x: float, y: float, size: float, color=INK, width=700) -> None:
        text = str(value).replace("\n", " ")
        # Shrink first, then truncate exceptionally long names in the shared label helper.
        measured = renderer._measure(text, size, True)
        size = max(size * 0.6, min(size, size * width / max(1, measured)))
        measured = min(width, renderer._measure(text, size, True))
        renderer._label(canvas, text, x - measured / 2, y, size=size, color=color,
                        bold=True, width=width)

    art = renderer.config.summary_art_path
    if art is not None:
        try:
            image = sk.Image.MakeFromEncoded(sk.Data.MakeWithCopy(art.read_bytes()))
        except (OSError, ValueError, RuntimeError) as exc:
            raise RenderFailed(f"无法读取总结卡底图：{art}") from exc
        if image is None or image.width() != 1024 or image.height() != 1536:
            raise RenderFailed("总结卡底图必须是可解码的 1024×1536 栅格图片")
        canvas.drawImageRect(image.makeRasterImage(), sk.Rect.MakeWH(1024, 1536))
    else:
        # A missing optional illustration still produces a complete, usable card.
        canvas.drawRect(sk.Rect.MakeXYWH(21, 19, 982, 1498), renderer._paint(BORDER, stroke=2))
        for x, y, sx, sy in ((21, 19, 1, 1), (1003, 19, -1, 1),
                              (21, 1517, 1, -1), (1003, 1517, -1, -1)):
            line([(x + sx * 12, y + sy * 66), (x + sx * 12, y + sy * 12),
                  (x + sx * 66, y + sy * 12)], ACCENT, 2)
            diamond(x + sx * 23, y + sy * 23, 7, BORDER)
        renderer._image(canvas, section.get("characterImageUrl"), 98, 72, 828, 1000,
                        background=PAPER)
        if not section.get("characterImageUrl"):
            for radius in (230, 270, 300):
                canvas.drawCircle(512, 550, radius, renderer._paint(0xFFE6DFD1, stroke=1))
            center(section.get("characterName") or "ETERNAL RETURN", 512, 560, 42, MUTED)
            center("实战表现 · 六维档案", 512, 610, 21, MUTED)

    # Blade-like flourishes either side of the player name.
    for origin, sign in ((368, 1), (656, -1)):
        line([(origin - 100 * sign, 1142), (origin - 12 * sign, 1142)], ACCENT)
        line([(origin - 90 * sign, 1156), (origin - 37 * sign, 1125),
              (origin - 43 * sign, 1137), (origin - 77 * sign, 1156)], ACCENT)
        diamond(origin - 7 * sign, 1142, 4, ACCENT)
    center(payload.title, 512, 1162, 30, width=280)

    polygon([(346, 1177), (310, 1177), (327, 1192), (310, 1207), (354, 1207)], ACCENT, ACCENT)
    polygon([(678, 1177), (714, 1177), (697, 1192), (714, 1207), (670, 1207)], ACCENT, ACCENT)
    polygon([(352, 1171), (672, 1171), (686, 1191), (672, 1211),
             (352, 1211), (338, 1191)], INK, ACCENT, 2)
    line([(358, 1176), (667, 1176)], ACCENT)
    line([(358, 1206), (667, 1206)], ACCENT)
    diamond(367, 1191, 3, 0xFFEDCB8B)
    diamond(657, 1191, 3, 0xFFEDCB8B)
    center(renderer.config.summary_title or section.get("displayTitle") or "六维实战档案",
           512, 1201, 26, 0xFFFFF0D0, width=250)

    polygon([(384, 1217), (639, 1217), (659, 1239), (639, 1261),
             (384, 1261), (364, 1239)], 0xFFF7EAD8, ACCENT)
    rp = section.get("rp")
    has_rp = _finite(rp) and rp >= 0
    tier_image = section.get("tierImageUrl")
    if tier_image:
        renderer._image(canvas, tier_image, 377, 1215, 48, 48, background=0)
    center(f"{rp:,.0f} RP" if has_rp else "RP 暂无数据", 539 if tier_image else 512,
           1249, 29, width=220)

    for points in ([(137, 1277), (137, 1265), (176, 1265)],
                   [(848, 1265), (887, 1265), (887, 1277)],
                   [(137, 1456), (137, 1476), (176, 1476)],
                   [(848, 1476), (887, 1476), (887, 1456)]):
        line(points, ACCENT, 2)
    axes = {a.get("key"): a for a in section.get("axes", ()) if isinstance(a, Mapping)}
    available = [a["score"] for a in axes.values() if _finite(a.get("score"))]
    highest = max(available) if available else None
    for index, key in enumerate(AXIS_ORDER):
        axis = axes.get(key, {})
        score = axis.get("score")
        ready = _finite(score)
        highlighted = ready and score == highest
        fill, edge, color = ((0xFFFFF3D7, 0xFFC69A4B, 0xFF8E6129) if highlighted else
                             (0xFFF4EFE7, 0xFFD1C8BD, MUTED))
        x, y, w, h = 168 + index % 3 * 236, 1277 + index // 3 * 101, 216, 87
        polygon([(x + 12, y), (x + w - 12, y), (x + w, y + 12),
                 (x + w, y + h - 12), (x + w - 12, y + h), (x + 12, y + h),
                 (x, y + h - 12), (x, y + 12)], fill, edge)
        if highlighted:
            for points in ([(x + 6, y + 25), (x + 6, y + 14), (x + 14, y + 6), (x + 45, y + 6)],
                           [(x + w - 45, y + 6), (x + w - 14, y + 6),
                            (x + w - 6, y + 14), (x + w - 6, y + 25)]):
                line(points, edge, 2)
            diamond(x + 37, y + 49, 3, edge)
            diamond(x + w - 37, y + 49, 3, edge)
        center(LABELS[index], x + w / 2, y + 26, 20, 0xFF7F7061, width=w - 30)
        center(f"{score:.1f}" if ready else "—", x + w / 2, y + 59, 34, color, width=w - 50)
        count = axis.get("sampleCount", 0)
        center(f"{count} 场 · / 100" if ready else f"{count} 场 · 数据不足",
               x + w / 2, y + 78, 12, 0xFF7F7061, width=w - 20)

    # Keep the source/scope explicit; raw local scores are never presented as percentiles.
    scope = section.get("scopeLabel", "最近对局")
    center(f"{scope} · 本地评分", 512, 1495, 17, width=860)
    cached = " · 缓存" if payload.footer.get("cached") else ""
    center(f"数据 DAK.GG{cached} · 历史六维公式 v1.1", 512, 1513, 12, MUTED, width=900)
    encoded = surface.makeImageSnapshot().encodeToData(sk.kPNG, 100)
    if encoded is None:
        raise RenderFailed("总结卡 PNG 编码失败")
    return bytes(encoded)
