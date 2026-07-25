from __future__ import annotations

import pytest

from erbs_plugin import ERBSConfig, HtmlCardRenderer
from erbs_plugin.models import CardPayload
from erbs_plugin.rendering.html import _footer_display_time, _theme


def test_theme_embeds_player_emblem_background() -> None:
    assert _theme()["player_emblem_background"].startswith("data:image/png;base64,")


def test_footer_time_uses_configured_fixed_timezone() -> None:
    config = ERBSConfig(
        render_timezone_name="CST",
        render_timezone_offset_hours=8,
    )

    assert _footer_display_time("2026-07-25T15:16:03+00:00", config) == (
        "7月25日 23:16:03",
        "CST GMT+8",
    )


@pytest.mark.asyncio
async def test_html_renderer_returns_png() -> None:
    renderer = HtmlCardRenderer()
    try:
        image = await renderer.render(
            CardPayload(
                kind="player",
                title="Kanami",
                subtitle="ERBS 渲染验证",
                sections=(
                    {
                        "title": "当前段位",
                        "type": "rank",
                        "tierId": 7,
                        "tierName": "半神",
                        "imageUrl": "//cdn.dak.gg/assets/er/images/rank/full/7.png",
                        "items": [
                            {"label": "MMR", "value": 8123},
                            {"label": "段位", "value": "半神"},
                            {"label": "小段", "value": 1},
                            {"label": "小段 RP", "value": 606},
                        ],
                    },
                ),
                footer={"source": "DAK.GG", "cached": False},
            )
        )
    finally:
        await renderer.close()

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 10_000
