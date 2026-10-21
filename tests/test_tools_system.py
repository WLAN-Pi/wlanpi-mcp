import httpx
import pytest
import respx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from wlanpi_mcp.tools import system

CORE = "https://localhost:31415/api/v1/system"


def _tools(client):
    mcp = MCPServer("test")
    system.register(mcp, client)
    return mcp._tool_manager._tools


@respx.mock
@pytest.mark.asyncio
async def test_get_device_info(client):
    respx.get("https://localhost:31415/api/v1/system/device/info").mock(
        return_value=httpx.Response(
            200, json={"model": "WLAN Pi Pro", "mode": "classic"}
        )
    )
    result = await client.get("/api/v1/system/device/info")
    assert result["model"] == "WLAN Pi Pro"


@respx.mock
@pytest.mark.asyncio
async def test_get_service_status(client):
    respx.get("https://localhost:31415/api/v1/system/service/status").mock(
        return_value=httpx.Response(
            200, json={"name": "wlanpi-profiler", "active": False}
        )
    )
    result = await client.get(
        "/api/v1/system/service/status", params={"name": "wlanpi-profiler"}
    )
    assert result["active"] is False


@respx.mock
async def test_list_allowed_services_reads_core_allowlist(client):
    services = ["wlanpi-profiler", "iperf2", "iperf2-udp", "iperf3"]
    route = respx.get(f"{CORE}/services").mock(
        return_value=httpx.Response(200, json={"services": services})
    )

    result = await _tools(client)["list_allowed_services"].run({}, Context())

    assert route.called
    assert result == {"services": services}


@respx.mock
@pytest.mark.parametrize("action", ["start", "stop", "restart"])
async def test_service_actions_defer_to_core_allowlist(client, action):
    # No local copy of the allowlist: iperf2 used to be refused here
    # before reaching core, which allows it (#64).
    route = respx.post(f"{CORE}/service/{action}").mock(
        return_value=httpx.Response(200, json={"name": "iperf2", "active": True})
    )

    result = await _tools(client)[f"{action}_service"].run(
        {"name": "iperf2"}, Context()
    )

    assert route.calls.last.request.url.params["name"] == "iperf2"
    assert result["name"] == "iperf2"


@respx.mock
async def test_start_service_surfaces_core_refusal(client):
    respx.post(f"{CORE}/service/start").mock(
        return_value=httpx.Response(
            400, text="starting iperf access is restricted or does not exist"
        )
    )

    with pytest.raises(ToolError, match="restricted or does not exist"):
        await _tools(client)["start_service"].run({"name": "iperf"}, Context())
