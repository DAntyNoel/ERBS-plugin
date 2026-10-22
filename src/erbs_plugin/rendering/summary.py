"""Local six-axis portrait cards, inspired by ERCraft's public play-card layout."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from ..exceptions import AssetMissing, RenderFailed
from ..models import CardPayload
from ..scoring.axes import AXIS_ORDER
from ..scoring.grades import summary_grade
from .resources import is_summary_art_url

PAPER = 0xFFFFFCF2
INK = 0xFF323746
ACCENT = 0xFF4A7BB2
BORDER = 0xFF705449
MUTED = 0xFF857B70
LABELS = ("生存", "交战", "运营", "支援", "战绩", "稳定性")
# The bundled illustrations use ERCraft style 10, whose title is 빛과 소금.
ORIGINAL_TITLE = "光与盐"


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _count(value: object) -> int:
    return int(value) if _finite(value) and value >= 0 and int(value) == value else 0


def _background_image(sk: Any, path: Any) -> Any:
    image = sk.Image.MakeFromEncoded(sk.Data.MakeWithCopy(path.read_bytes()))
    if image is None or image.width() != 1024 or image.height() != 1536:
        return None
    return image.makeRasterImage()


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
    background = None
    if art is not None:
        try:
            background = _background_image(sk, art)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RenderFailed(f"无法读取总结卡底图：{art}") from exc
        if background is None:
            raise RenderFailed("总结卡底图必须是可解码的 1024×1536 栅格图片")
    elif is_summary_art_url(source := section.get("summaryArtUrl")):
        try:
            background = _background_image(sk, renderer.assets.resolve_source(source))
        except (AssetMissing, OSError, ValueError, RuntimeError):
            background = None
    if background is not None:
        canvas.drawImageRect(background, sk.Rect.MakeWH(1024, 1536))
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

    # Blade-like flourishes either side of the player name.
    for origin, sign in ((368, 1), (656, -1)):
        line([(origin - 100 * sign, 1142), (origin - 12 * sign, 1142)], ACCENT)
        line([(origin - 90 * sign, 1156), (origin - 37 * sign, 1125),
              (origin - 43 * sign, 1137), (origin - 77 * sign, 1156)], ACCENT)
        diamond(origin - 7 * sign, 1142, 4, ACCENT)
    nickname = "".join(char for char in payload.title if ord(char) >= 32 and ord(char) != 127)[:32]
    center(nickname, 512, 1162, min(28, 410 / max(1, len(nickname))), width=410)

    polygon([(346, 1177), (310, 1177), (327, 1192), (310, 1207), (354, 1207)], ACCENT, ACCENT)
    polygon([(678, 1177), (714, 1177), (697, 1192), (714, 1207), (670, 1207)], ACCENT, ACCENT)
    polygon([(352, 1171), (672, 1171), (686, 1191), (672, 1211),
             (352, 1211), (338, 1191)], INK, ACCENT, 2)
    line([(358, 1176), (667, 1176)], ACCENT)
    line([(358, 1206), (667, 1206)], ACCENT)
    diamond(367, 1191, 4, 0xFFEDCB8B)
    diamond(657, 1191, 4, 0xFFEDCB8B)
    center(renderer.config.summary_title or ORIGINAL_TITLE, 512, 1201, 26,
           0xFFFFF0D0, width=250)

    polygon([(384, 1217), (639, 1217), (659, 1239),
             (639, 1261), (384, 1261), (364, 1239)],
            0xFFF7EAD8, ACCENT)
    rp = section.get("rp")
    has_rp = _finite(rp) and rp >= 0
    tier_image = section.get("tierImageUrl")
    if tier_image:
        renderer._image(canvas, tier_image, 377, 1215, 48, 48, background=0)
    center(f"{rp:,.0f} RP" if has_rp else "— RP", 539 if tier_image else 512,
           1249, 29, width=220)

    for points in ([(137, 1277), (137, 1265), (176, 1265)],
                   [(848, 1265), (887, 1265), (887, 1277)],
                   [(137, 1456), (137, 1476), (176, 1476)],
                   [(848, 1476), (887, 1476), (887, 1456)]):
        line(points, ACCENT, 2)
    axes = {a.get("key"): a for a in section.get("axes", ()) if isinstance(a, Mapping)}
    for index, key in enumerate(AXIS_ORDER):
        axis = axes.get(key, {})
        score = axis.get("score")
        # Recompute display bands for cached or caller-provided payloads as well.
        grade = summary_grade(score)
        ready = grade is not None
        highlighted = grade == "S"
        fill, edge, color = ((0xFFFFF3D7, 0xFFC69A4B, 0xFF8E6129) if highlighted else
                             (0xFFF4EFE7, 0xFFD1C8BD, MUTED))
        x, y, w, h = 168 + index % 3 * 236, 1277 + index // 3 * 101, 216, 87
        polygon([(x + 12, y), (x + w - 12, y), (x + w, y + 12),
                 (x + w, y + h - 12), (x + w - 12, y + h), (x + 12, y + h),
                 (x, y + h - 12), (x, y + 12)], fill, edge)
        if highlighted:
            ornament = 0xFFB57C30
            for points in ([(x + 6, y + 25), (x + 6, y + 14), (x + 14, y + 6), (x + 45, y + 6)],
                           [(x + w - 45, y + 6), (x + w - 14, y + 6),
                            (x + w - 6, y + 14), (x + w - 6, y + 25)],
                           [(x + 6, y + h - 25), (x + 6, y + h - 14),
                            (x + 14, y + h - 6), (x + 34, y + h - 6)],
                           [(x + w - 34, y + h - 6), (x + w - 14, y + h - 6),
                            (x + w - 6, y + h - 14), (x + w - 6, y + h - 25)]):
                line(points, ornament, 2)
            diamond(x + 37, y + 49, 3, ornament)
            diamond(x + w - 37, y + 49, 3, ornament)
        center(LABELS[index], x + w / 2, y + 26, 20, 0xFF7F7061, width=w - 30)
        center(grade if ready else "—", x + w / 2, y + 59, 34, color, width=w - 50)
        count = _count(axis.get("sampleCount"))
        # The percentage is the local 0..100 score, never the payload's percentile.
        percentage = f"{score:.2f}".rstrip("0").rstrip(".") if ready else ""
        center(f"{percentage}% · {count}场" if ready else f"{count}场",
               x + w / 2, y + 78, 12, 0xFF7F7061, width=w - 20)

    # DAK season IDs/keys are internal sequences; only the display name supplies S12, etc.
    season = re.search(r"\bS\d+\b", str(section.get("seasonName") or ""), re.IGNORECASE)
    footer = f"{season[0].upper()} ERCraft 全部" if season else "ERCraft 全部"
    center(footer, 512, 1498, 16, width=860)
    encoded = surface.makeImageSnapshot().encodeToData(sk.kPNG, 100)
    if encoded is None:
        raise RenderFailed("总结卡 PNG 编码失败")
    return bytes(encoded)
