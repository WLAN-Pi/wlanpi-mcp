"""
Per-request wlanpi-core JWT, captured from the inbound MCP connection.

The MCP server does not implement its own authentication: clients present a
JWT issued by wlanpi-core, and that token is passed through on every outbound
API call, where wlanpi-core validates it.
"""

from contextvars import ContextVar

current_token: ContextVar[str | None] = ContextVar("wlanpi_core_token", default=None)


def get_token() -> str | None:
    """Return the current request's wlanpi-core JWT, or None."""
    return current_token.get()
