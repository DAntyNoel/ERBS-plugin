# Developer guide

This guide covers development and troubleshooting for the standalone ERBS-plugin package.

## Architecture

```text
CLI or Python caller
  -> functional API and operation dispatcher
  -> private SQLite query cache with per-operation TTLs
  -> ERBSService and ERBSAnalysisService
  -> AsyncERBSClient and in-process caches
  -> TextRenderer or SkiaCardRenderer
  -> on-demand DAK.GG CDN assets and local manifest for PNG rendering
```

The package boundary ends after returning JSON text, PNG bytes, or a saved `Path`.

## Local checks

Run from the repository root with Python 3.12:

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run pytest
uv run python -m compileall -q src
uv build
```

CLI smoke checks:

```bash
uv run erbs --help
uv run python -m erbs_plugin --help
uv run erbs overview eternalreturn
```

## Card preview scaffold

The repository has a live debug command for reviewing every command image against the shared card
renderer. It executes the same service methods as normal commands and prepares referenced CDN
image assets on demand:

```bash
uv run erbs debug
```

Pre-downloading assets is optional. Failed downloads use placeholders; JSON output never prepares images.

The command renders all 24 supported default command cards, then writes their PNG results,
`manifest.json`, and a browser-friendly contact sheet to `.debug/cards/`.
Open `.debug/cards/index.html`, adjust
`src/erbs_plugin/rendering/skia.py`, and rerun the command to refresh the
whole set.

Every bare `erbs debug` run rerenders all supported default command cards. Debug and normal queries
share the private SQLite query database when the operation, arguments, language, and API endpoint
match, so rendering iterations do not repeatedly call DAK.GG. Pass `--refresh-data` to replace
matching cached payloads with fresh network results. The former `--only` interface has been removed
so visual reviews cannot accidentally omit layouts. `erbs debug cards` remains as a compatibility
alias for the same full rerender.

The default players are `B站丨咕咕禽OC`, `Preme`, and `페이블`. Player commands use the first
player.

Render an additional custom query into the same gallery when needed:

```bash
uv run erbs debug overview eternalreturn
uv run erbs debug matches eternalreturn --count 10
```

The live debug commands mirror the normal query command arguments and output options. Their stdout
is identical to the corresponding normal command (JSON by default, or the requested bytes/path),
while a PNG is also stored as a persistent custom entry in `.debug/cards/index.html`. The debug
save notice is written to stderr so it cannot corrupt JSON or PNG output. Both full and custom
debug runs use the configured DAK.GG endpoint and local asset directory.

The default query arguments live in `src/erbs_plugin/debug.py`. Add a real default query there when
a new query command or section layout is introduced; player-facing preview data must not be
handwritten.

## Query failures

Successful high-level queries are persisted to `ERBSConfig.private_database_path`, which defaults to
the current user's platform data directory. Each operation has its own TTL in
`query_cache_seconds`; expired rows are removed lazily, cache hits update `last_accessed_at`, and the
oldest rows are bounded by `query_cache_max_entries`. SQLite failures are treated as cache misses so
the private cache cannot make an otherwise healthy network query fail.

The high-level query boundary stamps every fresh payload with `footer.updatedAt` before it is stored.
Database hits retain the original timestamp and add `footer.cached=true` plus a localized
`footer.notice`. Player source synchronization timestamps remain available separately as
`footer.sourceUpdatedAt`.

`AsyncERBSClient` defaults to `https://er.dakgg.io`, an 8-second timeout, two bounded exponential
retries, and bounded concurrency. It retries transient transport failures, 408/425/429 responses,
5xx responses, and invalid response payloads; `Retry-After` is honored up to the configured retry
delay cap. A successful response remains available as a stale fallback for 15 minutes after its
normal cache TTL, so a brief upstream outage does not immediately break an otherwise cached query.
Stale results include `_erbs_cached: true` and `_erbs_stale: true`.

Player 404 responses become `PlayerNotFound`. An exhausted 429 becomes `RateLimited`; other
exhausted transient failures become `UpstreamUnavailable`. Configure this behavior with
`retry_count`, `retry_backoff_seconds`, `retry_max_delay_seconds`, and `stale_cache_seconds` on
`ERBSConfig`.

Use `--api-base-url` and `--language` for CLI configuration, or pass `ERBSConfig` from Python.

## Rendering failures

PNG rendering requires:

- installation with the `render` extra;
- fonts covering the requested language (Noto Sans CJK on Linux, or `render_font_path`);
- CDN access or a downloaded asset manifest for real character and item images.

Check asset consistency and rendering with:

```bash
uv run erbs assets check --directory ./data/erbs-assets
uv run erbs overview eternalreturn \
  --format path \
  --output /tmp/erbs-card.png
```

The renderer automatically searches the current directory and its parents for `assets/`,
`data/erbs-assets/`, or `erbs-assets/`, then checks the platform user-data directory. It maps
remote image references to matching local files, downloads missing referenced `cdn.dak.gg` images,
and draws them natively. Set `download_render_assets=False` for local-only rendering. Failed
downloads use the bundled placeholder; successful files are kept even when another download fails.

## Asset maintenance

```bash
uv run erbs assets download --directory ./data/erbs-assets
uv run erbs assets update --directory ./data/erbs-assets
uv run erbs assets prune --directory ./data/erbs-assets
uv run erbs assets check --directory ./data/erbs-assets
```

CDN 403 or 404 responses are stored as explicit placeholder entries. Other HTTP failures remain
errors. Manifest writes and final `format="path"` card writes are atomic.

## Fixture alignment

`tests/test_dak_alignment.py` contains a captured public response fixture and verifies model parsing,
match ordering, character names, and equipment names. When the upstream response shape changes,
capture a new fixture deliberately and update assertions only after confirming the new semantics.

## Boundary checks

Package source must remain independent from any consuming application's framework, event types,
identity storage, cooldown rules, and transport implementation. Add integration behavior to the
consumer and expose only reusable data/query/rendering behavior here.

## DAK.GG and graphics migration

Character details are read from the public character page's `__NEXT_DATA__` snapshot; player,
character-table and tier statistics use public GET endpoints. No page JavaScript is executed.
See [the query guide](DAK_QUERIES.zh-CN.md) for endpoint and aggregation contracts.

The archived HTML/CSS renderer, bundled theme and SVG geometry are under
[`src/erbs_plugin/legacy/`](../src/erbs_plugin/legacy/README.md). Active radar payloads contain
semantic scores; the legacy renderer adds its own coordinates without mutating the payload.
