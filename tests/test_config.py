"""Tests for wlanpi_mcp configuration defaults."""

from wlanpi_mcp.config import Settings


def test_loopback_only_bind_default() -> None:
    """The daemon must stay loopback-only so only nginx fronts the public ports."""
    assert Settings(_env_file=None).WLANPI_MCP_HOST == "127.0.0.1"
