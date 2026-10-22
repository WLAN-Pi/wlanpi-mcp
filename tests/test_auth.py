import hashlib

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from wlanpi_mcp.auth.token_context import current_request, current_token, get_token
from wlanpi_mcp.download_links import request_base_url
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


# --- get_token() and request_base_url() read what the middleware set -------


def test_get_token_is_none_outside_any_request():
    assert get_token() is None


async def _echo_base_url(request):
    return JSONResponse({"base_url": request_base_url()})


async def test_middleware_current_request_reaches_request_base_url():
    app = Starlette(routes=[Route("/probe", _echo_base_url)])
    app.add_middleware(BearerTokenMiddleware)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(
            "/probe",
            headers={
                "Authorization": "Bearer t",
                "Host": "wlanpi-9be.local:8767",
                "X-Forwarded-Proto": "https",
            },
        )
    assert response.json() == {"base_url": "https://wlanpi-9be.local:8767"}
    assert current_request.get() is None
