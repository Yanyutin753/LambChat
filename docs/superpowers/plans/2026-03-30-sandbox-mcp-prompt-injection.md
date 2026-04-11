# Sandbox MCP Prompt Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject sandbox MCP tool descriptions into the system prompt so the LLM can use them via bash/mcporter, with in-memory caching for KV cache optimization.

**Architecture:** After sandbox is ready, call `mcporter list --json`, format the output into a prompt section, and append it at the end of the system prompt. Cache the result per-user with 30-min TTL. Invalidate cache when MCP servers are added/updated/removed. Remove sandbox transport option from the frontend MCP management UI.

**Tech Stack:** Python (asyncio, langchain), React/TypeScript, mcporter CLI

---

### Task 1: Create sandbox MCP prompt builder with cache

**Files:**
- Create: `src/infra/tool/sandbox_mcp_prompt.py`

- [ ] **Step 1: Write the sandbox MCP prompt module**

```python
"""Sandbox MCP Prompt Builder - Injects sandbox MCP tool descriptions into system prompt.

Caches mcporter list output per-user to maximize KV cache hit rate.
The prompt section is appended at the END of the system prompt so that
changes only invalidate the tail of the KV cache, not the stable prefix.
"""

import json
import shlex
import time
from typing import Any, Optional

from src.infra.logging import get_logger

logger = get_logger(__name__)

# Cache: user_id -> (prompt_string, timestamp)
_sandbox_mcp_prompt_cache: dict[str, tuple[str, float]] = {}

# Cache TTL in seconds
_CACHE_TTL = 1800  # 30 minutes

# mcporter timeout
_MCPORTER_TIMEOUT = 15


async def build_sandbox_mcp_prompt(
    backend: Any,
    user_id: str,
    force_refresh: bool = False,
) -> str:
    """Build a prompt section describing available sandbox MCP tools.

    Args:
        backend: The sandbox backend (CompositeBackend) to run mcporter on.
        user_id: User ID for cache keying.
        force_refresh: If True, bypass cache and refresh.

    Returns:
        Formatted prompt string, or empty string if no tools available.
    """
    # Check cache
    if not force_refresh and user_id in _sandbox_mcp_prompt_cache:
        prompt, ts = _sandbox_mcp_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[SandboxMCP Prompt] Cache hit for user {user_id}")
            return prompt

    # Fetch from mcporter
    prompt = await _fetch_and_format(backend)

    # Update cache (even if empty — avoids repeated mcporter calls when no servers exist)
    _sandbox_mcp_prompt_cache[user_id] = (prompt, time.time())
    logger.info(
        f"[SandboxMCP Prompt] {'Cache miss' if not force_refresh else 'Force refresh'} "
        f"for user {user_id}, prompt length={len(prompt)}"
    )

    return prompt


def invalidate_sandbox_mcp_prompt_cache(user_id: str) -> None:
    """Invalidate the cached prompt for a user.

    Call this after sandbox_mcp_add/update/remove operations.
    """
    if user_id in _sandbox_mcp_prompt_cache:
        del _sandbox_mcp_prompt_cache[user_id]
        logger.debug(f"[SandboxMCP Prompt] Cache invalidated for user {user_id}")


def _format_tools_list(data: Any) -> str:
    """Format mcporter list JSON output into a readable prompt section.

    Expected mcporter list --json format (per-server):
    {
      "server_name": {
        "tools": [
          {
            "name": "tool_name",
            "description": "...",
            "inputSchema": { ... }
          }
        ]
      }
    }
    """
    if not isinstance(data, dict):
        return ""

    lines = ["## Sandbox MCP Tools", ""]
    lines.append(
        "The following MCP tools are registered in your sandbox. "
        "Use them via bash with `mcporter call`:"
    )
    lines.append("")

    tool_count = 0

    for server_name, server_data in sorted(data.items()):
        if not isinstance(server_data, dict):
            continue

        tools = server_data.get("tools", [])
        if not tools:
            continue

        for tool in tools:
            tool_name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("inputSchema", {})

            if not tool_name:
                continue

            tool_count += 1

            # Tool header
            lines.append(f"- **{tool_name}** (from `{server_name}`)")
            if description:
                lines.append(f"  {description}")

            # Parameters from inputSchema
            properties = input_schema.get("properties", {})
            required = set(input_schema.get("required", []))

            if properties:
                param_parts = []
                for param_name, param_info in properties.items():
                    req = "required" if param_name in required else "optional"
                    param_desc = param_info.get("description", "")
                    param_parts.append(f"`{param_name}` ({req}{': ' + param_desc if param_desc else ''})")

                lines.append(f"  Parameters: {', '.join(param_parts)}")

            # Usage example
            if properties:
                required_params = [p for p in properties if p in required]
                if required_params:
                    args_example = " ".join(
                        f'{p}="<value>"' for p in required_params[:3]
                    )
                else:
                    first_param = next(iter(properties), "")
                    args_example = f'{first_param}="<value>"' if first_param else ""
                lines.append(f"  Usage: `mcporter call {server_name}.{tool_name} {args_example}`")
            else:
                lines.append(f"  Usage: `mcporter call {server_name}.{tool_name}`")

            lines.append("")

    if tool_count == 0:
        return ""

    return "\n".join(lines)


async def _fetch_and_format(backend: Any) -> str:
    """Run mcporter list and format the output."""
    try:
        result = await backend.aexecute("mcporter list --json", timeout=_MCPORTER_TIMEOUT)
        if result.exit_code != 0:
            logger.warning(f"[SandboxMCP Prompt] mcporter list failed: {result.output}")
            return ""

        try:
            data = json.loads(result.output)
        except json.JSONDecodeError:
            logger.warning("[SandboxMCP Prompt] mcporter list returned invalid JSON")
            return ""

        return _format_tools_list(data)

    except Exception as e:
        logger.warning(f"[SandboxMCP Prompt] Failed to fetch tools: {e}")
        return ""
```

