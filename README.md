# ERBS-plugin

[中文说明](docs/README.zh-CN.md) · [中文快速开始](docs/QUICK_START.md)

ERBS-plugin is a bot plugin for Chinese internet services. It queries public Eternal Return data,
performs analysis, produces JSON output, manages local image assets, and renders PNG data cards.

This is a personal project intended only for learning, discussion, and reference. Ongoing updates
and availability are not guaranteed. Please contact the author to request removal or correction of
any infringing material or code issue.

## Install

Python 3.12 is required.

```bash
pip install erbs-plugin
```

PNG output uses native Skia drawing. Install the render extra:

```bash
pip install 'erbs-plugin[render]'
```

## Command line

Query JSON directly:

```bash
erbs overview playername
erbs matches playername --count 10
```

Render a PNG file (referenced CDN images are cached on demand):

```bash
erbs overview playername \
  --format path \
  --output ./player.png
```

Raw PNG bytes can be piped or redirected:

```bash
erbs overview eternalreturn --format bytes > player.png
```

The same CLI is available through `python -m erbs_plugin`. The existing `erbs-assets` command is
retained for compatibility.

## Illustrated player summary

For website-backed evaluation, call `ERBSService.published_player_summary(nickname)` and pass
the returned payload to `SkiaCardRenderer.render()`. It reads ERCraft's current-season
`scope=overall` report and displays the supplied grades (E through SSS), population percentiles
(`P`), and eligible game counts. It never fetches DAK matches or falls back to local scoring.
Published values are displayed as supplied, without local sample, grade, percentile, or identity
cross-checks. Missing axis values remain blank. Identity resolution and report preparation are
polled without a total deadline; explicit API/job failures stop the request. Pending responses
are never cached. Pass an async `progress` callback to receive website lookup stages and queue
details (position, players ahead, and estimated wait). Website report timestamps and versions
remain in the payload.
DAK character metadata is optional and used only for artwork names and rarity.
The ribbon title follows the website's `play-card-percentile.v4` selector, using only the
returned percentiles and preserving its rule priority and ties. The 13 Chinese titles are
listed in the [Chinese guide](docs/README.zh-CN.md). Payloads include `styleId`,
`styleRuleVersion`, and `displayTitle`; `summary_title` still overrides the displayed ribbon.
Drawing retains the existing illustration and layout. Local match scores never supply a
website-style title.

The separate `summary` CLI/API follows ERCraft's illustrated card layout and uses the existing local
six-axis calculation. The sample includes ranked squad games from the current season, up to
500 newest games by default (the whole season when there are at most 500);
when there are fewer than 20, recent normal squad games from that season fill it to 20:

```bash
erbs summary dantynoel --format path --output ./summary.png
erbs summary dantynoel --art ./illustration.png \
  --card-title "六维实战档案" --format path --output ./summary-custom.png
```

`--count` remains accepted (1–60) for compatibility and no longer changes the sample scope.
`--season` selects a DAK season; otherwise the sample uses DAK's current season, including
players with no ranked games this season. `--max-matches` sets the ranked cap (at least 20).
In Python use `ERBSConfig(summary_match_limit=1000)` to change it, or `None` for no cap.
Samples are not limited by the old `--count` range of 1–60.
Normal games only fill the gap to 20; if fewer games are available, the card keeps the real
count. JSON records `rankedCount`, `rankedTotal`, `normalCount`, and `truncated` so a capped
sample is never represented as the whole season. The clean card displays each axis's local
letter grade, score as a percentage and eligible game count. This percentage is a local
0–100 score, not a population percentile. Grades use fixed score bands:
S ≥70, A ≥55, B ≥40, C ≥25, D ≥10, otherwise E. These are local display bands
(`gradeVersion=local-six-axis-bands.v1`), independent of ERCraft's website grades and population
percentiles. Missing or invalid scores have no grade. The summary never uses the optional ERCraft
API fallback.

Normal fill games use the player's selected-season ranked tier as their local scoring baseline;
unranked players use the iron baseline. This policy is recorded in the JSON payload. Normal
matchmaking MMR is not treated as ranked RP. Existing ranked and radar scoring behavior is unchanged.

The default 500-game cap follows a local service-to-PNG benchmark: four runs with empty local
HTTP/asset caches took 8.00–11.61 seconds at 500 games and 17.85–20.83 seconds at 1,000.
Warm runs took about 0.16–0.21 and 0.21–0.28 seconds respectively. This excludes QQ
upload; network/CDN times vary. Reproduce with `python scripts/benchmark_summary.py --output DIR`.

`--art` requires a decodable local raster background image with exactly 1024×1536 pixels.
Without it, each render draws a character with probability proportional to its play count in the
selected season's ranked squad overview, independently of the 500-game sample cap. With no ranked
games it uses same-season normal game usage; unavailable season usage falls back to sampled games.
For the selected character, artwork is drawn first from its existing ERCraft illustrated cards,
regardless of whether the player has used the corresponding skin. Only characters with no ERCraft
cards fall back to their publicly recorded used skins, then to the base skin when no skin evidence
is available. Card and skin candidates for Epic (heroic, purple, DAK `grade=4`) skins have weight 10;
other candidates have weight 1. Skin usage counts do not multiply those weights. Used/base skin
fallbacks use DAK artwork, and public used-skin records are not a complete owned-skin inventory.
Selected artwork is cached locally; each generation draws again even when query data
comes from cache. `--card-title` changes only the displayed title.
In Python, use
`ERBSConfig(summary_art_path=Path("illustration.png"), summary_title="六维实战档案")`.
Both settings default to `None` and do not change the scoring data or query-cache identity.

