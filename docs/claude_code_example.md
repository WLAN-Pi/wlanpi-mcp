# Claude Code Example MCP Config

This is an example of how to setup claude code to use the WLANPi MCP server.

## CLI Command

```bash
claude mcp add --transport http wlanpi https://<pi-ip-address>:8767/mcp --header "Authorization: Bearer <your-wlanpi-core-jwt>"
```

### Config File

Or you can drop a .mcp.json file in the project folder:

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
