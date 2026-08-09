# Lazy Sandbox Tool Event Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the first Search Agent sandbox tool emit lifecycle events before its public tool events without restoring eager sandbox initialization.

**Architecture:** Add an optional pre-tool-start callback to the shared event processor. Search Agent connects it to the run-scoped `LazySandboxBackend`, whose callback classifies filesystem routes and awaits the existing single-flight initializer.

**Tech Stack:** Python 3.12, asyncio, LangGraph event streams, pytest.

## Global Constraints

- Preserve lazy initialization for model-only turns and `/skills` or `/memories` operations.
- Preserve existing event payloads and do not reorder non-filesystem tools.
- Do not modify the user's unrelated frontend worktree changes.

---

### Task 1: Reproduce the event race

**Files:**
- Modify: `tests/agents/test_search_agent_lazy_sandbox.py`

**Interfaces:**
- Consumes: Search Agent's existing scripted `write_file` graph fixture.
- Produces: A regression test for `sandbox:starting -> sandbox:ready -> tool:start -> tool:result`.

- [ ] Add a gated sandbox manager that pauses initialization after `sandbox:starting`.
- [ ] Run the focused test and verify that current code emits `tool:start` while the manager remains blocked.

### Task 2: Serialize lifecycle and tool-start events

**Files:**
- Modify: `src/infra/agent/events/processor.py`
- Modify: `src/infra/agent/events/tool_events.py`
- Modify: `src/infra/backend/lazy_sandbox.py`
- Modify: `src/agents/search_agent/nodes.py`
- Test: `tests/infra/backend/test_lazy_sandbox_backend.py`
- Test: `tests/agents/test_search_agent_lazy_sandbox.py`

**Interfaces:**
- Consumes: `before_tool_start(tool_name: str, tool_input: dict[str, Any]) -> Awaitable[None]`.
- Produces: `LazySandboxBackend.before_tool_start(...)`, connected only by Search Agent.

- [ ] Add routed-path and failure behavior tests before production changes.
- [ ] Add and await the optional callback immediately before presenting `tool:start`.
- [ ] Implement filesystem-tool classification and wait on `_ensure_ready()` for default-sandbox operations.
- [ ] Pass the callback when Search Agent constructs `AgentEventProcessor`.
- [ ] Run focused tests until green.

### Task 3: Verify the repair

**Files:**
- Verify only; no new files.

**Interfaces:**
- Consumes: Completed implementation and regression suite.
- Produces: Test and static-analysis evidence.

- [ ] Run the Search Agent lazy-sandbox tests.
- [ ] Run the event processor and lazy backend tests.
- [ ] Run Ruff on changed Python files.
- [ ] Run the relevant broader Search Agent regression suite and report any external limitations separately.
