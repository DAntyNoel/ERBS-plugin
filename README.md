# ERBS-plugin

[中文说明](docs/README.zh-CN.md) · [中文快速开始](docs/QUICK_START.md)

ERBS-plugin is a bot plugin for Chinese internet services. It queries public Eternal Return data,
performs analysis, produces JSON output, manages local image assets, and renders PNG data cards.

This is a personal project intended only for learning, discussion, and reference. Ongoing updates
and availability are not guaranteed. Please contact the author to request removal or correction of
any infringing material or code issue.

## Install

Python >= 3.12 is required.

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
erbs overview playername
erbs matches playername --count 10
```

Prepare local assets and render a PNG file:

```bash
erbs assets download --directory ./data/erbs-assets
erbs assets check --directory ./data/erbs-assets
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

Long-running applications can reuse `AsyncERBSClient` and `HtmlCardRenderer`; resources supplied by
the caller remain owned by the caller.

## Data, cache, and assets

Data is read from public DAK.GG Eternal Return endpoints used by its public website. The package
does not invoke player refresh, authentication, management, or write endpoints. Consumers should
use conservative request rates and display `Data source: DAK.GG` where appropriate.

Successful high-level queries are cached in a private SQLite database under the current user's
platform data directory. Cache expiry is configured independently for every query operation through
`ERBSConfig.query_cache_seconds`; cache identity also includes arguments, language, and API endpoint.
Every result includes `footer.updatedAt`; cache hits additionally include `footer.cached=true` and a
human-readable `footer.notice` warning that the data may not be current.

Runtime rendering searches the current directory and its parents for downloaded local assets. It
reuses matching files and falls back to the bundled placeholder when an image is missing; it never
downloads missing assets implicitly.

## Disclaimer and trademarks

ERBS-plugin is an unofficial project and is not affiliated with Nimble Neuron. Eternal Return is a
trademark of Nimble Neuron. The bundled two-line Chinese/English wordmark is independently generated
for this project and is not an official Eternal Return logo.

## License

Apache-2.0. Third-party inspiration and notices are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
