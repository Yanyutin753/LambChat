# Session History Loading UX Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make full session history open responsively, reveal only one stable complete message list, and guarantee that a running assistant never appears before its user message.

**Architecture:** Keep the existing session and events APIs, but add an opt-in race-safe history snapshot to the events response. Batch MongoDB event reads across traces, then make the frontend run essential reads concurrently, defer mark-read/feedback, cancel stale loads, navigate immediately, and use snapshot metadata as the only reconnect authority.

**Tech Stack:** React 19, TypeScript, Vitest, FastAPI, Python 3.12, Motor/PyMongo, pytest

---

## File structure

- Modify `src/infra/session/trace_event_chunks.py`: batch compatibility reader for legacy and chunked trace documents.
- Modify `src/infra/session/trace_storage.py`: full-history snapshot value object and batched session-history assembly.
- Modify `src/infra/session/dual_writer.py`: expose the snapshot read through the existing storage facade.
- Modify `src/api/routes/session.py`: additive `include_active_user_message` query contract and snapshot metadata response.
- Modify `tests/infra/session/test_trace_event_chunks.py`: batch read, query-count, ordering, and compatibility coverage.
- Modify `tests/api/routes/test_session_runs.py`: route contract and active/terminal snapshot coverage.
- Modify `frontend/src/types/session.ts`: typed `history_mode` and `stream_run_id` response fields.
- Modify `frontend/src/services/api/session.ts`: abortable concurrent session/event API calls and active-user option.
- Create `frontend/src/hooks/useAgent/historyLoadState.ts`: pure helpers for reconnect selection and delayed feedback reconciliation.
- Create `frontend/src/hooks/useAgent/__tests__/historyLoadState.test.ts`: behavior tests for those helpers.
- Modify `frontend/src/hooks/useAgent/historyLoader.ts`: user-before-assistant preparation invariant.
- Modify `frontend/src/hooks/useAgent/eventHandlers.ts`: atomic SSE user/assistant insertion fallback.
- Modify `frontend/src/hooks/useAgent/sseConnection.ts`: per-connection controller and generation isolation across async token acquisition.
- Modify `frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts`: no assistant-only history state coverage.
- Modify `frontend/src/hooks/useAgent/__tests__/eventHandlers.test.ts`: SSE fallback ordering and deduplication coverage.
- Modify `frontend/src/hooks/useAgent/__tests__/sseConnection.test.ts`: stale connection generation race coverage.
- Modify `frontend/src/hooks/useAgent.ts`: frontend-led loading state machine, cancellation, concurrency, and deferred side effects.
- Modify `frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`: source-level critical-path and abort wiring guards.
- Modify `frontend/src/components/layout/AppContent/useSessionSync.ts`: immediate navigation before awaiting history.
- Modify `frontend/src/components/layout/AppContent/__tests__/useSessionSync.test.ts`: immediate navigation and duplicate-load source guards.

## Task 1: Batch legacy and chunk event reads

**Files:**
- Modify: `tests/infra/session/test_trace_event_chunks.py`
- Modify: `src/infra/session/trace_event_chunks.py`

- [ ] **Step 1: Extend the fake collections and write failing batch-reader tests**

Add query counters and `$in` handling to `_FakeChunkCollection.find`. Add tests that pass two trace documents at once and assert:

```python
events_by_trace = await storage.read_trace_events_batch_compat(
    [
        {"trace_id": "legacy", "events": [_event("message", "old", 1)]},
        {"trace_id": "chunked", "events": []},
    ]
)

assert [event["data"]["content"] for event in events_by_trace["legacy"]] == ["old"]
assert [event["data"]["content"] for event in events_by_trace["chunked"]] == ["new"]
assert chunk_collection.find_count == 1
```

