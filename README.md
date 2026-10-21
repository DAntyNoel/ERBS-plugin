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

The portrait summary follows ERCraft's illustrated card layout and uses the existing local
six-axis calculation. Generate a card from the most recent 20 ranked squad games:

```bash
erbs summary dantynoel --format path --output ./summary.png
erbs summary dantynoel --count 40 --art ./illustration.png \
  --card-title "六维实战档案" --format path --output ./summary-custom.png
```

`--count` accepts 1–60 games. `--season` selects a DAK season; otherwise the sample uses the
profile's current season. The card labels the actual recent-match sample and displays each
axis's score and eligible game count. Missing scores remain unavailable. It does not assign
website population percentiles or letter grades, and never uses the optional ERCraft API fallback.

`--art` requires a decodable local raster background image with exactly 1024×1536 pixels.
Without it, the renderer uses the most-played character from the sampled games and cached DAK
artwork. `--card-title` changes only the displayed title. In Python, use
`ERBSConfig(summary_art_path=Path("illustration.png"), summary_title="六维实战档案")`.
Both settings default to `None` and do not change the scoring data or query-cache identity.

```python
from erbs_plugin import player_summary, query

png_path = await player_summary("dantynoel", format="path", output="summary.png")
json_text = await query("summary", "dantynoel", count=20)
```

Summary results have an independent 180-second cache and do not reuse radar payloads.

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

The public letter-grade cuts differ from today's ERCraft website; JSON identifies them through
`gradeVersion`, while cards display numeric scores. See [scoring details](docs/SCORING.zh-CN.md)
for provenance, formulas, supported inputs, and offline verification.

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
