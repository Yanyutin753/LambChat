# Hide Internal IDs from the Memory Index

## Problem

The native memory index currently renders the first six characters of each
`memory_id` beside its human-readable label. These identifiers do not help the
model understand the memory and add noise to every injected index entry.

For example, the current output is:

```text
- 团队路由器通知 (1067c7, stale:76d)
```

## Approved Output

Remove the internal ID while preserving useful age and staleness metadata:

```text
- 团队路由器通知 (stale:76d)
```

Fresh entries without age metadata contain only the display label. Entries
with relative age metadata keep that metadata in parentheses.

## Implementation

Update `build_memory_index` in
`src/infra/memory/client/native/indexing.py` so each selected memory is rendered
from its display label and optional age string only. Remove `memory_id` from the
MongoDB projection because index rendering no longer consumes it.

Selection, type grouping, ordering, labels, age calculation, staleness
thresholds, cache behavior, and recall behavior remain unchanged.

## Testing

Add focused tests in `tests/infra/memory/native/test_indexing.py` that first
demonstrate the current failure and then verify:

- a stale entry renders its label and staleness metadata without any internal
  ID;
- a same-day entry renders only its label without empty parentheses or an ID;
- existing memory-type ordering remains intact.

Run the focused indexing tests, followed by the relevant native-memory test
suite if the focused tests pass.

## Scope

This change affects only the model-facing `<memory_index>` prompt text. It does
not change memory records, public memory APIs, recall-tool results, the Memory
Space UI, or deletion/update operations that legitimately require full IDs.
