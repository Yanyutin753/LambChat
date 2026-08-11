# Bounded File Reference Fences Design

## Goal

Keep file-record idempotency and scheduled-task mutation fencing bounded without
allowing a delayed stale claim or release to resurrect or delete a reference.

## Scheduled-task mutation epoch

Scheduled-task attachment mutations use a globally comparable positive integer
epoch allocated from the scheduler metadata collection with an atomic MongoDB
`$inc`. Redis remains only the serialization lease; it is not the authority for
ordering.

`claim_attachment_mutation(task_id, token)` behaves as follows:

1. If the task already stores the same token and a positive epoch, return that
   fence unchanged. This is the idempotent retry path.
2. Otherwise atomically increment the global scheduler attachment epoch.
3. CAS-bind the returned epoch and token to the task document, replacing the
   previous fence only if its snapshot still matches.
4. If the counter reply is lost, retrying may consume another epoch. Gaps are
   safe. An epoch is usable only after it is durably bound to the task.
5. If the task CAS reply is lost, reread the exact token and epoch; return it
   only when the binding is confirmed.

The existing `attachment_mutation_generation` field becomes the global epoch,
so existing service interfaces remain token-plus-generation fences while their
ordering becomes global.

## File-record representation

Each file record stores:

- `scheduled_task_reference_generations`: live references only, one entry per
  task ID with its currently bound global epoch;
- `scheduled_task_reference_ids`: the matching bounded live task IDs, retained
  for compatibility and count updates;
- `scheduled_task_generation_high_water`: the greatest global epoch observed by
  a successful claim, adoption, or release.

The high-water scalar replaces retired per-task tombstones.

Claim rules:

- a new live task reference is accepted only when its epoch is greater than the
  high-water mark;
- an exact retry at the high-water mark is accepted only when the same task ID
  already owns the live entry at that epoch;
- every lower epoch and every same-epoch different task is rejected;
- advancing an existing task to a newer epoch does not increment the reference
  count;
- every successful claim raises the high-water mark.

Adoption raises the high-water mark and advances the matching live entry when
present, but never creates a live reference. This fences an ambiguous older
claim even when that claim never reached the file record.

Release removes only a matching live task/epoch entry, decrements the count
once, and raises the high-water mark. A retry after removal cannot match and is
therefore idempotent. Since every later task mutation receives a greater global
epoch, compacting retired UUIDs into the scalar cannot permit resurrection.

Legacy records without a high-water field derive their initial high-water from
the maximum valid live generation entry. Existing live references therefore
remain usable during rolling deployment.

## Session release-operation compaction

`applied_release_operations` remains the atomic per-file idempotency marker
while a clear group is pending. Once the session document durably records that
group as `released`, retries no longer call `release_reference_counts` for that
group. At that point the manager removes the operation ID from every file in the
group.

The session clear operation may complete only after all released groups have
successfully forgotten their operation IDs. Partial `$pull` cleanup is
idempotent. If cleanup fails or the process crashes, the durable released group
remains and the next retry resumes marker cleanup without decrementing again.

## Failure behavior

- Counter reply loss may create an unused gap, never an ambiguous usable epoch.
- Task-fence binding reply loss is resolved by exact token/epoch reread.
- Stale file mutations fail closed against the high-water mark.
- Marker cleanup failure retains the session clear operation for retry.
- File records that have already disappeared make marker cleanup a successful
  no-op because no future decrement can target them.

## Tests

- Thousands of random scheduled task claim/release cycles leave no retired live
  entries and one scalar high-water mark.
- An arbitrary old task claim is rejected after compaction; a newly bound global
  epoch succeeds.
- Counter reply loss consumes a gap, then binds one confirmed epoch; retrying the
  same token does not increment again.
- Thousands of completed session release operations leave no historical IDs.
- Crashes before and during marker cleanup retry without double decrement and
  without completing the clear operation early.

