"""Application errors whose messages are safe to show to the shopper."""


class ShopError(RuntimeError):
    """An actionable error safe to expose to the local presenter."""
