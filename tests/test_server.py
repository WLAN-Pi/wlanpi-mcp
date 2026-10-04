"""Regression guards for the assembled streamable HTTP app as nginx presents it."""

import shlex
from contextlib import asynccontextmanager

import httpx
import pytest
import respx

from wlanpi_mcp.client.core_client import CoreClient
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

# The streamable HTTP transport refuses a POST without both media types in
# Accept (406), whatever the response mode.
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

DEVICE_INFO_URL = "https://localhost:31415/api/v1/system/device/info"


def _initialize(request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }


def _call_tool(name: str, request_id: int = 2) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    }


@pytest.fixture
def core(settings):
    # Deliberately not the conftest `client` fixture: that one pre-sets the
    # token contextvar, which would mask whether the token really travels
    # from the HTTP header into the tool call.
    return CoreClient(settings)


@pytest.fixture
def mcp(core):
    return create_server(core, host="127.0.0.1", port=8768)


@asynccontextmanager
async def _serve(mcp, *, with_middleware: bool = True):
    """Yield an httpx client bound to the assembled app, with its lifespan running.

    httpx's ASGITransport does not run the app lifespan, which is where the
    session manager starts the task group every request is served from. This
    is a context manager rather than an async fixture because the manager's
    task group must be entered and exited in the same task, and pytest-asyncio
    tears async-generator fixtures down elsewhere.

    Pass with_middleware=False to omit BearerTokenMiddleware, so the contextvar
    it would set stays untouched and get_token() has only the transport-bound
    request to read from.
    """
    app = mcp.streamable_http_app()
    if with_middleware:
        app.add_middleware(BearerTokenMiddleware)
    transport = httpx.ASGITransport(app=app)
    async with mcp.session_manager.run():
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8768"
        ) as http:
            yield http


def test_dns_rebinding_protection_is_off_for_loopback_bind(mcp):
    # FastMCP flips this on automatically for host=127.0.0.1; the nginx front
    # forwards LAN Host headers, so it must stay off (the Bearer gate is the
    # protection).
    security = mcp.settings.transport_security
    assert security is not None
    assert security.enable_dns_rebinding_protection is False


def test_transport_is_stateless_json_on_mcp_path(mcp):
    # Stateless is the point of the move: no server-side session for a
    # reconnecting client to strand on. JSON responses keep nginx/curl simple.
    assert mcp.settings.streamable_http_path == "/mcp"
    assert mcp.settings.stateless_http is True
    assert mcp.settings.json_response is True


@pytest.mark.parametrize("headers", FORWARDED_HEADERS)
async def test_mcp_accepts_forwarded_lan_host(mcp, headers):
    async with _serve(mcp) as http:
        response = await http.post(
            "/mcp",
            json=_initialize(),
            headers={
                "Authorization": "Bearer core.jwt.abc123",
                **MCP_HEADERS,
                **headers,
            },
        )
    # 421/403 mean the Host/Origin check fired.
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "WLAN Pi"


async def test_mcp_rejects_missing_bearer(mcp):
    async with _serve(mcp) as http:
        response = await http.post("/mcp", json=_initialize(), headers=MCP_HEADERS)
    assert response.status_code == 401


