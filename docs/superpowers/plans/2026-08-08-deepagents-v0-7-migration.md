# Deepagents v0.7 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade LambChat to `deepagents` 0.7.5 while preserving todo planning and making every custom backend and tool consumer conform to the v0.7 structured filesystem protocol.

**Architecture:** LambChat will target only deepagents 0.7, install `TodoListMiddleware` explicitly, construct concrete composite backends before graph creation, and use upstream result dataclasses end to end. Backend-specific SDK logic remains private to each backend; shared callers consume only `BackendProtocol` methods and structured results.

**Tech Stack:** Python 3.12, deepagents 0.7.5, LangChain agent middleware, pytest/pytest-asyncio, Ruff, Mypy, uv.

---

## File Map

- `pyproject.toml`, `uv.lock`: deepagents 0.7 dependency contract and resolved artifacts.
- `src/agents/{fast_agent,search_agent,team_agent}/nodes.py`: explicit todo middleware and concrete backend use.
- `src/infra/backend/deepagent.py`, `src/infra/backend/__init__.py`: concrete backend construction and workflow-scoped v0.7 result remapping.
- `src/infra/backend/protocol_compat.py`: v0.7 protocol re-exports plus LambChat-specific upload/download helpers.
- `src/infra/backend/skills_store.py`: Mongo-backed v0.7 `ls`, `grep`, `glob`, and raw paginated `ReadResult`.
- `src/infra/backend/{e2b,daytona,cubesandbox}.py`: SDK-backed v0.7 filesystem results.
- `src/infra/agent/middleware/artifact_delivery.py`, `src/infra/tool/{backend_utils,reveal_project_tool,transfer_file_tool}.py`: callers of removed helper APIs.
- `tests/agents/`: todo and concrete-backend agent construction coverage.
- `tests/infra/backend/`: backend protocol, pagination, path scoping, grep timeout, and glob coverage.
- `tests/infra/agent/`, `tests/infra/tool/`: structured consumer and model-facing output coverage.

### Task 1: Pin and Resolve Deepagents 0.7.5

**Files:**
- Modify: `tests/test_dependency_metadata.py`
- Modify: `pyproject.toml:22`
- Modify: `uv.lock`

- [ ] **Step 1: Write the failing dependency test**

Add a test that reads the project dependency metadata and requires the normalized constraint to contain `deepagents>=0.7.5,<0.8`. It must also reject any remaining `<0.7` constraint.

```python
def test_deepagents_targets_supported_v0_7_line() -> None:
    dependencies = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    deepagents = next(item for item in dependencies if item.startswith("deepagents"))
    assert deepagents == "deepagents>=0.7.5,<0.8"
```

- [ ] **Step 2: Run the test to verify RED**

Run: `uv run pytest tests/test_dependency_metadata.py::test_deepagents_targets_supported_v0_7_line -q`

Expected: FAIL because `pyproject.toml` still contains `deepagents>=0.6.5,<0.7`.

- [ ] **Step 3: Update the dependency and lockfile**

Change the dependency to `deepagents>=0.7.5,<0.8`, remove the obsolete migration comment, and run:

`uv lock --upgrade-package deepagents`

Confirm the lock selects 0.7.5 and does not unexpectedly upgrade unrelated direct dependencies beyond resolver requirements.

- [ ] **Step 4: Run the dependency test and import smoke check**

Run:

```bash
uv run pytest tests/test_dependency_metadata.py -q
uv run python -c "from importlib.metadata import version; assert version('deepagents') == '0.7.5'"
```

