# Bugbot

Review rules for wlanpi-mcp. This is an on-device MCP server and a thin bridge to the wlanpi-core API at `https://localhost:31415`. Every tool and resource goes through that API (REST, or the capture WebSocket at `/api/v1/streaming/capture`). CI already runs `tox -e lint` (ruff, then mypy), `tox -e formatcheck`, and pytest on Python 3.13. Flag the gaps below.

## Reporting Threshold

Judge customer impact before you raise an implementation gap. Describe a realistic task, the normal steps a user takes, and what the user materially loses. Report a finding only when it would materially prevent or mislead a customer doing ordinary work. Omit a low-impact finding. Do not include it at a lower priority. The Flag rules below name changes that meet this bar.

## Python, typing, and tests

- Bare `dict`, `list`, `set`, or `tuple`. `mypy.ini` sets `disallow_any_generics` and `disallow_untyped_defs`. JSON payloads are `dict[str, Any]`.
- A new or changed tool, resource, or prompt whose docstring does not tell an MCP client what the call does and what a non-2xx from wlanpi-core means. The SDK serves `__doc__` as the description. ruff only checks Google shape (D100-D106, D205, D401, D415). `tests/**` is exempt from docstring presence.
- Hand-wrapping to satisfy E501. E501 is disabled. `ruff format` owns line length.
- `skip_install = true` on `[testenv:lint]` in `tox.ini`. mypy resolves `mcp`, `httpx`, and `uvicorn` from the installed package.
- A runtime dependency added outside `pyproject.toml`, a cap that allows `mcp` 2.x (`mcp[cli]>=1.21.1,<2` is required; 2.x renames FastMCP), or an import of scapy or dpkt. The pcapng reader and radiotap dissector stay stdlib-only.
- Committed coverage artifacts (`.coverage`, `coverage.xml`, `coverage.svg`) or a new whitespace-fixing script. ruff owns W291 and W293.
- `time.sleep` or other blocking work called directly from an async tool or resource.
- A behavior change under `wlanpi_mcp/` with no new or updated test under `tests/`. Tool tests go through `tool.run(args)` (dispatch and validation). `.fn(...)` alone misses argument-name bugs.
- A new tool that `create_server()` in `wlanpi_mcp/server.py` does not register, or that lacks `annotations=hints.READ_ONLY`, `hints.ADDITIVE`, or `hints.DESTRUCTIVE`. MCP treats an unannotated tool as destructive. Add the tool to the matching set in `tests/test_tool_annotations.py`. Reboot, delete, overwrite, or interrupting a service, radio, link, or the device is `DESTRUCTIVE`. A mutating tool marked `READ_ONLY` is a bug: the annotation test treats every unclassified tool as read-only, so a wrong `READ_ONLY` hint passes.
- An expected tool failure raised as an exception, or a `CoreAPIError` swallowed into a generic message. Tools return `{"error": "..."}` and let `CoreAPIError` propagate with core's status and `detail`. The exception is `fetch_pcap_file`: it raises `ToolError`, is registered with `structured_output=False`, and is annotated `-> EmbeddedResource` only. Dropping `structured_output=False` sends the pcap twice (mcp 1.27+).

## Debian packaging and versions

