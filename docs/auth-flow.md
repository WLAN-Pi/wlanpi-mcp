# Authentication flow: Claude → MCP → nginx → wlanpi-core

wlanpi-mcp implements **no authentication of its own**. The user holds a single
wlanpi-core JWT, and that same token is forwarded on every outbound wlanpi-core API call,
where core validates it. This document traces the token end to end.

The MCP endpoint (`/mcp`, streamable HTTP, stateless) is fronted by an MCP-owned
nginx site: the uvicorn daemon binds loopback-only (127.0.0.1:8768) and nginx
exposes it on `8767`, terminating the device's self-signed TLS. That is the
only MCP endpoint: the plaintext `8766` fallback was removed (#17), so the JWT
never crosses the LAN in cleartext.

## Sequence

```mermaid
sequenceDiagram
    participant CD as Claude Desktop
    participant MR as mcp-remote (proxy)
    participant MG as nginx (:8767 TLS, MCP front)
    participant MW as MCP: BearerTokenMiddleware
    participant CC as MCP: CoreClient
    participant NG as nginx (:31415)
    participant API as wlanpi-core (root)

    Note over CD,MR: User holds ONE wlanpi-core JWT
    CD->>MR: launch w/ Authorization: Bearer <JWT>
    Note over CD,CC: every MCP call is one POST - stateless, no server-side session
    CD->>MR: CallTool (e.g. scan_wlan)
    MR->>MG: POST /mcp (TLS on 8767)<br/>Authorization: Bearer <JWT>
    MG->>MW: proxy_pass → 127.0.0.1:8768/mcp
    alt no / non-Bearer token
        MW-->>MR: 401 (reject tokenless request)
    else Bearer present
        MW->>MW: stash JWT in contextvar<br/>publish sha256(JWT) principal on scope["user"]
        MW->>CC: dispatch tool → CoreClient.get(...)<br/>token read off this request (get_token)
    end
    CC->>NG: GET /api/v1/... over localhost<br/>Authorization: Bearer <JWT>
    NG->>API: proxy_pass unix:/run/wlanpi_core.sock<br/>Bearer JWT, unchanged
    API->>API: verify_auth_wrapper sees a Bearer<br/>⇒ verify_jwt_token (DB lookup + revocation)
    alt JWT valid
        API-->>NG: 200 + data
        NG-->>CC: 200 + data
        CC-->>CD: tool result
    else JWT invalid/expired/revoked
        API-->>CC: 401
        CC-->>CD: tool error (no retry - MCP doesn't own the token)
    end
```

## Where each auth decision happens

```mermaid
flowchart LR
    A[Claude Desktop<br/>+ user JWT] -->|Bearer JWT| B[mcp-remote]
    B -->|Bearer JWT| C{MCP middleware<br/>token present?}
    C -->|no| C401[401 reject]
    C -->|yes| D[CoreClient<br/>forwards Bearer only]
    D -->|localhost:31415| H{core verify_auth_wrapper<br/>credential presented?}
    H -->|Bearer| J[verify_jwt_token<br/>validate + revocation]
    H -->|X-Request-Signature| I[HMAC path<br/>localhost only]
    H -->|neither| L401[401]
    J -->|valid| K[200 + data]
    J -->|invalid| L[401]
```

## The key handoffs, in words

| Hop | Carries | Auth decision |
|---|---|---|
| Claude Desktop → mcp-remote | `Authorization: Bearer <JWT>` | none - just transport |
| mcp-remote → MCP nginx front (`:8767` TLS) | the same Bearer on every `/mcp` POST | **nginx:** TLS termination with the self-signed cert; the JWT is encrypted in transit |
| MCP nginx front → MCP middleware | same Bearer, forwarded to `127.0.0.1:8768` | **MCP:** reject if no Bearer (401); else stash JWT in contextvar |
| MCP CoreClient → core nginx | `Bearer <JWT>` | none yet - MCP never validates |
| core nginx → core (unix socket) | the same Bearer, proxied unchanged | none - nginx only proxies |
| core `verify_auth_wrapper` | sees a Bearer | **core:** takes JWT branch → validates token, checks revocation |

The single source of truth for "is this caller allowed" stays in core's `verify_jwt_token` -
MCP and nginx only route; neither mints nor validates tokens. The one JWT the user holds
is the same credential end to end.

## How core picks the auth scheme

Core chooses the scheme from the credentials presented (wlanpi-core#159): a Bearer goes to
JWT validation, an `X-Request-Signature` goes to HMAC (localhost only), and neither is a
401. Source IP no longer matters for a Bearer, so the MCP service needs no special header
and never touches the root-owned HMAC secret.

## One token per request: the stateless transport

The daemon serves streamable HTTP in stateless mode (`stateless_http=True` in
`create_http_app`). There is no server-side MCP session: every `POST /mcp` is a complete
exchange, handled by a server instance created for that request and torn down after it.
Two consequences:

- **The token that reaches wlanpi-core is the Bearer on that very request.**
  The middleware sets a contextvar from that request's `Authorization` header, and
  `get_token()` (`wlanpi_mcp/auth/token_context.py`) reads only that contextvar. mcp 2.x
  runs each handler in the context of the request that carried the call, so concurrent
  requests with different tokens stay isolated.
- **There is no session for another caller to inject into.** Under the legacy SSE
  transport a session spanned a long-lived `GET /sse` plus per-call `POST /messages/`
  requests routed by `session_id`, and the server had to bind each session to the token
  that opened it. With nothing shared between requests, that attack surface is gone.

`BearerTokenMiddleware` still publishes a principal on `scope["user"]` keyed by
`sha256(token)`. The SDK's streamable HTTP session manager binds sessions to that
principal and refuses a mismatched request with the same `404` as a nonexistent session,
so the per-token binding is in place should stateful mode ever be enabled. The token is
not parsed or validated here (that stays wlanpi-core's job); the fingerprint only needs to
be stable and unique per token, so a raw SHA-256 suffices and keeps the token itself off
the principal object.

Why stateless: the legacy SSE transport stranded Claude Code after any reconnect (daemon
restart, idle gap). The client re-opened the stream without re-sending `initialize`, and
the server answered every later tool call with `-32602 Invalid request parameters`
(python-sdk issue #2579, closed as not planned). A stateless server has no handshake
state to lose. Transport
encryption is a separate control and is provided by the MCP nginx front:
nginx terminates TLS on 8767 (self-signed cert) in front of the loopback-only
daemon, so the token never crosses the wire in cleartext.

## Stdio mode

There are no HTTP headers in stdio transport, so the middleware/contextvar path does not
apply. `WLANPI_CORE_TOKEN` from config/env is the fallback token source.
