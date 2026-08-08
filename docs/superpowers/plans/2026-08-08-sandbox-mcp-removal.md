# Sandbox MCP Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Sandbox MCP and every `mcporter` integration while preserving ordinary sandbox tools and safely ignoring legacy Sandbox MCP database records.

**Architecture:** Delete the model/runtime feature path, narrow MCP schemas and UI to SSE and Streamable HTTP, and add a storage compatibility boundary that recognizes legacy `transport="sandbox"` documents without returning or mutating them. Raw name-reservation checks keep hidden legacy records from causing duplicate-key failures or implicit conversion.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Motor/MongoDB, pytest, React 19, TypeScript, Vitest, TailwindCSS.

---

### Task 1: Lock the supported MCP transport contract

**Files:**
- Modify: `tests/api/test_mcp_routes.py`
- Modify: `tests/infra/test_mcp_storage_limits.py`
- Modify: `tests/test_mcp_role_access.py`
- Modify: `src/kernel/schemas/mcp.py`
- Modify: `src/infra/mcp/storage.py`
- Modify: `src/infra/mcp/storage_operations.py`
- Modify: `src/api/routes/mcp.py`
- Modify: `src/infra/tool/internal_registry.py`
- Modify: `tests/infra/tool/test_internal_registry_exposure.py`

- [ ] **Step 1: Write failing schema and legacy-storage tests**

Add tests proving:

```python
def test_mcp_schema_rejects_sandbox_transport() -> None:
    with pytest.raises(ValidationError):
        MCPServerCreate.model_validate({"name": "legacy", "transport": "sandbox"})
```

Add `test_import_mcp_servers_reports_sandbox_error_and_imports_http_entry`: submit one `sandbox` entry and one authorized HTTP entry through `/api/mcp/import`; assert HTTP 200, `imported_count == 1`, and the invalid Sandbox entry appears in `errors` instead of causing a request-wide 403.

Add `test_admin_toggle_tool_returns_not_found_for_hidden_legacy_server`: make `get_system_server()` return `None`, call the admin tool-toggle route, and assert HTTP 404 without calling `set_system_tool_disabled()`.

Add fake-collection coverage for these retained behaviors:

- list, direct lookup, effective config, visible list, and export omit legacy documents;
- `can_access_server`, update, toggle, policy/tool-toggle, promote/demote, and delete treat them as not found and never call a write method;
- a raw same-name check still reports the legacy document as reserved;
- import skips a same-name legacy record even when overwrite is requested and reports invalid Sandbox transport entries through the existing errors list.

- [ ] **Step 2: Run the focused backend tests and verify RED**

Run:

```bash
uv run pytest tests/api/test_mcp_routes.py tests/infra/test_mcp_storage_limits.py tests/test_mcp_role_access.py -q
```

Expected: failures showing `sandbox` is still a valid enum value and legacy records are still returned or mutated.

- [ ] **Step 3: Narrow schemas and add the legacy-record boundary**

In `src/kernel/schemas/mcp.py`, leave only:

```python
class MCPTransport(str, Enum):
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"
```

Remove `command` and `env_keys` from MCP server create/update/response models.

In storage, centralize the compatibility check:

```python
def _is_legacy_sandbox_server(doc: Mapping[str, Any] | None) -> bool:
    return bool(doc) and doc.get("transport") == "sandbox"
```

Apply it before converting any database document to a Pydantic model or mutating it. Iteration-based reads `continue`; direct reads and mutations return `None`/`False` according to their existing signatures.

Add raw name-reservation methods that do not expose the record:

```python
async def system_server_name_exists(self, name: str) -> bool:
    return await self._get_system_collection().find_one({"name": name}, {"_id": 1}) is not None

async def user_server_name_exists(self, name: str, user_id: str) -> bool:
    query = {"name": name, "user_id": user_id}
    return await self._get_user_collection().find_one(query, {"_id": 1}) is not None
```

