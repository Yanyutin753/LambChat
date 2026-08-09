# Large Backend Module Split Design

## Goal

Reduce every backend source file reported by `frontend/scripts/find-large-files.ts` to no more than 1000 lines without changing artifact-delivery or trace-storage behavior, public imports, persistence formats, or runtime lifecycle.

## Current Structure

Two backend modules exceed the repository threshold:

- `src/infra/agent/middleware/artifact_delivery.py` contains artifact data models, path and result parsing helpers, middleware orchestration, workspace snapshots, background delivery, presenter emission, and payload construction.
- `src/infra/session/trace_storage.py` contains trace lifecycle and index management, trace writes, token usage reconciliation, trace/session queries, cleanup, and singleton lifecycle.

Existing callers import `ArtifactDeliveryMiddleware`, `TraceStorage`, `get_trace_storage`, and `close_trace_storage` from their current modules. Tests also monkeypatch selected module-level settings, so those compatibility seams must remain effective.

## Design

### Artifact delivery

Create `src/infra/agent/middleware/_artifact_delivery_support.py` for the internal data and parsing layer:

- `RevealTool`;
- artifact and per-run state dataclasses;
- URL, path, content, file-info, and reveal-result normalization helpers;
- constants used exclusively by those helpers and dataclasses.

Keep `ArtifactDeliveryMiddleware` and all orchestration methods in `artifact_delivery.py`. Import the extracted private names back into that module so its existing class implementation and incidental private imports continue to resolve. Keep background-drain timing constants in `artifact_delivery.py`, because tests monkeypatch them through that module.

This is a dependency-direction split: the public middleware entry module depends on a private support module, while the support module does not import the middleware.

### Trace storage

Create `src/infra/session/_trace_storage_support.py` for helpers shared by retained read methods and extracted write methods. `trace_storage.py` will import these private helpers back into its module namespace, preserving existing internal/test imports. This support module may depend on `settings`, but it will not import `trace_storage.py`.

Create `src/infra/session/trace_storage_writes.py` with `TraceStorageWriteMixin`. Move the cohesive write path into it:

- `create_trace`;
- `append_event`;
- `set_run_recommend_questions`;
- token usage event reconciliation;
- `complete_trace`.

Keep `_write_usage_log` in `trace_storage.py` because existing tests call it there and monkeypatch `trace_storage.get_trace_storage`. `TraceStorageWriteMixin.complete_trace` will resolve `_write_usage_log` with a function-local import only when scheduling the post-completion task. This preserves the monkeypatch seam and avoids an import-time cycle.

`TraceStorage` will inherit `TraceStorageWriteMixin` before `TraceEventChunkMixin` and will continue to own collection properties, index setup, event merger startup, reads, deletes, close, and singleton access. The mixin will use the same storage attributes and chunk-mixin methods as the current class, so no forwarding layer or new runtime object is introduced.

Helpers and constants whose monkeypatch behavior is part of current tests either stay in `trace_storage.py` or are re-exported there. `_normalize_recommend_questions`, event chunk index/preview helpers, and their shared limits live in `_trace_storage_support.py`; the retained read path and write mixin both import them from that one owner. The mutable `SESSION_EVENT_FILTER_LIST_LIMIT` stays in `trace_storage.py`, where retained query methods resolve it at call time. Imports from `trace_storage.py` remain unchanged for all production callers.

## Compatibility Constraints

- Preserve the current import locations and public class/function names.
- Preserve method signatures and return values.
- Preserve MongoDB queries, projections, updates, collection selection, event shapes, and ordering.
- Preserve background task scheduling, cancellation, timeout, and error-isolation behavior.
- Preserve test monkeypatch points in `artifact_delivery.py` and `trace_storage.py`.
- Avoid circular imports between entry modules and extracted modules.
- Do not perform unrelated cleanup or behavior changes while moving code.

## Testing Strategy

Implementation follows red-green-refactor:

1. Add a source-structure regression test alongside the existing frontend script and run it in the Node-enabled frontend test context. It will assert that backend source files are no more than 1000 lines without introducing a pnpm/Node dependency into backend pytest. Confirm it fails against the current two files.
2. Extract artifact support code, then run the complete artifact-delivery middleware test module.
3. Extract trace support helpers and write operations, then run trace storage lifecycle, event chunk, token usage, recommendation, and usage-log write test modules.
4. Run Ruff and targeted Mypy checks on all changed Python modules.
5. Run the repository large-file script again and verify every reported section is empty.

The existing behavioral suites are the primary regression contract because this change is structural. The new structure test prevents the exact line-count regression that motivated the work.

## Scope

This work will not change artifact selection, reveal behavior, trace schemas, event compatibility, index definitions, query limits, logging semantics, or frontend behavior. It will not split files further than needed to keep every source file at or below the configured threshold.
