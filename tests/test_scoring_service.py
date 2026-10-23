from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService, SkiaCardRenderer


@pytest.mark.asyncio
async def test_match_card_exposes_and_renders_performance_evidence() -> None:
    case = json.loads(
        (Path(__file__).parent / "fixtures/ercraft-scoring-reference.json").read_text(
            encoding="utf-8"
        )
    )["matches"][0]

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/matches"):
            return httpx.Response(200, json={"matches": [case["raw"]]})
        return httpx.Response(200, json={"characters": [], "items": []})

    async with AsyncERBSClient(
        ERBSConfig(),
        transport=httpx.MockTransport(handler),
    ) as client:
        card = await ERBSService(client).matches_card("sample", count=1)
    result = card.sections[0]["items"][0]["performance"]
    assert result["score"] == case["onlineScore"]
    assert result["roleScoreDetail"] == case["expected"]["roleScoreDetail"]
    async with SkiaCardRenderer() as renderer:
        png = await renderer.render(card)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
