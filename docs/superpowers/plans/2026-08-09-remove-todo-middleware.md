# Remove Todo Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `TodoListMiddleware` from every LambChat main-agent and declarative-subagent stack so `write_todos` and the `todos` state channel are no longer exposed.

**Architecture:** LambChat currently opts back into the upstream-removed middleware through one shared factory called from fast, search, and team agent builders. Remove that compatibility layer at its six call sites, delete the now-unused factory, and keep all neighboring middleware in their current order. A focused source-structure regression covers every user-facing agent builder because the middleware lists are nested inside their node functions and are not independently callable.

**Tech Stack:** Python 3.12, DeepAgents 0.7.5, LangChain middleware, pytest, Ruff

## Global Constraints

- Remove the middleware from fast, search, and team main agents and their declarative subagents.
- Do not add a feature flag, no-op shim, or replacement planning tool.
- Do not alter task/subagent behavior, prompt caching, or other middleware ordering.
- Preserve unrelated working-tree changes.

---

### Task 1: Remove Todo Middleware From User-Facing Agents

**Files:**
- Modify: `tests/agents/test_todo_middleware_registration.py`
- Modify: `tests/agents/core/test_system_prompt_budget.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/agents/core/persona.py`
- Delete: `src/agents/core/todo_middleware.py`

**Interfaces:**
- Consumes: each node's existing `_build_subagent_middleware(...) -> list` and `user_middleware` construction.
- Produces: fast, search, and team graphs whose caller-supplied middleware contains no `TodoListMiddleware`; there is no replacement API.

- [ ] **Step 1: Replace the positive registration checks with a failing removal regression**

Replace `tests/agents/test_todo_middleware_registration.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "src" / "agents"


@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_deep_agent_nodes_do_not_register_todo_middleware(agent_name: str) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()

    assert "todo_middleware" not in source
    assert "create_todo_middleware" not in source
    assert "TodoListMiddleware" not in source
```

This test catches any explicit todo-middleware import or construction in all six main/subagent registration sites. It deliberately does not test DeepAgents itself; the project dependency's no-default behavior is characterized by the absence of LambChat registrations.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py -q
```

Expected: three failures because each `nodes.py` still imports and calls `create_todo_middleware()`.

- [ ] **Step 3: Remove the compatibility layer with the smallest production change**

In each of these files:

- `src/agents/fast_agent/nodes.py`
- `src/agents/search_agent/nodes.py`
- `src/agents/team_agent/nodes.py`

delete this import:

```python
from src.agents.core.todo_middleware import create_todo_middleware
```

Delete `create_todo_middleware(),` from the leading entries of every `_build_subagent_middleware(...)` list and delete:

```python
user_middleware.append(create_todo_middleware())
```

from every main-agent stack. Do not move or otherwise edit adjacent middleware.

Delete `src/agents/core/todo_middleware.py` because it has no remaining callers.

In `tests/agents/core/test_system_prompt_budget.py`, delete the `create_todo_middleware` import and remove `create_todo_middleware().system_prompt` from `blocks`.

In `src/agents/core/persona.py`, replace the stale block map with:

```python
最终 system message 结构：
  [Block 0] SANDBOX/DEFAULT/FAST_SYSTEM_PROMPT + BEHAVIOR_GUIDE      ← 全局稳定
  [Block 1+] Persona / Skills / Memory / dynamic middleware sections
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Verify affected agent behavior and style**

Run:

```bash
uv run pytest \
  tests/agents/core/test_system_prompt_budget.py \
  tests/agents/test_disabled_skills_config_propagation.py \
  tests/agents/test_team_agent_sandbox_support.py \
  tests/agents/test_todo_middleware_registration.py -q
uv run ruff check \
  src/agents/core/persona.py \
  src/agents/fast_agent/nodes.py \
  src/agents/search_agent/nodes.py \
  src/agents/team_agent/nodes.py \
  tests/agents/test_todo_middleware_registration.py
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 6: Audit the removal**

Run:

```bash
rg -n "TodoListMiddleware|create_todo_middleware|todo_middleware" src/agents tests/agents
git diff --check
git status --short
```

Expected: matches only in the negative registration test itself; no production Agent registrations, no whitespace errors, and only intended backend/test changes plus the user's pre-existing unrelated files appear in status. Historical `write_todos` event rendering remains outside the Agent registration scope.

- [ ] **Step 7: Commit the implementation**

```bash
git add \
  src/agents/core/persona.py \
  src/agents/core/todo_middleware.py \
  src/agents/fast_agent/nodes.py \
  src/agents/search_agent/nodes.py \
  src/agents/team_agent/nodes.py \
  tests/agents/core/test_system_prompt_budget.py \
  tests/agents/test_todo_middleware_registration.py
git commit -m "refactor: remove todo middleware"
```
