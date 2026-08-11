# Session Trace Cleanup Guard Design

**Date:** 2026-08-11
**Status:** Approved

## Problem

Late trace compensation checks that a session is delete-fenced, then deletes
trace chunks and parent traces in separate MongoDB collections. The delete
fence can currently be cancelled between that check and either delete. A new
writer can then enter the session and update the same trace before the stale
compensator deletes it.

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

## Safety invariants

- No writer can enter between chunk deletion and parent deletion.
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
