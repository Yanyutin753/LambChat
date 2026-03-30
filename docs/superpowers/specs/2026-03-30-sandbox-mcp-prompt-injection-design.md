# Sandbox MCP Prompt Injection Design

## Problem

Sandbox MCP tools (e.g., `@anthropic/mcp-server-fetch`) run inside the sandbox via `mcporter`. Currently, the LLM can only discover and use these tools through 5 meta-tools (`sandbox_mcp_list`, `sandbox_mcp_call`, etc.), requiring a two-step process (list then call). The LLM should be able to use sandbox MCP tools as naturally as its other capabilities.

## Solution

Inject sandbox MCP tool descriptions into the system prompt so the LLM knows what tools are available and can call them directly via `bash` + `mcporter`. No dynamic tool creation, no LangChain BaseTool wrapping.

## Scope

### In Scope
- System prompt injection of sandbox MCP tool descriptions
- In-memory cache for `mcporter list` output with KV cache optimization
- Remove sandbox transport from frontend MCP management UI
- Keep 5 meta-tools for LLM-side MCP server management

### Out of Scope
- `MCPClientManager` / `get_global_mcp_tools` changes
- MongoDB persistence changes (already works)
- Sandbox lifecycle changes

## Architecture

### 1. System Prompt Injection

**Flow:**

```
prepare_assistant node:
  sandbox_backend = await sandbox_manager.get_or_create(...)
  ↓
  sandbox_mcp_prompt = get_cached_sandbox_mcp_prompt(sandbox_backend, user_id)
  ↓
  system_prompt = SANDBOX_SYSTEM_PROMPT
      .replace("{work_dir}", work_dir)
      .replace("{skills}", skills_prompt)
      .replace("{memory_guide}", memory_guide)
      + "\n" + sandbox_mcp_prompt  # appended at end
```

**New function: `build_sandbox_mcp_prompt(backend)`**

Location: `src/agents/search_agent/prompt.py` (or a new `src/infra/tool/sandbox_mcp_prompt.py`)

- Calls `mcporter list --json` on the backend
- Parses JSON output: server name → list of tools with name, description, parameters
- Formats into a readable prompt section:
  ```
  ## Sandbox MCP Tools
  The following MCP tools are registered in your sandbox. Use them via bash:
  - fetch (fetch server): Fetch web content
    mcporter call fetch.fetch url="https://example.com"
  - web_search (search server): Web search
    mcporter call search.web_search query="..."
  ```
- Returns empty string if no MCP servers registered

### 2. KV Cache Optimization

#### 2a. Dynamic Content at End

The `{sandbox_mcp_tools}` section is **appended at the very end** of the system prompt, after all stable content (including `SUBAGENT_TASK_GUIDE`). This ensures the long stable prefix always hits KV cache, and only the tail changes when MCP tools change.

#### 2b. In-Memory Cache for mcporter Output

```python
# In sandbox_mcp_prompt.py
_sandbox_mcp_prompt_cache: dict[str, tuple[str, float]] = {}
# user_id -> (prompt_string, timestamp)

CACHE_TTL = 1800  # 30 minutes
```

**Cache hit path (most requests):**
- Return cached prompt string directly, no `mcporter list` call, zero latency
- System prompt identical to previous request → KV cache 100% hit

**Cache miss/refresh triggers:**
1. `sandbox_mcp_add` / `update` / `remove` called → invalidate cache entry
2. Cache TTL expired (30 min)
3. Sandbox newly created (first `_rebuild_sandbox_mcp` completes)

**Invalidation mechanism:**
- New function `invalidate_sandbox_mcp_prompt_cache(user_id)` in `sandbox_mcp_prompt.py`
- Called from `_mcporter_add`, `_mcporter_update`, `_mcporter_remove` in `sandbox_mcp_tool.py`
- Called from `_rebuild_sandbox_mcp` in `session_manager.py` (after rebuild completes)

### 3. Frontend Changes

**`MCPServerForm.tsx`:**
- Remove `sandbox` from the transport type options array
- Remove sandbox-specific form fields (command, env_keys)

**`MCPServerCard.tsx`:**
- Sandbox transport servers: display as read-only cards (show name, transport badge, but no edit/delete buttons)
- Or hide sandbox servers from the list entirely (LLM manages them)

### 4. No Changes Required

- **5 meta-tools** (`sandbox_mcp_list/call/add/update/remove`): keep as-is
- **MongoDB persistence**: `_persist_server_to_mongodb` / `_delete_server_from_mongodb` already work
- **`_rebuild_sandbox_mcp`**: already restores servers from MongoDB on sandbox creation
- **`MCPClientManager`**: no changes, continues to handle SSE/HTTP transports only

## Files Changed

| File | Change |
|------|--------|
| `src/agents/search_agent/prompt.py` | Move dynamic placeholder to end of prompt |
| `src/agents/search_agent/nodes.py` | Call `build_sandbox_mcp_prompt` after sandbox ready |
| `src/infra/tool/sandbox_mcp_prompt.py` | **New**: `build_sandbox_mcp_prompt`, cache logic, invalidation |
| `src/infra/tool/sandbox_mcp_tool.py` | Call `invalidate_sandbox_mcp_prompt_cache` on add/update/remove |
| `src/infra/sandbox/session_manager.py` | Call invalidation after `_rebuild_sandbox_mcp` |
| `frontend/src/components/mcp/MCPServerForm.tsx` | Remove sandbox transport option |
| `frontend/src/components/mcp/MCPServerCard.tsx` | Sandbox servers read-only or hidden |

## Edge Cases

- **mcporter not available in sandbox**: `mcporter list` fails → return empty string, no prompt injection
- **No MCP servers registered**: return empty string
- **mcporter output unparseable**: log warning, return empty string
- **Sandbox paused and resumed**: cache may be stale → TTL (30 min) handles eventual consistency
- **Multiple concurrent requests for same user**: cache dict is not thread-safe, but Python GIL makes single-key read/write atomic enough; worst case is a redundant mcporter list call