Use these checks in create routes, imports, and promote/demote destination-conflict checks. A reserved legacy name returns the existing conflict/skip/not-found result; overwrite and server moves never convert it or reach a duplicate-key insert. Remove all `command`/`env_keys` copying from create, update, import, export, promote, demote, and response construction.

In the import route permission preflight, permission-check only recognized transports. Let unknown/removed transports reach `MCPStorage.import_servers`, which records per-entry invalid-transport errors and continues processing valid entries.

Update `build_internal_server_response()` to use `MCPTransport.STREAMABLE_HTTP` in this task so every caller remains valid immediately after removing the enum member. In the admin tool-toggle endpoint, check `get_system_server()` before mutation and return the existing 404 contract for missing or hidden legacy records.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the transport/storage contract**

```bash
git add src/kernel/schemas/mcp.py src/infra/mcp/storage.py src/infra/mcp/storage_operations.py src/api/routes/mcp.py src/infra/tool/internal_registry.py tests/api/test_mcp_routes.py tests/infra/test_mcp_storage_limits.py tests/test_mcp_role_access.py tests/infra/tool/test_internal_registry_exposure.py
git commit -m "refactor: remove sandbox mcp transport"
```

### Task 2: Remove model tools and runtime `mcporter` paths

**Files:**
- Modify: `tests/api/test_agent_catalog_config.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`
- Modify: `tests/infra/test_session_sandbox_manager.py`
- Modify: `tests/infra/envvar/test_sync.py`
- Modify: `tests/infra/tool/test_env_var_tool.py`
- Modify: `tests/infra/tool/test_cache_pubsub.py`
- Delete: `tests/infra/tool/test_sandbox_mcp_tool.py`
- Delete: `tests/infra/tool/test_sandbox_mcp_rebuild.py`
- Delete: `tests/test_sandbox_mcp_prompt_guidance.py`
- Modify: `src/agents/core/prompt_policy.py`
- Modify: `src/agents/core/tool_filter.py`
- Modify: `src/agents/fast_agent/context.py`
- Modify: `src/agents/search_agent/context.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/api/routes/agent/__init__.py`
- Modify: `src/infra/agent/middleware/__init__.py`
- Modify: `src/infra/agent/middleware/prompt_caching.py`
- Modify: `src/infra/agent/middleware/prompt_injection.py`
- Modify: `src/infra/agent/middleware/tool_interception.py`
- Modify: `src/infra/envvar/sync.py`
- Modify: `src/infra/sandbox/_cubesandbox_helpers.py`
- Modify: `src/infra/sandbox/_daytona_helpers.py`
- Modify: `src/infra/sandbox/_e2b_helpers.py`
- Modify: `src/infra/sandbox/session_manager.py`
- Modify: `src/infra/tool/cache_pubsub.py`
- Modify: `src/infra/tool/deferred_manager.py`
- Modify: `src/infra/tool/env_var_tool.py`
- Modify: `src/infra/tool/tool_search_tool.py`
- Modify: `src/infra/mcp/storage_operations.py`
- Modify: `scripts/create_e2b_template.py`
- Modify: `scripts/create_daytona_snapshot.py`
- Modify: `tests/scripts/test_create_e2b_template.py`
- Modify: `src/kernel/config/_definitions_sandbox.py`
- Modify: `src/kernel/config/base.py`
- Delete: `src/infra/tool/sandbox_mcp_tool.py`
- Delete: `src/infra/tool/sandbox_mcp_prompt.py`
- Delete: `src/infra/tool/sandbox_mcp_rebuild.py`
- Delete: `src/infra/tool/sandbox_mcp_utils.py`

- [ ] **Step 1: Add failing boundary/source tests**

