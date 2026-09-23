"""
Netconfig tools against the wlanpi-core 2.3.23 contract (namespace safety series).

Run through tool.run (FastMCP's real validation + dispatch) with a real
CoreClient and respx, so a core error is seen as the MCP client sees it.
"""

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreAPIError
from wlanpi_mcp.resources import netconfig as netconfig_res
from wlanpi_mcp.tools import netconfig

BASE = "https://localhost:31415/api/v1/network/config"

INVALID_OUTCOMES = {
    "message": "Configuration is invalid",
    "outcomes": [
        {
            "interface": "wlan1",
            "namespace": "ns_a",
            "status": "error",
            "detail": "WPA2-PSK requires a psk",
            "invalid": True,
        }
    ],
}


@pytest.fixture
def tools(client):
    mcp = FastMCP("test")
    netconfig.register(mcp, client)
    return mcp._tool_manager._tools


@respx.mock
async def test_core_error_shapes_reach_the_mcp_client(tools):
    # The two error shapes the new contract introduces: a 422 whose detail is
    # an object, and a 409 whose body is plain text (the deprecated routes).
    respx.post(f"{BASE}/activate/lab").mock(
        return_value=httpx.Response(422, json={"detail": INVALID_OUTCOMES})
    )
    respx.post(f"{BASE}/reset").mock(
        return_value=httpx.Response(409, text="Another network change is running")
    )

    with pytest.raises(ToolError) as invalid:
        await tools["activate_network_config"].run({"id": "lab"})
    cause = invalid.value.__cause__
    assert isinstance(cause, CoreAPIError)
    assert cause.status_code == 422
    assert cause.detail == INVALID_OUTCOMES
    assert "422" in str(invalid.value)
    assert '"invalid":true' in str(invalid.value)
    assert "WPA2-PSK requires a psk" in str(invalid.value)

    with pytest.raises(ToolError) as busy:
        await tools["reset_network_namespaces"].run({"namespaces": ["x"]})
    cause = busy.value.__cause__
    assert isinstance(cause, CoreAPIError)
    assert cause.status_code == 409
    assert cause.detail == "Another network change is running"
    assert "409: Another network change is running" in str(busy.value)


@respx.mock
async def test_partial_activation_is_returned_whole(tools):
    body = {
        "id": "lab",
        "message": "Configuration activated successfully",
        "outcomes": [
            {"interface": "wlan1", "namespace": "ns_a", "status": "connected"},
            {
                "interface": "wlan2",
                "namespace": None,
                "status": "in_use",
                "detail": "wlan2profiler on the same radio (phy#2) is in use",
            },
        ],
    }
    route = respx.post(f"{BASE}/activate/lab").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = await tools["activate_network_config"].run(
        {"id": "lab", "override_active": True}
    )
    assert result == body
    assert route.calls[0].request.url.params["override_active"] == "true"


@respx.mock
async def test_leftovers_and_reset_routes(tools):
    leftovers = {
        "left_alone": [
            {
                "namespace": "profiler_ns",
                "interfaces": ["wlan2"],
                "phys": ["phy2"],
                "core_created": False,
                "reason": "Not created by Core; holds wireless radios",
            }
        ]
    }
    respx.get(f"{BASE}/leftovers").mock(
        return_value=httpx.Response(200, json=leftovers)
    )
    reset = respx.post(f"{BASE}/reset").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    assert await tools["list_network_leftovers"].run({}) == leftovers
    await tools["reset_network_namespaces"].run({"namespaces": ["profiler_ns"]})
    assert reset.calls[0].request.read() == b'{"namespaces":["profiler_ns"]}'


@respx.mock
async def test_leftovers_resource(client):
    netconfig_res._cache.clear()
    respx.get(f"{BASE}/leftovers").mock(
        return_value=httpx.Response(200, json={"left_alone": []})
    )
    mcp = FastMCP("test")
    netconfig_res.register(mcp, client)
    contents = await mcp.read_resource("netconfig://leftovers")
    assert '"left_alone": []' in next(iter(contents)).content
