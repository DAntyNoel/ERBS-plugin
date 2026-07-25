# Integration contract

ERBS-plugin is a framework-neutral library. A consuming application should:

1. Import one of the async query functions or the lower-level client and service classes.
2. Reuse one `AsyncERBSClient` for the process lifetime when queries are frequent.
3. Reuse one `HtmlCardRenderer` when repeated PNG rendering is required.
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
- JSON output does not initialize the browser renderer.
- `path` output requires an explicit destination and is written through a temporary file followed
  by an atomic replace.

## Low-level API

Advanced consumers may create `AsyncERBSClient`, `ERBSService`, and `HtmlCardRenderer` directly.
Service methods return `CardPayload`, which can be rendered using `TextRenderer` or
`HtmlCardRenderer`.

## Operational boundary

The package reads public data, maintains in-process request caches and a private SQLite query-result
cache in the current user's platform data directory, resolves local assets, and renders cards. It
does not manage external-user identities, preferences, permissions, scheduling, command syntax, or
message delivery. Configure the database path and per-operation TTLs with `ERBSConfig`.
