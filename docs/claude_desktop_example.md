# Example of Claude Desktop config

Here is an example of using the WLANPi MCP server with Claude Desktop.

Claude Code speaks streamable HTTP natively, so no mcp-remote bridge is needed. Your Claude Desktop config confirms the self-signed workaround in use is the Node TLS override. The catch is that for an HTTP-transport server, Claude Code has no per-server env block, so the TLS override must come from the shell that launches Claude Code.

Option 1, native HTTP (recommended). Add the server:

```bash
claude mcp add --transport http wlanpi https://<pi-ip-address>:8767/mcp --header "Authorization: Bearer <your-wlanpi-core-jwt>"
```

Or the equivalent .mcp.json in the class folder, which is what --scope project writes:

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

Then launch Claude Code with the cert override in its environment:

```bash
WLANPI_TOKEN="<your-wlanpi-core-jwt>" NODE_TLS_REJECT_UNAUTHORIZED=0 claude
```

The ${WLANPI_TOKEN} expansion in .mcp.json keeps the JWT out of the checked-in file. The safer variant is to export the Pi's cert and set NODE_EXTRA_CA_CERTS to that file instead of disabling verification.

Option 2, stdio bridge with per-server env. If you don't want to touch the shell environment, mirror the Desktop config. This scopes the TLS override to the bridge process only:

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

Verify either way with /mcp inside Claude Code. The wlanpi server should show connected with tools like get_device_info and scan_wlan listed.
