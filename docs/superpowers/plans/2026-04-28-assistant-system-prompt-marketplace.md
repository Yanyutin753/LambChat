# Assistant System Prompt Marketplace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class assistant marketplace and personal assistant library where each assistant stores a `system_prompt`, can be selected for a chat session, and injects a session-stable prompt snapshot into the agent runtime.

**Architecture:** Introduce a dedicated assistant domain on the backend with storage, manager, and REST routes. Persist assistant selection in session metadata as both `assistant_id` and `assistant_prompt_snapshot`, then inject that snapshot into the existing prompt middleware chain before skills and memory. Add a lightweight frontend assistant page plus a chat header selector that reuses current session config and panel patterns.

**Tech Stack:** FastAPI, MongoDB/Motor, Pydantic, existing session/chat APIs, React, TypeScript, existing panel/hook architecture, pytest, Node `node:test`.

---

## File Structure

- Create: `src/infra/assistant/__init__.py`
  Re-export assistant storage/manager helpers.
- Create: `src/infra/assistant/types.py`
  Backend Pydantic models for assistant create/update/list/select payloads and response objects.
- Create: `src/infra/assistant/storage.py`
  MongoDB persistence, indexes, ownership-aware CRUD, list/filter helpers, clone helper.
- Create: `src/infra/assistant/manager.py`
  Marketplace visibility rules, clone semantics, session snapshot preparation, runtime lookup helper.
- Create: `src/api/routes/assistant.py`
  Authenticated CRUD/list/select/clone routes for assistants.
- Create: `tests/infra/assistant/test_storage.py`
  Unit tests for assistant storage behavior and clone semantics.
- Create: `tests/infra/assistant/test_manager.py`
  Unit tests for prompt snapshot resolution and visibility rules.
- Create: `tests/api/routes/test_assistant_routes.py`
  Route-level tests with fakes for list/create/select/clone permission and ownership flows.
- Modify: `src/api/main.py`
  Mount assistant routes and initialize assistant indexes on startup.
- Modify: `src/kernel/schemas/agent.py`
  Add optional `assistant_id` to chat requests.
- Modify: `src/api/routes/chat.py`
  Accept `assistant_id`, persist assistant snapshot into session metadata during submit.
- Modify: `frontend/src/hooks/useAgent/types.ts`
  Extend restored session config shape with assistant metadata.
- Modify: `src/agents/search_agent/nodes.py`
  Append assistant prompt section before skills and memory.
- Modify: `src/agents/fast_agent/nodes.py`
  Mirror assistant prompt injection if fast agent shares the same middleware chain.
- Create: `tests/agents/search_agent/test_assistant_prompt_injection.py`
  Focused tests for prompt section ordering and snapshot precedence.
- Modify: `src/kernel/schemas/session.py`
  No schema shape change is required, but update typing/comments if helpful when exposing assistant metadata.
- Modify: `frontend/src/types/index.ts`
  Re-export assistant types.
- Create: `frontend/src/types/assistant.ts`
  Frontend assistant list/detail/request types.
- Create: `frontend/src/services/api/assistant.ts`
  REST client for assistant APIs.
- Create: `frontend/src/services/api/assistant.test.ts`
  Small URL/build contract tests for assistant API helper functions.
- Create: `frontend/src/hooks/useAssistants.ts`
  Fetch/search/filter/create/update/delete/clone/select hook.
- Create: `frontend/src/components/assistant/AssistantSelector.tsx`
  Chat header selector for the current session assistant.
- Create: `frontend/src/components/panels/AssistantsPanel.tsx`
  Public + personal assistant browser/editor panel.
- Modify: `frontend/src/components/layout/AppContent/Header.tsx`
  Render the assistant selector next to the model selector in chat view.
- Modify: `frontend/src/components/layout/AppContent/TabContent.tsx`
  Register the assistants panel.
- Modify: `frontend/src/components/layout/AppContent/types.ts`
  Add `assistants` tab.
- Modify: `frontend/src/components/layout/UserMenu.tsx`
  Add navigation entry for assistants.
- Modify: `frontend/src/App.tsx`
  Register `/assistants` page route.
- Modify: `frontend/src/hooks/useSessionConfig.ts`
  Track current `assistantId`, `assistantName`, and restore them from session metadata.
- Modify: `frontend/src/components/layout/AppContent/sessionState.ts`
  Add helper coverage for restored assistant metadata if needed.
- Modify: `frontend/src/components/layout/AppContent/index.tsx`
  Wire selected assistant into chat submit flow and restore it when loading a session.
