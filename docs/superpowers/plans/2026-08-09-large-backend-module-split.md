# Large Backend Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the two backend Python modules over 1000 lines into focused internal modules while preserving all current imports and behavior.

**Architecture:** Keep `artifact_delivery.py` and `trace_storage.py` as stable entry modules. Move artifact data/parsing support into a private support module; move trace shared helpers into a private support module and cohesive write operations into a mixin inherited by `TraceStorage`.

**Tech Stack:** Python 3.12+, asyncio, MongoDB async collections, pytest, Ruff, Mypy, TypeScript, Vitest

---

### Task 1: Add the backend source-size regression

**Files:**
- Create: `frontend/src/utils/__tests__/largeBackendModulesSource.test.ts`
- Reference: `frontend/scripts/find-large-files.ts`

- [ ] **Step 1: Write the failing source-size test**

Create a Node-environment Vitest test that resolves the repository root from `import.meta.url`, scans `src/**/*.py` with `glob`, counts lines using the same `content.split("\n").length` rule as the script, and expects the sorted list of files over 1000 lines to equal `[]`. Include each relative path and line count in the failure value.

- [ ] **Step 2: Run the test to verify RED**

Run `cd frontend && pnpm test -- src/utils/__tests__/largeBackendModulesSource.test.ts`.

Expected: FAIL listing `src/infra/agent/middleware/artifact_delivery.py` and `src/infra/session/trace_storage.py`.

- [ ] **Step 3: Keep the test as the structural acceptance contract**

Do not weaken the threshold, exclude either module, or change its line-count semantics.

### Task 2: Extract artifact-delivery support

**Files:**
- Create: `src/infra/agent/middleware/_artifact_delivery_support.py`
- Modify: `src/infra/agent/middleware/artifact_delivery.py:1-257`
- Test: `tests/infra/agent/test_artifact_delivery_middleware.py`

- [ ] **Step 1: Move support definitions without behavior changes**

Move `RevealTool`, artifact/run-state dataclasses, support-only constants, and all module helpers from `_json_dumps_result` through `_reveal_error` into `_artifact_delivery_support.py`. Include only their required standard-library, `ToolMessage`, and `run_blocking_io` imports. Keep each body equivalent apart from import placement.

Keep `_ARTIFACT_BACKGROUND_DRAIN_TIMEOUT` and `_ARTIFACT_BACKGROUND_CANCEL_GRACE` in `artifact_delivery.py` because tests monkeypatch the former through that module.

- [ ] **Step 2: Re-export support names from the stable entry module**

Replace the removed definitions with explicit imports from `_artifact_delivery_support`. Keep the current names in the entry-module namespace and remove only imports that became unused.

- [ ] **Step 3: Run artifact-delivery tests**

Run `uv run pytest -q tests/infra/agent/test_artifact_delivery_middleware.py`.

Expected: all tests pass, including entry-module drain-timeout monkeypatch coverage.

- [ ] **Step 4: Run focused lint**

Run `uv run ruff check src/infra/agent/middleware/artifact_delivery.py src/infra/agent/middleware/_artifact_delivery_support.py tests/infra/agent/test_artifact_delivery_middleware.py`.

Expected: exit zero.

### Task 3: Extract trace-storage support and writes

**Files:**
- Create: `src/infra/session/_trace_storage_support.py`
- Create: `src/infra/session/trace_storage_writes.py`
- Modify: `src/infra/session/trace_storage.py:27-576`
- Reference: `src/infra/session/trace_event_chunks.py`
- Test: `tests/infra/session/test_trace_storage_lifecycle.py`
- Test: `tests/infra/session/test_trace_event_chunks.py`
- Test: `tests/infra/session/test_trace_storage_token_usage.py`
- Test: `tests/infra/session/test_trace_storage_recommendations.py`
- Test: `tests/infra/session/test_trace_usage_log_write.py`

- [ ] **Step 1: Move shared helper definitions**