```python
from erbs_plugin import player_summary, query

png_path = await player_summary("dantynoel", format="path", output="summary.png")
json_text = await query("summary", "dantynoel", count=20)
```

Summary results have an independent 180-second cache and do not reuse radar payloads.
Its cache key includes sample scope, local grade and art selection versions so earlier summaries
are regenerated.

## Python API

The recommended API consists of async query functions:

```python
from erbs_plugin import player_overview

json_text = await player_overview("playername", format="json")
png_bytes = await player_overview("playername", format="bytes")
png_path = await player_overview(
    "playername",
    format="path",
    output="player.png",
)
```

Available functions cover player overview, rank, statistics, matches, recent performance, radar,
characters, teammates, best matches, hero pools, equipment habits, leaderboards, character
statistics, items, and routes. The generic `query()` function exposes the same supported operations
through a single entry point.

Long-running applications can reuse `AsyncERBSClient` and `SkiaCardRenderer`; resources supplied by
the caller remain owned by the caller.

## DAK.GG commands and rendering migration

LoMu-style queries share the existing API, cache, metadata and performance scoring:

```bash
erbs command '/查询玩家 玩家名称 排位'
erbs command '/查询角色 席琳 排位 灭钻' --format path --output celine.png
erbs character-equipment 席琳 --tier meteorite_plus
erbs character-stats --tier diamond_plus
erbs tier-stats --server seoul
erbs tier-cutoffs --server asia2
```

Python exports `search`, `character_equipment`, `character_stats`, `tier_stats`, `tier_cutoffs`,
and `execute_command`. Existing queries remain available. See the [command and migration guide](docs/DAK_QUERIES.zh-CN.md)
for filters, endpoint behavior and examples.

Player search and character analysis PNGs follow DAK.GG's desktop layout. Player cards use
rank/statistics and match-history columns; character cards omit the character selector and keep
the horizontal metrics, skill/tactical columns, augment combinations, and item tables.
These are local Skia templates using the same structured JSON data, with no browser required.

The previous HTML/CSS renderer, theme, fonts and SVG radar geometry are archived in
[`legacy`](src/erbs_plugin/legacy/README.md). Explicit legacy use requires the `legacy-render`
extra and `from erbs_plugin.legacy.rendering import HtmlCardRenderer`.

## Performance scoring

Ranked squad match cards use ERCraft's public `role-score.v3` numerical core. The six-axis radar
uses a Python port of its `production-analysis-axes.v1.1`: survival, combat, macro, support,
finish, and consistency. Both run locally with the bundled historical baselines and duration curves.
The radar preserves the upstream metric weights, rounding, result-score fallback, and population
standard deviation formula. Its header shows the finish axis, not an average of all six axes.
Local summaries cover recent matches and do not invent comparison percentiles.

Automatic pre-match RP classification supports DAK season IDs 39 and 41 (S11/S12).
`score_match(raw_match, tier_key="platinum")` accepts an explicit pre-match tier for other seasons.
Missing fields and unsupported character/weapon combinations produce `null` with a reason.
The previous eight-axis `style-v1` calibration and its custom rule/profile classes are replaced.

ERCraft's public scoring API is an optional backup, disabled by default. Set
`ERBSConfig(ercraft_api_fallback=True)` to try its cache-only `recent20` report only when local
six-axis data is incomplete. A successful backup replaces the whole radar and identifies its source;
it never mixes current published axes with historical local axes or substitutes a season-wide report.
Unavailable backups preserve the local scores and missing-data reason.

The historical match-grade cuts differ from today's ERCraft website; match JSON identifies them
through `gradeVersion=ercraft-public-fine-cuts.v1`. The illustrated summary applies the separate
local S/A/B/C/D/E display bands described above to unchanged six-axis scores. Radar scores and their
presentation remain unchanged. See [scoring details](docs/SCORING.zh-CN.md) for provenance,
formulas, supported inputs, and offline verification.

## Data, cache, and assets

Data is read from public DAK.GG Eternal Return endpoints used by its public website. An explicitly
enabled radar backup also reads ERCraft's public cache-only GET endpoints. The package
does not invoke player refresh, authentication, management, or write endpoints. Consumers should
use conservative request rates and display `Data source: DAK.GG` where appropriate.

Successful high-level queries are cached in a private SQLite database under the current user's
platform data directory. Cache expiry is configured independently for every query operation through
`ERBSConfig.query_cache_seconds`; cache identity also includes arguments, language, and API endpoint.
Every result includes `footer.updatedAt`; cache hits additionally include `footer.cached=true` and a
human-readable `footer.notice` warning that the data may not be current.

PNG rendering reuses local asset manifests and downloads only referenced `cdn.dak.gg` images
that are missing. Assets are stored in the discovered asset directory or the platform user-data
directory. Failed downloads use placeholders; JSON output never downloads images. Set
`ERBSConfig(download_render_assets=False)` for local-only image rendering.

## Disclaimer and trademarks

ERBS-plugin is an unofficial project and is not affiliated with Nimble Neuron. Eternal Return is a
trademark of Nimble Neuron. The bundled two-line Chinese/English wordmark is independently generated
for this project and is not an official Eternal Return logo.

## License

Apache-2.0. Third-party inspiration and notices are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
