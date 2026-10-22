"""Measure the bot's service-to-PNG path using bounded real DAK match samples.

The production collector selects newest real records up to the configured cap.
Each size gets a fresh HTTP/TTL client and empty asset directory. Repeats reuse
the client and renderer, as the bot does. Reset RNG keeps selected art comparable.
Timing excludes QQ upload and optional PNG saving.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from erbs_plugin import AsyncERBSClient, ERBSConfig, ERBSService
from erbs_plugin.rendering import SkiaCardRenderer


class MeasuredClient(AsyncERBSClient):
    def __init__(self, config, limit):
        super().__init__(config)
        self.limit = limit
        self.network_requests = 0
        self.available = None
        self._client.event_hooks["request"] = [self.record_request]

    async def record_request(self, request):
        self.network_requests += 1

    async def player_matches(self, nickname, **options):
        data = await super().player_matches(nickname, **options)
        if options.get("matching_mode") != "RANK":
            return data
        self.available = data["meta"]["count"]
        return data


async def measure(folder, nickname, limit, run):
    config = ERBSConfig(
        query_cache_enabled=False,
        summary_match_limit=limit,
        asset_directory=folder / f"assets-{limit}-{run}",
        private_database_path=folder / f"query-{limit}-{run}.sqlite3",
    )
    results = []
    async with MeasuredClient(config, limit) as client, SkiaCardRenderer(config) as renderer:
        service = ERBSService(client)
        for state in ("cold", "warm1", "warm2", "warm3"):
            random.seed(20261022)
            before = client.network_requests
            start = time.perf_counter()
            card = await service.player_summary(nickname)
            collected = time.perf_counter()
            image = await renderer.render(card)
            ended = time.perf_counter()
            with Image.open(BytesIO(image)) as im:
                im.verify()
                assert im.size == (1024, 1536)
            section = card.sections[0]
            row = {
                "limit": limit, "run": run, "state": state,
                "sample": section["sampleSize"], "available": client.available,
                "source_s": round(collected-start, 4),
                "render_s": round(ended-collected, 4),
                "total_s": round(ended-start, 4),
                "api_network_requests": client.network_requests-before,
                "png_bytes": len(image),
            }
            results.append(row)
            print(json.dumps(row), flush=True)
            (folder / f"{limit}-{run}-{state}.png").write_bytes(image)
    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", default="Sans")
    parser.add_argument("--limits", type=int, nargs="+", default=[20, 100, 200, 500, 1000])
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(UTC).isoformat(), "player": args.player,
        "cache": "cold=fresh HTTP/TTL client and empty assets; warm=same client and renderer",
        "path": "ERBSService.player_summary -> SkiaCardRenderer.render -> valid PNG bytes",
        "qq_upload_included": False, "rows": [],
    }
    for run in range(args.runs):
        # Reverse alternate runs to expose persistent time/order effects.
        for limit in args.limits if run % 2 == 0 else reversed(args.limits):
            try:
                report["rows"].extend(await measure(args.output, args.player, limit, run))
            except Exception as exc:
                row = {"limit": limit, "run": run, "error": f"{type(exc).__name__}: {exc}"}
                report["rows"].append(row)
                print(json.dumps(row), flush=True)
            (args.output / "results.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
            )


if __name__ == "__main__":
    asyncio.run(main())