Add assertions that the built-in catalog and agent context sources contain no `sandbox_mcp_` tools, sandbox session startup contains no MCP rebuild hook, and prompt/tool guidance contains no `mcporter` instructions. Retain assertions for ordinary sandbox tools such as `read_file`, `write_file`, and `execute`.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
uv run pytest tests/api/test_agent_catalog_config.py tests/agents/core/test_subagent_prompts.py tests/infra/test_session_sandbox_manager.py tests/infra/envvar/test_sync.py tests/infra/tool/test_env_var_tool.py tests/infra/tool/test_cache_pubsub.py -q
```

Expected: new absence assertions fail while Sandbox MCP is still registered.

- [ ] **Step 3: Remove all runtime registrations and dedicated modules**

Remove:

- all `get_sandbox_mcp_tools()` context registration;
- `SandboxMCPMiddleware` and prompt-cache integration;
- `MCPQuotaMiddleware`'s `execute`/`mcporter` parsing path if it has no remaining non-Sandbox use;
- all `ensure_sandbox_mcp()` calls and wrappers from sandbox lifecycle helpers;
- env-var-triggered rebuild behavior while retaining env-var CRUD;
- Sandbox MCP cache pub/sub handling;
- built-in catalog entries and prompt/deferred-search guidance;
- the four dedicated Sandbox MCP source modules and their implementation-only tests;
- the obsolete `MCPStorage.get_sandbox_servers()` operation;
- the `mcporter` install and home-directory setup from E2B/Daytona templates;
- `SANDBOX_MCP_REBUILD_CONCURRENCY` from runtime settings and definitions.

In `scripts/create_e2b_template.py`, preserve the independently useful `@jackwener/opencli` installation and every unrelated user hunk. Change only the combined install command so it no longer installs `mcporter`, remove only the `.mcporter` setup command, and update only the matching assertions in `tests/scripts/test_create_e2b_template.py`.

Do not remove generic sandbox creation, execution, filesystem, upload, artifact, or reveal behavior.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

Also run:

```bash
uv run pytest tests/scripts/test_create_e2b_template.py -q
```

- [ ] **Step 5: Prove no runtime feature references remain**

```bash
rg -n "sandbox_mcp|SandboxMCP|mcporter" src tests --glob '!tests/fixtures/**'
```

Expected: no current runtime/test references. Review any remaining historical comments individually.

- [ ] **Step 6: Commit runtime removal**

```bash
git add -- src/agents/core/prompt_policy.py src/agents/core/tool_filter.py src/agents/fast_agent/context.py src/agents/search_agent/context.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py src/api/routes/agent/__init__.py src/infra/agent/middleware/__init__.py src/infra/agent/middleware/prompt_caching.py src/infra/agent/middleware/prompt_injection.py src/infra/agent/middleware/tool_interception.py src/infra/envvar/sync.py src/infra/mcp/storage_operations.py src/infra/sandbox/_cubesandbox_helpers.py src/infra/sandbox/_daytona_helpers.py src/infra/sandbox/_e2b_helpers.py src/infra/sandbox/session_manager.py src/infra/tool/cache_pubsub.py src/infra/tool/deferred_manager.py src/infra/tool/env_var_tool.py src/infra/tool/tool_search_tool.py src/infra/tool/sandbox_mcp_tool.py src/infra/tool/sandbox_mcp_prompt.py src/infra/tool/sandbox_mcp_rebuild.py src/infra/tool/sandbox_mcp_utils.py src/kernel/config/_definitions_sandbox.py src/kernel/config/base.py tests/api/test_agent_catalog_config.py tests/agents/core/test_subagent_prompts.py tests/infra/test_session_sandbox_manager.py tests/infra/envvar/test_sync.py tests/infra/tool/test_env_var_tool.py tests/infra/tool/test_cache_pubsub.py tests/infra/tool/test_sandbox_mcp_tool.py tests/infra/tool/test_sandbox_mcp_rebuild.py tests/test_sandbox_mcp_prompt_guidance.py scripts/create_daytona_snapshot.py
git add -p -- scripts/create_e2b_template.py tests/scripts/test_create_e2b_template.py
git diff --cached --check
git commit -m "refactor: remove sandbox mcp runtime"
```

### Task 3: Remove Sandbox MCP permissions and internal-server coupling

**Files:**
- Modify: `src/kernel/types.py`
- Modify: `src/kernel/schemas/permission.py`
- Modify: `tests/api/test_role_routes.py`

- [ ] **Step 1: Write failing permission and internal-registry tests**

Assert that permission metadata/groups do not expose `mcp:write_sandbox`. The internal registry transport assertion already belongs to Task 1, where the enum is narrowed.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest tests/api/test_role_routes.py -q
```