- Modify: `frontend/src/services/api/session.ts`
  Send `assistant_id` with chat submissions if selected.
- Modify: `frontend/src/types/session.ts`
  Narrow metadata typing if needed for assistant fields in frontend consumers.
- Modify: `frontend/src/types/auth.ts`
  Add assistant permissions if this implementation chooses explicit assistant permission enums.
- Modify: `src/kernel/types.py`
  Add matching backend assistant permissions if explicit permissions are added.
- Modify: `src/kernel/schemas/permission.py`
  Register new permission metadata and group placement if explicit assistant permissions are added.

## Implementation Choice Lock-Ins

- Use a dedicated `/assistants` route and frontend page, not the existing skill marketplace route.
- Keep assistants phase-1-only: `system_prompt` plus display metadata.
- Store `assistant_prompt_snapshot` in `session.metadata` and prefer it over live assistant lookup.
- Allow direct use of public assistants without cloning.
- Allow cloning a public assistant into a private assistant record with `cloned_from_assistant_id`.
- Use one `assistants` collection with `scope = "public" | "private"`.
- Prefer explicit assistant permissions if the team is comfortable updating role metadata now; otherwise fall back to authenticated-user access for private CRUD and admin-only checks for public writes. Make this decision once before implementation starts and apply it consistently across backend and frontend.

### Task 1: Assistant Domain Tests and Models

**Files:**
- Create: `src/infra/assistant/types.py`
- Create: `tests/infra/assistant/test_storage.py`
- Create: `tests/infra/assistant/test_manager.py`

- [ ] **Step 1: Write the failing backend domain tests**

Create tests that cover:

