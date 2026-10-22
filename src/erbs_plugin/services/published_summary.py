"""Build a local portrait from ERCraft's website report, without local scoring."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ..assets.summary_cards import FIRST_PICK_SKIN_SUFFIXES, VERIFIED_CHARACTER_IDS
from ..client import AsyncERBSClient
from ..exceptions import ERBSError, InvalidQuery, UpstreamUnavailable
from ..models import CardPayload
from ..published_summary import PUBLISHED_SUMMARY_SOURCE, SummaryProgressCallback
from ..scoring.axes import AXIS_LABELS, AXIS_ORDER
from ..summary_art import SUMMARY_ART_VERSION
from ..summary_style import SUMMARY_STYLE_TITLES, SUMMARY_STYLE_VERSION, select_summary_style
from .summary_art import build_summary_art_candidates


def _positive_id(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


async def _art_metadata(client: AsyncERBSClient, usage: list[Mapping]) -> Mapping:
    # Metadata supplies only artwork names/rarity. A DAK outage must not block a report.
    try:
        return await asyncio.wait_for(
            client.metadata("characters"), timeout=min(3.0, client.config.timeout_seconds),
        )
    except (ERBSError, TimeoutError):
        characters = []
        for row in usage:
            character_id = row.get("characterNum")
            if character_id not in VERIFIED_CHARACTER_IDS:
                continue
            base = 1_000_000 + character_id * 1_000
            suffix = FIRST_PICK_SKIN_SUFFIXES.get(character_id)
            characters.append({
                "id": character_id,
                "skins": [{"id": base + offset} for offset in (0, suffix) if offset is not None],
            })
        return {"characters": characters}


async def published_player_summary(
    client: AsyncERBSClient, nickname: str, *, progress: SummaryProgressCallback | None = None,
) -> CardPayload:
    if not nickname.strip():
        raise InvalidQuery("玩家昵称不能为空")
    summary = await client.ercraft_player_summary(nickname.strip(), progress=progress)
    identity = summary.get("data")
    if not isinstance(identity, Mapping):
        raise UpstreamUnavailable("ERCraft 暂无玩家资料，请先在网站查询该玩家。")
    owner, season = identity.get("playerId"), identity.get("currentSeason")
    analysis = await client.ercraft_overall_analysis(
        owner, season, nickname=nickname.strip(), progress=progress,
    )
    report, scope = analysis.get("report"), analysis.get("scope")
    if not isinstance(report, Mapping):
        raise UpstreamUnavailable("ERCraft 评价报告结构不完整。")
    scope = scope if isinstance(scope, Mapping) else {}
    target = report.get("target")
    if not isinstance(target, Mapping):
        raise UpstreamUnavailable("ERCraft 评价报告缺少目标数据。")
    rows = target.get("overallAxes") or []
    axes_by_key = {row.get("axis"): row for row in rows if isinstance(row, Mapping)}
    axes = [{
        **axes_by_key.get(key, {}), "key": key, "label": AXIS_LABELS[key],
        "score": axes_by_key.get(key, {}).get("combinedScore"),
        "sampleCount": axes_by_key.get(key, {}).get("eligibleGames"),
    } for key in AXIS_ORDER]
    style_id = select_summary_style(axes)
    character_scopes = target.get("characterScopes")
    usage = [
        row for row in (character_scopes if isinstance(character_scopes, list) else ())
        if isinstance(row, Mapping) and _positive_id(row.get("characterNum"))
        and _positive_id(row.get("sourceGames"))
    ]
    metadata = await _art_metadata(client, usage) if usage else {}
    # Adapt only character usage for the existing random-art selector, never match scores.
    api_season = scope.get("apiSeasonId")
    art_season = api_season if _positive_id(api_season) else season
    candidates, _ = build_summary_art_candidates({
        "playerSeasonOverviews": [{
            "seasonId": art_season, "matchingModeId": 3, "teamModeId": 3,
            "characterStats": [
                {"key": row["characterNum"], "play": row["sourceGames"]} for row in usage
            ],
        }],
    }, metadata, (), art_season)
    sample_size = max((row.get("sourceGames") for row in rows if isinstance(row, Mapping)
                       and isinstance(row.get("sourceGames"), int)), default=None)
    section: dict[str, Any] = {
        "type": "player-summary", "source": PUBLISHED_SUMMARY_SOURCE,
        "sourceLabel": "ERCraft", "axes": axes,
        "styleId": style_id, "styleRuleVersion": SUMMARY_STYLE_VERSION,
        "displayTitle": SUMMARY_STYLE_TITLES.get(style_id),
        "sampleSize": sample_size, "scopeLabel": f"S{season} ERCraft 全部",
        "seasonId": api_season, "displaySeasonId": season, "seasonName": f"S{season}",
        "rp": identity.get("rp"), "tierName": identity.get("tier"),
        "formulaVersion": report.get("axisFormulaVersion"), "reportVersion": report.get("version"),
        "sourceMeta": {
            "scope": dict(scope), "authority": report.get("authority"),
            "sourceContract": report.get("sourceContract"), "ownerPlayerId": owner,
            "profileRefreshedAt": identity.get("lastRefreshedAt"),
        },
        "artCandidates": candidates, "artSelectionVersion": SUMMARY_ART_VERSION,
        "artSelectionSource": "ERCraft 报告角色场次",
    }
    # The icon is a static CDN asset; rank and RP still come entirely from ERCraft.
    normalized_tier = identity.get("normalizedTier")
    if isinstance(normalized_tier, Mapping):
        tier = str(normalized_tier.get("tierId") or "").split("-", 1)[0]
        tier_id = {
            "iron": 1, "bronze": 2, "silver": 3, "gold": 4, "platinum": 5,
            "diamond": 6, "meteorite": 63, "mithril": 66, "demigod": 7, "eternity": 8,
        }.get(tier)
        if tier_id is not None:
            suffix = "?1" if tier_id == 63 else ""
            section["tierImageUrl"] = (
                f"https://cdn.dak.gg/assets/er/images/rank/full/{tier_id}.png{suffix}"
            )
    return CardPayload(
        kind="summary", title=str(identity.get("nickname") or nickname.strip()),
        sections=(section,),
        footer={
            "source": "ERCraft", "scoringSource": PUBLISHED_SUMMARY_SOURCE,
            "cached": summary.get("source") == "cache" or bool(analysis.get("_erbs_cached")),
            "reportComputedAt": scope.get("computedAt"),
        },
    )
