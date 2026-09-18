"""Regression guards for the assembled SSE app as nginx presents it."""

import uuid

import httpx
import pytest

from wlanpi_mcp.middleware.bearer_token import BearerTokenMiddleware
from wlanpi_mcp.server import create_server

# What the daemon sees through the nginx front: the client's real Host and
# Origin are forwarded verbatim (proxy_set_header Host $http_host), so the
# loopback-only daemon must accept LAN addresses, hostnames and both ports.
FORWARDED_HEADERS = [
    {"Host": "10.254.102.51:8767", "Origin": "https://10.254.102.51:8767"},
    {"Host": "10.254.102.51:8766", "Origin": "http://10.254.102.51:8766"},
    {"Host": "wlanpi-9be.local:8767"},
]


@pytest.fixture
def sse_app(client):
    mcp = create_server(client, host="127.0.0.1", port=8768)
    app = mcp.sse_app()
    app.add_middleware(BearerTokenMiddleware)
    return app


@pytest.fixture
def http(sse_app):
    transport = httpx.ASGITransport(app=sse_app)
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8768")


def test_dns_rebinding_protection_is_off_for_loopback_bind(client):
    # FastMCP flips this on automatically for host=127.0.0.1; the nginx front
    # forwards LAN Host headers, so it must stay off (the Bearer gate is the
    # protection).
    mcp = create_server(client, host="127.0.0.1", port=8768)
    security = mcp.settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is False


@pytest.mark.parametrize("headers", FORWARDED_HEADERS)
async def test_messages_accepts_forwarded_lan_host(http, headers):
    response = await http.post(
        f"/messages/?session_id={uuid.uuid4().hex}",
        json={},
        headers={"Authorization": "Bearer core.jwt.abc123", **headers},
    )
    # The request must reach the transport: 404 is "unknown session", which
    # is the expected answer here. 421/403 mean the Host/Origin check fired.
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("headers", FORWARDED_HEADERS)
async def test_sse_accepts_forwarded_lan_host(sse_app, headers):
    # GET /sse is a never-ending stream, so drive the ASGI app directly and
    # capture the response status, then disconnect.
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/sse",
        "raw_path": b"/sse",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in {"Authorization": "Bearer core.jwt.abc123", **headers}.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8768),
    }
    status: list[int] = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status.append(message["status"])

    try:
        await sse_app(scope, receive, send)
    except ValueError:
        # The SDK raises "Request validation failed" after sending a 421; the
        # status assertion below is the finding, not this exception.
        pass

    # The SDK also emits a trailing empty Response() once the stream closes on
    # disconnect; only the first response start is the stream's status.
    assert status[:1] == [200], status