Expected: PASS and exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_dependency_metadata.py
git commit -m "build: upgrade deepagents to v0.7"
```

### Task 2: Restore Todo Planning Explicitly

**Files:**
- Create: `tests/agents/test_todo_middleware_registration.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`

- [ ] **Step 1: Write failing registration tests**

Test each production node source for the correct import and for explicit root and custom-subagent registration. Also compile a small graph with `TodoListMiddleware()` and assert `write_todos` is present in the graph's tool node and `todos` is present in its state schema.

```python
@pytest.mark.parametrize("agent_name", ["fast_agent", "search_agent", "team_agent"])
def test_agent_restores_todo_middleware(agent_name: str) -> None:
    source = (AGENTS_ROOT / agent_name / "nodes.py").read_text()
    assert "from langchain.agents.middleware import TodoListMiddleware" in source
    assert "TodoListMiddleware()" in source
    assert "from deepagents" not in source.split("TodoListMiddleware")[0][-80:]
```

- [ ] **Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/agents/test_todo_middleware_registration.py -q`

Expected: FAIL because no node imports or installs the middleware.

- [ ] **Step 3: Add the minimum middleware registrations**

In all three node modules:

```python
from langchain.agents.middleware import TodoListMiddleware
```

Append one `TodoListMiddleware()` to each main `user_middleware` before the final prompt-caching middleware, and add one to each `_build_subagent_middleware` list. Do not add it to `MemoryCompactionAgent`.

- [ ] **Step 4: Verify GREEN and existing agent-node behavior**

Run:

```bash
uv run pytest tests/agents/test_todo_middleware_registration.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py tests/agents/test_todo_middleware_registration.py
git commit -m "fix: restore deep agent todo middleware"
```

### Task 3: Replace Compatibility Result Types with v0.7 Types

**Files:**
- Modify: `tests/infra/backend/test_deepagents_protocol_compat.py`
- Modify: `src/infra/backend/protocol_compat.py`

- [ ] **Step 1: Write failing v0.7 identity and raw-read tests**

Require every re-exported result class to be the upstream class, require `DeleteResult`, and assert `read_result_to_string` returns raw content without a synthetic gutter.

```python
def test_protocol_results_are_upstream_v0_7_types() -> None:
    assert compat.ReadResult is protocol.ReadResult
    assert compat.LsResult is protocol.LsResult
    assert compat.GrepResult is protocol.GrepResult
    assert compat.GlobResult is protocol.GlobResult
    assert compat.DeleteResult is protocol.DeleteResult

def test_read_result_to_string_returns_raw_content() -> None:
    result = protocol.ReadResult(file_data=create_file_data("alpha\nbeta"))
    assert compat.read_result_to_string(result) == "alpha\nbeta"
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/infra/backend/test_deepagents_protocol_compat.py -q`

Expected: FAIL because the module dynamically subclasses and monkey-patches protocol result classes.

- [ ] **Step 3: Simplify the compatibility module**

Replace fallback/type-detection code with direct imports from `deepagents.backends.protocol`, including `DeleteResult`. Keep `ExtendedFileError`, `file_upload_response`, `file_download_response`, `is_read_result`, and a `read_result_to_string` that reads `error` or `file_data["content"]`. Do not add `rendered_content`, string subclassing, or `__getitem__` monkey patches.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/infra/backend/test_deepagents_protocol_compat.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/infra/backend/protocol_compat.py tests/infra/backend/test_deepagents_protocol_compat.py
git commit -m "refactor: adopt deepagents v0.7 result types"
```

### Task 4: Build Concrete Backends and Scope Every Operation

**Files:**
- Modify: `tests/infra/backend/test_deepagent_backend_factory.py`
- Modify: `tests/infra/backend/test_deepagents_protocol_compat.py`
- Modify: `tests/agents/test_disabled_skills_config_propagation.py`
- Modify: `tests/agents/test_team_agent_sandbox_support.py`
- Modify: `src/infra/backend/deepagent.py`
- Modify: `src/infra/backend/__init__.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `src/infra/tool/backend_utils.py`

- [ ] **Step 1: Write failing concrete-instance and protocol tests**

Update factory tests to call `create_memory_backend`, `create_persistent_backend`, and `create_sandbox_backend` once and assert each returns a `CompositeBackend`, not a callable. Add a recording backend and cover structured `ls/als`, `grep/agrep(max_count=...)`, `glob/aglob`, `read/aread`, and `delete/adelete` path stripping/prefixing.

