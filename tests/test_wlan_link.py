"""get_wlan_link against wlanpi-core's wlan-link endpoint (MLO links from core #359)."""

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreAPIError
from wlanpi_mcp.tools import network

URL = "https://localhost:31415/api/v1/network/interfaces/mlo-client/wlan-link"

MLO = {
    "interface": "mlo-client",
    "namespace": "lab",
    "connected": True,
    "ssid": "Cisco Multilink",
    "bssid": "ae:88:81:5a:a3:41",
    "freq_mhz": None,
    "signal_dbm": None,
    "links": [
        {
            "link_id": 1,
            "bssid": "ae:88:91:5a:a3:40",
            "freq_mhz": 5745.0,
            "active": True,
        },
        {
            "link_id": 2,
            "bssid": "8e:88:a1:5a:a3:48",
            "freq_mhz": 5955.0,
            "active": True,
        },
    ],
    "rx_bitrate": None,
    "tx_bitrate": "68.8 MBit/s 40MHz EHT-MCS 1 EHT-NSS 2 EHT-GI 0",
    "rx_bytes": 143688,
    "tx_bytes": 2675,
}


def _tools(client):
    mcp = FastMCP("test")
    network.register(mcp, client)
    return mcp._tool_manager._tools


@respx.mock
async def test_get_wlan_link_returns_core_links(client):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=MLO))

    result = await _tools(client)["get_wlan_link"].run({"interface": "mlo-client"})

    assert route.called
    assert result["connected"] is True
    assert [link["link_id"] for link in result["links"]] == [1, 2]
    assert all(link["active"] for link in result["links"])


@respx.mock
async def test_get_wlan_link_not_connected(client):
    respx.get("https://localhost:31415/api/v1/network/interfaces/wlan0/wlan-link").mock(
        return_value=httpx.Response(
            200,
            json={
                "interface": "wlan0",
                "namespace": None,
                "connected": False,
                "links": [],
            },
        )
    )

    result = await _tools(client)["get_wlan_link"].run({"interface": "wlan0"})

    assert result["connected"] is False


@respx.mock
async def test_get_wlan_link_passes_older_core_payload_through(client):
    # A core without multi-link support sends no links key; the tool must not
    # invent one, so the model can tell "no links" from "older core".
    legacy = {
        "interface": "wlan0",
        "namespace": None,
        "connected": True,
        "ssid": "lab",
        "bssid": "ae:88:81:5a:a3:41",
        "freq_mhz": 5180.0,
        "signal_dbm": -48.0,
    }
    respx.get("https://localhost:31415/api/v1/network/interfaces/wlan0/wlan-link").mock(
        return_value=httpx.Response(200, json=legacy)
    )

    result = await _tools(client)["get_wlan_link"].run({"interface": "wlan0"})

    assert result == legacy


@respx.mock
async def test_get_wlan_link_core_error_reaches_the_client(client):
    respx.get(URL).mock(
        return_value=httpx.Response(
            503, text="Unable to determine the interface namespace"
        )
    )

    with pytest.raises(ToolError) as exc_info:
        await _tools(client)["get_wlan_link"].run({"interface": "mlo-client"})

    cause = exc_info.value.__cause__
    assert isinstance(cause, CoreAPIError)
    assert cause.status_code == 503
    assert "Unable to determine the interface namespace" in str(exc_info.value)