Add a mixed-prefix test where legacy sequences 1-2 and chunks starting at sequence 3 produce 1-2-3 exactly once. Add a filter test proving event types are applied per trace without changing order.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py -k "batch_compat" -v
```

Expected: FAIL because `read_trace_events_batch_compat` does not exist.

- [ ] **Step 3: Implement the batch compatibility reader**

Add to `TraceEventChunkMixin`:

```python
async def read_trace_events_batch_compat(
    self,
    trace_docs: List[Dict[str, Any]],
    event_types: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    trace_ids = [str(doc.get("trace_id") or "") for doc in trace_docs]
    trace_ids = [trace_id for trace_id in trace_ids if trace_id]
    allowed_types = set(event_types or [])
    chunks_by_trace: Dict[str, List[Dict[str, Any]]] = {trace_id: [] for trace_id in trace_ids}

    cursor = self.chunks_collection.find(
        {"trace_id": {"$in": trace_ids}},
        {"_id": 0, "trace_id": 1, "chunk_index": 1, "start_seq": 1, "events": 1},
    ).sort([("trace_id", 1), ("chunk_index", 1)])
    async for chunk in cursor:
        chunks_by_trace.setdefault(str(chunk.get("trace_id") or ""), []).append(chunk)

    result: Dict[str, List[Dict[str, Any]]] = {}
    for doc in trace_docs:
        trace_id = str(doc.get("trace_id") or "")
        chunks = chunks_by_trace.get(trace_id, [])
        first_chunk_seq = min(
            (int(chunk.get("start_seq") or 1) for chunk in chunks),
            default=None,
        )
        events = []
        for index, event in enumerate(doc.get("events", []) or [], start=1):
            seq = trace_storage_helpers._event_seq(event, index)
            if first_chunk_seq is not None and seq >= first_chunk_seq:
                continue
            if not allowed_types or event.get("event_type") in allowed_types:
                events.append(event)
        for chunk in chunks:
            for index, event in sorted(
                enumerate(chunk.get("events", []) or []),
                key=lambda item: trace_storage_helpers._event_seq(item[1], item[0]),
            ):
                if not allowed_types or event.get("event_type") in allowed_types:
                    events.append(event)
        result[trace_id] = events
    return result
```

Adapt cursor sorting to the real Motor API while keeping test fakes representative. Return `{}` without querying when there are no trace IDs.

- [ ] **Step 4: Run the batch-reader tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py -k "batch_compat" -v
```

Expected: all selected tests PASS.

- [ ] **Step 5: Run existing chunk compatibility tests**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py -v
```

Expected: all tests PASS, including single-trace legacy fallback and partial migration cases.

- [ ] **Step 6: Commit**

```bash
git add src/infra/session/trace_event_chunks.py tests/infra/session/test_trace_event_chunks.py
git commit -m "perf: batch session trace event reads"
```

## Task 2: Add a race-safe active-user history snapshot

**Files:**
- Modify: `tests/infra/session/test_trace_event_chunks.py`
- Modify: `src/infra/session/trace_storage.py`
- Modify: `src/infra/session/dual_writer.py`

- [ ] **Step 1: Write failing snapshot tests**

Add tests for a session containing one completed trace and one current trace:

```python
snapshot = await storage.get_session_events_snapshot(
    "session-1",
    active_run_id="run-active",
)

assert snapshot.history_mode == "active_user_only"
assert snapshot.stream_run_id == "run-active"
assert [(event["run_id"], event["event_type"]) for event in snapshot.events] == [
    ("run-old", "user:message"),
    ("run-old", "message:chunk"),
    ("run-active", "user:message"),
]
```

Cover both trace status orderings:

- `status="running"`: active trace returns only `user:message` and requires replay.
- `status="completed"`: active trace returns every event, `history_mode="complete"`, and `stream_run_id is None`.

Assert one trace `find` and one chunk `find` regardless of trace count. Add explicit regression cases for `run_id`, `exclude_run_id`, and `run_ids` so the shared assembler cannot weaken the existing events route or partial-session sharing. Retain tests for event filters, explicit limits, `followup:questions` compatibility, and chronological ordering.

- [ ] **Step 2: Run the snapshot tests and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py -k "session_events_snapshot" -v
```

Expected: FAIL because the snapshot type and method do not exist.

- [ ] **Step 3: Implement the snapshot value object and batched assembly**

In `trace_storage.py`, add:

```python
@dataclass(frozen=True)
class SessionEventsSnapshot:
    events: list[dict[str, Any]]
    history_mode: Literal["complete", "active_user_only"] = "complete"
    stream_run_id: str | None = None
```

Import `dataclass`, `Literal`, and `Any`. Add a private assembly method that accepts and preserves `run_id`, `exclude_run_id`, `run_ids`, `completed_only`, `event_types`, and `max_events`. It must build the same selector precedence as the current method, project `events`, status, trace/run IDs, timestamps, and recommendation fields in the initial trace query, call `read_trace_events_batch_compat` once, and apply the existing recommendation synthesis and response event shape.

For `active_run_id`, do not exclude its trace in MongoDB. If its trace status is `running`, retain only `user:message`, set `active_user_only`, and return its run ID. If it is terminal, include all of its events and return `complete`. Other running traces remain excluded.

Make existing `get_session_events` pass every selector unchanged to the same batched assembler and return `snapshot.events`, preserving its public list return type, selector precedence, and `completed_only` semantics. Run the existing partial-share/run-filter tests in addition to the new snapshot tests before committing.

- [ ] **Step 4: Expose the snapshot through `DualEventWriter`**

Add, including the existing run selectors so facade behavior stays complete:

```python
async def read_session_events_snapshot(
    self,
    session_id: str,
    *,
    active_run_id: str | None,
    event_types: list[str] | None = None,
    run_id: str | None = None,
    exclude_run_id: str | None = None,
    run_ids: list[str] | None = None,
    max_events: int | None = None,
) -> SessionEventsSnapshot:
    return await self.trace.get_session_events_snapshot(
        session_id,
        active_run_id=active_run_id,
        event_types=event_types,
        run_id=run_id,
        exclude_run_id=exclude_run_id,
        run_ids=run_ids,
        max_events=max_events,
    )
```

- [ ] **Step 5: Run the storage tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py tests/infra/session/test_trace_storage_recommendations.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/infra/session/trace_storage.py src/infra/session/dual_writer.py tests/infra/session/test_trace_event_chunks.py
git commit -m "feat: expose race-safe session history snapshots"
```

## Task 3: Extend the existing events endpoint additively

**Files:**
- Modify: `tests/api/routes/test_session_runs.py`
- Modify: `src/api/routes/session.py`

- [ ] **Step 1: Write failing route contract tests**

Extend `_FakeSessionManager` metadata and the fake dual writer. Add tests proving:

```python
response = await session_routes.get_session_events(
    "session-1",
    event_types=None,
    run_id=None,
    exclude_run_id=None,
    limit=None,
    include_active_user_message=True,
    user=SimpleNamespace(sub="user-1"),
)

assert response["history_mode"] == "active_user_only"
assert response["stream_run_id"] == "run-active"
assert fake_writer.snapshot_calls[0]["active_run_id"] == "run-active"
```

Add a terminal snapshot test with `stream_run_id is None`. Keep the existing default-option test asserting the old `read_session_events(... completed_only=True)` call and response fields.

- [ ] **Step 2: Run the route tests and verify RED**

Run:

```bash
uv run pytest tests/api/routes/test_session_runs.py -k "session_events" -v
```

Expected: FAIL because the query parameter and snapshot method are absent.

- [ ] **Step 3: Implement the additive route branch**

Add `include_active_user_message: bool = Query(False)` after `limit`. Reuse the already authorized `session` and resolve only its `metadata.current_run_id` as the candidate active run. When enabled, call `read_session_events_snapshot`; otherwise retain the current read call.

Return these fields only when `include_active_user_message=True`:

```python
"history_mode": snapshot.history_mode if snapshot else "complete",
"stream_run_id": snapshot.stream_run_id if snapshot else None,
```

Keep `events_limited`, `events_limit`, `run_id`, event-type parsing, and default compatibility unchanged.
When the option is false, omit `history_mode` and `stream_run_id` so existing exact-dictionary callers and tests retain the original response contract.

- [ ] **Step 4: Run route tests and verify GREEN**

Run:

```bash
uv run pytest tests/api/routes/test_session_runs.py -k "session_events" -v
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/session.py tests/api/routes/test_session_runs.py
git commit -m "feat: include active user in history snapshots"
```

## Task 4: Enforce user-before-assistant behavior in pure message logic

**Files:**
- Modify: `frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts`
- Modify: `frontend/src/hooks/useAgent/historyLoader.ts`
- Modify: `frontend/src/hooks/useAgent/__tests__/eventHandlers.test.ts`
- Modify: `frontend/src/hooks/useAgent/eventHandlers.ts`

- [ ] **Step 1: Write a failing history-preparation test**

Add:

```typescript
test("does not reveal a running assistant before its user message", () => {
  const result = prepareMessagesForRunningRun(
    [],
    "run-active",
    () => "assistant-active",
  );

  expect(result.streamingMessageId).toBe("assistant-active");
  expect(result.messages).toEqual([]);
});

test("removes an existing same-run assistant when its user is absent", () => {
  const result = prepareMessagesForRunningRun(
    [{
      id: "assistant-active",
      role: "assistant",
      content: "partial",
      timestamp: new Date(),
      runId: "run-active",
    }],
    "run-active",
  );

  expect(result.streamingMessageId).toBe("assistant-active");
  expect(result.messages).toEqual([]);
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/hooks/useAgent/__tests__/historyLoader.test.ts
```

Expected: FAIL because an assistant-only message is currently appended.

- [ ] **Step 3: Implement the minimal preparation guard**

Resolve the same-run user and existing assistant first, but apply the invariant before the existing-assistant early return. If no same-run user exists, preserve the stream target ID while removing any same-run assistant from the visible list:

```typescript
const hasRunUser = messagesWithPendingUser.some(
  (message) => message.role === "user" && message.runId === runId,
);
if (!hasRunUser) {
  return {
    streamingMessageId: existingAssistant?.id ?? createId(),
    messages: messagesWithPendingUser.filter(
      (message) => !(message.role === "assistant" && message.runId === runId),
    ),
  };
}
```

Only after this guard may the existing-assistant branch mark that message streaming or the new-assistant branch append a placeholder.

- [ ] **Step 4: Run the history-loader test and verify GREEN**

Run the same Vitest command. Expected: PASS.

- [ ] **Step 5: Write failing SSE fallback tests**

In `eventHandlers.test.ts`, start with no messages and dispatch a `user:message` containing `run_id="run-active"` using stream target `assistant-active`. Assert the single state update yields:

```typescript
[
  ["run-active:user", "user", "run-active"],
  ["assistant-active", "assistant", "run-active"],
]
```

Dispatch the same user event again and assert neither message duplicates.

- [ ] **Step 6: Run SSE tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/hooks/useAgent/__tests__/eventHandlers.test.ts
```

Expected: FAIL because the handler currently adds only the user and does not retain its run ID.

- [ ] **Step 7: Implement atomic user and stream-target insertion**

Update `handleUserMessage` to use `messageId`, assign `runId: data.run_id`, deduplicate by message ID/run ID before content fallback, place the user before an existing stream target, and create this target only after the user when missing:

```typescript
const assistant: Message = {
  id: messageId,
  role: "assistant",
  content: "",
  timestamp: eventTimestamp ? parseDate(eventTimestamp) : new Date(),
  parts: [],
  isStreaming: true,
  runId: data.run_id,
};
```

Return user and assistant in one `setMessages` updater so React cannot render an intermediate assistant-only state.

- [ ] **Step 8: Run both message suites and verify GREEN**

Run:

```bash
cd frontend && pnpm exec vitest run \
  src/hooks/useAgent/__tests__/historyLoader.test.ts \
  src/hooks/useAgent/__tests__/eventHandlers.test.ts
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/hooks/useAgent/historyLoader.ts frontend/src/hooks/useAgent/eventHandlers.ts frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts frontend/src/hooks/useAgent/__tests__/eventHandlers.test.ts
git commit -m "fix: keep active user ahead of assistant history"
```

## Task 5: Type the snapshot and extract frontend history helpers

**Files:**
- Modify: `frontend/src/types/session.ts`
- Modify: `frontend/src/services/api/session.ts`
- Create: `frontend/src/hooks/useAgent/historyLoadState.ts`
- Create: `frontend/src/hooks/useAgent/__tests__/historyLoadState.test.ts`

- [ ] **Step 1: Write failing pure-helper tests**

Test that `resolveHistoryStreamRunId` returns the server stream ID when no URL run is selected or when it matches, and returns null for a different historical URL run. Test `applyFeedbackToMessages` updates matching assistant runs without changing unrelated message object identity.

```typescript
expect(resolveHistoryStreamRunId("run-current", undefined)).toBe("run-current");
expect(resolveHistoryStreamRunId("run-current", "run-old")).toBe(null);
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/hooks/useAgent/__tests__/historyLoadState.test.ts
```

Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Add response types and API options**

Extend `SessionEventsResponse`:

```typescript
export type SessionHistoryMode = "complete" | "active_user_only";

export interface SessionEventsResponse {
  events: SSEEventRecord[];
  history_mode?: SessionHistoryMode;
  stream_run_id?: string | null;
}
```

Add optional `signal?: AbortSignal` to `sessionApi.get` and `getEvents`, pass it into `authFetch`, and serialize `include_active_user_message=true` when requested.

- [ ] **Step 4: Implement pure helpers**

Create `historyLoadState.ts` with:

```typescript
export function resolveHistoryStreamRunId(
  streamRunId: string | null | undefined,
  targetRunId?: string,
): string | null {
  if (!streamRunId) return null;
  return targetRunId && targetRunId !== streamRunId ? null : streamRunId;
}

export function applyFeedbackToMessages(
  messages: Message[],
  items: Feedback[],
): Message[] {
  const byRun = new Map(items.map((item) => [item.run_id, item]));
  let changed = false;
  const next = messages.map((message) => {
    const feedback = message.runId ? byRun.get(message.runId) : undefined;
    if (!feedback) return message;
    changed = true;
    return { ...message, feedback: feedback.rating, feedbackId: feedback.id };
  });
  return changed ? next : messages;
}
```

Use the exact existing `Feedback` and `Message` types.

- [ ] **Step 5: Run helper tests and verify GREEN**

Run the same Vitest command. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/session.ts frontend/src/services/api/session.ts frontend/src/hooks/useAgent/historyLoadState.ts frontend/src/hooks/useAgent/__tests__/historyLoadState.test.ts
git commit -m "feat: type session history snapshot state"
```

## Task 6: Shorten and harden the frontend loading critical path

**Files:**
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/hooks/useAgent/sseConnection.ts`
- Modify: `frontend/src/hooks/useAgent/__tests__/sseConnection.test.ts`
- Modify: `frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`

- [ ] **Step 1: Write failing source guards for the intended orchestration**

Extend `useAgentLoadHistoryRace.test.ts` to assert:

- `historyAbortControllerRef` exists and is aborted on a new load and cleanup.
- `sessionApi.get` and `sessionApi.getEvents` receive the same signal and appear in one `Promise.all`.
- `include_active_user_message: true` is sent.
- there is no `await markReadPromise`.
- feedback is not part of the essential `Promise.all`.
- `resolveHistoryStreamRunId` controls reconnection.
- a per-connection SSE generation is invalidated when history selection changes.

- [ ] **Step 2: Run the source tests and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/hooks/__tests__/useAgentLoadHistoryRace.test.ts
```

Expected: FAIL on the missing history abort controller and old serial flow.

- [ ] **Step 3: Add a dedicated history abort lifecycle**

Create `historyAbortControllerRef`. At load start, abort the previous controller, create a new one, and capture its signal. Abort it on unmount and in `clearMessages`. Keep the existing SSE abort behavior separate.

Treat `AbortError` as a silent stale exit. Keep request-ID checks before every state write and in delayed feedback callbacks.

- [ ] **Step 4: Write and verify a failing stale-SSE race test**

In `sseConnection.test.ts`, mock a deferred `getValidAccessToken`. Start connection A, invalidate/start connection B before A's token resolves, then resolve A. Assert A never calls `fetchEventSource`, never changes connection status, and never handles a message with B's controller/generation.

Run:

```bash
cd frontend && pnpm exec vitest run src/hooks/useAgent/__tests__/sseConnection.test.ts
```

Expected: FAIL because `connectToSSE` currently reads the shared controller after token acquisition and has no generation guard.

- [ ] **Step 5: Implement per-connection SSE generation isolation**

Add `sseGenerationRef` to `useAgent` and `SSEConnectionContext`. Invalidate it synchronously whenever a new history load or clear begins. In `connectToSSE`, capture a new generation and a local `AbortController` before the first await. After token refresh/acquisition and in every `onopen`, `onmessage`, `onerror`, `onclose`, catch, and finally callback, return without state writes when the captured generation differs from `sseGenerationRef.current`.

Always pass the local controller's signal to `fetchEventSource`; never read `abortControllerRef.current.signal` after an await. Pass the same captured generation through the 401 recursive retry so retrying one logical connection does not invalidate itself. Only the current generation may clear `isConnectingRef` in `finally`.

Run the SSE test again. Expected: PASS, including existing terminal/transport behavior tests.

- [ ] **Step 6: Run essential requests concurrently and defer side effects**

Replace the serial mark-read/session/events/status/feedback block with this shape:

```typescript
void sessionApi.markRead(targetSessionId).catch(() => {});
const feedbackPromise = canReadFeedback
  ? feedbackApi.list(0, 100, undefined, undefined, targetSessionId).catch(() => null)
  : Promise.resolve(null);

const [sessionData, eventsData] = await Promise.all([
  sessionApi.get(targetSessionId, { signal }),
  sessionApi.getEvents(targetSessionId, {
    include_active_user_message: true,
    signal,
  }),
]);
```

Reconstruct the complete message list, install timestamps/goals, call `resolveHistoryStreamRunId`, and prepare/connect a stream only when it returns a run ID. Commit the complete list once. Remove the blocking status request from the normal path.

Attach delayed feedback after the message commit:

```typescript
void feedbackPromise.then((feedbackList) => {
  if (!feedbackList || isStaleHistoryLoad()) return;
  setMessages((previous) => applyFeedbackToMessages(previous, feedbackList.items));
});
```

- [ ] **Step 7: Run focused useAgent, SSE, and message tests**

Run:

```bash
cd frontend && pnpm exec vitest run \
  src/hooks/__tests__/useAgentLoadHistoryRace.test.ts \
  src/hooks/useAgent/__tests__/sseConnection.test.ts \
  src/hooks/useAgent/__tests__/historyLoadState.test.ts \
  src/hooks/useAgent/__tests__/historyLoader.test.ts \
  src/hooks/useAgent/__tests__/eventHandlers.test.ts
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hooks/useAgent.ts frontend/src/hooks/useAgent/sseConnection.ts frontend/src/hooks/useAgent/__tests__/sseConnection.test.ts frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts
git commit -m "perf: shorten session history loading path"
```

## Task 7: Navigate immediately on session selection

**Files:**
- Modify: `frontend/src/components/layout/AppContent/useSessionSync.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/useSessionSync.test.ts`

- [ ] **Step 1: Write a failing source-order test**

Read `useSessionSync.ts`, extract `handleSelectSession`, and assert `navigate(\`/chat/${selectedSessionId}\`)` occurs before `await loadHistory(selectedSessionId)`. Retain the existing no-page-scroll assertion and add a guard that internal navigation is set before `navigate`.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd frontend && pnpm exec vitest run src/components/layout/AppContent/__tests__/useSessionSync.test.ts
```

Expected: FAIL because navigation currently occurs after history resolves.

- [ ] **Step 3: Move navigation before the history await**

Inside `handleSelectSession`, increment the request ID, set `isInternalNavRef.current = true`, navigate immediately, then await `loadHistory`. Keep the request-ID/path guards for late config restoration and errors, but remove the second navigation after the await.

- [ ] **Step 4: Run session sync tests and verify GREEN**

Run the same Vitest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/AppContent/useSessionSync.ts frontend/src/components/layout/AppContent/__tests__/useSessionSync.test.ts
git commit -m "perf: navigate before loading session history"
```

## Task 8: Integrated verification and completion audit

**Files:**
- Verify all files listed above.

- [ ] **Step 1: Run focused backend tests**

```bash
uv run pytest \
  tests/infra/session/test_trace_event_chunks.py \
  tests/infra/session/test_trace_storage_recommendations.py \
  tests/api/routes/test_session_runs.py -v
```

Expected: PASS with zero failures.

- [ ] **Step 2: Run full frontend tests**

```bash
cd frontend && pnpm test
```

Expected: PASS with zero failures.

- [ ] **Step 3: Run frontend lint and production build**

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: both exit 0.

- [ ] **Step 4: Run backend lint and typecheck**

```bash
make lint
make typecheck
```

Expected: both exit 0.

- [ ] **Step 5: Run cross-stack checks**

```bash
make check-all
```

Expected: exit 0. If an unrelated concurrent/environment failure occurs, isolate it with the focused suites and report exact evidence without weakening this task's acceptance criteria.

- [ ] **Step 6: Audit the user-visible requirements**

Confirm from tests and current source that:

- every session event is still requested with no frontend limit;
- selection changes the URL and skeleton immediately;
- no mark-read, feedback, or status request gates the stable reveal;
- stale HTTP and SSE work is cancelled and cannot overwrite the active session;
- active history contains the user message but no duplicated assistant events;
- no code path inserts a real assistant bubble before its user message;
- terminal transition races use either a complete snapshot or required SSE replay.

- [ ] **Step 7: Inspect final diff and commit any verification-only fixes**

```bash
git status --short
git diff --check
git log --oneline -10
```

Expected: no uncommitted implementation files and no whitespace errors.
