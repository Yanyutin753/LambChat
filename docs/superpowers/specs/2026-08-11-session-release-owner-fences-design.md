# Session Release Owner Fences Design

## Goal

Prevent a delayed session-clear releaser from decrementing a file again after
another caller has completed the same clear group and compacted its idempotency
marker.

## Root cause

The session group's `deleted -> released` CAS orders status writers, but it does
not fence a Mongo file-record command that an older caller already issued. If a
new caller observes `deleted`, releases idempotently, changes the group to
`released`, and removes the marker, the older command can arrive afterward and
match the now marker-free record. It decrements twice and recreates the marker.

## Group owner lease

Every `deleted` group must be claimed before file mutation. The durable group
stores `release_owner_token`, a globally comparable positive
`release_owner_epoch`, and `release_owner_expires_at`; its status becomes
`releasing`.

- A token retry returns its already-bound epoch without allocating another.
- A missing or expired owner may be replaced. Replacement always receives a
  higher epoch from an atomic Mongo counter in a dedicated metadata collection.
- Counter reply loss consumes an unused gap. Binding reply loss is resolved by
  rereading the exact token and epoch.
- A heartbeat renews only the exact token/epoch. A crash stops renewal and makes
  takeover possible after expiry.
- Only the exact token/epoch may transition `releasing -> released` or perform
  terminal marker cleanup.

## File-record live marker

Each file retains one scalar `session_release_epoch_high_water` plus only the
currently necessary live operation markers:

```text
session_release_operations: [{operation_id, epoch, applied}]
```

After acquiring a group owner, the caller first adopts its epoch on every key.
Adoption creates the live marker with `applied=false`, or advances the same
operation to a takeover epoch while preserving `applied`. A stale epoch cannot
replace a newer live marker. If an operation has no live marker and its epoch is
not above the compacted scalar, adoption fails closed; the manager must obtain a
newer owner epoch before release.

Release matches the exact operation ID and epoch. It decrements only when
`applied=false`, then atomically sets `applied=true`; retries and takeover do not
decrement again. A takeover adopts every key before relying on the old owner
being fenced, so either the old release wins first and the new marker preserves
`applied=true`, or the higher epoch wins first and the old release cannot match.

After the exact owner durably changes the group to `released`, cleanup removes
the exact live marker and raises `session_release_epoch_high_water` to its epoch.
Delayed commands then fail even though the operation ID is no longer stored.
Concurrent unrelated operations remain represented by their live markers until
their own groups complete, so out-of-order completion is safe.

## Cancellation and completion

The manager runs claim, adopt, release, owner-CAS transition, and cleanup as a
safety-critical child operation with a heartbeat. Repeated cancellation of the
request waiter cannot interrupt it. The heartbeat is stopped and drained after
the child reaches a terminal result. The clear operation completes only when
every group is `released` with its exact live marker compacted, or `survivor`.

## Verification

- Two callers reproduce the old race from reference count 2 and finish at 1,
  with no live marker left.
- Expired-owner takeover binds a higher global epoch and fences the old release.
- Counter and owner-binding reply loss are gap-safe and idempotent.
- Repeated cancellation cannot interrupt release fencing or marker cleanup.
- 1,100 sequential completed operations leave an empty live-marker array and a
  single scalar high-water value.
