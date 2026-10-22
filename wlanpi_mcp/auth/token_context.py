"""
Per-request wlanpi-core JWT, captured from the inbound MCP request.

The MCP server does not implement its own authentication: clients present a
JWT issued by wlanpi-core, and that token is passed through on every outbound
API call, where wlanpi-core validates it.

BearerTokenMiddleware sets ``current_token`` (and ``current_request``) around
the downstream app. The MCP SDK runs each request's handler in the context of
the task that received it, so a tool or resource sees the values of the very
request that carried the call, with concurrent requests isolated from each
other.
"""

from contextvars import ContextVar

from starlette.requests import Request

current_token: ContextVar[str | None] = ContextVar("wlanpi_core_token", default=None)
current_request: ContextVar[Request | None] = ContextVar("wlanpi_request", default=None)


def get_token() -> str | None:
    """Return the current request's wlanpi-core JWT, or None."""
    return current_token.get()