- [ ] **Step 3: Remove the permission and decouple the internal registry**

Delete `MCP_WRITE_SANDBOX` from the Python enum and permission metadata/groups. Leave the TypeScript enum until Task 4 removes all of its frontend consumers in the same buildable change.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: both test modules pass.

- [ ] **Step 5: Commit permission cleanup**

```bash
git add -- src/kernel/types.py src/kernel/schemas/permission.py tests/api/test_role_routes.py
git commit -m "refactor: drop sandbox mcp permission"
```

### Task 4: Remove the frontend transport and dedicated tool renderer

**Files:**
- Modify: `frontend/src/types/mcp.ts`
- Modify: `frontend/src/types/auth.ts`
- Modify: `frontend/src/components/mcp/MCPServerForm.tsx`
- Modify: `frontend/src/components/mcp/MCPServerCard.tsx`
- Modify: `frontend/src/components/mcp/MCPServerToolsSidebar.tsx`
- Modify: `frontend/src/components/panels/MCPPanel.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/MessagePartRenderer.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/ToolCallItem.tsx`
- Delete: `frontend/src/components/chat/ChatMessage/items/SandboxMcpItem.tsx`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/dedicatedInlineToolItemsSource.test.ts`
- Modify: `frontend/src/components/chat/ChatMessage/items/__tests__/themedToolItemsSource.test.ts`
- Create: `frontend/src/components/mcp/__tests__/sandboxMcpRemovalSource.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/zh.json`

- [ ] **Step 1: Write a failing frontend source contract**

The source test should assert:

```ts
expect(mcpTypeSource).not.toContain('"sandbox"');
expect(formSource).not.toContain('value: "sandbox"');
expect(rendererSource).not.toContain("SandboxMcpItem");
expect(panelSource).not.toContain("MCP_WRITE_SANDBOX");
```

Also retain positive assertions for `sse` and `streamable_http`.

- [ ] **Step 2: Run the test and verify RED**

```bash
cd frontend && pnpm test -- src/components/mcp/__tests__/sandboxMcpRemovalSource.test.ts
```

Expected: assertions fail against current sources.

- [ ] **Step 3: Remove the frontend feature surface**

Narrow `MCPTransport` to `"sse" | "streamable_http"` and remove `MCP_WRITE_SANDBOX` from the frontend permission enum in the same change that removes all consumers. Remove command/env-key fields from frontend MCP types and form state/payload/validation/UI. Remove Sandbox labels/icons, permissions, panel fallbacks, dedicated message rendering, component file, and locale keys that are no longer referenced.

Remove the `SandboxMcpItem` re-export from `ToolCallItem.tsx` and remove the deleted component from `themedToolItemsSource.test.ts` fixtures/assertions.

- [ ] **Step 4: Run frontend tests and verify GREEN**

```bash
cd frontend && pnpm test -- src/components/mcp/__tests__/sandboxMcpRemovalSource.test.ts src/components/chat/ChatMessage/items/__tests__/dedicatedInlineToolItemsSource.test.ts
cd frontend && pnpm test -- src/components/chat/ChatMessage/items/__tests__/themedToolItemsSource.test.ts
```

Expected: both test files pass.

- [ ] **Step 5: Commit frontend removal**

```bash
git add frontend/src
git commit -m "refactor: remove sandbox mcp ui"
```

### Task 5: Remove obsolete documentation and verify the whole change

**Files:**
- Delete: `docs/superpowers/plans/2026-03-30-sandbox-mcp-prompt-injection.md`
- Delete: `docs/superpowers/plans/mcporter.md`
- Delete: `docs/superpowers/specs/2026-03-30-sandbox-mcp-prompt-injection-design.md`
- Modify: `docs/superpowers/plans/2026-08-08-prompt-discovery-compression.md`
- Modify: `docs/superpowers/plans/2026-08-08-system-prompt-compression.md` (preserve unrelated content)
- Modify: `docs/superpowers/specs/2026-08-08-prompt-discovery-compression-design.md`
- Modify: `docs/superpowers/specs/2026-08-08-system-prompt-compression-design.md`
- Keep: `docs/superpowers/specs/2026-08-08-sandbox-mcp-removal-design.md`
- Keep: `docs/superpowers/plans/2026-08-08-sandbox-mcp-removal.md`

- [ ] **Step 1: Delete dedicated obsolete documents and clean mixed current docs**

Remove only Sandbox MCP/`mcporter` sections from tracked mixed prompt-discovery and system-prompt-compression documents. The system-prompt implementation plan is now tracked; clean only its Sandbox-specific sections and preserve every unrelated section. Keep this removal spec and plan as the decision record.

- [ ] **Step 2: Check for unexpected residual references**

```bash
rg -ni "sandbox_mcp|mcporter|mcp:write_sandbox|transportSandbox|SANDBOX_MCP_REBUILD_CONCURRENCY" src tests frontend scripts docs \
  --glob '!docs/superpowers/specs/2026-08-08-sandbox-mcp-removal-design.md' \
  --glob '!docs/superpowers/plans/2026-08-08-sandbox-mcp-removal.md'
