"""MCP resources for saved network configuration profiles."""

import json

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the network config list, status and leftovers resources."""

    @mcp.resource("netconfig://list")
    async def netconfig_list() -> str:
        """All saved WLAN Pi network configuration profiles and their active status."""
        data = await client.get("/api/v1/network/config/")
        return json.dumps(data, indent=2)

    @mcp.resource("netconfig://status")
    async def netconfig_status() -> str:
        """Status of the currently active network configuration profile."""
        data = await client.get("/api/v1/network/config/status")
        return json.dumps(data, indent=2)

    @mcp.resource("netconfig://leftovers")
    async def netconfig_leftovers() -> str:
        """Namespaces holding radios that Core left alone (another tool's, or Core's own that could not be removed)."""
        data = await client.get("/api/v1/network/config/leftovers")
        return json.dumps(data, indent=2)
