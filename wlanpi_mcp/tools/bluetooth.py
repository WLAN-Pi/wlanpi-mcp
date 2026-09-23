"""MCP tools for Bluetooth status, power, and pairing."""

from typing import Any, Literal

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient
from wlanpi_mcp.tools import hints


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the Bluetooth control tools."""

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_bluetooth_status() -> dict[str, Any]:
        """
        Get Bluetooth adapter status.

        Includes the adapter name, address, power state, and list of paired
        devices.
        """
        return await client.get("/api/v1/bluetooth/status")

    @mcp.tool(annotations=hints.DESTRUCTIVE)
    async def set_bluetooth_power(action: Literal["on", "off"]) -> dict[str, Any]:
        """
        Turn Bluetooth on or off.

        Args:
            action: 'on' to enable Bluetooth, 'off' to disable it
        """
        return await client.post(f"/api/v1/bluetooth/power/{action}")

    @mcp.tool(annotations=hints.ADDITIVE)
    async def start_bluetooth_pairing() -> dict[str, Any]:
        """
        Put the WLAN Pi into Bluetooth discoverable pairing mode.

        Starts bt-timedpair so a phone or laptop can pair with it.
        """
        return await client.post("/api/v1/bluetooth/pair")
