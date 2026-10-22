"""MCP resource for WLAN Pi systemd service status."""

import json

from mcp.server.mcpserver import MCPServer

from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: MCPServer, client: CoreClient) -> None:
    """Register the service status resource."""

    @mcp.resource("services://status/{name}")
    async def service_status(name: str) -> str:
        """Live status of a WLAN Pi systemd service. wlanpi-core only answers for names in its allowlist."""
        data = await client.get("/api/v1/system/service/status", params={"name": name})
        return json.dumps(data, indent=2)