```

Expected: no references, except any explicitly justified immutable historical record.

- [ ] **Step 3: Run backend regression checks**

```bash
uv run pytest tests/api/test_mcp_routes.py tests/api/test_agent_catalog_config.py tests/api/test_role_routes.py tests/agents/core/test_subagent_prompts.py tests/infra/test_mcp_storage_limits.py tests/test_mcp_role_access.py tests/infra/test_session_sandbox_manager.py tests/infra/envvar/test_sync.py tests/infra/tool/test_env_var_tool.py tests/infra/tool/test_cache_pubsub.py -q
uv run ruff check src/agents src/api/routes/agent src/api/routes/mcp.py src/infra src/kernel tests
```

Expected: tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 4: Run frontend regression checks**

```bash
cd frontend && pnpm test
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: Vitest, ESLint, TypeScript, and Vite build all succeed.

- [ ] **Step 5: Confirm unrelated work is untouched**

```bash
git status --short
git diff -- scripts/create_e2b_template.py tests/scripts/test_create_e2b_template.py
```

Expected: only the `mcporter` install/setup lines and their exact test assertions differ from the pre-task E2B changes; every unrelated hunk remains intact. Compare against the pre-task diff or commit and stage these files by explicit path, never with a broad `git add scripts tests`.

- [ ] **Step 6: Commit documentation cleanup**

```bash
git add -- docs/superpowers/plans/2026-03-30-sandbox-mcp-prompt-injection.md docs/superpowers/plans/mcporter.md docs/superpowers/plans/2026-08-08-prompt-discovery-compression.md docs/superpowers/plans/2026-08-08-system-prompt-compression.md docs/superpowers/specs/2026-03-30-sandbox-mcp-prompt-injection-design.md docs/superpowers/specs/2026-08-08-prompt-discovery-compression-design.md docs/superpowers/specs/2026-08-08-system-prompt-compression-design.md docs/superpowers/plans/2026-08-08-sandbox-mcp-removal.md
git diff --cached --name-only
git commit -m "docs: retire sandbox mcp guidance"
```
