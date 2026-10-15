"""
Resources call wlanpi-core on every read, with the reading request's token.

wlanpi-core is the only thing that validates the JWT, so a resource must never
answer from a response fetched for an earlier caller: a TTL cache keyed by path
alone served that data to any Bearer string (WLAN-Pi/wlanpi-mcp#66).
"""

import httpx
import pytest
import respx

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.auth.token_context import current_token
from wlanpi_mcp.resources import bluetooth, device, netconfig, network, profiler

CORE = "https://localhost:31415"
GOOD = "good.jwt.token"
BAD = "not-a-token"

RESOURCES = [
    (device, "device://info", "/api/v1/system/device/info"),
    (device, "device://stats", "/api/v1/system/device/stats"),
    (network, "network://interfaces", "/api/v1/network/interfaces"),
    (network, "network://info", "/api/v1/network/info/"),
    (netconfig, "netconfig://list", "/api/v1/network/config/"),
    (netconfig, "netconfig://status", "/api/v1/network/config/status"),
    (netconfig, "netconfig://leftovers", "/api/v1/network/config/leftovers"),
    (bluetooth, "bluetooth://status", "/api/v1/bluetooth/status"),
    (profiler, "profiler://status", "/api/v1/profiler/status"),
]


def _core_response(request: httpx.Request) -> httpx.Response:
    if request.headers.get("authorization") == f"Bearer {GOOD}":
        return httpx.Response(200, json={"secret": "device data"})
    return httpx.Response(401, json={"detail": "Invalid token"})


async def _read(mcp: FastMCP, uri: str, token: str) -> str:
    ctx = current_token.set(token)
    try:
        return next(iter(await mcp.read_resource(uri))).content
    finally:
        current_token.reset(ctx)


@pytest.mark.parametrize(("module", "uri", "path"), RESOURCES)
@respx.mock
async def test_resource_is_not_served_to_a_later_bad_token(client, module, uri, path):
    route = respx.get(f"{CORE}{path}").mock(side_effect=_core_response)
    mcp = FastMCP("test")
    module.register(mcp, client)

    assert "device data" in await _read(mcp, uri, GOOD)
    with pytest.raises(Exception, match="401"):
        await _read(mcp, uri, BAD)

    assert [c.request.headers["authorization"] for c in route.calls] == [
        f"Bearer {GOOD}",
        f"Bearer {BAD}",
    ]