- `AssistantCreate` defaults `scope="private"` and `version="1.0.0"`.
- storage list helpers separate public assistants from a user's private assistants.
- cloning copies `name`, `description`, `system_prompt`, and `tags` while setting `cloned_from_assistant_id`.
- manager runtime resolution prefers `assistant_prompt_snapshot` over re-reading the source assistant.
- manager runtime resolution snapshots the live `system_prompt` when only `assistant_id` is present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/infra/assistant/test_storage.py tests/infra/assistant/test_manager.py -q`

Expected: FAIL because the assistant domain modules do not exist yet.

- [ ] **Step 3: Add minimal assistant schema module**

Define backend models similar to:

```python
class AssistantScope(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class AssistantRecord(BaseModel):
    assistant_id: str
    name: str
    description: str = ""
    system_prompt: str
    scope: AssistantScope
    created_by: str | None = None
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    avatar_url: str | None = None
    cloned_from_assistant_id: str | None = None
    version: str = "1.0.0"
    bound_skill_names: list[str] = Field(default_factory=list)
    default_model: str | None = None
    default_agent_options: dict[str, Any] = Field(default_factory=dict)
    default_disabled_tools: list[str] = Field(default_factory=list)
    default_disabled_skills: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

Also add request/response models:

- `AssistantCreate`
- `AssistantUpdate`
- `AssistantResponse`
- `AssistantSelectRequest`

- [ ] **Step 4: Add minimal manager contracts to satisfy test imports**

Define signatures only:

```python
class AssistantManager:
    async def resolve_session_prompt_snapshot(...): ...
    async def clone_public_assistant(...): ...
```

- [ ] **Step 5: Run tests again**

Run: `pytest tests/infra/assistant/test_storage.py tests/infra/assistant/test_manager.py -q`

Expected: still FAIL, now on missing storage and manager behavior instead of missing imports.

- [ ] **Step 6: Commit**

```bash
git add src/infra/assistant/types.py tests/infra/assistant/test_storage.py tests/infra/assistant/test_manager.py
git commit -m "test: scaffold assistant domain coverage"
```

### Task 2: Assistant Storage, Manager, and Startup Wiring

**Files:**
- Create: `src/infra/assistant/__init__.py`
- Create: `src/infra/assistant/storage.py`
- Create: `src/infra/assistant/manager.py`
- Modify: `src/api/main.py`
- Test: `tests/infra/assistant/test_storage.py`
- Test: `tests/infra/assistant/test_manager.py`

- [ ] **Step 1: Implement assistant storage**

Add:

- `ensure_indexes()`
- `create_assistant()`
- `get_assistant()`
- `list_public_assistants()`
- `list_user_assistants()`
- `update_assistant()`
- `delete_assistant()`
- `clone_assistant()`

Use `assistant_id` as the stable external key and store reserved future fields even if empty.

- [ ] **Step 2: Implement assistant manager**

Add logic for:

- public visibility filtering
- ownership checks
- cloning from public assistants only
- session snapshot preparation
- runtime assistant lookup

Minimal runtime helper:

```python
async def resolve_session_prompt_snapshot(
    self,
    session_metadata: Mapping[str, Any],
    assistant_id: str | None,
) -> tuple[str | None, dict[str, Any]]:
    ...
```

Return the resolved prompt plus any session metadata fields that should be written back.

- [ ] **Step 3: Initialize indexes at app startup**

In `src/api/main.py`, create the assistant storage instance and call `ensure_indexes()` during lifespan, near the existing skill/revealed-file index initialization.

- [ ] **Step 4: Run backend domain tests**

Run: `pytest tests/infra/assistant/test_storage.py tests/infra/assistant/test_manager.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/infra/assistant/__init__.py src/infra/assistant/storage.py src/infra/assistant/manager.py src/api/main.py
git commit -m "feat: add assistant storage and manager"
```

### Task 3: Assistant API and Permission Surface

**Files:**
- Create: `src/api/routes/assistant.py`
- Modify: `src/kernel/types.py`
- Modify: `src/kernel/schemas/permission.py`
- Modify: `frontend/src/types/auth.ts`
- Test: `tests/api/routes/test_assistant_routes.py`

- [ ] **Step 1: Write the failing assistant route tests**

Add tests for:

- listing public assistants hides inactive public records from ordinary users
- listing `scope=mine` returns only private assistants owned by the current user
- selecting an assistant writes `assistant_id`, `assistant_name`, and `assistant_prompt_snapshot`
- cloning a public assistant creates a private copy for the current user
- editing/deleting another user's private assistant returns 403

- [ ] **Step 2: Run route tests to verify they fail**

Run: `pytest tests/api/routes/test_assistant_routes.py -q`

Expected: FAIL because the assistant route module does not exist.

- [ ] **Step 3: Decide and implement permission strategy**

Choose one:

- explicit assistant permissions:
  - `assistant:read`
  - `assistant:write`
  - `assistant:marketplace_admin`
- or authenticated-user + admin checks only

If using explicit permissions, add them to:

- `src/kernel/types.py`
- `src/kernel/schemas/permission.py`
- `frontend/src/types/auth.ts`

If using the lighter strategy, skip enum churn and make the route use `get_current_user_required` plus manager ownership checks.

- [ ] **Step 4: Implement assistant routes**

Add endpoints:

- `GET /api/assistants`
- `GET /api/assistants/{assistant_id}`
- `POST /api/assistants`
- `PATCH /api/assistants/{assistant_id}`
- `DELETE /api/assistants/{assistant_id}`
- `POST /api/assistants/{assistant_id}/clone`
- `POST /api/assistants/{assistant_id}/select`

Mount the router in `src/api/main.py`.

- [ ] **Step 5: Run route tests**

Run: `pytest tests/api/routes/test_assistant_routes.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/assistant.py src/kernel/types.py src/kernel/schemas/permission.py frontend/src/types/auth.ts tests/api/routes/test_assistant_routes.py src/api/main.py
git commit -m "feat: add assistant marketplace api"
```

### Task 4: Session Snapshot Plumbing Through Chat and Session Restore

**Files:**
- Modify: `src/kernel/schemas/agent.py`
- Modify: `src/api/routes/chat.py`
- Modify: `frontend/src/hooks/useAgent/types.ts`
- Modify: `frontend/src/services/api/session.ts`
- Modify: `frontend/src/hooks/useSessionConfig.ts`
- Modify: `frontend/src/components/layout/AppContent/index.tsx`
- Modify: `frontend/src/components/layout/AppContent/sessionState.ts`
- Test: `frontend/src/services/api/assistant.test.ts`
- Test: `frontend/src/components/layout/AppContent/sessionState.test.ts`

- [ ] **Step 1: Write the failing frontend contract tests**

Add tests that assert:

- assistant list/detail/select URLs are built correctly in `assistantApi`
- restored session config can safely extract `assistant_id` and `assistant_name`
- chat submit includes `assistant_id` when present

- [ ] **Step 2: Run the focused frontend tests**

Run: `node --test frontend/src/services/api/assistant.test.ts frontend/src/components/layout/AppContent/sessionState.test.ts`

Expected: FAIL because assistant API helpers and session restore helpers do not exist yet.

- [ ] **Step 3: Extend backend request/restore typing**

Update `src/kernel/schemas/agent.py`:

```python
assistant_id: Optional[str] = Field(
    None,
    description="Assistant ID to snapshot into the session for this conversation",
)
```

Update `frontend/src/hooks/useAgent/types.ts` session config typing:

```ts
assistant_id?: string;
assistant_name?: string;
assistant_prompt_snapshot?: string;
```

- [ ] **Step 4: Persist assistant selection during chat submit**

In `src/api/routes/chat.py`:

- accept `assistant_id`
- resolve and snapshot the assistant before updating the session config
- write:
  - `assistant_id`
  - `assistant_name`
  - `assistant_prompt_snapshot`

In `frontend/src/services/api/session.ts`:

- extend `submitChat(...)` to accept `assistantId`
- include `assistant_id` in the request body

In `frontend/src/hooks/useSessionConfig.ts` and `frontend/src/components/layout/AppContent/index.tsx`:

- track selected assistant state
- restore it from loaded session metadata
- pass it into chat submit calls

- [ ] **Step 5: Add helper for restored assistant metadata**

In `frontend/src/components/layout/AppContent/sessionState.ts`, add a small extractor similar to `getRestoredModelSelection()`:

```ts
export function getRestoredAssistantSelection(config: SessionConfig) {
  return {
    assistantId:
      typeof config.assistant_id === "string" ? config.assistant_id : "",
    assistantName:
      typeof config.assistant_name === "string" ? config.assistant_name : "",
  };
}
```

- [ ] **Step 6: Run frontend tests again**

Run: `node --test frontend/src/services/api/assistant.test.ts frontend/src/components/layout/AppContent/sessionState.test.ts`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/kernel/schemas/agent.py src/api/routes/chat.py frontend/src/services/api/session.ts frontend/src/hooks/useAgent/types.ts frontend/src/hooks/useSessionConfig.ts frontend/src/components/layout/AppContent/index.tsx frontend/src/components/layout/AppContent/sessionState.ts frontend/src/services/api/assistant.test.ts frontend/src/components/layout/AppContent/sessionState.test.ts
git commit -m "feat: persist assistant snapshots in chat sessions"
```

### Task 5: Assistant Prompt Injection in Search and Fast Agents

**Files:**
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Test: `tests/agents/search_agent/test_assistant_prompt_injection.py`

- [ ] **Step 1: Write the failing prompt injection tests**

Test:

- assistant prompt section is added when `assistant_prompt_snapshot` exists in session metadata or request config
- assistant prompt appears before skills and memory in `_prompt_sections`
- no assistant section is injected when no assistant is selected

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/search_agent/test_assistant_prompt_injection.py -q`

Expected: FAIL because no assistant prompt section exists yet.

- [ ] **Step 3: Implement assistant prompt resolution in agent nodes**

Add a helper inside each node flow, or a shared helper if that stays focused:

```python
assistant_prompt = configurable.get("assistant_prompt", "")
if not assistant_prompt:
    metadata = await _load_session_metadata(...)
    assistant_prompt = metadata.get("assistant_prompt_snapshot", "")
```

Then build prompt sections in this order:

```python
_prompt_sections = [
    s for s in (assistant_prompt, skills_prompt, memory_guide) if s
]
```

Do not place the assistant prompt after memory or after prompt caching.

- [ ] **Step 4: Run prompt injection tests**

Run: `pytest tests/agents/search_agent/test_assistant_prompt_injection.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/search_agent/nodes.py src/agents/fast_agent/nodes.py tests/agents/search_agent/test_assistant_prompt_injection.py
git commit -m "feat: inject assistant system prompts into agent runtime"
```

### Task 6: Frontend Assistant Types, API, and Hook

**Files:**
- Create: `frontend/src/types/assistant.ts`
- Create: `frontend/src/services/api/assistant.ts`
- Create: `frontend/src/hooks/useAssistants.ts`
- Modify: `frontend/src/types/index.ts`
- Test: `frontend/src/services/api/assistant.test.ts`

- [ ] **Step 1: Implement frontend assistant types**

Add:

- `AssistantScope`
- `AssistantSummary`
- `AssistantDetail`
- `AssistantCreateRequest`
- `AssistantUpdateRequest`
- `AssistantSelectRequest`

- [ ] **Step 2: Implement assistant API client**

Add helpers for:

- `list(params)`
- `get(assistantId)`
- `create(data)`
- `update(assistantId, data)`
- `delete(assistantId)`
- `clone(assistantId)`
- `select(assistantId, sessionId)`

Mirror the style used in `frontend/src/services/api/marketplace.ts`.

- [ ] **Step 3: Implement `useAssistants`**

Track:

- marketplace list
- personal list
- search query
- selected tags
- loading/error state
- create/update/delete/clone/select actions

Keep the hook narrow; avoid adding preview modal complexity in phase 1.

- [ ] **Step 4: Run assistant frontend tests**

Run: `node --test frontend/src/services/api/assistant.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/assistant.ts frontend/src/services/api/assistant.ts frontend/src/hooks/useAssistants.ts frontend/src/types/index.ts frontend/src/services/api/assistant.test.ts
git commit -m "feat: add frontend assistant data layer"
```

### Task 7: Assistants Panel and Chat Header Selector

**Files:**
- Create: `frontend/src/components/assistant/AssistantSelector.tsx`
- Create: `frontend/src/components/panels/AssistantsPanel.tsx`
- Modify: `frontend/src/components/layout/AppContent/Header.tsx`
- Modify: `frontend/src/components/layout/AppContent/TabContent.tsx`
- Modify: `frontend/src/components/layout/AppContent/types.ts`
- Modify: `frontend/src/components/layout/UserMenu.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppContent/index.tsx`

- [ ] **Step 1: Build a simple chat header selector**

Model it on the existing agent/model selector pattern:

- show current assistant name or a fallback like `"Default Assistant"`
- list public + personal assistants in one dropdown
- selecting an assistant updates local session config immediately

Do not block chat on a network round-trip; selection should be optimistic and the backend snapshot happens on submit or explicit select.

- [ ] **Step 2: Build the assistants panel**

Keep it phase-1 simple:

- tabs or segmented buttons for `Marketplace` and `My Assistants`
- search
- tag filters
- create/edit modal with:
  - name
  - description
  - tags
  - system prompt
- clone button on public assistants
- delete button on owned assistants

Reuse existing panel styling and form patterns from `MarketplacePanel` and `SkillsPanel`.

- [ ] **Step 3: Wire the new tab into app navigation**

Update:

- `frontend/src/components/layout/AppContent/types.ts`
- `frontend/src/components/layout/AppContent/TabContent.tsx`
- `frontend/src/components/layout/UserMenu.tsx`
- `frontend/src/App.tsx`

Recommended route: `/assistants`

- [ ] **Step 4: Ensure loaded sessions restore the selected assistant in chat**

In `frontend/src/components/layout/AppContent/index.tsx`:

- when `loadHistory()` returns session metadata with `assistant_id` and `assistant_name`, restore them into local state
- clear assistant selection on `onNewSession()` reset if you want new chats to start neutral by default, or keep the last local assistant selection if that matches current UX expectations; pick one behavior and document it in code comments

- [ ] **Step 5: Run targeted frontend verification**

Run: `node --test frontend/src/services/api/assistant.test.ts frontend/src/components/layout/AppContent/sessionState.test.ts frontend/src/components/layout/AppContent/useSessionSync.test.ts`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/assistant/AssistantSelector.tsx frontend/src/components/panels/AssistantsPanel.tsx frontend/src/components/layout/AppContent/Header.tsx frontend/src/components/layout/AppContent/TabContent.tsx frontend/src/components/layout/AppContent/types.ts frontend/src/components/layout/UserMenu.tsx frontend/src/App.tsx frontend/src/components/layout/AppContent/index.tsx
git commit -m "feat: add assistants panel and chat selector"
```

### Task 8: End-to-End Verification and Cleanup

**Files:**
- No intended source edits unless fixes are required.

- [ ] **Step 1: Run backend assistant test suite**

Run: `pytest tests/infra/assistant/test_storage.py tests/infra/assistant/test_manager.py tests/api/routes/test_assistant_routes.py tests/agents/search_agent/test_assistant_prompt_injection.py -q`

Expected: PASS

- [ ] **Step 2: Run existing related backend tests for regression coverage**

Run: `pytest tests/infra/backend/test_skills_store_backend.py tests/api/routes/test_session_runs.py tests/api/routes/test_session_favorites.py -q`

Expected: PASS

- [ ] **Step 3: Run targeted frontend tests**

Run: `node --test frontend/src/services/api/assistant.test.ts frontend/src/components/layout/AppContent/sessionState.test.ts frontend/src/components/layout/AppContent/useSessionSync.test.ts frontend/src/services/api/session.test.ts`

Expected: PASS

- [ ] **Step 4: Manual smoke-test checklist**

Verify in the browser:

- create a private assistant
- browse public assistants
- clone a public assistant
- select an assistant in chat
- send a message and confirm the session metadata stores assistant snapshot fields
- edit the public assistant and confirm an old session still uses the old snapshot

- [ ] **Step 5: Run final repo status check**

Run: `git status --short`

Expected: only intended assistant-related files changed.

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: add assistant system prompt marketplace"
```
