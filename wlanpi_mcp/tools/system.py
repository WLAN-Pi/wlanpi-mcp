from typing import Optional

from mcp.server.fastmcp import FastMCP

from wlanpi_mcp.client.core_client import CoreClient
from wlanpi_mcp.config import ALLOWED_SERVICES, get_settings


def register(mcp: FastMCP, client: CoreClient) -> None:

    @mcp.tool()
    async def get_device_info() -> dict:
        """Get WLAN Pi device identity: model, hostname, software version, and current operating mode."""
        return await client.get("/api/v1/system/device/info")

    @mcp.tool()
    async def get_device_stats() -> dict:
        """Get WLAN Pi live system metrics: IP address, CPU usage, RAM usage, disk usage, CPU temperature, and uptime."""
        return await client.get("/api/v1/system/device/stats")

    @mcp.tool()
    async def list_allowed_services() -> dict:
        """List all services that can be managed on this WLAN Pi (started, stopped, or queried)."""
        return {"services": ALLOWED_SERVICES}

    @mcp.tool()
    async def get_service_status(name: str) -> dict:
        """
        Get the running status of a WLAN Pi service.

        Args:
            name: Service name (use list_allowed_services to see valid names)
        """
        return await client.get("/api/v1/system/service/status", params={"name": name})

    @mcp.tool()
    async def start_service(name: str) -> dict:
        """
        Start a WLAN Pi service.

        Args:
            name: Service name (use list_allowed_services to see valid names)
        """
        if name.replace(".service", "") not in ALLOWED_SERVICES:
            return {"error": f"'{name}' is not in the allowed services list"}
        return await client.post("/api/v1/system/service/start", params={"name": name})

    @mcp.tool()
    async def stop_service(name: str) -> dict:
        """
        Stop a WLAN Pi service.

        Args:
            name: Service name (use list_allowed_services to see valid names)
        """
        if name.replace(".service", "") not in ALLOWED_SERVICES:
            return {"error": f"'{name}' is not in the allowed services list"}
        return await client.post("/api/v1/system/service/stop", params={"name": name})

    @mcp.tool()
    async def restart_service(name: str) -> dict:
        """
        Restart a WLAN Pi service.

        Args:
            name: Service name (use list_allowed_services to see valid names)
        """
        if name.replace(".service", "") not in ALLOWED_SERVICES:
            return {"error": f"'{name}' is not in the allowed services list"}
        return await client.post("/api/v1/system/service/restart", params={"name": name})

    @mcp.tool()
    async def get_device_model() -> dict:
        """Get the WLAN Pi hardware model (e.g. WLAN Pi Pro, R4, M4)."""
        return await client.get("/api/v1/system/device/model")

    @mcp.tool()
    async def get_datetime() -> dict:
        """Get the WLAN Pi's current local date, time, and timezone."""
        return await client.get("/api/v1/system/datetime")

    @mcp.tool()
    async def get_timezone() -> dict:
        """Get the WLAN Pi's current system timezone."""
        return await client.get("/api/v1/system/timezone")

    @mcp.tool()
    async def list_timezones() -> dict:
        """List all timezones available on the WLAN Pi (for use with set_timezone)."""
        return await client.get("/api/v1/system/timezone/list")

    @mcp.tool()
    async def set_timezone(timezone: str) -> dict:
        """
        Set the WLAN Pi system timezone.

        Args:
            timezone: Timezone name, e.g. 'America/Denver' (use list_timezones for valid values)
        """
        return await client.post(
            "/api/v1/system/timezone/set", json={"timezone": timezone}
        )

    @mcp.tool()
    async def enable_auto_timezone() -> dict:
        """Enable NTP automatic time synchronization on the WLAN Pi."""
        return await client.post("/api/v1/system/timezone/auto")

    @mcp.tool()
    async def reboot_device() -> dict:
        """
        Reboot the WLAN Pi immediately. Active sessions and captures will be
        interrupted. Can be disabled via ALLOW_POWER_CONTROL=false in the server config.
        """
        if not get_settings().ALLOW_POWER_CONTROL:
            return {
                "error": "Power control is disabled. Set ALLOW_POWER_CONTROL=true "
                "in /etc/wlanpi-mcp/config.env to allow reboot/shutdown."
            }
        return await client.post("/api/v1/system/reboot")

    @mcp.tool()
    async def shutdown_device() -> dict:
        """
        Shut down the WLAN Pi immediately. The device must be powered back on
        manually. Can be disabled via ALLOW_POWER_CONTROL=false in the server config.
        """
        if not get_settings().ALLOW_POWER_CONTROL:
            return {
                "error": "Power control is disabled. Set ALLOW_POWER_CONTROL=true "
                "in /etc/wlanpi-mcp/config.env to allow reboot/shutdown."
            }
        return await client.post("/api/v1/system/shutdown")

    @mcp.tool()
    async def get_hotspot_clients(iface: Optional[str] = None) -> dict:
        """
        Get the connected client count when the WLAN Pi is in hotspot mode.
        Returns an error if the device is not in hotspot mode.

        Args:
            iface: Optional AP interface name; auto-detected if omitted.
        """
        params = {"iface": iface} if iface else None
        return await client.get("/api/v1/system/hotspot/clients", params=params)

    @mcp.tool()
    async def get_hotspot_ssid_passphrase() -> dict:
        """
        Get the hotspot SSID and WPA passphrase from the hostapd configuration.
        Returns an error if the device is not in hotspot mode.
        """
        return await client.get("/api/v1/system/hotspot/ssid-passphrase")
