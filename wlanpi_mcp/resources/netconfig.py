"""MCP resources for saved network configuration profiles."""

import json
import time
from typing import Any

from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreClient

_cache: dict[str, tuple[Any, float]] = {}


async def _cached_get(client: CoreClient, path: str, ttl: float) -> Any:
    now = time.monotonic()
    if path in _cache:
        data, ts = _cache[path]
        if now - ts < ttl:
            return data
    data = await client.get(path)
    _cache[path] = (data, now)
    return data


def register(mcp: FastMCP, client: CoreClient) -> None:
    """Register the network config list, status and leftovers resources."""

    @mcp.resource("netconfig://list")
    async def netconfig_list() -> str:
        """All saved WLAN Pi network configuration profiles and their active status."""
        data = await _cached_get(client, "/api/v1/network/config/", ttl=30.0)
        return json.dumps(data, indent=2)

    @mcp.resource("netconfig://status")
    async def netconfig_status() -> str:
        """Status of the currently active network configuration profile."""
        data = await _cached_get(client, "/api/v1/network/config/status", ttl=15.0)
        return json.dumps(data, indent=2)

    @mcp.resource("netconfig://leftovers")
    async def netconfig_leftovers() -> str:
        """Namespaces holding radios that Core left alone (another tool's, or Core's own that could not be removed)."""
        data = await _cached_get(client, "/api/v1/network/config/leftovers", ttl=15.0)
        return json.dumps(data, indent=2)
