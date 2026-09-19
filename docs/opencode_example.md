# Opencode Example MCP Config

This is an example of how to setup opencode to use the WLANPi MCP server.

## CLI Command

`opencode mcp add` takes the URL and header as flags, and always writes to the global `~/.config/opencode/opencode.json`, not a project file. Note the header uses `KEY=VALUE`, not a colon:

```bash
opencode mcp add wlanpi --url https://<pi-ip-address>:8767/mcp --header "Authorization=Bearer <your-wlanpi-core-jwt>"
```

### Config File

Or you can drop the same block into either the global file above, or an `opencode.json` in the class folder:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "wlanpi": {
      "type": "remote",
      "url": "https://<pi-ip-address>:8767/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:WLANPI_TOKEN}"
      }
    }
  }
}
```

Then launch with the certificate override:

```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 opencode
```