Only a release pull request edits `debian/changelog` or `wlanpi_mcp/__version__.py`. A fix or a feature pull request leaves both unchanged. Do not add a Debian revision `-N`. Follow [Land a Fix and Cut a Release](https://github.com/WLAN-Pi/developers/blob/main/RELEASING.md).

Today, `deploy-to-packagecloud.yml` builds and publishes to Packagecloud `wlanpi/dev` when `debian/changelog` changes on `main`. It fails if `wlanpi_mcp/__version__.py` differs from the changelog `major.minor.patch` (`0.7.0` matches `0.7.0-1`). The dev-build stamp is planned. It is not live yet. When it is, CI writes `X.Y.Z~dev<YYYYMMDD>.<run_id>.<run_attempt>+g<sha>` in the build workspace, uploads that `.deb` to Packagecloud `wlanpi/dev`, and does not tag it. Under that same CI, the release pull request uploads to `wlanpi/main` and tags `v<version>`.

- Flag a pull request that edits `debian/changelog` or `wlanpi_mcp/__version__.py` unless that pull request is the release. A fix or a feature is not a release.
- Flag a pull request that sets the newest changelog version to one that contains a Debian revision `-N`.
- Flag a release pull request where `wlanpi_mcp/__version__.py` differs from the changelog `major.minor.patch`.
- Flag a new call to a wlanpi-core route that needs core newer than `Depends: wlanpi-core (>= 2.4.8)` unless `debian/control` raises that floor. The release pull request records the new floor. Where older core is still possible, a 404 becomes an upgrade message, as `get_profiler_reports` does.
- Flag `debian/rules` building with anything other than `SNAKE ?= /usr/bin/python3.13`, dropping `--no-compile` or the bytecode cleanup, or installing outside `/opt/wlanpi-mcp`.
- Flag a new `debian/compat`. Compatibility is `debhelper-compat (= 13)` in `debian/control`.
- Flag an `Architecture` change with no stated reason. This package is `any` because dh-virtualenv ships arch-specific wheels.
- Flag a license change away from BSD-3-Clause, or a new dependency licensed GPL or AGPL.

## systemd and install paths

The packaged unit runs as `wlanpi`, with `EnvironmentFile=/etc/wlanpi-mcp/config.env`, `Environment=PYTHONDONTWRITEBYTECODE=1`, and `ExecStart=/opt/wlanpi-mcp/bin/python -m wlanpi_mcp --transport streamable-http`. nginx (`install/etc/wlanpi-mcp/nginx/wlanpi-mcp.conf`) is the only public listener: TLS on 8767, proxy to `127.0.0.1:8768`. UFW opens `8767/tcp` only. `config.env` is mode `640`, owner `root:wlanpi`. Defaults live in `debian/postinst` and `install/etc/wlanpi-mcp/config.env.example`.

- Flag the daemon binding `0.0.0.0`, port 8766, or port 8767. 8767 belongs to nginx. 8766 was the removed plaintext listener. Defaults stay `WLANPI_MCP_HOST=127.0.0.1` and `WLANPI_MCP_PORT=8768`.
- Flag a plaintext listener, a UFW port other than `8767/tcp`, or an nginx site that drops `Host`, `X-Real-IP`, `X-Forwarded-For`, or `X-Forwarded-Proto`.
- Flag config, state, or logs placed under `/opt`. Config belongs in `/etc/wlanpi-mcp/`. Ship this package's own unit, nginx site, or a drop-in. Do not edit another package's files in place.
- Flag `postinst` overwriting an existing `config.env`. Upgrades may `sed` one exact old default.
- Flag removal of `PYTHONDONTWRITEBYTECODE=1`. Bytecode under the venv is not owned by dpkg and survives purge.
- Flag a unit that runs as root, or an `ExecStart` that is not `/opt/wlanpi-mcp/bin/python`.

## Security

The process runs on the device. It can reboot the box, change network config, and capture Wi-Fi. It does not authenticate callers itself.

- Flag new authentication, token minting, verification, refresh, or a token cache. Clients present a wlanpi-core JWT (`Authorization: Bearer`). `CoreClient` forwards that token. A 401 goes back to the client with no retry.
- Flag `WLANPI_CORE_TOKEN` consulted when the request already has a Bearer token, written into a log, or required for the HTTP daemon. It is the stdio fallback only and stays empty in the packaged `config.env`.
- Flag a token in a URL, query string, WebSocket URL, log line, or error string. The capture socket sends it only as the first message, `{"command":"auth","token":...}`.
- Flag a route that skips `BearerTokenMiddleware` and is not under `/pcap/` or `/profiler-report/`. Those prefixes exist for single-use download tickets. A new ticket route checks the ticket itself, is listed in `TICKET_PATH_PREFIXES`, and has a `tests/test_server.py` case: served once without a JWT, second fetch 404, expired ticket refused, `/mcp` still 401.
- Flag a download ticket that is reusable, outlives `DOWNLOAD_TTL_S` (300 seconds), is stored on disk, or is minted before `download_links.check_token` accepts the caller. pcap tickets name one path inside `PCAP_CAPTURE_DIR`. Profiler-report tickets hold an in-memory byte snapshot, not a path. Both pop on first use.
- Flag a `curl` command or other shell string built from `Host`, a path, or tool input that skips `download_links.HOST_RE` or `shlex.quote`.
- Flag `subprocess` with `shell=True`, `os.system`, or a command line interpolated from tool arguments. This server does not shell out. A missing capability is added as a wlanpi-core endpoint first, then called over REST or the capture WebSocket. If a subprocess is unavoidable, pass an argument list, set `timeout=`, and check the return code.
- Flag local file reads or writes outside `Settings.PCAP_CAPTURE_DIR` (default `/tmp/wlanpi-mcp/captures`). `fetch_pcap_file` realpath-checks and refuses any path outside that directory. Profiler results come from `GET /api/v1/profiler/files`, not from disk.
- Flag a path join that honors a caller-supplied `..` segment, or a capture filename that skips `storage.safe_component`.
- Flag `reboot_device` or `shutdown_device` skipping `ALLOW_POWER_CONTROL`, or a new power tool with no such gate.
- Flag a local copy of the service allowlist. `list_allowed_services` reads `GET /api/v1/system/services`. Core enforces the list on every service call.
- Flag `stateless_http` turned off, the legacy SSE transport brought back, or `enable_dns_rebinding_protection` turned on. nginx forwards the client `Host`, and the JWT middleware is the gate. A stateful session has to bind to the `sha256(token)` principal on `scope["user"]` and ship a test that proves it.
- Flag renaming the public capture handle from `capture_id` to `session_id`. `session_id` stays only as a back-compat alias. The legacy MCP SSE transport dropped a tool argument of that name.
- Flag a capture owner that does not `stop()` and close its WebSocket in a `finally`. Closing the socket stops the capture on the device. `CHANNEL_SET_FAILED` stays non-fatal and is reported in `channel_issues`.
- Flag logging a JWT, hotspot passphrase, or other secret. Module-level resource caches (`_cached_get`) are keyed only by path and are shared across callers. Caller-specific data and secrets do not belong in them.
- Flag a change to `get_profiler_reports` argument names or result shape (`output`, `mac`, `max_clients`, and the json, links, and zip results). Existing callers depend on that shape.

## Capture and new capabilities

- Streaming capture returns a dissected summary and tees raw pcapng via `CaptureSocket.consume`'s `raw_sink`. File capture (`start_pcap_file` and the stop, list, and fetch tools) is the only path that returns raw pcapng and writes a local file, and that write stays under `PCAP_CAPTURE_DIR`.
- Keep the shared pcapng and 802.11 parse logic aligned with wlanpi-core `tools/capture_harness/capture_harness.py`. Keep this tree's extensions: per-frame timestamps, full radiotap decode, frame addresses, RSN/WPA detail, and the QBSS load element.
- A capability with no wlanpi-core endpoint does not get a local subprocess, a local file read, or a second transport. Add the endpoint upstream first.