- [ ] **Step 2: Commit**

```bash
git add src/infra/tool/sandbox_mcp_prompt.py
git commit -m "feat: add sandbox MCP prompt builder with per-user cache"
```

---

### Task 2: Inject prompt in search agent

**Files:**
- Modify: `src/agents/search_agent/nodes.py:275-280` (system prompt assembly)
- Modify: `src/agents/search_agent/nodes.py:1-30` (imports)

- [ ] **Step 1: Add import in nodes.py**

At the top of `src/agents/search_agent/nodes.py`, add the import alongside the existing imports. Find the existing `from src.infra.tool.sandbox_mcp_tool import` line or the imports block, and add:

```python
from src.infra.tool.sandbox_mcp_prompt import build_sandbox_mcp_prompt
```

- [ ] **Step 2: Inject sandbox MCP prompt after sandbox ready**

In `src/agents/search_agent/nodes.py`, find the system prompt assembly block (around line 276):

```python
        # 格式化沙箱提示词，注入 work_dir, skills 和 memory_guide
        system_prompt = (
            SANDBOX_SYSTEM_PROMPT.replace("{work_dir}", work_dir)
            .replace("{skills}", skills_prompt)
            .replace("{memory_guide}", memory_guide)
        )
```

Replace with:

```python
        # 格式化沙箱提示词，注入 work_dir, skills 和 memory_guide
        system_prompt = (
            SANDBOX_SYSTEM_PROMPT.replace("{work_dir}", work_dir)
            .replace("{skills}", skills_prompt)
            .replace("{memory_guide}", memory_guide)
        )

        # 注入沙箱 MCP 工具描述（放在 system prompt 末尾，最大化 KV cache 命中率）
        sandbox_mcp_prompt = await build_sandbox_mcp_prompt(sandbox_backend, user_id)
        if sandbox_mcp_prompt:
            system_prompt = system_prompt + "\n\n" + sandbox_mcp_prompt
```

