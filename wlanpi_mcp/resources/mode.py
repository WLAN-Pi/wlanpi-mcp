"""MCP resource for the current WLAN Pi operating mode."""

import json

import httpx

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient

VALID_MODES = {"classic", "wconsole", "hotspot", "wiperf", "server", "bridge"}


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the device mode resource."""

    @mcp.resource("device://mode")
    async def device_mode() -> str:
        """Report the current WLAN Pi operating mode from wlanpi-core."""
        try:
            info = await client.get("/api/v1/system/device/info")
            mode = info.get("mode", "")
            return json.dumps({"mode": mode, "valid": mode in VALID_MODES}, indent=2)
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            return json.dumps({"error": str(exc)})
