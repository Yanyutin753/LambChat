# Local Reference Upload Concurrency Implementation Plan

> Execute inline with strict TDD. Keep upload/storage contracts unchanged.

**Goal:** Remove linear local-reference upload latency while preserving bounded resource use, deterministic reference ordering, and best-effort failure behavior.

**Architecture:** Add a small worker-pool helper in `reveal_file_tool.py`. It creates at most four workers, assigns each discovered reference an index, stores results into a pre-sized list, and lets the existing resolver build replacements in discovery order. The existing 20-reference cap remains the outer bound and `_upload_local_resource` remains responsible for isolating individual failures.

**Tech Stack:** Python asyncio, pytest, existing reveal-file upload helpers.

## Task 1: Prove bounded overlap and ordering

**Files:**
- Modify: `tests/infra/tool/test_reveal_file_tool_local_fallback.py`

1. Add a failing async test with more references than the concurrency limit.
2. Gate uploads so the test proves more than one upload starts before release.
3. Track active uploads and assert the maximum never exceeds four.
4. Complete workers out of order and assert returned replacements still follow discovery order.
5. Add a failure-isolation assertion: one `None` result leaves that reference unchanged while successful references are replaced.
6. Run the focused test and observe RED because uploads are currently serial.

## Task 2: Implement the bounded worker pool

**Files:**
- Modify: `src/infra/tool/reveal_file_tool.py`

1. Add `_LOCAL_REF_UPLOAD_CONCURRENCY = 4` and clamp it to at least one.
2. Add `_upload_local_references_bounded(...)` using at most `min(limit, path_count)` workers and an indexed result list.
3. Replace the serial loop in `_resolve_local_references` with the helper.
4. Preserve the existing path cap, URL mapping, original-content fallback, and per-resource exception handling.
5. Run the new focused test, then the entire reveal-file test module.
6. Commit as `perf: bound concurrent local reference uploads`.

## Task 3: Verify and record evidence

**Files:**
- Modify: `docs/performance-audit-2026-08-09.md`

1. Run Ruff and Mypy.
2. Run the complete backend suite.
3. Record the maximum concurrency, ordering/failure guarantees, focused tests, and full-suite result.
4. Commit as `docs: record local reference upload optimization`.
