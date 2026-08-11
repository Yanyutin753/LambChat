# Session Trace Cleanup Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent delete-fence cancellation from admitting a new trace writer while late trace cleanup is deleting across MongoDB collections.

**Architecture:** Store an expiring, identity-bearing cleanup guard inside the existing session delete operation. Session storage owns guard CAS transitions; trace storage claims the guard before deleting chunks and parents and releases it afterward. Pending delete cancellation is applied atomically only by exact guard release or expired-guard recovery.

**Tech Stack:** Python 3.12, asyncio, Motor/PyMongo semantics, pytest-asyncio, Ruff, MyPy.

## Global Constraints

- Preserve pinned custom-ID/ObjectId authority.
- Malformed guard state fails closed and is not automatically removed.
- Missing session anchors may be cleaned directly.
- Do not modify scheduler, frontend, presenter, or unrelated session behavior.

---

### Task 1: Observable cleanup-guard lifecycle

**Files:**
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Consumes: `SessionStorage` and `TraceStorage` production behavior.
- Produces: deterministic regression coverage for guard ownership and recovery.

- [ ] **Step 1: Write the failing interleaving test**

Create a fenced session with an expired writer lease, one parent trace, and one
chunk. Block the chunk collection's `delete_many` after cleanup begins. While
blocked, cancel the original delete operation and assert:

```python
assert await storage.acquire_trace_write("session-1") is None
assert await storage.claim_attachment_delete_operation("session-1") is None
assert await storage.delete_claimed_session("session-1", "delete-1") is False
```

Then allow cleanup, assert both collections are empty, assert the pending
cancel removed the exact delete operation, and prove a new writer lease can be
acquired and released.

- [ ] **Step 2: Run the interleaving test and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py::test_trace_cleanup_guard_defers_delete_cancel_until_cross_collection_cleanup_finishes -q --disable-warnings
```

Expected: FAIL because no cleanup guard is persisted and cancellation opens the
session during the blocked delete.

- [ ] **Step 3: Add expired, stale-token, and malformed tests**

Cover these literal outcomes:

```python
assert replacement_guard_id != "crashed-guard"
assert await storage.release_trace_cleanup_guard("session-1", "crashed-guard") is False
assert current_guard_id == replacement_guard_id
assert await trace_storage.discard_session_trace_writes_after_lease_loss(...) is False
```

Malformed scalar, missing-ID, invalid-expiry, and invalid-writer-ID guards must
leave the session, delete operation, parent traces, and chunks unchanged.

- [ ] **Step 4: Run all new tests and verify each fails for missing behavior**

Run the named guard tests with `pytest -k 'cleanup_guard'` and inspect every
failure before changing production code.

### Task 2: Session-anchor guard state machine

**Files:**
- Modify: `src/infra/session/session_attachment_operations.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Produces: `acquire_trace_cleanup_guard(session_id: str, writer_lease_id: str) -> dict[str, Any] | None`
- Produces: `release_trace_cleanup_guard(session_id: str, guard_id: str) -> bool`
- Consumes: pinned `_load_trace_writer_session`, `utc_now`, and existing delete-operation state.

- [ ] **Step 1: Add strict guard parsing**

Add constants for the nested field and a five-minute expiry, plus a validator
that distinguishes missing from malformed state. Require non-empty string
`id`, non-empty string `writer_lease_id`, and timezone-compatible `datetime`
`expires_at`.

- [ ] **Step 2: Implement exact acquire and release CAS transitions**

Acquire only under the same delete-operation ID observed in the snapshot and
only when `cancel_requested` is absent/false. Replace a valid expired guard by
matching its exact ID and expiry. Release must match both the delete-operation
ID and guard ID; pending cancellation unsets the whole delete operation,
otherwise only its nested guard.

- [ ] **Step 3: Fence existing lifecycle operations**

Make active guards block `claim_attachment_delete_operation` and
`delete_claimed_session`. Make `cancel_attachment_delete_operation` set
`cancel_requested=True` for an active guard, directly unset an unguarded delete
operation, and recover an expired valid guard. Preserve malformed state.

- [ ] **Step 4: Run storage-focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py -k 'cleanup_guard or delete_claim or trace_writer' -q --disable-warnings
```

### Task 3: Guard cross-collection trace cleanup

**Files:**
- Modify: `src/infra/session/trace_storage.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Consumes: `SessionStorage.acquire_trace_cleanup_guard` and `SessionStorage.release_trace_cleanup_guard`.
- Produces: guarded `discard_session_trace_writes_after_lease_loss` behavior.

- [ ] **Step 1: Claim before the first collection delete**

After validating that the writer lease is lost, acquire the guard. Return
`False` when acquisition is refused. Treat the explicit missing-session result
as direct cleanup.

- [ ] **Step 2: Hold ownership through both deletes and release exactly**

Delete chunks and parents inside one `try` and release the exact guard token in
`finally`. A stale token must never clear a replacement guard.

- [ ] **Step 3: Run focused and affected tests**

Run:

```bash
uv run pytest tests/infra/session/test_attachment_cleanup.py -q --disable-warnings
uv run pytest tests/infra/session/test_attachment_cleanup.py tests/infra/session/test_fork_title.py tests/infra/session/test_trace_event_chunks.py tests/infra/test_dual_writer_limits.py tests/infra/test_event_merger.py -q --disable-warnings
```

- [ ] **Step 4: Run quality gates and commit scoped files**

Run:

```bash
uv run ruff check src/infra/session/session_attachment_operations.py src/infra/session/trace_storage.py tests/infra/session/test_attachment_cleanup.py
uv run mypy src
git diff --check
```

Stage only the two production files, the focused test file, and this approved
documentation, then commit with `fix(session): guard cross-collection trace cleanup`.
