# Claude Code Example MCP Config:

This is an example of how to setup claude code to use the WLANPi MCP server.

### CLI Command

```bash
claude mcp add --transport http wlanpi https://<pi-ip-address>:8767/mcp --header "Authorization: Bearer <your-wlanpi-core-jwt>"
```

### Config File

Or you can use drop a .mcp.json file in the projec folder:

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
