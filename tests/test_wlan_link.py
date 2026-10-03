"""get_wlan_link against wlanpi-core's wlan-link endpoint (MLO links from core #359)."""

import httpx
import respx

from wlanpi_mcp._compat import FastMCP
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
