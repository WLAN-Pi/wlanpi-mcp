"""MCP resources for device identity and system metrics."""

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the device info and stats resources."""

    @mcp.resource("device://info")
    async def device_info() -> str:
        """WLAN Pi device identity: model, hostname, software version, and operating mode."""
        import json

        data = await client.get("/api/v1/system/device/info")
        return json.dumps(data, indent=2)

    @mcp.resource("device://stats")
    async def device_stats() -> str:
        """WLAN Pi live system metrics: CPU, RAM, disk, temperature, uptime, IP."""
        import json

        data = await client.get("/api/v1/system/device/stats")
        return json.dumps(data, indent=2)
