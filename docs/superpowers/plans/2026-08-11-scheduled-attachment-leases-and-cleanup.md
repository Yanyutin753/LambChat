# Scheduled Attachment Leases and Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep scheduled-task attachments alive for the persisted definition lifetime and run bounded delayed file cleanup in production.

**Architecture:** File records receive idempotent task-UUID lease tokens whose insertion/removal changes `reference_count` exactly once. Scheduled-task documents persist current keys plus crash-recoverable pending claim/release state; service mutations serialize per task, claim before publishing new input, and reconcile interrupted operations. The existing runtime scheduler runs a bounded cleanup job regardless of the scheduled-task feature flag and closes its wrapper before shared storage clients.

**Tech Stack:** Python 3.12, FastAPI service layer, Pydantic, Motor/PyMongo update pipelines, APScheduler, pytest/pytest-asyncio, Ruff, MyPy.

## Global Constraints

- Do not touch chat presenter/session lease/frontend code.
- Preserve each run message's existing independent attachment reference.
- Reject more than 100 unique task attachments and scope every lease mutation to the owning user.
- Never decrement a missing lease or let `reference_count` become negative.
- Keep pause and completed date-task definition leases until input replacement or deletion.
- Stage only scheduler/upload backend files, their tests, and these scoped design/plan documents.

---

### Task 1: Idempotent file-record definition leases

**Files:**
- Modify: `src/infra/upload/file_record.py`
- Test: `tests/infra/test_file_record_storage_lifecycle.py`

**Interfaces:**
- Produces: `claim_scheduled_task_references(keys: list[str], uploaded_by: str, task_id: str) -> list[str]`
- Produces: `release_scheduled_task_references(keys: list[str], uploaded_by: str, task_id: str) -> int`
- Stores: `scheduled_task_reference_ids: list[str]` on each file record.

- [ ] **Step 1: Write failing tests for one-time claim semantics**

  Add real fake-collection tests proving a unique owned key inserts the task UUID and increments once, a retry does not increment again, a foreign/tombstoned key fails closed, a partial claim rolls back only tokens inserted by that call, and 101 unique keys are rejected before mutation.

- [ ] **Step 2: Run the lease claim tests and verify RED**

  Run: `uv run pytest tests/infra/test_file_record_storage_lifecycle.py -k scheduled_task -vv`

  Expected: failures because both scheduled-task lease methods are absent.

- [ ] **Step 3: Implement minimal owner-scoped claim pipeline**

  Normalize with the existing 100-key helper, validate the UUID token, cap the per-record token array, and use a pipeline equivalent to:

  ```python
  existing = {"$ifNull": ["$scheduled_task_reference_ids", []]}
  already_claimed = {"$in": [task_id, existing]}
  reference_count = {
      "$cond": [
          already_claimed,
          {"$ifNull": ["$reference_count", 0]},
          {"$add": [{"$ifNull": ["$reference_count", 0]}, 1]},
      ]
  }
  ```

  Return only keys newly claimed by this call so its exception/cancellation rollback never removes an older live token.

- [ ] **Step 4: Write and run RED tests for idempotent release**

  Prove an existing token is removed/decremented once, a repeated release is a no-op, zero is clamped, cleanup grace is set only when the resulting count is zero, and owner/tombstone filters prevent cross-owner release.

- [ ] **Step 5: Implement release and verify GREEN**

  Match only documents containing the task UUID and use `$max: [0, reference_count - 1]`; remove the token with `$setDifference`. Run the full file-record lifecycle test file.

### Task 2: Durable scheduled-task ownership state

**Files:**
- Modify: `src/kernel/schemas/scheduled_task.py`
- Modify: `src/infra/scheduler/storage.py`
- Test: `tests/infra/scheduler/test_storage.py`

**Interfaces:**
- Adds task fields: `attachment_keys`, `pending_attachment_claim_keys`, `pending_attachment_release_keys`, and `attachment_setup_pending`.
- Produces storage transitions that begin a claim, commit desired attachment state, mark deletion, clear completed pending keys, list reconciliation candidates, and finalize only released deleted tasks.

- [ ] **Step 1: Write failing schema/storage transition tests**

  Test literal Mongo filters/pipelines and returned task state: pending claims are persisted before file mutation; commit atomically replaces input/current keys, clears pending claims, and unions removed keys into pending release; delete disables and soft-deletes before release; physical delete requires empty pending sets.

- [ ] **Step 2: Run storage tests and verify RED**

  Run: `uv run pytest tests/infra/scheduler/test_storage.py -k attachment -vv`

  Expected: failures for missing schema fields and transition methods.

- [ ] **Step 3: Implement the minimal storage transitions**

  Use `find_one_and_update(..., return_document=ReturnDocument.AFTER)` so each transition is atomic and returns the durable state the service must act on. Bump the scheduler-definition revision only when a transition modifies a document.

