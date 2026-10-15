"""MCP resources for Bluetooth status."""

import json

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the Bluetooth status resource."""

    @mcp.resource("bluetooth://status")
    async def bluetooth_status() -> str:
        """WLAN Pi Bluetooth adapter status, name, address, power state, and paired devices."""
        data = await client.get("/api/v1/bluetooth/status")
        return json.dumps(data, indent=2)
