"""MCP tools for Wi-Fi adapter capabilities and hotspot status."""

from typing import Any

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient
from wlanpi_mcp.tools import hints


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the Wi-Fi capability and hotspot tools."""

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_wifi_capabilities() -> dict[str, Any]:
        """
        Get Wi-Fi adapter capabilities.

        Returns 'iw phy' capability dumps for each PHY, including supported
        bands, channels, HT/VHT/HE features, and interface modes.

        Lists radios in the root namespace and in every network namespace a
        network configuration moved them into. Each adapter's 'namespace' is
        the namespace it is in, or null for root - a radio in a namespace is
        not missing. A namespace that can't be read is skipped, so the list is
        best effort.
        """
        return await client.get("/api/v1/wifi/capabilities")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_wifi_regulatory() -> dict[str, Any]:
        """Get Wi-Fi regulatory domain information reported by the kernel."""
        return await client.get("/api/v1/wifi/regulatory")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_hotspot_stations(iface: str | None = None) -> dict[str, Any]:
        """
        List stations connected to the hotspot AP interface.

        Returns an error if the device is not in hotspot mode.

        Args:
            iface: Optional AP interface name; auto-detected if omitted.
        """
        params = {"iface": iface} if iface else None
        return await client.get("/api/v1/wifi/hotspot/stations", params=params)

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_hotspot_link_stats(iface: str | None = None) -> dict[str, Any]:
        """
        Get per-station link statistics for hotspot AP clients.

        Reports signal, rates, and retries. Returns an error if the device is
        not in hotspot mode.

        Args:
            iface: Optional AP interface name; auto-detected if omitted.
        """
        params = {"iface": iface} if iface else None
        return await client.get("/api/v1/wifi/hotspot/link", params=params)
