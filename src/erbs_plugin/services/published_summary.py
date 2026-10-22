"""Build a local portrait from ERCraft's website report, without local scoring."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ..assets.summary_cards import FIRST_PICK_SKIN_SUFFIXES, VERIFIED_CHARACTER_IDS
from ..client import AsyncERBSClient
from ..exceptions import ERBSError, InvalidQuery, UpstreamUnavailable
from ..models import CardPayload
from ..published_summary import PUBLISHED_SUMMARY_SOURCE, published_summary_grade
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


async def published_player_summary(client: AsyncERBSClient, nickname: str) -> CardPayload:
    if not nickname.strip():
        raise InvalidQuery("玩家昵称不能为空")
    summary = await client.ercraft_player_summary(nickname.strip())
    identity = summary.get("data")
    if not isinstance(identity, Mapping):
        raise UpstreamUnavailable("ERCraft 暂无玩家资料，请先在网站查询该玩家。")
    owner, season = identity.get("playerId"), identity.get("currentSeason")
    if not isinstance(owner, str) or not owner.strip() or not _positive_id(season):
        raise UpstreamUnavailable("ERCraft 缺少有效玩家身份或当前赛季。")
    analysis = await client.ercraft_overall_analysis(owner, season)
    report, scope = analysis.get("report"), analysis.get("scope")
    if not isinstance(report, Mapping) or not isinstance(scope, Mapping):
        raise UpstreamUnavailable("ERCraft 评价报告结构不完整。")
    target = report.get("target")
    if (
        not isinstance(target, Mapping) or target.get("ownerPlayerId") != owner
        or scope.get("displaySeasonId") != season or scope.get("analysisScope") != "overall"
        or report.get("comparisonTierBand") is not None
        or not isinstance(report.get("version"), str)
        or not isinstance(report.get("axisFormulaVersion"), str)
    ):
        raise UpstreamUnavailable("ERCraft 评价身份、赛季或统计范围不匹配。")
    rows = target.get("overallAxes")
    if (
        not isinstance(rows, list) or len(rows) != len(AXIS_ORDER)
        or any(not isinstance(row, Mapping) for row in rows)
        or any(not isinstance(row.get("axis"), str) for row in rows)
        or {row.get("axis") for row in rows} != set(AXIS_ORDER)
    ):
        raise UpstreamUnavailable("ERCraft 缺少完整的六维评价。")
    if any(published_summary_grade(row) is None for row in rows):
        raise UpstreamUnavailable("ERCraft 六维评价样本不足或等级、百分位不可用。")
    axes_by_key = {row["axis"]: row for row in rows}
    axes = [{
        **axes_by_key[key], "key": key, "label": AXIS_LABELS[key],
        "score": axes_by_key[key].get("combinedScore"),
        "sampleCount": axes_by_key[key]["eligibleGames"],
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
    sample_size = max(row["sourceGames"] for row in rows)
    section: dict[str, Any] = {
        "type": "player-summary", "source": PUBLISHED_SUMMARY_SOURCE,
        "sourceLabel": "ERCraft", "axes": axes,
        "styleId": style_id, "styleRuleVersion": SUMMARY_STYLE_VERSION,
        "displayTitle": SUMMARY_STYLE_TITLES.get(style_id),
        "sampleSize": sample_size, "scopeLabel": f"S{season} ERCraft 全部",
        "seasonId": api_season, "displaySeasonId": season, "seasonName": f"S{season}",
        "rp": identity.get("rp"), "tierName": identity.get("tier"),
        "formulaVersion": report["axisFormulaVersion"], "reportVersion": report["version"],
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
