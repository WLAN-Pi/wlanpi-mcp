"""
Per-request wlanpi-core JWT, captured from the inbound MCP request.

The MCP server does not implement its own authentication: clients present a
JWT issued by wlanpi-core, and that token is passed through on every outbound
API call, where wlanpi-core validates it.

Two sources feed get_token(), checked in this order:

1. The HTTP request bound to the MCP call being handled. The streamable HTTP
   transport attaches the Starlette request to every JSON-RPC message and the
   MCP server exposes it through its request context while a tool/resource
   handler runs. This is authoritative: it is the header that carried this
   very call, and it does not depend on which task the handler runs in.
2. The ``current_token`` contextvar set by BearerTokenMiddleware. Tool calls
   run in a task the session manager spawns from inside the request, so the
   contextvar is inherited too, but it is the fallback rather than the rule.
"""

from contextvars import ContextVar

from mcp.server.lowlevel.server import request_ctx

current_token: ContextVar[str | None] = ContextVar("wlanpi_core_token", default=None)


def _bearer_from_request_context() -> str | None:
    """Return the Bearer token on the HTTP request behind the current MCP call."""
    try:
        ctx = request_ctx.get()
    except LookupError:
        return None
    headers = getattr(getattr(ctx, "request", None), "headers", None)
    if headers is None:
        return None
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return auth.removeprefix("Bearer ").strip() or None


def get_token() -> str | None:
    """Return the current request's wlanpi-core JWT, or None."""
    return _bearer_from_request_context() or current_token.get()
