# Bounded File Reference Fences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unbounded file-record operation history with a globally ordered scheduled-task high-water fence and terminal session marker cleanup.

**Architecture:** Mongo scheduler metadata allocates global epochs which are durably bound to task mutation tokens before use. File records retain only bounded live task leases plus one high-water scalar, while session release IDs are removed only after the session group durably reaches `released`.

**Tech Stack:** Python 3.12, asyncio, Motor/PyMongo update pipelines, Pydantic, pytest, Ruff, MyPy.

## Global Constraints

- Do not use Redis to allocate or order mutation epochs.
- Never accept a scheduled file mutation whose epoch was not durably bound to its task token.
- Never remove a session release ID before its group is durably `released`.
- Preserve owner scoping, exact reference counts, cancellation behavior, and the existing live-reference cap.
- Stage and commit only files belonging to this protocol expansion.

---

### Task 1: Globally ordered task mutation fences

**Files:**
- Modify: `src/infra/scheduler/storage.py`
- Test: `tests/infra/scheduler/test_storage.py`

**Interfaces:**
- Produces: `ScheduledTaskStorage.claim_attachment_mutation(task_id: str, token: str) -> ScheduledTask | None` with globally comparable `attachment_mutation_generation`.
- Consumes: scheduler metadata collection and the existing `AttachmentMutationFence` schema.

- [ ] Write failing tests proving two task UUIDs receive increasing epochs, an exact token retry reuses its epoch, counter reply loss only creates a gap, and task-CAS reply loss is confirmed by exact reread.
- [ ] Run the named storage tests and confirm failures are caused by per-task generation allocation.
- [ ] Add an atomic metadata `$inc` allocator and CAS-bind the allocated epoch to the task token; add exact rereads for ambiguous task writes.
- [ ] Run the named storage tests and the full scheduler storage suite.
- [ ] Commit the storage fence change with its tests.

### Task 2: Bounded file-record scheduled leases

**Files:**
- Modify: `src/infra/upload/file_record.py`
- Test: `tests/infra/test_file_record_storage_lifecycle.py`

**Interfaces:**
- Consumes: globally comparable positive `mutation_generation` values.
- Produces: bounded live `scheduled_task_reference_generations` and scalar `scheduled_task_generation_high_water` behavior in claim, adopt, and release methods.

- [ ] Write failing tests for a large random-task claim/release loop, stale replay rejection, exact high-water retry, newer-epoch success, live-entry advancement, and legacy high-water derivation.
- [ ] Run the named lifecycle tests and confirm the historical generation array remains large or stale replay is accepted.
- [ ] Replace retired tombstones with live-only entries and the scalar high-water update pipeline, preserving reference-count idempotency.
- [ ] Run the named lifecycle tests, then scheduler service and file-record suites.
- [ ] Commit the bounded scheduled lease change with its tests.

### Task 3: Terminal session release-marker cleanup

**Files:**
- Modify: `src/infra/upload/file_record.py`
- Modify: `src/infra/session/manager.py`
- Test: `tests/infra/test_file_record_storage_lifecycle.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Produces: `FileRecordStorage.forget_release_operation(keys: list[str], *, operation_id: str, uploaded_by: str) -> bool`.
- Consumes: durable clear-group status `released` and its exact `release_operation_id`.

- [ ] Write failing tests proving released groups remove operation IDs, cleanup failure prevents operation completion, retry cleans without another decrement, partial cleanup is idempotent, and many completed operations remain bounded.
- [ ] Run the named tests and confirm marker history remains or completion occurs too early.
- [ ] Implement owner-scoped `$pull` marker cleanup and invoke it for every durable released group before completing the session clear operation.
- [ ] Run the named tests and all attachment cleanup tests.
- [ ] Commit the session marker cleanup change with its tests.

### Task 4: Integrated verification

**Files:**
- Verify only; no planned production changes.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: evidence that the expanded protocol remains type-safe and regression-free.

- [ ] Run scheduler storage/service, file-record lifecycle, session attachment cleanup, runtime service, and upload cleanup tests.
- [ ] Run Ruff check and format verification on changed Python files.
- [ ] Run MyPy over `src/`.
- [ ] Inspect `git diff --check`, worktree ownership, and staged paths; stage only protocol files.
- [ ] Create the final scoped implementation commit.

