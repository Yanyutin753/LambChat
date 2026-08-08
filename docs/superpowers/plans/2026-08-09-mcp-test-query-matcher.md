# MCP Test Query Matcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the effective MCP configuration regression tests by making their local MongoDB collection fake understand the `$ne` query already used by production.

**Architecture:** Keep production MCP storage unchanged. Extend only the `_FakeCollection` in the policy test module with a narrow query matcher for equality and `$ne`, matching the established fake used by the MCP storage-limit tests.

**Tech Stack:** Python 3.12+, pytest, pytest-asyncio, Git worktrees

## Global Constraints

- Modify only test behavior for the query matcher; do not change production MCP queries.
- Support ordinary equality and `$ne` only; do not build a general MongoDB emulator.
- Preserve the pre-limit exclusion of legacy `sandbox` MCP records.
- Use the existing two failures as RED evidence before changing the fake.

---

### Task 1: Repair the MCP policy test collection fake

**Files:**
- Modify: `tests/test_mcp_tool_policies.py:307-322`
- Reference: `tests/infra/test_mcp_storage_limits.py:108-126`

**Interfaces:**
- Consumes: `_FakeCollection.find(query: dict[str, Any]) -> _AsyncCursor`
- Produces: `_FakeCollection._matches(doc: dict[str, Any], query: dict[str, Any]) -> bool`

- [ ] **Step 1: Re-run the existing regression tests to verify RED**

Run:

```bash
uv run --no-sync pytest -q \
  tests/test_mcp_tool_policies.py::test_effective_config_loads_system_tool_policies_in_bulk \
  tests/test_mcp_tool_policies.py::test_effective_config_caps_loaded_servers
```

Expected: both tests fail because `config["mcpServers"]` is empty and `bulk_calls` receives an empty server list.

- [ ] **Step 2: Implement the minimal query matcher**

Change `_FakeCollection` to use this narrow matcher:

```python
class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            if isinstance(expected, dict) and "$ne" in expected:
                if doc.get(key) == expected["$ne"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    def find(self, query: dict[str, Any]):
        return _AsyncCursor([doc for doc in self._docs if self._matches(doc, query)])
```

Do not edit `src/infra/mcp/storage_operations.py`.

- [ ] **Step 3: Verify the two regressions are GREEN**

Run:

```bash
uv run --no-sync pytest -q \
  tests/test_mcp_tool_policies.py::test_effective_config_loads_system_tool_policies_in_bulk \
  tests/test_mcp_tool_policies.py::test_effective_config_caps_loaded_servers
```

Expected: `2 passed`.

- [ ] **Step 4: Run the complete policy test module**

Run:

```bash
uv run --no-sync pytest -q tests/test_mcp_tool_policies.py
```

Expected: all tests pass with no failures.

- [ ] **Step 5: Run backend and project regression suites**

Run:

```bash
uv run --no-sync pytest
make test
```

Expected: both commands exit zero. The backend suite has no failures, and `make test` confirms both frontend and backend suites pass.

- [ ] **Step 6: Commit the focused fix**

```bash
git add tests/test_mcp_tool_policies.py
git commit -m "test: support excluded MCP transports in fake query"
```

### Task 2: Clean up the merged feature worktree

**Files:**
- Remove worktree directory: `.worktrees/background-artifact-delivery`
- Delete local branch: `perf/background-artifact-delivery`

**Interfaces:**
- Consumes: the verified relationship `perf/background-artifact-delivery` is an ancestor of `main`
- Produces: a single normal `main` worktree with the merged feature branch removed locally

- [ ] **Step 1: Reconfirm merge ancestry and clean worktree state**

Run:

```bash
git merge-base --is-ancestor perf/background-artifact-delivery main
git -C .worktrees/background-artifact-delivery status --short
```

Expected: the ancestry command exits zero and the worktree status has no output.

- [ ] **Step 2: Remove the merged worktree and branch**

Run:

```bash
git worktree remove .worktrees/background-artifact-delivery
git worktree prune
git branch -d perf/background-artifact-delivery
```

Expected: Git removes the worktree and reports the local branch deleted without forcing.

- [ ] **Step 3: Verify final repository state**

Run:

```bash
git status --short --branch
git worktree list
git branch --list perf/background-artifact-delivery
```

Expected: `main` is clean, only the main worktree remains, and the feature branch listing is empty.
