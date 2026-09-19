# Example of Claude Desktop config:

Here is an example of using the wlanpi MCP server with Claude Desktop.

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
