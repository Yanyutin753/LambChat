# Session History Loading UX Optimization Design

## Goal

Make opening an existing session feel immediate while still loading and displaying its complete history. Loading must be visually stable, and a running session must never reveal a real assistant placeholder before its corresponding user message.

The work is frontend- and user-experience-led. Backend changes are limited to the two things the frontend cannot solve alone: returning the persisted user message for an active run and avoiding run-by-run database latency.

## Root causes

The frontend currently waits for `mark-read`, then fetches the session, then blocks first render on the slowest of events, status, and feedback. The session detail and events requests could start together, while mark-read and feedback do not need to gate display. Clicking a sidebar item also delays URL navigation until history finishes, making the interface feel unresponsive even before network latency is considered.

For an active run, the events route excludes the running trace. The initial user message is already persisted there, but the frontend cannot see it after refresh. `prepareMessagesForRunningRun` then creates an empty streaming assistant message even when no user message for that run exists, producing the observed assistant-only state.

The storage path compounds the visible delay by first listing traces and then reading every trace sequentially. Chunked traces require multiple MongoDB probes per trace, so the events request becomes slower as the number of runs grows even when the complete message history is small.

## Chosen approach

Keep the product's full-history behavior and existing endpoints. Restructure the frontend loading state machine so only essential data gates the stable reveal, add explicit cancellation and immediate navigation, and enforce user-before-assistant ordering. Extend the existing events request with a narrowly scoped active-user option and batch its storage reads.

No pagination, truncation, "load older" control, cache invalidation layer, or replacement bootstrap endpoint is introduced.

## Frontend loading experience

### Immediate selection feedback

Selecting a sidebar session immediately:

1. marks the navigation as internal,
2. navigates to `/chat/{session_id}`,
3. aborts the previous history request and SSE connection,
4. clears the previous conversation frame, and
5. displays the existing alternating user/assistant conversation skeleton.

The skeleton is the only message-area content exposed during the full-history transition. Real messages are committed once as one complete reconstructed list, then the existing Virtuoso history-settling overlay remains until bottom measurement is stable. The UI never progressively reveals a partial set of real history.

The URL effect must not issue a duplicate load for this internal navigation. A failed load keeps the selected URL and shows the existing localized request error rather than silently returning to the previous session.

### Short critical path

`useAgent.loadHistory` starts the session-detail request and full events request concurrently. Both accept the same history `AbortSignal`. The normal critical path awaits only these two essential reads.

`mark-read` starts without being awaited. Feedback starts without being awaited and is applied later to matching run messages only if the history request is still current. Neither failure changes the history loading result.

Session metadata restores configuration but is not authoritative for deciding whether the returned event snapshot needs SSE completion. The events response carries that decision from the same trace snapshot used to select history events. A `run_id` URL parameter that differs from `metadata.current_run_id` is historical context and must never inherit the current run's status or trigger SSE reconnection.

The events response identifies either a complete snapshot or an active-user-only snapshot with a `stream_run_id`. The frontend reconnects only when `stream_run_id` is present. This covers `queued`, `pending`, `starting`, `running`, `cancelling`, and `recovering` without racing a separate session/status response. A complete snapshot or historical URL run never reconnects.

### Cancellation and stale-result isolation

History HTTP requests use a dedicated abort controller separate from the long-lived SSE controller. Starting another load aborts both the previous history request and previous SSE connection. The existing monotonically increasing request ID remains a second guard.

An aborted or stale request cannot set session identity, configuration, messages, goals, feedback, errors, loading flags, or an SSE connection. `AbortError` is silent; a current non-abort failure uses the existing localized request failure state.

## User-before-assistant invariant

The events request opts into receiving the active run's persisted `user:message`, while active assistant/tool lifecycle events remain excluded because SSE owns them.

History reconstruction may create or mark a streaming assistant message only when a user message for the same run already exists. `prepareMessagesForRunningRun` therefore returns a stream target without inserting an assistant bubble when the matching user is absent.

