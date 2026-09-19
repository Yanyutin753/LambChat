# Agent Todo and Memory Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable structured Todo planning in user-facing Agents and improve memory guidance and scope-aware recall for reliable multi-step work.

**Architecture:** Centralize Todo middleware construction in `src/agents/core/todo_middleware.py`; each main Agent and executable subagent adds the same factory result, while the maintenance compaction Agent stays unchanged. Improve memory behavior inside the native search ranking and memory guide, preserving the existing MongoDB extraction, deduplication, project-scope enforcement, and compaction pipelines.

**Tech Stack:** Python 3.12, LangChain middleware, deepagents, FastAPI runtime, MongoDB native memory backend, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-agent-todos-memory-design.md`

## Global Constraints

- Preserve current `user`, `project`, and `reference` durable memory scope boundaries.
- Todo state is session/checkpoint state and must not be written to durable memory.
- Do not add Todo middleware to memory compaction or extraction workers.
- Keep five-locale UI unchanged because this feature has no new user-facing locale key.
- Run focused pytest, Ruff, mypy, and the local Agent/memory fixture before completion.

---

### Task 1: Central Todo middleware factory

**Files:**
- Create: `src/agents/core/todo_middleware.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Test: `tests/agents/test_todo_middleware_registration.py`

**Interfaces:**
- Produces `create_todo_middleware() -> TodoListMiddleware`.
- Main and executable subagent stacks append the returned middleware exactly once.

- [ ] **Step 1: Write failing registration and factory tests**

  Assert each Agent node imports and calls `create_todo_middleware`, assert the factory returns a `TodoListMiddleware` with `write_todos`, and assert a memory compaction stack does not import it.

- [ ] **Step 2: Run the focused tests and confirm they fail**

  Run `uv run pytest tests/agents/test_todo_middleware_registration.py -q`; expected failure is the missing factory/calls.

- [ ] **Step 3: Implement the factory and register it**

  Add the small factory and append it to each main `user_middleware` plus each `_build_subagent_middleware` result. Do not add it to `src/infra/memory/compaction_agent.py`.

- [ ] **Step 4: Run the focused tests and confirm they pass**

  Run `uv run pytest tests/agents/test_todo_middleware_registration.py -q`.

- [ ] **Step 5: Commit**

  `git add src/agents tests/agents/test_todo_middleware_registration.py && git commit -m "feat(agent): enable todo planning middleware"`

### Task 2: Improve memory guidance and scope-aware ranking

**Files:**
- Modify: `src/infra/memory/client/types.py`
- Modify: `src/infra/memory/client/native/search.py`
- Modify: `src/infra/agent/middleware/prompt_injection.py`
- Test: `tests/infra/memory/test_tools.py`
- Test: `tests/infra/memory/native/test_search.py`

**Interfaces:**
- `prioritize_sources(memories, project_id=...) -> list[dict]` remains deterministic and keeps scope isolation enforced by Mongo queries.
- `MemoryRecallIndexMiddleware` adds explicit current-project and current-session recall guidance without injecting raw durable memory into user messages.

- [ ] **Step 1: Write failing memory behavior tests**

  Add tests that project memories outrank generic user memories when both match, feedback beats stale generic context for correction queries, and the memory guide states that Todo/session state is not durable memory.

- [ ] **Step 2: Run the tests and confirm the expected failures**

  Run the selected test nodes with `uv run pytest ... -q` and verify the new assertions fail against the current ordering/guide.

- [ ] **Step 3: Implement deterministic ranking and guidance**

  Add a scope-aware ranking key with current project first, feedback second, user/reference afterward, then semantic score and recency. Keep the existing `build_scope_clause` as the authoritative isolation filter. Add a short framed guidance block to the recall tool description identifying project/session context and instructing the model to recall before relying on prior decisions.

- [ ] **Step 4: Run memory tests**

  Run `uv run pytest tests/infra/memory/test_tools.py tests/infra/memory/native/test_search.py -q`.

- [ ] **Step 5: Commit**

  `git add src/infra/memory src/infra/agent/middleware tests/infra/memory && git commit -m "feat(memory): improve scoped recall guidance"`

### Task 3: Local end-to-end Agent fixture

**Files:**
- Create: `tests/agents/test_todo_memory_local_case.py`

**Interfaces:**
- Uses fake model/tool/backend components only; no network or production Mongo writes.

- [ ] **Step 1: Write the local scenario**

  Simulate two turns: create a three-step Todo list, complete the first step, recall a project decision while a similarly worded user memory exists, then assert the Todo state remains in the checkpoint and the project memory is selected.

- [ ] **Step 2: Run the scenario and fix integration issues**

  Run `uv run pytest tests/agents/test_todo_memory_local_case.py -q`.

- [ ] **Step 3: Commit**

  `git add tests/agents/test_todo_memory_local_case.py && git commit -m "test(agent): cover local todo and memory workflow"`

### Task 4: Full verification

- [ ] **Step 1: Run focused Agent and memory suites**

  `uv run pytest tests/agents tests/infra/agent tests/infra/memory -q`

- [ ] **Step 2: Run quality checks**

  `uv run ruff check src tests` and `uv run mypy src`

- [ ] **Step 3: Review the diff and run the local fixture again**

  `git diff origin/develop...HEAD --check` and `uv run pytest tests/agents/test_todo_memory_local_case.py -q`.

- [ ] **Step 4: Commit verification-only changes if any**

  Do not change production behavior during this step; only commit required formatting/test corrections.
