# ERBS-plugin

Framework-agnostic Eternal Return data, analysis, asset, and card-rendering library.

ERBS-plugin contains no NoneBot, Discord, QQ, or platform event types. Bot projects consume the
Python API and provide their own command adapters.

## Install

```bash
pip install erbs-plugin
pip install 'erbs-plugin[render]'
```

The render extra uses an existing Chrome, Edge, or Chromium installation; it does not download a
browser automatically.

## Quick start

```python
from erbs_plugin import AsyncERBSClient, ERBSService

async with AsyncERBSClient() as client:
    service = ERBSService(client)
    card = await service.player_overview("eternalreturn")
```

Download image assets before enabling image rendering:

```bash
erbs-assets download --directory ./data/erbs-assets
erbs-assets check --directory ./data/erbs-assets
```

Runtime code never downloads missing images. See [docs/integration.md](docs/integration.md).

## Data source and boundaries

Data is read from public DAK.GG Eternal Return endpoints used by its public website. The library
does not invoke player refresh, authentication, management, or write endpoints. Consumers should
use conservative caching and request rates and display `Data source: DAK.GG`.

## License

Apache-2.0. Third-party inspiration and notices are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
