# Session Trace Cleanup Guard Design

**Date:** 2026-08-11
**Status:** Approved

## Problem

Late trace compensation checks that a session is delete-fenced, then deletes
trace chunks and parent traces in separate MongoDB collections. The delete
fence can currently be cancelled between that check and either delete. A new
writer can then enter the session and update the same trace before the stale
compensator deletes it.

An expiring session guard alone does not close the race. A cleanup owner can
block inside a MongoDB delete until its guard expires. A replacement owner can
then claim and release the guard, the delete fence can be cancelled, and a new
writer can update the same trace before the old delete reaches MongoDB.

## State model

Cleanup ownership is nested in the existing server-only delete operation:

```text
attachment_delete_operation = {
  id,
  claimed_at,
  cleanup_guard: {
    id,
    writer_lease_id,
    expires_at,
  },
  cancel_requested,
}
```

The guard is valid only when all required fields have the exact expected
types. A malformed guard fails closed and is never automatically removed.
The expiry permits a new cleanup owner to replace a crashed owner's guard by
compare-and-set. An old token cannot release or mutate the replacement.

## Transitions

1. A compensator whose writer lease is lost claims an exact guard only while
   the pinned session anchor still has a valid delete operation. A missing
   anchor needs no guard and may be cleaned directly.
2. While an unexpired guard exists, writer acquisition, another delete claim,
   and deletion of the session anchor fail closed.
3. Cancelling the matching delete operation while the guard is active sets
   `cancel_requested` and leaves the delete fence in place.
4. The guard owner deletes chunks and parent traces while holding the token.
5. Exact release matches both delete-operation ID and guard ID. Without a
   pending cancel it removes only the guard. With a pending cancel it removes
   the whole delete operation atomically, opening the session only after the
   cross-collection cleanup is finished.
6. A valid expired guard may be replaced by a new cleanup owner. A retry of
   delete cancellation may instead remove the expired guard and delete fence.

## Cross-collection version fence

Before issuing either delete, a guarded cleanup freezes both target
collections into exact document snapshots. Parent snapshots contain `_id`,
`session_id`, `trace_id`, `event_revision`, and `updated_at`. Chunk snapshots
contain `_id`, `session_id`, `trace_id`, `append_fence_revision`, `event_count`,
and `updated_at`. Missing version fields are represented by exact
`$exists: false` predicates rather than broad matches.

After both snapshots complete and before either delete begins, cleanup renews
the same unexpired guard by compare-and-set on the delete-operation ID, guard
ID, writer-lease ID, expiry, and cancel state. It must not revive an expired or
replaced guard. A failed renewal aborts without deleting either collection.

Both deletes match only the frozen `_id` and version predicates. If a guard is
replaced while a delete is blocked, a new writer either updates the parent and
chunk version fields or recreates a document under a different `_id`; the old
delete therefore cannot remove the new write. An unchanged old-generation
document may still be removed safely. The exact guard release remains the
authority for applying a pending delete-fence cancellation.

The established missing-anchor path retains direct broad cleanup: the pinned
session identity is absent and cannot be reopened under the same authority.

## Safety invariants

- No writer can enter between chunk deletion and parent deletion.
- A cleanup whose snapshot phase outlives its guard performs no deletes.
- A cleanup blocked after exact renewal cannot delete a later-generation write.
- Cancelling a delete fence cannot expose a session while cleanup is active.
- Session-anchor deletion cannot race an active cleanup guard.
- Release and takeover are token-owned; forged or stale tokens have no effect.
- Malformed state is preserved for operator recovery and blocks every unsafe
  transition.
- Missing anchors retain the established direct-cleanup behavior.

## Verification

Tests deterministically block chunk deletion after guard acquisition, request
delete cancellation, and prove that writer admission, a second delete claim,
and anchor deletion remain blocked. After both collections are cleaned, exact
release applies the pending cancellation and a new writer may enter. Separate
tests cover expired-guard takeover, stale-token release, direct cleanup for a
missing session, and malformed guard shapes across the full lifecycle.

Additional tests block the snapshot phase across expiry and prove that no
delete begins after failed exact renewal. A second interleaving blocks the
first exact delete, replaces and releases the guard, cancels the fence, writes
the same trace under a new lease, and proves that both the new parent version
and any new chunk version survive the stale cleanup.
