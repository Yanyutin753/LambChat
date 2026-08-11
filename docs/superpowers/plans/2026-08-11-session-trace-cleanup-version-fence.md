# Session Trace Cleanup Version Fence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent an expired cleanup owner from deleting trace data written after a replacement guard opens the session.

**Architecture:** Snapshot exact parent and chunk document identities and versions while the cleanup guard is held, then renew the exact still-live guard before either delete. Delete only the frozen versions so later writes or recreated documents cannot match a stale cleanup operation.

**Tech Stack:** Python 3.12, asyncio, Motor/PyMongo query semantics, pytest-asyncio, Ruff, MyPy.

## Global Constraints

- Never revive an expired or replaced cleanup guard.
- Snapshot both collections before the first delete and renew the exact token afterward.
- Guarded deletes require `_id` plus strict version predicates; missing version fields use `$exists: false`.
- Preserve direct cleanup for a missing pinned session anchor.
- Do not modify scheduler, frontend, presenter, or unrelated session behavior.

---

### Task 1: Deterministic stale-cleanup regressions

**Files:**
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Consumes: `TraceStorage.discard_session_trace_writes_after_lease_loss` and the production session guard lifecycle.
- Produces: observable regressions for snapshot expiry and delete expiry.

- [ ] **Step 1: Write the snapshot-expiry test**

Block parent snapshot materialization after the original guard is acquired. Advance the controlled clock past the five-minute guard TTL, take over and release with a second empty cleanup, cancel the delete fence, acquire a new writer lease, and append to the same trace. Unblock the first snapshot and assert its failed exact renewal caused zero deletes and preserved the new event.

- [ ] **Step 2: Run the snapshot-expiry test and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py::test_trace_cleanup_snapshot_expiry_aborts_before_any_delete -q --disable-warnings
```

Expected: FAIL because guarded cleanup currently issues a broad chunk delete without taking or renewing an exact snapshot.

- [ ] **Step 3: Write the blocked-delete takeover test**

Block the original exact chunk delete before it mutates storage. Advance the clock past the renewed guard TTL, take over and release with a second empty cleanup, cancel the fence, acquire a new lease, update the same parent through `append_event`, and advance the same chunk's version fields. Unblock the original delete and assert the new parent event and chunk survive even though the old guard release is rejected.

- [ ] **Step 4: Run the blocked-delete test and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py::test_expired_cleanup_delete_cannot_remove_newer_parent_or_chunk_versions -q --disable-warnings
```

Expected: FAIL because the existing `session_id + trace_id` deletes remove both newer documents.

### Task 2: Exact guard renewal and document-version deletes

**Files:**
- Modify: `src/infra/session/session_attachment_operations.py`
- Modify: `src/infra/session/trace_storage.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Produces: `SessionStorage.renew_trace_cleanup_guard(session_id: str, delete_operation_id: str, guard_id: str, writer_lease_id: str) -> bool`.
- Consumes: parent version fields `event_revision`, `updated_at`; chunk version fields `append_fence_revision`, `event_count`, `updated_at`.

- [ ] **Step 1: Implement exact non-reviving guard renewal**

Load the pinned guard identity, validate the delete operation, cancel state, guard shape, IDs, writer lease ID, and timezone-compatible expiry. Return `False` when the guard is expired. Compare-and-set the exact operation/guard snapshot to a new expiry and return success only for a matched document.

- [ ] **Step 2: Implement strict document snapshot predicates**

Before either guarded delete, read both collections with `_id`, `session_id`, `trace_id`, and their version fields. Refuse guarded cleanup if any returned Mongo document lacks `_id`. Encode every present value literally and every absent version as `{ "$exists": false }`.

- [ ] **Step 3: Renew after both snapshots and use only exact deletes**

Call exact renewal after both snapshots complete. If renewal fails, perform no delete and release only the stale token in `finally`. Otherwise delete chunks and then parents with `$or` lists of exact frozen predicates. Keep the missing-session branch on the established broad query and document why it is safe.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py -k 'cleanup_guard or cleanup_snapshot or expired_cleanup_delete' -q --disable-warnings
```

### Task 3: Version-field audit and quality gates

**Files:**
- Inspect: `src/infra/session/trace_storage_writes.py`
- Inspect: `src/infra/session/dual_writer_helpers.py`
- Inspect: `src/infra/session/trace_event_chunks.py`
- Inspect: `src/infra/session/trace_chunk_append_recovery.py`

**Interfaces:**
- Verifies: every real new parent event write changes `event_revision` and `updated_at`, while every chunk event write changes `append_fence_revision` and `updated_at` (with `event_count` as an additional exact fence).

- [ ] **Step 1: Audit production write queries**

Trace `append_event`, dual-writer bulk upserts, chunk append, replacement, and recovery. If any path can write new event data without changing the selected fields, add that path to the RED regression before modifying it to advance a stable monotonic version.

- [ ] **Step 2: Run affected tests**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py tests/infra/session/test_fork_title.py tests/infra/session/test_trace_event_chunks.py tests/infra/test_dual_writer_limits.py tests/infra/test_event_merger.py -q --disable-warnings
```

- [ ] **Step 3: Run static gates**

Run:

```bash
uv run ruff check src/infra/session/session_attachment_operations.py src/infra/session/trace_storage.py tests/infra/session/test_attachment_cleanup.py
uv run mypy src
git diff --check
```

- [ ] **Step 4: Commit scoped files**

Stage only the two production files, focused test file, and this plan, then commit with `fix(session): version-fence stale trace cleanup`.