@respx.mock
async def test_tool_call_without_initialize_forwards_bearer(mcp):
    # The failure that forced the move off SSE: a client that reconnected
    # without re-sending initialize had every tools/call answered -32602.
    # Stateless mode has no handshake to miss, and the call's own Bearer is
    # what reaches wlanpi-core.
    route = respx.get(DEVICE_INFO_URL).mock(
        return_value=httpx.Response(200, json={"hostname": "wlanpi-9be"})
    )
    async with _serve(mcp) as http:
        response = await http.post(
            "/mcp",
            json=_call_tool("get_device_info"),
            headers={"Authorization": "Bearer core.jwt.abc123", **MCP_HEADERS},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    assert body["result"]["isError"] is False
    assert body["result"]["structuredContent"] == {"hostname": "wlanpi-9be"}
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer core.jwt.abc123"


@respx.mock
async def test_each_request_carries_its_own_token(mcp):
    # Stateless replacement for the SSE session binding: with no session to
    # share, a request can only ever run with the token it carried itself.
    route = respx.get(DEVICE_INFO_URL).mock(
        return_value=httpx.Response(200, json={"hostname": "wlanpi-9be"})
    )
    async with _serve(mcp) as http:
        for token in ("token-A", "token-B", "token-A"):
            response = await http.post(
                "/mcp",
                json=_call_tool("get_device_info"),
                headers={"Authorization": f"Bearer {token}", **MCP_HEADERS},
            )
            assert response.status_code == 200, response.text
            assert response.json()["result"]["isError"] is False
    seen = [call.request.headers["Authorization"] for call in route.calls]
    assert seen == ["Bearer token-A", "Bearer token-B", "Bearer token-A"]


@respx.mock
async def test_transport_populates_request_header_token(mcp):
    # get_token() reads the Authorization header off the Starlette request the
    # streamable HTTP transport binds to each MCP call (the SDK's request_ctx).
    # The middleware path would set the same token on the contextvar, so it
    # cannot distinguish the two. Run the app WITHOUT the middleware and poison
    # the contextvar with a decoy: only a transport-bound request can supply the
    # real token, so this fails if the SDK ever stops populating request_ctx.
    from wlanpi_mcp.auth.token_context import current_token

    route = respx.get(DEVICE_INFO_URL).mock(
        return_value=httpx.Response(200, json={"hostname": "wlanpi-9be"})
    )
    reset = current_token.set("decoy.contextvar.token")
    try:
        async with _serve(mcp, with_middleware=False) as http:
            response = await http.post(
                "/mcp",
                json=_call_tool("get_device_info"),
                headers={"Authorization": "Bearer header.token", **MCP_HEADERS},
            )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["isError"] is False
        # The decoy contextvar is still set, so only a transport-bound request
        # could have produced the real token; core saw the header, not the decoy.
        assert route.call_count == 1
        assert route.calls[0].request.headers["Authorization"] == "Bearer header.token"
    finally:
        current_token.reset(reset)


@respx.mock
async def test_pcap_download_link_serves_the_file_once_without_a_jwt(
    mcp, monkeypatch, tmp_path
):
    # The point of the link: an agent saves a pcap with plain curl, the bytes
    # never pass through the MCP result, and curl needs no JWT. The ticket is
    # minted by an authenticated tool call, works once, then 404s.
    from wlanpi_mcp.capture import storage
    from wlanpi_mcp.config import Settings
    from wlanpi_mcp.tools import capture_file

    settings = Settings(PCAP_CAPTURE_DIR=str(tmp_path), _env_file=None)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(capture_file, "get_settings", lambda: settings)
    capture_file._TICKETS.clear()
    data = b"\x0a\x0d\x0d\x0a" + bytes(range(256)) * 4
    pcap = tmp_path / "capture-20261003T120000-cap_e2e.pcapng"
    pcap.write_bytes(data)
    respx.get(DEVICE_INFO_URL).mock(
        return_value=httpx.Response(200, json={"hostname": "wlanpi-9be"})
    )

    call = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "get_pcap_download_url",
            "arguments": {"capture_id": "cap_e2e"},
        },
    }
    async with _serve(mcp) as http:
        response = await http.post(
            "/mcp",
            json=call,
            headers={
                "Authorization": "Bearer core.jwt.abc123",
                "Host": "wlanpi-9be.local:8767",
                "X-Forwarded-Proto": "https",
                **MCP_HEADERS,
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]["structuredContent"]
        url = result["download_url"]
        assert url.startswith("https://wlanpi-9be.local:8767/pcap/")
        assert result["size_bytes"] == len(data)
        assert url in result["curl"] and result["curl"].startswith("curl -gsSfk -o ")
        route = url.removeprefix("https://wlanpi-9be.local:8767")

        first = await http.get(route)  # no Authorization header
        assert first.status_code == 200
        assert first.content == data
        assert first.headers["content-type"] == capture_file.PCAP_MIME

        again = await http.get(route)
        assert again.status_code == 404

        bogus = await http.get("/pcap/not-a-ticket")
        assert bogus.status_code == 404

        # Everything else still needs the Bearer token.
        still_gated = await http.post("/mcp", json=_initialize(), headers=MCP_HEADERS)
        assert still_gated.status_code == 401


async def test_expired_pcap_download_link_is_refused(mcp, monkeypatch, tmp_path):
    from wlanpi_mcp.capture import storage
    from wlanpi_mcp.config import Settings
    from wlanpi_mcp.tools import capture_file

    settings = Settings(PCAP_CAPTURE_DIR=str(tmp_path), _env_file=None)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    pcap = tmp_path / "capture-20261003T120000-cap_old.pcapng"
    pcap.write_bytes(b"\x0a\x0d\x0d\x0a")
    capture_file._TICKETS.clear()
    capture_file._TICKETS["stale"] = (str(pcap.resolve()), 1.0)  # long expired
    async with _serve(mcp) as http:
        response = await http.get("/pcap/stale")
    assert response.status_code == 404
    assert capture_file._TICKETS == {}


@respx.mock
async def test_profiler_report_links_serve_each_file_once_without_a_jwt(
    mcp, monkeypatch, tmp_path
):
    # get_profiler_reports(output="links") mints a ticket per file through an
    # authenticated /mcp call; plain curl then fetches each one once.
    from wlanpi_mcp.config import Settings
    from wlanpi_mcp.tools import profiler_reports

    settings = Settings(PROFILER_DATA_DIR=str(tmp_path), _env_file=None)
    monkeypatch.setattr(profiler_reports, "get_settings", lambda: settings)
    profiler_reports._TICKETS.clear()
    client_dir = tmp_path / "clients" / "aa-bb-cc-dd-ee-ff"
    client_dir.mkdir(parents=True)
    (client_dir / "aa-bb-cc-dd-ee-ff_5GHz.json").write_text('{"mac": "x"}')
    (client_dir / "aa-bb-cc-dd-ee-ff_5GHz.pcap").write_bytes(b"\xd4\xc3\xb2\xa1")
    (tmp_path / "reports").mkdir()
    respx.get(DEVICE_INFO_URL).mock(return_value=httpx.Response(200, json={}))
    call = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "get_profiler_reports", "arguments": {"output": "links"}},
    }
    async with _serve(mcp) as http:
        response = await http.post(
            "/mcp",
            json=call,
            headers={
                "Authorization": "Bearer core.jwt.abc123",
                "Host": "wlanpi-9be.local:8767",
                "X-Forwarded-Proto": "https",
                **MCP_HEADERS,
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]["structuredContent"]
        files = {f["path"]: f["download_url"] for f in result["files"]}
        pcap_url = files["clients/aa-bb-cc-dd-ee-ff/aa-bb-cc-dd-ee-ff_5GHz.pcap"]
        assert pcap_url.startswith("https://wlanpi-9be.local:8767/profiler-report/")
        route = pcap_url.removeprefix("https://wlanpi-9be.local:8767")

        first = await http.get(route)  # no Authorization header
        assert first.status_code == 200
        assert first.content == b"\xd4\xc3\xb2\xa1"
        assert first.headers["content-type"] == "application/vnd.tcpdump.pcap"
        assert "aa-bb-cc-dd-ee-ff_5GHz.pcap" in first.headers["content-disposition"]

        assert (await http.get(route)).status_code == 404
        assert (await http.get("/profiler-report/nope")).status_code == 404
    # The core token check ran with the caller's own JWT.
    assert respx.calls[0].request.headers["Authorization"] == "Bearer core.jwt.abc123"


def test_ticket_download_routes_are_the_only_routes_without_a_jwt(mcp):
    # BearerTokenMiddleware exempts everything under TICKET_PATH_PREFIXES, so
    # any other route added there would be served without authentication.
    from wlanpi_mcp.middleware.bearer_token import TICKET_PATH_PREFIXES
    from wlanpi_mcp.tools import capture_file, profiler_reports

    exempt = sorted(
        route.path
        for route in mcp.streamable_http_app().routes
        if route.path.startswith(TICKET_PATH_PREFIXES)
    )
    assert exempt == sorted(
        [
            capture_file.DOWNLOAD_PREFIX + "{ticket}",
            profiler_reports.REPORT_PREFIX + "{ticket}",
        ]
    )
    assert sorted(TICKET_PATH_PREFIXES) == sorted(
        [capture_file.DOWNLOAD_PREFIX, profiler_reports.REPORT_PREFIX]
    )


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        # A list from a proxy chain: the first hop is the client's scheme.
        (
            {"Host": "wlanpi-9be.local:8767", "X-Forwarded-Proto": "https, http"},
            "https://wlanpi-9be.local:8767/pcap/",
        ),
        (
            {"Host": "[fe80::1]:8767", "X-Forwarded-Proto": "https"},
            "https://[fe80::1]:8767/pcap/",
        ),
        # Not a scheme: fall back to the one the request arrived on.
        (
            {"Host": "10.0.0.5:8766", "X-Forwarded-Proto": "javascript"},
            "http://10.0.0.5:8766/pcap/",
        ),
        # A Host that is not a plain host[:port] gets no link or curl command.
        ({"Host": "evil'; rm -rf ~; echo '"}, None),
    ],
)
@respx.mock
async def test_pcap_download_link_sanitises_forwarded_headers(
    mcp, monkeypatch, tmp_path, headers, expected
):
    from wlanpi_mcp.capture import storage
    from wlanpi_mcp.config import Settings
    from wlanpi_mcp.tools import capture_file

    settings = Settings(PCAP_CAPTURE_DIR=str(tmp_path), _env_file=None)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(capture_file, "get_settings", lambda: settings)
    (tmp_path / "capture-20261003T120000-cap_h.pcapng").write_bytes(b"x")
    respx.get(DEVICE_INFO_URL).mock(return_value=httpx.Response(200, json={}))
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_pcap_download_url",
            "arguments": {"capture_id": "cap_h"},
        },
    }
    async with _serve(mcp) as http:
        response = await http.post(
            "/mcp",
            json=call,
            headers={"Authorization": "Bearer t", **headers, **MCP_HEADERS},
        )
    result = response.json()["result"]["structuredContent"]
    if expected is None:
        assert "download_url" not in result and "curl" not in result
        assert result["download_path"].startswith("/pcap/")
    else:
        assert result["download_url"].startswith(expected)
        # IPv6 brackets are quoted for the shell; -g stops curl globbing them.
        args = shlex.split(result["curl"])
        assert args[0] == "curl" and "g" in args[1]
        assert args[-1] == result["download_url"]
