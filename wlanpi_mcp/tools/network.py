"""MCP tools for network interfaces, routing, DHCP, and WLAN drivers."""

from typing import Any

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient
from wlanpi_mcp.tools import hints


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the network diagnostic tools."""

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_network_interfaces(interface: str | None = None) -> dict[str, Any]:
        """
        Get network interface details including IP addresses, flags, MTU, and link state.

        Args:
            interface: Optional interface name (e.g. 'eth0'). If omitted, returns all interfaces.
        """
        if interface:
            return await client.get(f"/api/v1/network/interfaces/{interface}")
        return await client.get("/api/v1/network/interfaces")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_network_info() -> dict[str, Any]:
        """
        Get a full network snapshot.

        Covers all interfaces, WLAN details, ethernet IP config, VLAN info,
        LLDP/CDP neighbours, and public IP address. Best starting point for
        network diagnostics.
        """
        return await client.get("/api/v1/network/info/")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_public_ipv6() -> dict[str, Any]:
        """Get the WLAN Pi's public IPv6 address and related details."""
        return await client.get("/api/v1/network/info/publicip6")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_ethernet_interface(interface: str) -> dict[str, Any]:
        """
        Get ethernet interface details for a specific interface.

        Args:
            interface: Ethernet interface name (e.g. 'eth0'), or 'all' for every interface
        """
        return await client.get(f"/api/v1/network/ethernet/{interface}")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_routing_table(namespace: str | None = None) -> dict[str, Any]:
        """
        Get the structured IP routing table.

        Args:
            namespace: Optional network namespace to query (default: root namespace)
        """
        params = {"namespace": namespace} if namespace else None
        return await client.get("/api/v1/network/routing", params=params)

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_tcp_connections(namespace: str | None = None) -> dict[str, Any]:
        """
        Get active TCP sockets/connections on the WLAN Pi.

        Args:
            namespace: Optional network namespace to query (default: root namespace)
        """
        params = {"namespace": namespace} if namespace else None
        return await client.get("/api/v1/network/connections/tcp", params=params)

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_udp_connections(namespace: str | None = None) -> dict[str, Any]:
        """
        Get active UDP sockets on the WLAN Pi.

        Args:
            namespace: Optional network namespace to query (default: root namespace)
        """
        params = {"namespace": namespace} if namespace else None
        return await client.get("/api/v1/network/connections/udp", params=params)

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_dhcp_leases() -> dict[str, Any]:
        """Get DHCP leases held by the WLAN Pi (parsed from dhclient lease files)."""
        return await client.get("/api/v1/network/dhcp/leases")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_interface_link_stats(interface: str) -> dict[str, Any]:
        """
        Get per-interface link statistics (via ethtool): speed, duplex, errors, drops.

        Args:
            interface: Interface name (e.g. 'eth0')
        """
        return await client.get(f"/api/v1/network/interfaces/{interface}/link-stats")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_wlan_link(interface: str) -> dict[str, Any]:
        """
        Report whether a Wi-Fi client interface is associated, and to what.

        A small answer from `iw dev <interface> link`; wlanpi-core finds the
        interface's network namespace itself. Use it to check a client after
        activate_network_config: 'provisioned' there only means the config was
        applied. Prefer it to get_network_config_status, whose 'channel' is
        null for a Wi-Fi 7 multi-link (MLO) client.

        connected: associated or not. ssid, bssid (for MLO, the AP MLD
        address), signal_dbm, rx/tx bitrate and byte counters as iw reports
        them.

        links (wlanpi-core with multi-link support; absent on older cores): one
        entry per set-up MLO link with link_id, the AP link bssid, freq_mhz and
        active, plus local_addr (this client's own MAC on that link: each link
        has its own, none equals the interface MAC, and it is the address on
        the air) and, for active links, width_mhz and center1_mhz. Only active
        links carry traffic; a set-up link can be idle. The set of links can
        change between associations. Empty for a non-MLO connection. With more
        than one active link, freq_mhz at the top level is null. On older cores
        without links, freq_mhz and signal_dbm are unreliable for MLO: freq_mhz
        can name an idle link, and signal_dbm often reads 0.

        Errors: 400 means the interface name is invalid; 404 means no such
        interface in any namespace (check get_network_config_status for the
        names a profile created); 503 means core could not work out the
        interface's namespace or read the link (retry shortly).

        Args:
            interface: The client interface, e.g. 'wlan0', or a network
                profile's iface_display_name such as 'mlo-client'.
        """
        return await client.get(f"/api/v1/network/interfaces/{interface}/wlan-link")

    @mcp.tool(annotations=hints.DESTRUCTIVE)
    async def renew_dhcp_lease(interface: str) -> dict[str, Any]:
        """
        Renew the DHCP lease for an interface.

        The renewal happens in the interface's current namespace, and the
        interface IP address may change as a result.

        Args:
            interface: Interface name (e.g. 'eth0')
        """
        return await client.post(f"/api/v1/network/interfaces/{interface}/renew")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_wlan_usb_drivers() -> dict[str, Any]:
        """
        List USB-attached WLAN adapters and their bound drivers.

        If 'adapters' is empty but interfaces_scanned > 0, the radios are
        PCI/on-board — use get_wlan_pci_drivers instead.

        Covers the root namespace and every network namespace a network
        configuration moved an interface into. Each adapter's 'namespace' is
        the namespace it is in, or null for root - an interface in a namespace
        is not missing. A namespace that can't be read is skipped, so the list
        is best effort; interfaces_scanned counts across all namespaces read.
        """
        return await client.get("/api/v1/network/wlan/usb-drivers")

    @mcp.tool(annotations=hints.READ_ONLY)
    async def get_wlan_pci_drivers() -> dict[str, Any]:
        """
        List PCI/platform wireless devices and their bound WLAN drivers.

        Comes from lspci, covering built-in Wi-Fi radios.

        Covers the root namespace and every network namespace a network
        configuration moved an interface into. Each adapter's 'namespace' is
        the namespace it is in, or null for root - an interface in a namespace
        is not missing. A namespace that can't be read is skipped, so the list
        is best effort; interfaces_scanned counts across all namespaces read.
        """
        return await client.get("/api/v1/network/wlan/pci-drivers")
