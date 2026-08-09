# Session History Loading Optimization Design

## Goal

Make opening an existing session feel immediate while still loading and displaying the complete session history. A running session must never reveal an assistant placeholder before its corresponding user message.

## Root causes

The current frontend waits for `mark-read`, then fetches the session, then blocks first render on the slowest of events, status, and feedback. The session, events, and status routes each repeat session lookup and authorization work. Clicking a sidebar item also delays the route update until history finishes loading.

The storage path first lists all traces and then reads every trace sequentially. Chunked traces require multiple MongoDB probes per trace, so latency grows with the number of runs even when the total event payload is modest.

For an active run, the events route excludes the running trace. The initial user message is already persisted in that trace, but the frontend cannot see it after a refresh. `prepareMessagesForRunningRun` then creates an empty streaming assistant message even when no user message for that run exists, producing the observed assistant-only state.

## Chosen approach

Keep the product's full-history behavior. Replace the multi-request critical path with one full-history bootstrap request, batch event reads across every trace, and move nonessential work out of the rendering gate. This retains all messages instead of introducing pagination, truncation, or a "load older" interaction.

### Bootstrap API

Add `GET /api/sessions/{session_id}/history` with an optional `run_id` query parameter. The response contains:

```json
{
  "session": {},
  "events": [],
  "active_run": {
    "run_id": "...",
    "status": "running",
    "error": null
  }
}
```

`session` is the same normalized session representation returned by the existing session detail route. `events` contains the complete chronological history. `active_run` is null when there is no selected/current run and otherwise describes the run requested by `run_id` or the session's `current_run_id`.

The route performs one session lookup and ownership check. For the current run, status and error come from the already loaded session metadata when available. A non-current requested run may use the existing task status query internally, but it does not add another client round trip.

Existing session detail, events, and status endpoints remain supported for other consumers. The new endpoint is an additive optimized read contract.

### Batched event storage reads

Add a batch-compatible trace event reader used by full session history:

1. Query all matching trace summaries once in chronological order, including legacy embedded `events` needed for compatibility.
2. Query all chunk documents for those trace IDs once, ordered by trace and `chunk_index`.
3. Group chunks in memory and reconstruct each trace in chronological sequence.
4. When a trace has chunks beginning after sequence 1, preserve the legacy prefix below the first chunk sequence.
5. Apply event-type filters, event limits, recommendation synthesis, and run metadata with the same semantics as the existing per-trace reader.

This changes the normal full-history read from a number of MongoDB round trips proportional to the run count to a constant number of collection reads. It must support sessions containing only legacy traces, only chunked traces, or a mixture of both.

No event count limit or pagination is added to the new history endpoint. The existing response-limit behavior on the old events endpoint is unchanged.

### Active-run message consistency

When `active_run.status` is one of `queued`, `pending`, `starting`, `running`, `cancelling`, or `recovering`, the bootstrap history includes the active trace's persisted `user:message` event but excludes its assistant/tool lifecycle events. Those events continue through SSE and therefore are not duplicated by the bootstrap response.

All other traces contribute their complete event history. The active user event is merged by chronological event identity so a status transition during the request cannot duplicate it.

The frontend may create or mark a streaming assistant message only when a user message for the same run already exists. If the active user event is unexpectedly absent, the UI keeps the history/skeleton state free of an assistant-only bubble and connects to SSE. The SSE `user:message` handler inserts the user message first and, only then, creates the matching assistant stream target when it is missing. Later assistant events therefore have a target without violating message order.

Queued and other nonterminal states receive the same reconnect treatment as `pending` and `running`; terminal states do not reconnect.

### Frontend loading flow

`sessionApi.getHistory` accepts an `AbortSignal`. `useAgent.loadHistory` owns a history-request abort controller separate from the long-lived SSE controller. Starting another session load aborts the previous HTTP request in addition to retaining the existing request-ID stale-result guard.

The critical path is:

1. Clear the old message frame and show the history skeleton.
2. Start the bootstrap request.
3. Start `mark-read` and feedback reads without awaiting them.
4. Reconstruct and commit all history as soon as bootstrap completes.
5. Restore session configuration and connect SSE for a nonterminal active run.
6. Apply feedback to matching run messages later, only if the same history request is still current.

Sidebar selection navigates to `/chat/{session_id}` immediately and then loads history. Existing internal-navigation guards prevent the URL effect from issuing a duplicate request. Failed loads retain the selected URL and show the existing localized request error instead of silently returning to the previous session.

The existing skeleton and history-scroll settling behavior stays in place so the complete Virtuoso list is not exposed mid-measurement. The optimization shortens the time before that single stable reveal; it does not progressively reveal partial history.

## Error and race behavior

- An aborted or stale bootstrap request cannot set messages, session configuration, errors, loading state, feedback, or an SSE connection.
- Mark-read and feedback failures are best-effort and do not delay or fail history display.
- A bootstrap failure clears the loading state and uses the existing localized request failure message.
- SSE is started only after the baseline event timestamp and processed-event state are installed, preserving duplicate suppression.
- Switching sessions aborts both the old history request and the old SSE connection.

## Compatibility and scope

- Full session history remains the user-visible behavior.
- Legacy embedded trace events, chunked events, mixed migrations, recommendation compatibility events, feedback, goals, attachments, approvals, and run-based SSE reconstruction remain supported.
- Existing API consumers do not need to migrate.
- This work does not add caching, prefetch-on-hover, history pagination, message truncation, or database migration. Those features are unnecessary for the reported session sizes and would introduce invalidation or interaction complexity.

## Verification

Backend tests cover the bootstrap response, one ownership lookup, current-run status selection, all nonterminal statuses, active user inclusion without active assistant duplication, batch query counts, chronological ordering, event filters, recommendation synthesis, and legacy/chunked/mixed trace compatibility.

Frontend tests cover the single-request critical path, nonblocking mark-read and feedback, request cancellation and stale-result isolation, immediate navigation, complete history reconstruction, queued/running reconnects, active user-before-assistant ordering, absence of assistant-only placeholders, SSE fallback insertion, and delayed feedback application to only the active session.

Focused frontend and backend suites run first. Final verification includes frontend lint/build/tests and the repository's cross-stack checks appropriate to the touched API, storage, and UI paths.
