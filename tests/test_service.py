from __future__ import annotations

import httpx
import pytest

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService


@pytest.mark.asyncio
async def test_player_overview_card() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "player": {"name": "Kanami", "accountLevel": 88},
                "playerSeasons": [{"seasonId": 39, "mmr": 8123, "tierId": 7}],
                "playerSeasonOverviews": [
                    {"play": 20, "win": 4, "top3": 9, "playerKill": 33}
                ],
            },
        )

    client = AsyncERBSClient(ERBSConfig(), transport=httpx.MockTransport(handler))
    try:
        card = await ERBSService(client).player_overview("Kanami")
    finally:
        await client.aclose()

    assert card.kind == "player"
    assert card.title == "Kanami"
    assert card.sections[0]["items"][1]["value"] == 8123
