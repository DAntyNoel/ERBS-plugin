class ERBSError(Exception):
    """Base exception for ERBS-plugin."""


class InvalidQuery(ERBSError):
    pass


class PlayerNotFound(ERBSError):
    pass


class RateLimited(ERBSError):
    pass


class UpstreamUnavailable(ERBSError):
    pass


class AssetMissing(ERBSError):
    pass


class RenderFailed(ERBSError):
    pass