- [ ] **Step 4: Run complete scheduler storage tests and refactor while green**

  Run: `uv run pytest tests/infra/scheduler/test_storage.py -vv`

### Task 3: Create/update/delete and recovery orchestration

**Files:**
- Modify: `src/infra/scheduler/locks.py`
- Modify: `src/infra/scheduler/service.py`
- Test: `tests/infra/scheduler/test_service.py`
- Test: `tests/infra/scheduler/test_runner.py`

**Interfaces:**
- Adds a short-lived per-task mutation lock separate from execution locks.
- Produces: `ScheduledTaskService.reconcile_attachment_references() -> int`.
- Consumes the Task 1 lease API and Task 2 durable transitions.

- [ ] **Step 1: Write RED tests for create ownership and rollback**

  Prove create persists pending claim state before claiming, returns a finalized definition only after successful claim, releases newly claimed keys on insert/finalize failure, and on registration failure soft-deletes before releasing. Assert a task scheduled beyond the 15-minute grace still has its definition lease.

- [ ] **Step 2: Implement create flow and verify GREEN**

  Extract unique keys from `input_payload.attachments`, allocate the UUID before claiming, use `attachment_setup_pending=True` while non-runnable, and compensate in reverse durable order on exceptions and cancellation.

- [ ] **Step 3: Write RED tests for update/delete/retry semantics**

  Cover add-before-remove ordering, no-op duplicate keys, removed-key pending release, retry after partial release, pause/date completion retention, owner propagation, and delete's soft-delete/release/finalize ordering. Verify retries never decrement twice.

- [ ] **Step 4: Implement update/delete under the mutation lock and verify GREEN**

  Persist pending claims before file mutation; on update commit the new payload and pending releases atomically; on delete mark `DELETED` and disabled before releasing. Drain pending releases idempotently, then clear them/finalize deletion.

- [ ] **Step 5: Write RED recovery tests and implement reconciliation**

  Reconciliation rolls back interrupted pending claims, adopts attachment keys on legacy active or paused task documents, retries pending releases, and finalizes released deleted tasks. It must never release a key currently listed in `attachment_keys`.

- [ ] **Step 6: Run service and runner suites**

  Run: `uv run pytest tests/infra/scheduler/test_service.py tests/infra/scheduler/test_runner.py -vv`

### Task 4: Bounded production cleanup lifecycle

**Files:**
- Create: `src/infra/upload/cleanup.py`
- Modify: `src/infra/upload/file_record.py`
- Modify: `src/infra/runtime_services.py`
- Test: `tests/infra/test_file_record_cleanup.py`
- Test: `tests/infra/test_runtime_services.py`

**Interfaces:**
- Produces: `run_file_record_cleanup() -> int` and `close_file_record_cleanup() -> None`.
- Registers runtime job id `upload.file_records.cleanup` with immediate first run and a fixed interval.

- [ ] **Step 1: Write RED tests for bounded cleanup and retryable tombstones**

  Prove each invocation deletes at most 100 records, object failures clear exact tombstones, and stale tombstones become claimable after their lease expires.

- [ ] **Step 2: Implement cleanup wrapper and stale-tombstone lease**

  The wrapper owns only its `FileRecordStorage` instance, lazily obtains shared object storage, and logs its deleted count. Closing it cancels only its index task/collection reference and does not close MongoDB or S3 clients.

- [ ] **Step 3: Write RED runtime lifecycle tests**

  Prove startup reconciles scheduled definitions before scheduler start, registers cleanup when `ENABLE_SCHEDULED_TASK` is false, starts the runtime scheduler once, and shutdown stops jobs before closing the cleanup wrapper.

- [ ] **Step 4: Register/start/close the job and verify GREEN**

  Run: `uv run pytest tests/infra/test_file_record_cleanup.py tests/infra/test_runtime_services.py -vv`

- [ ] **Step 5: Run affected backend tests and static checks**

  Run:

  ```bash
  uv run pytest tests/infra/test_file_record_storage_lifecycle.py tests/infra/scheduler tests/infra/test_runtime_services.py tests/api/routes/test_upload_owner_scope.py -vv
  uv run ruff check src/infra/upload src/infra/scheduler src/infra/runtime_services.py src/kernel/schemas/scheduled_task.py tests/infra/test_file_record_storage_lifecycle.py tests/infra/scheduler tests/infra/test_runtime_services.py
  uv run mypy src/infra/upload src/infra/scheduler src/infra/runtime_services.py src/kernel/schemas/scheduled_task.py
  ```

- [ ] **Step 6: Review scope and commit**

  Inspect `git diff --check`, `git status --short`, and the staged diff. Stage only the files listed in this plan, excluding `tests/infra/session/test_attachment_cleanup.py`, then commit with `fix(scheduler): retain task attachments and reclaim files`.
