# Background Run Recommendations Design

## Goal

Generate follow-up question recommendations only after the current agent has produced its final `output_text`, without delaying the main agent run, and persist those recommendations on the trace document associated with the run.

## Chosen approach

Each completed agent node captures its final `output_text` and schedules one bounded process-local background task. The task reads the graph checkpoint for recent history, generates recommendations using the current user input plus final assistant output, persists them as the run trace's `recommend_questions` field, and publishes a small `recommend:questions` WebSocket notification to the owning user.

The main agent never awaits recommendation generation. Existing background-task limits and shutdown draining remain in place so recommendation work cannot grow without bounds or leak during process shutdown.

## Persistence and compatibility

The trace document is already the one-to-one persisted record for a `session_id` and `run_id`. It gains these bounded fields:

- `recommend_questions`: up to three non-empty question strings.
- `recommend_questions_updated_at`: the server timestamp of the latest successful write.

New writes do not append late recommendation events to a completed trace. Session event reads synthesize the existing `recommend:questions` event shape from the run field when no legacy `recommend:questions` or `followup:questions` event exists. Old traces that only contain recommendation events remain unchanged and readable. This keeps the frontend history contract stable without duplicating new recommendation data in the large events array.

The run summary endpoint exposes `recommend_questions` directly. Reads accept both the new list field and a defensive object form containing `questions`, while legacy event records remain the fallback format.

## Realtime delivery

The existing authenticated, distributed WebSocket manager sends:

```json
{
  "type": "recommend:questions",
  "data": {
    "session_id": "...",
    "run_id": "...",
    "questions": ["...", "...", "..."]
  }
}
```

The shared frontend WebSocket hook recognizes this message. `ChatAppContent` ignores notifications for other sessions and asks `useAgent` to upsert a recommendation part onto the assistant message matching the `run_id`. The existing renderer then displays it once the message is no longer streaming. Duplicate WebSocket delivery or a later history reload replaces the same recommendation part rather than adding another one.

## Failure behavior

Recommendation model, persistence, or WebSocket failures are best-effort and logged without changing the main run status. Model failures retain the existing deterministic recommendation fallback. A missing active WebSocket is not an error because the persisted run field will restore recommendations on the next history load.

## Performance

- Recommendation LLM calls start only after final output is available and run outside the main agent path.
- Concurrency remains capped by `RECOMMEND_QUESTIONS_MAX_BACKGROUND_TASKS`.
- Persistence is one indexed `session_id + run_id` update with a three-item bounded payload.
- History compatibility uses fields already projected by the trace query and adds no per-run database query.
- WebSocket messages are small and reuse the existing cross-instance user routing.

## Tests

Backend tests cover final-output scheduling, non-blocking behavior, atomic run-field persistence, WebSocket payloads, old-event deduplication, and synthesized history events. Frontend tests cover WebSocket dispatch and idempotent run-based message updates. Existing recommendation, presenter, trace-storage, session-route, and frontend event-processing tests remain regression coverage.
