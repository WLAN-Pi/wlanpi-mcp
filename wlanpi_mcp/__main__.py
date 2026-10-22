"""Command-line entry point for the WLAN Pi MCP server."""

import argparse
import logging
import sys

from mcp.server.mcpserver import MCPServer

from wlanpi_mcp.client.core_client import init_client
from wlanpi_mcp.config import Settings, get_settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    """Run the WLAN Pi MCP server over the requested transport."""
    parser = argparse.ArgumentParser(
        description="WLAN Pi MCP server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help=(
            "MCP transport: stdio (for direct client invocation) or "
            "streamable-http (HTTP daemon mode, stateless, on /mcp)"
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for the HTTP transport (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for the HTTP transport (overrides config)",
    )
    args = parser.parse_args()

    settings = get_settings()
    _configure_logging(settings.LOG_LEVEL)

    client = init_client(settings)

    host = args.host or settings.WLANPI_MCP_HOST
    port = args.port or settings.WLANPI_MCP_PORT

    from wlanpi_mcp.server import create_server

    mcp = create_server(client)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        _run_http(mcp, settings, host, port)


def _run_http(mcp: MCPServer, settings: Settings, host: str, port: int) -> None:
    import uvicorn

    from wlanpi_mcp.middleware.bearer_token import BearerTokenMiddleware
    from wlanpi_mcp.server import create_http_app

    # create_http_app() builds the Starlette ASGI app for streamable HTTP;
    # its lifespan runs the session manager, which uvicorn drives. Every
    # request must present a wlanpi-core JWT, which is passed through to
    # wlanpi-core on API calls (validated there, not here).
    http_app = create_http_app(mcp)
    http_app.add_middleware(BearerTokenMiddleware)

    uvicorn.run(
        http_app,
        host=host,
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
