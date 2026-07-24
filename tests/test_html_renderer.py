from __future__ import annotations

import pytest

from erbs_plugin import HtmlCardRenderer
from erbs_plugin.models import CardPayload


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
                        "title": "赛季概览",
                        "type": "stats",
                        "items": [
                            {"label": "MMR", "value": 8123},
                            {"label": "胜率", "value": "20.0%"},
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
