"""MCP resources for network interfaces and the network snapshot."""

import json

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the network interfaces and info resources."""

    @mcp.resource("network://interfaces")
    async def network_interfaces() -> str:
        """All WLAN Pi network interfaces with addresses, flags, MTU, and link state."""
        data = await client.get("/api/v1/network/interfaces")
        return json.dumps(data, indent=2)

    @mcp.resource("network://info")
    async def network_info() -> str:
        """Full WLAN Pi network snapshot: interfaces, WLAN details, LLDP/CDP neighbours, public IP."""
        data = await client.get("/api/v1/network/info/")
        return json.dumps(data, indent=2)