Move the limits and pure helpers needed by both retained reads and extracted writes into `_trace_storage_support.py`: `_get_session_event_read_default_limit`, `_clamp_positive_int`, `_clamp_event_read_limit`, `_clamp_nonnegative_int`, `_get_event_chunk_size`, `_event_chunk_index`, `_event_preview`, `_event_seq`, `_bounded_unique_strings`, and `_normalize_recommend_questions`, plus immutable limits other than `SESSION_EVENT_FILTER_LIST_LIMIT`.

Explicitly import these names back into `trace_storage.py`. Keep `SESSION_EVENT_FILTER_LIST_LIMIT = 100` there and pass it explicitly at retained query call sites so its monkeypatch remains effective.

- [ ] **Step 2: Move the write methods into a mixin**

Create `TraceStorageWriteMixin` and move `create_trace`, `append_event`, `set_run_recommend_questions`, `_ensure_token_usage_event`, and `complete_trace` without changing signatures or database operations. Move `_USAGE_LOGS_ENABLED` with `complete_trace` into this write module and preserve its existing conditional scheduling behavior. Import support helpers, logging/time utilities, and settings directly. Use narrow type annotations under `TYPE_CHECKING` for attributes supplied by `TraceStorage`; do not introduce runtime forwarding objects.

- [ ] **Step 3: Preserve the usage-log test seam**

Keep `_write_usage_log` in `trace_storage.py`. Inside `TraceStorageWriteMixin.complete_trace`, resolve it with a function-local import from `src.infra.session.trace_storage` immediately before `asyncio.create_task`.

- [ ] **Step 4: Compose the concrete class**

Change the declaration to `class TraceStorage(TraceStorageWriteMixin, TraceEventChunkMixin):`. Keep initialization, collection properties, index setup, merger startup, reads, deletes, close, and singleton functions in `trace_storage.py`.

- [ ] **Step 5: Run the targeted trace-storage suite**

Run:

```bash
uv run pytest -q \
  tests/infra/session/test_trace_storage_lifecycle.py \
  tests/infra/session/test_trace_event_chunks.py \
  tests/infra/session/test_trace_storage_token_usage.py \
  tests/infra/session/test_trace_storage_recommendations.py \
  tests/infra/session/test_trace_usage_log_write.py
```

Expected: all tests pass.

- [ ] **Step 6: Run focused static checks**

Run:

```bash
uv run ruff check \
  src/infra/session/trace_storage.py \
  src/infra/session/_trace_storage_support.py \
  src/infra/session/trace_storage_writes.py
uv run mypy \
  src/infra/session/trace_storage.py \
  src/infra/session/_trace_storage_support.py \
  src/infra/session/trace_storage_writes.py
```

Expected: both commands exit zero.

### Task 4: Verify the complete refactor

**Files:**
- Verify: all files changed in Tasks 1-3

- [ ] **Step 1: Verify the structural acceptance is GREEN**

Run:

```bash
cd frontend && pnpm test -- src/utils/__tests__/largeBackendModulesSource.test.ts
pnpm run find-large-files
```

Expected: the Vitest test passes; frontend and backend report `No files found`; total is zero.

- [ ] **Step 2: Run all directly affected behavioral tests together**

Run the artifact test module plus all five trace modules from Tasks 2-3 in one pytest invocation. Expected: zero failures.

- [ ] **Step 3: Run project-level static validation**

Run `make lint`, `make typecheck`, and `git diff --check`.

Expected: all commands exit zero.

- [ ] **Step 4: Inspect final scope and line counts**

Run `git status --short`, `git diff --stat`, and `wc -l` for the five backend entry/support/mixin files. Confirm no unrelated files changed and every source file is at or below 1000 lines.

- [ ] **Step 5: Commit the implementation**

Stage only the test and five backend entry/support/mixin files, then commit with `git commit -m "refactor: split large backend modules"`.