```python
result = scoped.grep("needle", "/workflow/session/src", max_count=3)
assert recording.grep_calls == [("needle", "/src", None, 3)]
assert result.matches == [{"path": "/workflow/session/src/a.py", "line": 1, "text": "needle"}]

deleted = scoped.delete("/workflow/session/report.md")
assert recording.delete_calls == ["/report.md"]
assert deleted.path == "/workflow/session/report.md"
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `uv run pytest tests/infra/backend/test_deepagent_backend_factory.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -q`

Expected: FAIL on callable factories and removed `*_info`/`*_raw` methods.

- [ ] **Step 3: Implement v0.7 `WorkflowScopedBackend`**

Import `DeleteResult`, `GlobResult`, `GrepResult`, and `LsResult`. Replace public helper methods with protocol methods and return new result objects rather than mutating upstream objects. Preserve errors and `truncated`; pass grep `max_count` keyword-only. Add path-scoped `delete/adelete`.

- [ ] **Step 4: Return concrete composite instances**

Rename creator functions and exports to `create_memory_backend`, `create_persistent_backend`, and `create_sandbox_backend`. Construct routes and namespaces immediately. Update the three node modules so they never test `callable(backend)` or invoke a runtime factory. Update test doubles and `backend_utils.py` terminology/lookup behavior to treat configured backends as instances.

- [ ] **Step 5: Verify GREEN**

Run the focused command from Step 2 again.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/infra/backend/deepagent.py src/infra/backend/__init__.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py src/infra/tool/backend_utils.py tests/infra/backend/test_deepagent_backend_factory.py tests/infra/backend/test_deepagents_protocol_compat.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py
git commit -m "refactor: pass concrete deep agent backends"
```

### Task 5: Migrate SkillsStoreBackend Reads and Searches

**Files:**
- Modify: `tests/infra/backend/test_skills_store_backend.py`
- Modify: `src/infra/backend/skills_store.py`

- [ ] **Step 1: Add failing pagination and truncation tests**

Assert text reads return raw content plus correct v0.7 pagination fields, zero-limit reads set `no_lines_requested`, grep honors `max_count` with `truncated=True`, and empty `ls`/`glob` remain structured empty lists at the backend boundary.

```python
result = await backend.aread("/skills/demo/SKILL.md", offset=1, limit=1)
assert result.file_data["content"] == "second"
assert (result.start_line, result.end_line, result.next_offset, result.total_lines) == (2, 2, 2, 3)

result = await backend.agrep("needle", "/skills/", max_count=1)
assert len(result.matches or []) == 1
assert result.truncated is True
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/infra/backend/test_skills_store_backend.py -q`

Expected: FAIL because reads render line numbers and grep lacks the v0.7 keyword-only cap.

- [ ] **Step 3: Implement raw `ReadResult` and v0.7 search signatures**

Use `slice_read_response` from deepagents 0.7 to create validated raw read windows. Remove backend calls to `format_content_with_line_numbers`. Add `max_count` to sync/async grep, cap the combined results deterministically, and preserve an existing truncation/error signal. Remove public `ls_info`, `grep_raw`, and `glob_info` compatibility methods after all consumers migrate.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/infra/backend/test_skills_store_backend.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/infra/backend/skills_store.py tests/infra/backend/test_skills_store_backend.py
git commit -m "refactor: migrate skills backend to v0.7 protocol"
```

### Task 6: Migrate E2B, Daytona, and CubeSandbox Backends

**Files:**
- Modify: `tests/infra/backend/test_sandbox_grep_timeout.py`
- Modify: `tests/infra/backend/test_e2b_glob.py`
- Modify: `tests/infra/backend/test_daytona_glob.py`
- Modify: `tests/infra/backend/test_cubesandbox_backend.py`
- Modify: `src/infra/backend/e2b.py`
- Modify: `src/infra/backend/daytona.py`
- Modify: `src/infra/backend/cubesandbox.py`

- [ ] **Step 1: Convert tests to the v0.7 public protocol and add RED cases**

Call `grep/agrep`, `glob/aglob`, and `ls/als` directly and inspect result dataclasses. Add `max_count`/`truncated` assertions. Add E2B and CubeSandbox read cases that assert raw content and valid pagination rather than `rendered_content` or fixed-width line numbers.

```python
result = backend.grep("needle", path="/tmp", glob="*.py", max_count=1)
assert result.error is None
assert result.matches == [{"path": "/tmp/app.py", "line": 3, "text": "needle"}]

