"""
Shared pieces of the one-time download links.

get_pcap_download_url (tools/capture_file.py) hands an agent a short-lived,
single-use link on this server's own host and port, so a file can be saved
with plain curl instead of passing through the conversation. A tool that
mints such links keeps its own ticket store and route; what any of them
needs lives here: checking the caller's JWT with wlanpi-core before minting
(the link itself carries none), and building a safe base URL from the
request that asked for it.
"""

import re

from mcp.server.lowlevel.server import request_ctx

from wlanpi_mcp.client.core_client import CoreAPIError, CoreClient

#: How long a download ticket stays valid, in seconds. Single use either way.
DOWNLOAD_TTL_S = 300

#: What a Host header may look like before it goes into a link and a shell
#: command: a DNS name, an IPv4 address or a bracketed IPv6 address, with an
#: optional port. Anything else gets no link (download_path only).
HOST_RE = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?$"
)


async def check_token(client: CoreClient) -> str | None:
    """
    Check the caller's JWT with wlanpi-core; return an error message, or None.

    A ticket is only as good as the call that asked for it, so this runs
    before any ticket is minted. Only a 401/403 means the token was refused;
    other core errors and an unreachable core are reported as such.
    """
    try:
        await client.get("/api/v1/system/device/info")
    except CoreAPIError as exc:
        if exc.status_code in (401, 403):
            return f"wlanpi-core refused this token: {exc}"
        return f"could not check the token with wlanpi-core: {exc}"
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller
        return f"could not reach wlanpi-core to check the token: {exc}"
    return None


def request_base_url() -> str | None:
    """
    Return scheme://host[:port] as the MCP client reached this server.

    nginx forwards the client's Host header and sets X-Forwarded-Proto, so a
    link built from them works from the client's side (e.g.
    https://wlanpi-9be.local:8767). None outside an HTTP request (stdio), or
    when the Host header is not a plain host[:port].
    """
    try:
        ctx = request_ctx.get()
    except LookupError:
        return None
    request = getattr(ctx, "request", None)
    if request is None:
        return None
    headers = request.headers
    host = headers.get("host", "")
    if not HOST_RE.match(host):
        return None
    # Behind more than one proxy this is a list; the first hop is the client's.
    proto = headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto not in ("http", "https"):
        proto = request.url.scheme
    return f"{proto}://{host}"
