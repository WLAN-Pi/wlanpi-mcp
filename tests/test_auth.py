import hashlib

import httpx
import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from wlanpi_mcp.auth.token_context import current_token, get_token
from wlanpi_mcp.middleware.bearer_token import BearerTokenMiddleware


async def _echo_token(request):
    # Reports what the downstream app sees in the token contextvar and the
    # principal the middleware published for the connection.
    user = request.scope.get("user")
    return JSONResponse(
        {
            "token": get_token(),
            "client_id": getattr(user, "username", None),
        }
    )


def _make_app():
    app = Starlette(routes=[Route("/probe", _echo_token)])
    return BearerTokenMiddleware(app)


@pytest.fixture
def http():
    transport = httpx.ASGITransport(app=_make_app())
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_rejects_missing_authorization(http):
    response = await http.get("/probe")
    assert response.status_code == 401
    assert "Bearer" in response.json()["detail"]


async def test_rejects_non_bearer_authorization(http):
    response = await http.get("/probe", headers={"Authorization": "Basic dXNlcjpwdw=="})
    assert response.status_code == 401


async def test_rejects_empty_bearer(http):
    response = await http.get("/probe", headers={"Authorization": "Bearer   "})
    assert response.status_code == 401


async def test_passes_token_to_downstream_context(http):
    response = await http.get(
        "/probe", headers={"Authorization": "Bearer core.jwt.abc123"}
    )
    assert response.status_code == 200
    assert response.json()["token"] == "core.jwt.abc123"


async def test_context_reset_after_request(http):
    await http.get("/probe", headers={"Authorization": "Bearer core.jwt.abc123"})
    assert current_token.get() is None


async def test_publishes_token_fingerprint_principal(http):
    token = "core.jwt.abc123"
    response = await http.get("/probe", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    expected = hashlib.sha256(token.encode()).hexdigest()
    assert response.json()["client_id"] == expected


# --- get_token(): the MCP request context is the primary source -------------
#
# The streamable HTTP transport binds the Starlette request to every MCP call
# and the server exposes it via request_ctx while a handler runs. Tool calls
# run in a task the session manager spawns, so the header on that request,
# not the middleware's contextvar, is the authoritative token for the call.


def _bind_request(authorization: str | None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": headers,
            "query_string": b"",
        }
    )
    ctx = RequestContext(
        request_id=1, meta=None, session=None, lifespan_context=None, request=request
    )
    return request_ctx.set(ctx)


def test_get_token_reads_bearer_from_request_context():
    reset = _bind_request("Bearer core.jwt.fromreq")
    try:
        assert get_token() == "core.jwt.fromreq"
    finally:
        request_ctx.reset(reset)


def test_request_context_wins_over_inherited_contextvar():
    # A stale inherited contextvar must never outrank the header that carried
    # the call being handled.
    ctx = current_token.set("core.jwt.inherited")
    reset = _bind_request("Bearer core.jwt.fromreq")
    try:
        assert get_token() == "core.jwt.fromreq"
    finally:
        request_ctx.reset(reset)
        current_token.reset(ctx)


def test_get_token_falls_back_to_contextvar_without_bearer_on_request():
    ctx = current_token.set("core.jwt.inherited")
    reset = _bind_request(None)
    try:
        assert get_token() == "core.jwt.inherited"
    finally:
        request_ctx.reset(reset)
        current_token.reset(ctx)


def test_get_token_is_none_outside_any_request():
    assert get_token() is None