timeout = await backend.agrep("needle", path="/tmp")
assert timeout.matches is None
assert "timed out after 30s" in (timeout.error or "")
```

- [ ] **Step 2: Run to verify RED**

Run:

```bash
uv run pytest tests/infra/backend/test_sandbox_grep_timeout.py tests/infra/backend/test_e2b_glob.py tests/infra/backend/test_daytona_glob.py tests/infra/backend/test_cubesandbox_backend.py -q
```

Expected: FAIL because tests still reach removed raw/info methods or backend reads construct extended `ReadResult` objects.

- [ ] **Step 3: Implement private SDK helpers and public v0.7 methods**

For each backend, keep command/SDK traversal in private helpers such as `_list_entries`, `_grep_matches`, and `_glob_entries`. Public methods must return upstream dataclasses. Preserve E2B/Daytona configured grep timeouts, translate timeout text to `GrepResult(error=...)`, apply `max_count`, and set `truncated` when matches are dropped. Use upstream read slicing/pagination and keep binary file data encoded without `rendered_content`.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 again.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/infra/backend/e2b.py src/infra/backend/daytona.py src/infra/backend/cubesandbox.py tests/infra/backend/test_sandbox_grep_timeout.py tests/infra/backend/test_e2b_glob.py tests/infra/backend/test_daytona_glob.py tests/infra/backend/test_cubesandbox_backend.py
git commit -m "refactor: migrate sandbox backends to v0.7 protocol"
```

### Task 7: Migrate Structured Backend Consumers

**Files:**
- Modify: `tests/infra/agent/test_artifact_delivery_middleware.py`
- Modify: `tests/infra/tool/test_reveal_project_tool.py`
- Modify: `tests/infra/tool/test_transfer_file_tool.py`
- Modify: `src/infra/agent/middleware/artifact_delivery.py`
- Modify: `src/infra/tool/reveal_project_tool.py`
- Modify: `src/infra/tool/transfer_file_tool.py`

- [ ] **Step 1: Write failing consumer error/result tests**

Use fake backends that expose only v0.7 `aglob`/`als`. Assert successful consumers extract `.matches`/`.entries`, structured errors do not become empty success, and artifact delivery does not probe `aglob_info`/`glob_info`.

- [ ] **Step 2: Run to verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_artifact_delivery_middleware.py tests/infra/tool/test_reveal_project_tool.py tests/infra/tool/test_transfer_file_tool.py -q
```

Expected: FAIL on removed helper probing or incomplete structured-error handling.

- [ ] **Step 3: Implement v0.7-only consumption**

Call `await backend.aglob(...)` and `await backend.als(...)` directly. Raise or return the existing user-facing error shape when `result.error` is present; otherwise use `result.matches or []` and `result.entries or []`. Do not parse model-facing strings.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 again.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/infra/agent/middleware/artifact_delivery.py src/infra/tool/reveal_project_tool.py src/infra/tool/transfer_file_tool.py tests/infra/agent/test_artifact_delivery_middleware.py tests/infra/tool/test_reveal_project_tool.py tests/infra/tool/test_transfer_file_tool.py
git commit -m "refactor: consume structured deep agent results"
```

### Task 8: Lock Down Tool-Boundary Output Changes

**Files:**
- Create: `tests/infra/backend/test_deepagents_v07_tool_outputs.py`
- Modify only if audit finds a parser: matching source/test file reported by `rg`

- [ ] **Step 1: Write model-facing output tests**

