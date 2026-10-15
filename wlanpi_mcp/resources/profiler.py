"""MCP resource for the wlanpi-profiler status."""

import json

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the profiler status resource."""

    @mcp.resource("profiler://status")
    async def profiler_status() -> str:
        """WLAN Pi profiler running state, SSID, channel, and interface."""
        data = await client.get("/api/v1/profiler/status")
        return json.dumps(data, indent=2)
