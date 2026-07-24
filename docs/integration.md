# Integration

ERBS-plugin is a framework-neutral library. Platform adapters should:

1. Create one `AsyncERBSClient` and one `ERBSService` for the process lifetime.
2. Store platform-user bindings outside ERBS-plugin.
3. Apply platform-specific cooldowns before invoking the service.
4. Pass the configured local asset directory to `ERBSConfig`.
5. Send the single PNG returned by `HtmlCardRenderer.render` on success.
6. Convert typed ERBS exceptions into short, platform-appropriate error messages.

Do not pass platform event or message objects into ERBS-plugin services.
