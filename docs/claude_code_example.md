# Claude Code Example MCP Config

This is an example of how to set up Claude Code to use the WLANPi MCP server.

Claude Code speaks streamable HTTP natively, so no mcp-remote bridge is needed. The one catch is TLS: the 8767 endpoint uses the device's self-signed certificate, and for an HTTP-transport server Claude Code has no per-server env block, so any certificate override must come from the shell that launches Claude Code. See the [README](../README.md#connecting-claude-code) for the endpoint and certificate details.

## Option 1: native HTTP (recommended)

Add the server:

```bash
claude mcp add --transport http wlanpi https://<pi-ip-address>:8767/mcp --header "Authorization: Bearer <your-wlanpi-core-jwt>"
```

Or drop the equivalent .mcp.json in the project folder, which is what --scope project writes:

```json
{
  "mcpServers": {
    "wlanpi": {
      "type": "http",
      "url": "https://<pi-ip-address>:8767/mcp",
      "headers": {
        "Authorization": "Bearer ${WLANPI_TOKEN}"
      }
    }
  }
}
```

Then launch Claude Code with the token and the certificate override in its environment:

```bash
WLANPI_TOKEN="<your-wlanpi-core-jwt>" NODE_TLS_REJECT_UNAUTHORIZED=0 claude
```

The ${WLANPI_TOKEN} expansion in .mcp.json keeps the JWT out of the checked-in file. The safer variant is to copy the Pi's certificate (/etc/nginx/ssl/self-signed-wlanpi.cert on the device) to your machine and set NODE_EXTRA_CA_CERTS to that file instead of disabling verification.

## Option 2: stdio bridge with per-server env

If you don't want to touch the shell environment, use the mcp-remote bridge, the same shape as the [Claude Desktop config](claude_desktop_example.md). This scopes the TLS override to the bridge process only:

```json
{
  "mcpServers": {
    "wlanpi": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://<pi-ip-address>:8767/mcp",
        "--transport", "http-only",
        "--header", "Authorization: Bearer ${WLANPI_TOKEN}"
      ],
      "env": {
        "WLANPI_TOKEN": "<your-wlanpi-core-jwt>",
        "NODE_TLS_REJECT_UNAUTHORIZED": "0"
      }
    }
  }
}
```

## Verify

Run /mcp inside Claude Code. The wlanpi server should show as connected, with tools like get_device_info and scan_wlan listed.
