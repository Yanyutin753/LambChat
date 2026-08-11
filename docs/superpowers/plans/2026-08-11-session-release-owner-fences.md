# Session Release Owner Fences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fence concurrent session-clear releasers so completed idempotency markers can be compacted without permitting a delayed double decrement.

**Architecture:** A Mongo-authoritative global epoch is bound to a leased clear-group owner. File records retain live operation state until the exact owner completes, then compact it into one scalar high-water fence.

**Tech Stack:** Python 3.12, asyncio, Motor/PyMongo atomic updates, pytest, Ruff, MyPy.

## Global Constraints

- Epoch allocation must use an atomic Mongo counter, never Redis or a per-operation counter.
- Only an exact group owner token and epoch may release, transition, or clean its marker.
- Takeover must adopt its newer epoch on every file before release.
- Completed history must be represented by one scalar, not retained operation IDs.
- Repeated cancellation must not interrupt the safety-critical group operation.
- Do not modify scheduler, chat, or runtime scheduler domains.

---

### Task 1: Reproduce the delayed-releaser race

**Files:**
- Test: `tests/infra/session/test_attachment_cleanup.py`
- Test: `tests/infra/test_file_record_storage_lifecycle.py`

**Interfaces:**
- Consumes: `SessionManager.clear_session_messages` and current file release APIs.
- Produces: deterministic concurrency and compact-history regression tests.

- [ ] Add a stateful two-caller test that pauses owner one after its release command starts, lets an expired-lease owner two complete, then resumes owner one; assert count `2 -> 1`, both callers have a safe outcome, and no marker remains.
- [ ] Add storage tests for 1,100 sequential operations, stale exact-epoch release rejection, and newer takeover adoption preserving `applied`.
- [ ] Run only the new tests and confirm double decrement or missing owner APIs cause RED.

### Task 2: Global epoch and group lease binding

**Files:**
- Modify: `src/infra/session/session_attachment_operations.py`
- Modify: `src/infra/session/storage.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Produces: `claim_attachment_clear_group_release`, `renew_attachment_clear_group_release`, and exact-owner `set_attachment_clear_group_status` behavior.
- Consumes: a dedicated Mongo metadata counter collection and the persisted clear-group document.

- [ ] Add RED tests for global ordering across groups, same-token retry, counter reply loss, bind reply loss, expiry takeover, and stale-owner transition rejection.
- [ ] Add lazy metadata collection access and atomic `$inc` epoch allocation.
- [ ] CAS-bind token/epoch/expiry to `deleted` or expired `releasing` groups and exact-reread ambiguous writes.
- [ ] Add exact-owner renewal and status transition filters; run the storage tests GREEN.

### Task 3: File live-operation fences

**Files:**
- Modify: `src/infra/upload/file_record.py`
- Test: `tests/infra/test_file_record_storage_lifecycle.py`

**Interfaces:**
- Produces: `adopt_release_operation_epoch`, exact-epoch `release_reference_counts`, and exact-epoch `forget_release_operation`.
- Consumes: positive globally comparable owner epochs.

- [ ] Add RED tests proving takeover preserves the first decrement, stale releases fail after cleanup, unrelated live operations survive out-of-order completion, and sequential history remains bounded.
- [ ] Replace historical string markers with live `{operation_id, epoch, applied}` entries and `session_release_epoch_high_water`.
- [ ] Make adoption, release, and cleanup atomic and owner-scoped; run lifecycle tests GREEN.

### Task 4: Cancellation-resistant manager orchestration

**Files:**
- Modify: `src/infra/session/manager.py`
- Test: `tests/infra/session/test_attachment_cleanup.py`

**Interfaces:**
- Consumes: the group lease and exact-epoch FileRecord APIs from Tasks 2–3.
- Produces: one fenced group operation per clear caller with heartbeat renewal and safe takeover.

- [ ] Add RED tests for repeated cancellation, expired takeover, and adopt-before-release ordering.
- [ ] Run each `deleted`/`releasing` group in a drained child task: claim, heartbeat, adopt all keys, release exact epoch, exact-owner transition, exact cleanup, stop heartbeat.
- [ ] Treat active foreign ownership as retryable in-progress state and never complete the parent clear operation early.
- [ ] Run all session attachment and file lifecycle tests GREEN.

### Task 5: Scoped verification and commit

**Files:**
- Verify/stage only files listed above plus these two documents.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: one reviewed scoped commit.

- [ ] Run affected session and FileRecord suites.
- [ ] Run Ruff check/format on changed Python files and MyPy on changed source files.
- [ ] Run `git diff --check`, verify staged paths, and commit only scoped files.