As a defensive fallback, the SSE `user:message` handler performs one atomic state update: it inserts or reconciles the user message first, then creates the matching streaming assistant target only if it does not already exist. The next assistant event can therefore update that target without any render containing an assistant-only pair.

User-message deduplication remains based on persisted `message_id` and `run_id`; content comparison remains only a legacy fallback. Baseline timestamps and processed-event state are installed before SSE starts so the active user event is not duplicated when the stream replays it.

## Minimal backend support

### Active user event option

Extend `GET /api/sessions/{session_id}/events` and `sessionApi.getEvents` with an additive boolean option such as `include_active_user_message`. When the option is enabled, the response also contains snapshot metadata:

```json
{
  "events": [],
  "history_mode": "complete",
  "stream_run_id": null
}
```

`history_mode` is `complete` or `active_user_only`. `stream_run_id` is always a `string | null`: it contains the active run ID only for `active_user_only` and is the sole frontend authority for history-time SSE reconnection.

When enabled and session metadata identifies a nonterminal current run, the response contains:

- complete events for all other traces, and
- only `user:message` events for the current active run.

It excludes all other active-run events. Trace status observed by the same initial trace query that selects event mode determines the response contract:

- A trace observed as terminal contributes its complete events and produces `history_mode: complete` with no stream run.
- A trace observed as nonterminal contributes only its user event and produces `history_mode: active_user_only` with its run ID, even if session metadata concurrently becomes terminal. SSE replay is then required to deliver the remaining events and terminal marker.

If a trace becomes terminal after the nonterminal snapshot is selected, the server must preserve a reliable replay path until the frontend receives the terminal event. Baseline timestamp deduplication makes replay of the already returned user event harmless. If a trace is already observed terminal, the full trace events are part of the stable reveal and no SSE dependency remains. These rules cover both transition orderings without losing the assistant response.

Events are merged by trace/run and event sequence so the user message is present once and a terminal trace is not duplicated. The option defaults to false so existing API consumers retain their current response metadata and behavior.

### Batched full-history storage read

The optimized events path:

1. queries matching trace documents once in chronological order, including legacy embedded events needed for compatibility;
2. queries all chunk documents for those trace IDs once;
3. groups chunks in memory and reconstructs each trace in chronological sequence;
4. preserves a legacy prefix when chunks begin after sequence 1; and
5. applies existing event filters, limits, recommendation synthesis, and run metadata.

This replaces MongoDB round trips proportional to run count with a constant number of reads. It must support all-legacy, all-chunked, and mixed sessions. The new frontend path requests all events with no limit, preserving complete-history behavior. Existing limit semantics remain unchanged for other consumers.

## Compatibility and scope

- Session history remains fully displayed in one stable reveal.
- The existing session detail, events, status, mark-read, feedback, and SSE endpoints remain available.
- Legacy embedded events, chunked events, mixed migrations, recommendations, feedback, goals, attachments, approvals, cancellation, and run-based SSE reconstruction remain supported.
- The existing conversation skeleton and Virtuoso settling behavior are retained and refined through state timing rather than visually redesigned.
- No database migration, pagination, message truncation, hover prefetch, or persistent frontend cache is added.

## Verification

Frontend tests cover immediate navigation, one load per selection, concurrent essential requests, nonblocking mark-read and feedback, abort propagation, stale-result isolation, one-shot complete-history commit, snapshot-directed reconnect behavior, historical `run_id` isolation, absence of assistant-only placeholders, atomic SSE fallback insertion, user-message deduplication, and delayed feedback applying only to the active session.

Backend tests cover the additive active-user option, one active user with no active assistant events, both active-to-terminal response orderings, replay-required snapshot metadata, complete terminal snapshots, status-transition deduplication, batch query counts, chronological ordering, limits and filters, recommendation synthesis, and legacy/chunked/mixed compatibility.

Focused frontend tests run after each TDD cycle. Final verification includes the relevant backend suite, full frontend tests, frontend lint and build, then cross-stack checks appropriate to the touched API, storage, and UI paths.
