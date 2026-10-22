from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..client import AsyncERBSClient
from ..exceptions import UpstreamUnavailable
from ..radar import RadarSample
from ..summary_scope import SUMMARY_DEFAULT_LIMIT, SUMMARY_MINIMUM_SAMPLE

_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class SummarySample(RadarSample):
    ranked_total: int | None = None
    truncated: bool = False


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


async def fetch_summary_sample(
    client: AsyncERBSClient, nickname: str, *, season: str, season_id: int,
    max_ranked_matches: int | None = SUMMARY_DEFAULT_LIMIT,
) -> SummarySample:
    """Read season ranked games up to the cap, filling samples below 20 with normal games."""
    matches: list[Mapping[str, object]] = []
    seen_ids: set[int] = set()
    cached = False
    page_count = 0
    ranked_total = None
    truncated = False

    for mode, mode_id in (("RANK", 3), ("NORMAL", 2)):
        if mode == "NORMAL" and len(matches) >= SUMMARY_MINIMUM_SAMPLE:
            break
        page = 1
        expected_total: int | None = None
        previous_pages: set[tuple[int | None, ...]] = set()
        while True:
            payload = await client.player_matches(
                nickname.strip(), season=season, matching_mode=mode,
                team_mode="SQUAD", page=page,
            )
            page_count += 1
            cached = cached or bool(payload.get("_erbs_cached"))
            metadata = payload.get("meta")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            if metadata.get("season") not in (None, season):
                raise UpstreamUnavailable("DAK.GG 总结图对局赛季不匹配")
            rows = payload.get("matches") or ()
            total = _integer(metadata.get("count"))
            if mode == "RANK" and total is not None:
                if expected_total is not None and total != expected_total:
                    raise UpstreamUnavailable("DAK.GG 排位总场数在查询期间变化，请重试")
                expected_total = total
            if not rows:
                if total is not None and (page - 1) * _PAGE_SIZE < total:
                    raise UpstreamUnavailable("DAK.GG 总结图对局分页不完整")
                break
            fingerprint = tuple(
                _integer(row.get("gameId")) for row in rows if isinstance(row, Mapping)
            )
            if fingerprint in previous_pages:
                raise UpstreamUnavailable("DAK.GG 总结图对局分页重复，无法读取完整赛季")
            previous_pages.add(fingerprint)
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                if _integer(row.get("matchingMode")) != mode_id or _integer(
                    row.get("matchingTeamMode", row.get("teamMode"))
                ) != 3:
                    continue
                match_season = _integer(row.get("seasonId"))
                # DAK normal games use seasonId=0; the server's season filter is authoritative.
                if match_season != season_id and not (
                    mode == "NORMAL" and match_season == 0 and metadata.get("season") == season
                ):
                    continue
                game_id = _integer(row.get("gameId"))
                if game_id is None or game_id <= 0 or game_id in seen_ids:
                    continue
                seen_ids.add(game_id)
                matches.append(dict(row))
                if mode == "RANK" and max_ranked_matches is not None and (
                    len(matches) >= max_ranked_matches
                ):
                    break
                if mode == "NORMAL" and len(matches) >= SUMMARY_MINIMUM_SAMPLE:
                    break
            if mode == "NORMAL" and len(matches) >= SUMMARY_MINIMUM_SAMPLE:
                break
            if mode == "RANK" and max_ranked_matches is not None and (
                len(matches) >= max_ranked_matches
            ):
                truncated = total is None or total > len(matches)
                break
            if total is not None and page * _PAGE_SIZE >= total:
                break
            if len(rows) < _PAGE_SIZE:
                if total is not None and page * _PAGE_SIZE < total:
                    raise UpstreamUnavailable("DAK.GG 总结图对局分页不完整")
                break
            page += 1
        if mode == "RANK":
            ranked_total = expected_total if expected_total is not None else (
                None if truncated else len(matches)
            )
            expected_sample = min(expected_total, max_ranked_matches) if (
                expected_total is not None and max_ranked_matches is not None
            ) else expected_total
            if expected_sample is not None and len(matches) != expected_sample:
                raise UpstreamUnavailable("DAK.GG 排位记录去重后与总场数不符，请重试")

    return SummarySample(
        nickname=nickname.strip(), matches=tuple(matches), cached=cached, page_count=page_count,
        ranked_total=ranked_total, truncated=truncated,
    )
