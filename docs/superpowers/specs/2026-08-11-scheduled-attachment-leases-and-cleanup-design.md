# Scheduled Attachment Leases and Cleanup Design

**Date:** 2026-08-11
**Status:** Approved

## Problem

Uploaded file records receive a fifteen-minute cleanup deadline, and the storage layer can
atomically tombstone and delete overdue zero-reference records. No production lifecycle calls
that cleanup method, so abandoned uploads are never reclaimed. Enabling the cleaner as-is would
expose a second defect: scheduled-task definitions persist attachment keys without owning a
reference, so a task whose next run is more than fifteen minutes away can lose its backing object.

Each scheduled execution already claims a separate message reference when its user message is
persisted. The missing ownership is therefore the task definition's lifetime, not the run's
lifetime.

## Considered approaches

1. Refresh cleanup deadlines before each scheduled run. This is small, but it cannot protect the
   gap between task creation and the first run and makes correctness depend on timer timing.
2. Increment and decrement the existing counter directly in service methods. This protects the
   definition, but retries, concurrent updates, and crashes between task/file-record writes can
   double-release or leak references.
3. Give each task a durable, idempotent definition lease and persist pending releases. This adds
   small schema/storage primitives but makes claim and release retry-safe. This is the selected
   design.

## Ownership invariant

A persisted scheduled-task definition owns exactly one reference lease per unique attachment key.
The lease token is derived from the task UUID and is stored on the owned file record. Claiming an
existing token is a no-op. Releasing a missing token is a no-op. The numeric `reference_count` is
incremented only when a new token is inserted and decremented with a zero clamp only when that
token is removed.

The definition lease remains held while the task document exists, including while it is paused or
after a one-time date task completes. Those definitions remain visible configuration and may be
resumed or inspected, so their attachment relationship is still live. Ownership ends only when an
update removes a key or deletion removes the definition. Each execution, including retries, keeps
using the existing independent persisted-message claim.

Attachment extraction uses unique non-empty keys and fails closed above the existing 100-key
limit. Every file-record mutation is scoped by `uploaded_by` and excludes tombstoned records.

## Create, update, and delete flow

Create validates the trigger and attachment set, allocates the task UUID, and claims the desired
definition leases before persistence. A persistence failure releases only tokens newly inserted by
that create attempt. If scheduler registration fails after persistence, the service rolls back the
document first and releases the leases only after the rollback is confirmed; an uncertain live
document keeps its leases.

Update claims the full desired set before exposing the new payload. The task update atomically
stores the desired attachment keys, retains the union of tokens that may still exist, and records
removed keys in a durable pending-release set. The service then idempotently releases pending
tokens and clears only the completed pending entries. A later reconciliation retries any entries
left by exceptions, cancellation, or process death. This ordering never drops a live definition
token.

Delete first unregisters and atomically marks the definition deleted/disabled while moving every
held key to the durable pending-release set. It then releases those tokens and physically removes
the definition only after the pending set is empty. Deleted tasks are excluded from listing and
execution during recovery. Reconciliation finishes interrupted deletes. Repeated update/delete or
release attempts are harmless because token removal is idempotent and the counter cannot go below
zero.

## Production cleanup lifecycle

The existing process-local runtime scheduler receives an always-registered file-record cleanup
job independent of `ENABLE_SCHEDULED_TASK`. Its handler obtains the shared S3 service through the
infrastructure entry point and processes at most the existing batch limit of 100 records per run.
MongoDB's atomic tombstone claim arbitrates multiple application instances.

The runtime scheduler starts after listener and storage initialization even when scheduled tasks
are disabled. Shutdown stops scheduled jobs before closing the shared S3 and MongoDB clients. The
cleanup-specific `FileRecordStorage` wrapper is closed without closing either shared client.

## Verification

Strict red-green-refactor tests cover owner-scoped idempotent token claims, partial rollback,
bounded keys, idempotent release and zero clamping; create rollback and registration failure;
update add/remove/no-op and pending-release retry; delete interruption and retry; pause/date-task
retention; independent run-message claims across retries; cleanup job registration when scheduled
tasks are disabled; bounded cleanup execution; and scheduler shutdown ordering. Focused scheduler,
file-record, runtime-service, and upload tests run before Ruff and MyPy.
