# Integration contract

ERBS-plugin is a framework-neutral library. A consuming application should:

1. Import one of the async query functions or the lower-level client and service classes.
2. Reuse one `AsyncERBSClient` for the process lifetime when queries are frequent.
3. Reuse one `SkiaCardRenderer` when repeated PNG rendering is required.
4. Store application identities, preferences, bindings, and cooldowns outside this package.
5. Convert typed ERBS exceptions into presentation appropriate for the consuming application.
6. Deliver the returned JSON string, PNG bytes, or saved path using its own transport layer.

Do not pass application event, request, session, or message objects into ERBS-plugin services.

## High-level function API

```python
from erbs_plugin import query

json_text = await query("overview", "eternalreturn", format="json")
png_bytes = await query("overview", "eternalreturn", format="bytes")
png_path = await query(
    "overview",
    "eternalreturn",
    format="path",
    output="player.png",
)
```

The named functions expose the same contract with operation-specific arguments.

All high-level results include an ISO 8601 `footer.updatedAt` value. Cached results preserve the
original information timestamp and add `footer.cached=true` plus `footer.notice`; consumers should
surface that notice when presenting cached JSON outside the bundled card renderer.

## Resource ownership

- When no client or renderer is supplied, the function creates and closes its own resources.
- A caller-supplied client or renderer remains open and is never closed by the function.
- JSON output does not initialize Skia or download image assets.
- `path` output requires an explicit destination and is written through a temporary file followed
  by an atomic replace.

## Low-level API

Advanced consumers may create `AsyncERBSClient`, `ERBSService`, and `SkiaCardRenderer` directly.
Service methods return `CardPayload`, which can be rendered using `TextRenderer` or
`SkiaCardRenderer`.

## Operational boundary

The package reads public data, maintains in-process request caches and a private SQLite query-result
cache in the current user's platform data directory, resolves local assets, and renders cards. It
provides optional stateless slash-command parsing through `parse_command` / `execute_command`. It
does not manage external-user identities, preferences, permissions, scheduling, or message delivery. Configure the database path and per-operation TTLs with `ERBSConfig`.

## Commands and legacy graphics

`execute_command('/查询角色 席琳 排位 灭钻', format='bytes')` shares the normal dispatcher and cache.
See [DAK.GG query contracts](DAK_QUERIES.zh-CN.md) for all new functions and filter values.
`CardRenderer` is a protocol with async `render(payload) -> bytes` and `close()` methods.

Default PNG output uses Skia. Previous browser graphics live under
[`erbs_plugin.legacy`](../src/erbs_plugin/legacy/README.md); existing explicit imports must move to
`from erbs_plugin.legacy.rendering import HtmlCardRenderer` and install `erbs-plugin[legacy-render]`.