Compile a minimal deep agent or instantiate `FilesystemMiddleware` with `StateBackend`. Invoke the `ls`, `glob`, and `read_file` tools through the middleware tool boundary. Assert empty `ls` and `glob` content is exactly `No files found`; assert read rows use the v0.7 marker plus two-space separator and do not match a fixed-width `cat -n` tab gutter.

- [ ] **Step 2: Run to verify RED against old assumptions**

Run: `uv run pytest tests/infra/backend/test_deepagents_v07_tool_outputs.py -q`

Expected: the new tests either fail on a LambChat wrapper assumption or pass against upstream v0.7. If a test passes immediately because upstream already owns the behavior, verify its value by temporarily asserting the old `[]`/tab-gutter behavior and observing failure before restoring the v0.7 assertion.

- [ ] **Step 3: Audit parsers and update only real dependencies**

Run:

```bash
rg -n --hidden -g '!uv.lock' -g '!frontend/node_modules/**' 'No files found|cat -n|rendered_content|format_content_with_line_numbers|grep_raw|agrep_raw|ls_info|als_info|glob_info|aglob_info' src tests
```

If LambChat parser code depends on `[]` or the old gutter, update it to consume structured backend results or recognize the v0.7 separator. If no parser exists, record that the change is fully upstream-owned and make no production edit.

- [ ] **Step 4: Verify tool output and event regressions**

Run:

```bash
uv run pytest tests/infra/backend/test_deepagents_v07_tool_outputs.py tests/infra/agent/test_events_processor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/infra/backend/test_deepagents_v07_tool_outputs.py
git add <only-any-real-parser-files-found-by-the-audit>
git commit -m "test: cover deepagents v0.7 tool output formats"
```

### Task 9: Remove v0.6 Symbols and Run Migration Verification

**Files:**
- Modify: any migration file still reported by the audit
- Verify: all changed Python and dependency files

- [ ] **Step 1: Run the removed-symbol audit**

Run:

```bash
rg -n --hidden -g '!uv.lock' -g '!frontend/node_modules/**' 'BackendFactory|BACKEND_TYPES|FileFormat|\bUnset\b|grep_raw|agrep_raw|ls_info|als_info|glob_info|aglob_info|rendered_content' src tests pyproject.toml
```

Expected: no production dependency on removed compatibility APIs. Mentions in migration regression tests are allowed only when asserting absence.

- [ ] **Step 2: Run focused backend and agent suites**

Run:

```bash
uv run pytest tests/infra/backend tests/infra/agent/test_artifact_delivery_middleware.py tests/infra/tool/test_reveal_project_tool.py tests/infra/tool/test_transfer_file_tool.py tests/agents/test_todo_middleware_registration.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -q
```

Expected: PASS with zero failures.

- [ ] **Step 3: Run lint and type checking**

Run:

```bash
uv run ruff check src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py src/infra/backend src/infra/agent/middleware/artifact_delivery.py src/infra/tool/backend_utils.py src/infra/tool/reveal_project_tool.py src/infra/tool/transfer_file_tool.py tests/agents/test_todo_middleware_registration.py tests/infra/backend
make typecheck
```

Expected: Ruff and Mypy exit 0. If repository-wide pre-existing type failures occur, isolate and report them separately after running a focused Mypy command over changed modules.

- [ ] **Step 4: Run the broad test suite**

Run: `uv run pytest -q`

Expected: PASS. External-service skips are acceptable; external credential/service failures must be reported separately from code failures.

- [ ] **Step 5: Review the final diff and dependency graph**

Run:

```bash
git diff --check HEAD~8..HEAD
git status --short
uv tree --package deepagents
```

Confirm every requirement in the design is represented by code and regression coverage. Record live E2B, Daytona, CubeSandbox, persistent store, deployed template/snapshot, and `deepagents-backends` behavior as manual-review items unless actually exercised.

- [ ] **Step 6: Commit any final cleanup**

```bash
git add <verified-cleanup-files>
git commit -m "chore: finish deepagents v0.7 migration"
```

Skip this commit if verification required no cleanup.
