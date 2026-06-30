# Sandbox Configuration

Code sandbox settings for secure remote code execution. Supports Daytona, E2B, and CubeSandbox platforms.

## General

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SANDBOX` | `false` | Enable sandbox execution. |
| `SANDBOX_PLATFORM` | `daytona` | Sandbox platform: `daytona`, `e2b`, or `cubesandbox`. |
| `SANDBOX_GREP_TIMEOUT` | `30` | Sandbox grep command timeout in seconds. |

## Daytona

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `DAYTONA_API_KEY` | _(empty)_ | Yes | Daytona API key. |
| `DAYTONA_SERVER_URL` | _(empty)_ | No | Daytona server URL. |
| `DAYTONA_TIMEOUT` | `180` | No | Command timeout in seconds (3 minutes). |
| `DAYTONA_IMAGE` | _(empty)_ | No | Sandbox image/snapshot ID to use. |
| `DAYTONA_AUTO_STOP_INTERVAL` | `5` | No | Auto-stop interval in minutes. |
| `DAYTONA_AUTO_ARCHIVE_INTERVAL` | `5` | No | Auto-archive interval in minutes. |
| `DAYTONA_AUTO_DELETE_INTERVAL` | `1440` | No | Auto-delete interval in minutes (24 hours). |

## E2B

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `E2B_API_KEY` | _(empty)_ | Yes | E2B API key. |
| `E2B_TEMPLATE` | `base` | No | Sandbox template name. |
| `E2B_TIMEOUT` | `3600` | No | Sandbox timeout in seconds (1 hour). |
| `E2B_AUTO_PAUSE` | `true` | No | Pause sandbox on timeout instead of killing (preserves state). |
| `E2B_AUTO_RESUME` | `true` | No | Auto-resume paused sandbox on next activity. |

## CubeSandbox

CubeSandbox is supported through the native CubeSandbox Python SDK. LambChat uses CubeSandbox metadata to keep a stable user-to-sandbox binding: each user should have one running sandbox that is shared across conversations and sessions.

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `CUBE_API_URL` | `http://127.0.0.1:3000` | No | CubeSandbox API base URL. For the local dev environment this is commonly `http://127.0.0.1:13000`. |
| `CUBE_TEMPLATE` | _(empty)_ | No | CubeSandbox template ID used when creating sandboxes. |
| `CUBE_TIMEOUT` | `3600` | No | Sandbox timeout in seconds. |
| `CUBE_PROXY_NODE_IP` | _(empty)_ | No | Proxy node IP used by the SDK to reach sandbox data-plane services. |
| `CUBE_PROXY_PORT_HTTP` | `80` | No | HTTP proxy port used by the SDK. |
| `CUBE_SANDBOX_DOMAIN` | `cube.app` | No | Sandbox domain suffix used by CubeSandbox proxy routing. |
| `CUBE_REQUEST_TIMEOUT` | `120` | No | SDK request timeout in seconds. Lower values fail faster on stale data-plane connections; higher values tolerate slower local starts. |
| `CUBE_AUTO_PAUSE` | `true` | No | Ask CubeSandbox to pause on timeout instead of killing when supported by the runtime. |
| `CUBE_AUTO_RESUME` | `true` | No | Ask CubeSandbox to auto-resume paused sandboxes when supported by the runtime. |

### Lifecycle Behavior

When `SANDBOX_PLATFORM=cubesandbox`, LambChat follows this order for a user:

1. Reuse the in-process cached sandbox if it is still healthy.
2. Reconnect to the MongoDB `user_sandbox_bindings` record.
3. If the binding is missing or unhealthy, list CubeSandbox instances with matching `metadata.user_id` and reuse a healthy running sandbox.
4. Create a new sandbox only when no healthy existing sandbox can be used.
5. Clean duplicate same-user running sandboxes while keeping the selected sandbox.

CubeSandbox may occasionally report a sandbox as `running` in the control plane even though the data plane returns `504 Gateway Time-out`. LambChat treats that as unhealthy when it cannot create the session work directory or run commands, then falls back to another existing sandbox or creates a new one.

### Production Migration

LambChat stores sandbox bindings per user and per platform. New records use:

- `sandboxes.e2b`
- `sandboxes.cubesandbox`

Older production records may only have top-level fields such as `sandbox_id` and `sandbox_state`. When `SANDBOX_PLATFORM=e2b`, those legacy top-level records are treated as E2B bindings for backward compatibility. On the next successful reuse, LambChat writes the same sandbox into `sandboxes.e2b`, so the existing E2B sandbox continues to be used and is not recreated.

Switching a user or deployment from `e2b` to `cubesandbox` creates or reuses a CubeSandbox binding under `sandboxes.cubesandbox` without overwriting `sandboxes.e2b`. Switching back to `e2b` reads the E2B slot again.

For production deployments that should keep using E2B, leave:

```bash
SANDBOX_PLATFORM=e2b
```

Do not set `SANDBOX_PLATFORM=cubesandbox` unless you intentionally want those users to start using CubeSandbox. The two platforms have separate sandbox IDs and separate lifecycle APIs.

### Performance Notes

- A cold CubeSandbox create depends on the template and local runtime restore time. In local testing this can take around 20-30 seconds.
- New conversations for the same user should normally reuse the same sandbox and avoid cold start.
- Duplicate sandbox cleanup runs outside the critical cache-hit path, so reuse can return before background cleanup finishes.
- `CubeSandboxBackend` uses `CUBE_TIMEOUT` for command execution and caches parent-directory creation for repeated file writes.
- The session manager caches successfully prepared session work directories in the current backend process. After a backend restart, `mkdir -p` is run again and remains safe.

### Console and API Checks

For the local CubeSandbox dev environment used during integration:

```bash
# CubeSandbox Web UI
open http://127.0.0.1:12088

# List sandboxes from the Cube API
curl http://127.0.0.1:13000/sandboxes
```

Useful checks:

- The selected sandbox should have `metadata.user_id` equal to the LambChat user ID.
- A user should normally have only one healthy `running` sandbox.
- If a sandbox is listed as `running` but command execution returns 504, kill it from CubeSandbox or let LambChat replace it on the next sandbox initialization.

## Examples

### Daytona (Self-hosted)

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=daytona
DAYTONA_API_KEY=your_daytona_api_key
DAYTONA_SERVER_URL=https://daytona.example.com
DAYTONA_TIMEOUT=180
```

### E2B (Cloud)

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=e2b
E2B_API_KEY=your_e2b_api_key
E2B_TEMPLATE=base
E2B_TIMEOUT=3600
```

### CubeSandbox (Local Dev)

```bash
ENABLE_SANDBOX=true
SANDBOX_PLATFORM=cubesandbox
CUBE_API_URL=http://127.0.0.1:13000
CUBE_TEMPLATE=tpl-your-template-id
CUBE_PROXY_NODE_IP=127.0.0.1
CUBE_PROXY_PORT_HTTP=11080
CUBE_SANDBOX_DOMAIN=cube.app
CUBE_TIMEOUT=3600
CUBE_REQUEST_TIMEOUT=120
CUBE_AUTO_PAUSE=true
CUBE_AUTO_RESUME=true
```

::: info
The `DAYTONA_AUTO_*_INTERVAL` settings control sandbox lifecycle management to optimize resource usage. Sandboxes are automatically stopped, archived, and eventually deleted based on these intervals.
:::

::: tip
For CubeSandbox, tune `CUBE_REQUEST_TIMEOUT` based on your local runtime. Shorter values make stale sandboxes fail faster; longer values reduce false failures during slow local restores.
:::
