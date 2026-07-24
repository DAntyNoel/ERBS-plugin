# Developer guide

This guide covers development and troubleshooting for the standalone ERBS-plugin package.

## Architecture

```text
CLI or Python caller
  -> functional API and operation dispatcher
  -> ERBSService and ERBSAnalysisService
  -> AsyncERBSClient and in-process caches
  -> TextRenderer or HtmlCardRenderer
  -> local asset manifest for PNG rendering
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

## Query failures

`AsyncERBSClient` defaults to `https://er.dakgg.io`, an 8-second timeout, two retries, and bounded
concurrency. Player 404 responses become `PlayerNotFound`, 429 becomes `RateLimited`, and network,
5xx, or invalid JSON failures become `UpstreamUnavailable`.

Use `--api-base-url` and `--language` for CLI configuration, or pass `ERBSConfig` from Python.

## Rendering failures

PNG rendering requires:

- installation with the `render` extra;
- Chrome, Edge, or Chromium;
- a valid local asset manifest;
- matching `asset_directory` values during download and rendering.

Check browser discovery and assets with:

```bash
uv run erbs assets check --directory ./data/erbs-assets
uv run erbs overview eternalreturn \
  --format path \
  --output /tmp/erbs-card.png \
  --asset-directory ./data/erbs-assets
```

The renderer maps remote image references to local assets and embeds them as data URIs. Runtime
queries do not download missing files.

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