- [ ] **Step 3: Commit**

```bash
git add src/agents/search_agent/nodes.py
git commit -m "feat: inject sandbox MCP tools into search agent system prompt"
```

---

### Task 3: Wire cache invalidation in sandbox_mcp_tool.py

**Files:**
- Modify: `src/infra/tool/sandbox_mcp_tool.py:1-10` (imports)
- Modify: `src/infra/tool/sandbox_mcp_tool.py` (add invalidation calls in _mcporter_add, _mcporter_update, _mcporter_remove)

- [ ] **Step 1: Add import**

At the top of `src/infra/tool/sandbox_mcp_tool.py`, add after the existing imports:

```python
from src.infra.tool.sandbox_mcp_prompt import invalidate_sandbox_mcp_prompt_cache
```

- [ ] **Step 2: Add invalidation in `_mcporter_add`**

In `_mcporter_add` (around line 239), after the success JSON return, add a cache invalidation call. Find the line:

```python
    return json.dumps({
        "success": True,
        "message": f"Server '{server_name}' added to sandbox and saved",
        "server_name": server_name,
        "command": command,
        "env_keys": env_key_list,
    })
```

Before this return, add:

```python
    invalidate_sandbox_mcp_prompt_cache(user_id or "unknown")
```

So it becomes:

```python
    invalidate_sandbox_mcp_prompt_cache(user_id or "unknown")
    return json.dumps({
        "success": True,
        "message": f"Server '{server_name}' added to sandbox and saved",
        "server_name": server_name,
        "command": command,
        "env_keys": env_key_list,
    })
```

- [ ] **Step 3: Add invalidation in `_mcporter_update`**

In `_mcporter_update` (around line 301), before the success return, add:

```python
    invalidate_sandbox_mcp_prompt_cache(user_id or "unknown")
```

Before the existing:

```python
    return json.dumps({
        "success": True,
        "message": f"Server '{server_name}' updated in sandbox and saved",
        ...
    })
```

- [ ] **Step 4: Add invalidation in `_mcporter_remove`**

In `_mcporter_remove` (around line 337), before the success returns, add invalidation. There are two success return paths. Add `invalidate_sandbox_mcp_prompt_cache(user_id or "unknown")` before each one. Specifically, before:

```python
    if result.exit_code != 0 and deleted:
        return json.dumps({
            "success": True,
            "message": f"Server '{server_name}' removed from database (was not in sandbox)",
        })
```

And before:

```python
    return json.dumps({
        "success": True,
        "message": f"Server '{server_name}' removed from sandbox and database",
        ...
    })
```

- [ ] **Step 5: Commit**

```bash
git add src/infra/tool/sandbox_mcp_tool.py
git commit -m "feat: invalidate sandbox MCP prompt cache on add/update/remove"
```

---

### Task 4: Wire cache invalidation in session_manager.py

**Files:**
- Modify: `src/infra/sandbox/session_manager.py:774-780` (after _rebuild_sandbox_mcp)

- [ ] **Step 1: Add import**

At the top of `src/infra/sandbox/session_manager.py`, add:

```python
from src.infra.tool.sandbox_mcp_prompt import invalidate_sandbox_mcp_prompt_cache
```

- [ ] **Step 2: Invalidate cache after MCP rebuild**

In `_create_and_bind_e2b` (around line 775), find:

```python
        try:
            await self._rebuild_sandbox_mcp(backend, user_id)
        except Exception as e:
            logger.warning(f"[E2B] Sandbox MCP rebuild failed (non-fatal): {e}")
```

Replace with:

```python
        try:
            await self._rebuild_sandbox_mcp(backend, user_id)
            invalidate_sandbox_mcp_prompt_cache(user_id)
        except Exception as e:
            logger.warning(f"[E2B] Sandbox MCP rebuild failed (non-fatal): {e}")
```

