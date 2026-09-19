# Example of Claude Desktop config

Here is an example of using the WLANPi MCP server with Claude Desktop.

Claude Desktop only launches stdio servers, so it reaches the daemon through the mcp-remote bridge. The env block scopes the JWT and the TLS override to the bridge process. NODE_TLS_REJECT_UNAUTHORIZED=0 accepts the Pi's self-signed certificate; the safer variant is to copy the certificate (/etc/nginx/ssl/self-signed-wlanpi.cert on the device) to your machine and set NODE_EXTRA_CA_CERTS to that file instead.

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

Restart Claude Desktop after saving the config. The wlanpi server should appear in the tools menu with tools like get_device_info and scan_wlan listed.
