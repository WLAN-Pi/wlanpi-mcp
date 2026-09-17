try:
    from wlanpi_mcp._compat import FastMCP  # mcp >= 2
except ImportError:
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]  # noqa: F401  # mcp < 2
