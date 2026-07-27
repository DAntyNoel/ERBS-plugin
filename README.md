# ERBS-plugin

[中文说明](README.zh-CN.md) · [中文快速开始](QUICK_START.md)

ERBS-plugin is an independent, framework-neutral Python package for Eternal Return data queries,
analysis, JSON output, local asset management, and PNG card rendering.

It does not parse application events, store application-user bindings, enforce application-level
cooldowns, or send messages. Consumers import its Python API or invoke its command-line interface
and decide how to present the returned JSON text or PNG data.

## Install

Python 3.12 is required.

```bash
pip install erbs-plugin
```

PNG output additionally requires the render extra and an existing Chrome, Edge, or Chromium
installation:

```bash
pip install 'erbs-plugin[render]'
```

## Command line

Query JSON directly:

```bash
erbs overview eternalreturn
erbs matches eternalreturn --count 10
```

Prepare local assets and render a PNG file:

```bash
erbs assets download --directory ./data/erbs-assets
erbs assets check --directory ./data/erbs-assets
erbs overview eternalreturn \
  --format path \
  --output ./player.png
```

Raw PNG bytes can be piped or redirected:

```bash
erbs overview eternalreturn --format bytes > player.png
```

The same CLI is available through `python -m erbs_plugin`. The existing `erbs-assets` command is
retained for compatibility.

## Python API

The recommended API consists of async query functions:

```python
from erbs_plugin import player_overview

json_text = await player_overview("eternalreturn", format="json")
png_bytes = await player_overview("eternalreturn", format="bytes")
png_path = await player_overview(
    "eternalreturn",
    format="path",
    output="player.png",
)
```

Available functions cover player overview, rank, statistics, matches, recent performance, radar,
characters, teammates, best matches, hero pools, equipment habits, leaderboards, character
statistics, items, and routes. The generic `query()` function exposes the same supported operations
through a single entry point.

Long-running consumers can pass an existing `AsyncERBSClient` and `HtmlCardRenderer`; resources
supplied by the caller remain owned by the caller. The lower-level client, service, model, analysis,
and renderer classes remain public for advanced use.

Successful high-level queries are cached in a private SQLite database under the current user's
platform data directory. Cache expiry is configured independently for every query operation through
`ERBSConfig.query_cache_seconds`; cache identity also includes arguments, language, and API endpoint.
Every result includes `footer.updatedAt`; cache hits additionally include `footer.cached=true` and a
human-readable `footer.notice` warning that the data may not be current.

See [QUICK_START.md](QUICK_START.md) and [docs/integration.md](docs/integration.md).

## Data source and boundaries

Data is read from public DAK.GG Eternal Return endpoints used by its public website. The package
does not invoke player refresh, authentication, management, or write endpoints. Consumers should
use conservative request rates and display `Data source: DAK.GG` where appropriate.

Runtime rendering searches the current directory and its parents for downloaded local assets. It
reuses matching files and falls back to the bundled placeholder when an image is missing; it never
downloads missing assets implicitly.

## License

Apache-2.0. Third-party inspiration and notices are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