- [ ] **Step 3: Commit**

```bash
git add src/infra/sandbox/session_manager.py
git commit -m "feat: invalidate sandbox MCP prompt cache after sandbox rebuild"
```

---

### Task 5: Remove sandbox transport from frontend

**Files:**
- Modify: `frontend/src/components/mcp/MCPServerForm.tsx` (remove sandbox option)
- Modify: `frontend/src/components/panels/MCPPanel.tsx` (remove sandbox permission from allowed transports)

- [ ] **Step 1: Remove sandbox transport from MCPServerForm**

In `frontend/src/components/mcp/MCPServerForm.tsx`, remove the sandbox entry from the `allTransports` array (lines 56-60):

```typescript
    {
      value: "sandbox" as MCPTransport,
      label: t("mcp.form.transportSandbox"),
      permission: Permission.MCP_WRITE_SANDBOX,
    },
```

Also remove `Permission.MCP_WRITE_SANDBOX` from the default `allowedTransports` prop (line 35):

```typescript
    Permission.MCP_WRITE_SANDBOX,
```

Remove the `isSandboxTransport` helper function (line 24) and all sandbox-specific code:
- The `isSandboxMode` variable (line 94)
- The sandbox fields state (lines 86-90: `command`, `envKeys`, `envKeyInput`)
- The sandbox validation branch (lines 132-135: `if (isSandboxMode)`)
- The sandbox submit branch (lines 157-161: `if (isSandboxMode)`)
- The sandbox form fields JSX (lines 288-370: `{isSandboxMode ? (...) : (...)}` → keep only the else branch)
- The sandbox state resets in useEffect (lines 111-112, 119-120)

After cleanup, the form should only have SSE/streamable_http transport options and URL/headers fields.

- [ ] **Step 2: Remove sandbox permission from MCPPanel allowed transports**

In `frontend/src/components/panels/MCPPanel.tsx`, find the `allowedTransports` definition (around line 87):

```typescript
  const allowedTransports = [
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_SSE])
      ? Permission.MCP_WRITE_SSE
      : null,
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_HTTP])
      ? Permission.MCP_WRITE_HTTP
      : null,
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_SANDBOX])
      ? Permission.MCP_WRITE_SANDBOX
      : null,
  ].filter(Boolean) as Permission[];
```

Remove the sandbox permission entry:

```typescript
  const allowedTransports = [
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_SSE])
      ? Permission.MCP_WRITE_SSE
      : null,
    hasAnyPermission([Permission.MCP_ADMIN, Permission.MCP_WRITE_HTTP])
      ? Permission.MCP_WRITE_HTTP
      : null,
  ].filter(Boolean) as Permission[];
```

- [ ] **Step 3: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/mcp/MCPServerForm.tsx frontend/src/components/panels/MCPPanel.tsx
git commit -m "feat: remove sandbox transport from frontend MCP management UI"
```

---

### Task 6: Clean up unused i18n keys (optional)

**Files:**
- Modify: `frontend/src/i18n/locales/en.json` (remove sandbox-related MCP form keys)
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`

- [ ] **Step 1: Remove sandbox-related i18n keys**

In each locale file, remove keys that are only used by the sandbox transport UI:
- `mcp.form.transportSandbox`
- `mcp.form.command`
- `mcp.form.commandPlaceholder`
- `mcp.form.commandHint`
- `mcp.form.commandRequired`
- `mcp.form.envKeys`
- `mcp.form.envKeyPlaceholder`
- `mcp.form.envKeysHint`
- `mcp.card.envVarsCount`

Keep any keys that might still be referenced elsewhere (search for usages before removing).

- [ ] **Step 2: Verify frontend builds**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/
git commit -m "chore: remove unused sandbox MCP i18n keys"
```
