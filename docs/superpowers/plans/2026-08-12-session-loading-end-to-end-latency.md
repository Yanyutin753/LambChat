# Session Loading End-to-End Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the full authenticated chat-opening critical path across session, history, feedback, teams, settings, and frontend rendering without truncating or reordering conversation history.

**Architecture:** Keep current public endpoints and semantics. Reduce MongoDB round trips with request-scoped concurrency, owner-scoped atomic writes, `$facet`, active-trace projections, and an explicitly invalidated settings snapshot; reduce frontend work by removing duplicate requests, compacting consecutive message chunks for chat hydration, deferring invisible requests, and uncovering messages after the first bottom settle.

**Tech Stack:** Python 3.12, FastAPI, Motor/PyMongo, asyncio, React 19, TypeScript, Vitest, pytest, react-virtuoso.

## Global Constraints

- Complete terminal history remains present, ordered, and untruncated.
- Legacy embedded events, chunked events, and mixed migrated traces remain readable.
- Active-run user-first and SSE replay semantics remain unchanged.
- Session, feedback, team, and settings authorization must not weaken.
- Existing request-id, AbortController, SSE generation, and stale-result guards remain authoritative.
- Do not add a persistent browser cache, Redis history cache, history pagination, or a bootstrap endpoint.
- Preserve unrelated changes already present on `main`; do not push.
- Every production change must follow red-green-refactor.

## File Structure

- `src/api/routes/session.py`: request orchestration for session detail/list/events/mark-read.
- `src/infra/session/storage.py`: concurrent count/page reads and owner-scoped mark-read mutation.
- `src/infra/session/trace_storage.py`: snapshot classification and assembly contract.
- `src/infra/session/trace_event_chunks.py`: completed/active chunk projections and compatibility reconstruction.
- `src/infra/session/history_compaction.py`: pure consecutive message-chunk compaction helper.
- `src/infra/feedback/manager.py`: concurrent feedback list/count/stats orchestration.
- `src/infra/team/storage.py`: one `$facet` query for team total and page.
- `src/infra/settings/service.py`: snapshot/in-flight cache and invalidation.
- `src/infra/settings/pubsub.py`: remote invalidation hook.
- `src/api/server_timing.py`: request-local bounded `Server-Timing` phase collector.
- `src/api/middleware/tracing.py`: serialize collected phase metrics into the response.
- `frontend/src/App.tsx`: event-driven SEO title without duplicate session reads.
- `frontend/src/hooks/useAgent.ts`: publish loaded title and request compact history.
- `frontend/src/services/api/session.ts`: additive compact-history request option.
- `frontend/src/hooks/useSettings.ts`: authenticated-generation/in-flight request coalescing.
- `frontend/src/hooks/useSession.ts`: coalesce equivalent list refreshes and guard pagination.
- `frontend/src/components/sidebar/ProjectItem.tsx`: do not load collapsed project lists.
- `frontend/src/components/sidebar/RecentChatsDialog.tsx`: do not load while closed; bound pagination.
- `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`: clear overlay on initial settle.
- `frontend/src/components/layout/AppContent/ChatView.tsx`: distinguish loading overlay from background recovery.

---

### Task 1: Shorten session list, detail, and mark-read database paths

**Files:**
- Modify: `src/api/routes/session.py`
- Modify: `src/infra/session/manager.py`
- Modify: `src/infra/session/storage.py`
- Test: `tests/api/routes/test_session_favorites.py`
- Test: `tests/api/routes/test_session_runs.py`
- Test: `tests/infra/session/test_batch_lookup_limits.py`
- Create: `tests/infra/session/test_session_read_paths.py`

**Interfaces:**
- Consumes: current `SessionManager.get_session`, `SessionStorage.list_sessions`, and route response schemas.
- Produces: `SessionStorage.mark_read_for_user(session_id: str, user_id: str) -> bool` and concurrent list/detail orchestration with unchanged response bodies.

- [ ] **Step 1: Write failing storage concurrency tests**

Add a barrier fake to `tests/infra/session/test_batch_lookup_limits.py` showing count and page begin before either completes:

```python
@pytest.mark.asyncio
async def test_list_sessions_starts_count_and_page_concurrently(monkeypatch):
    collection = _ConcurrentListCollection()
    storage = SessionStorage()
    storage._collection = collection
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)

    sessions, total = await storage.list_sessions(user_id="user-1", limit=20)

    assert collection.count_observed_find_started is True
    assert collection.find_observed_count_started is True
    assert sessions == []
    assert total == 0
```

Add route barriers proving ordinary list favorites lookup overlaps the manager list call, favorites-only resolves the favorite ID before constructing its predicate, and session detail overlaps session/favorites reads.

- [ ] **Step 2: Run the session concurrency tests and verify RED**

Run:

```bash
uv run pytest tests/api/routes/test_session_favorites.py tests/infra/session/test_batch_lookup_limits.py -k 'concurrent or favorites_only' -v
```

Expected: FAIL because list count/page and route favorites/session work are currently awaited serially.

- [ ] **Step 3: Implement minimal concurrent session reads**

In storage, create both awaitables before awaiting:

```python
count_awaitable = self.collection.count_documents(query)
page_awaitable = cursor.to_list(length=limit)
total, page_docs = await asyncio.gather(count_awaitable, page_awaitable)
```

In routes, use `asyncio.gather` only when the favorites ID is not required to build the query. Normalize returned sessions after both results arrive. Keep favorites-only predicate construction sequential, then rely on storage count/page concurrency.

- [ ] **Step 4: Run the session concurrency tests and verify GREEN**

Run the command from Step 2.

Expected: PASS with existing query and normalization assertions unchanged.

- [ ] **Step 5: Write failing owner-scoped mark-read tests**

Create `tests/infra/session/test_session_read_paths.py` with UUID and ObjectId cases:

```python
@pytest.mark.asyncio
async def test_mark_read_for_user_updates_custom_id_and_owner_once():
    storage = SessionStorage()
    storage._collection = collection = _RecordingUpdateCollection(matched=1)

    assert await storage.mark_read_for_user("session-1", "user-1") is True
    assert collection.query == {"session_id": "session-1", "user_id": "user-1"}
    assert collection.update_calls == 1


@pytest.mark.asyncio
async def test_mark_read_for_user_accepts_idempotent_matched_update():
    storage = SessionStorage()
    storage._collection = _RecordingUpdateCollection(matched=1, modified=0)
    assert await storage.mark_read_for_user("session-1", "user-1") is True
```

Add route tests asserting the common success path makes no `get_session` call, while an atomic miss retains 404 and 403 through a fallback lookup.

- [ ] **Step 6: Run the mark-read tests and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_session_read_paths.py tests/api/routes/test_session_runs.py -k 'mark_read' -v
```

Expected: FAIL because `mark_read_for_user` does not exist and the route always reads first.

- [ ] **Step 7: Implement owner-scoped mark-read with miss fallback**

Build the bounded identifier predicate:

```python
query: dict[str, Any] = {"session_id": session_id, "user_id": user_id}
if ObjectId.is_valid(session_id):
    query = {
        "user_id": user_id,
        "$or": [{"session_id": session_id}, {"_id": ObjectId(session_id)}],
    }
result = await self.collection.update_one(query, {"$set": {"unread_count": 0}})
return result.matched_count > 0
```

Expose it through `SessionManager`. In the route, return immediately on success; on false, load the session and use existing 404/ownership behavior.

- [ ] **Step 8: Verify Task 1 and commit**

Run:

```bash
uv run pytest tests/api/routes/test_session_favorites.py tests/api/routes/test_session_runs.py tests/infra/session/test_batch_lookup_limits.py tests/infra/session/test_session_read_paths.py -q
```

Expected: PASS.

Commit:

```bash
git add src/api/routes/session.py src/infra/session/manager.py src/infra/session/storage.py tests/api/routes/test_session_favorites.py tests/api/routes/test_session_runs.py tests/infra/session/test_batch_lookup_limits.py tests/infra/session/test_session_read_paths.py
git commit -m "perf: shorten session database paths"
```

---

### Task 2: Collapse feedback, teams, and settings database work

**Files:**
- Modify: `src/infra/feedback/manager.py`
- Modify: `src/infra/team/storage.py`
- Modify: `src/infra/settings/service.py`
- Modify: `src/infra/settings/pubsub.py`
- Create: `tests/infra/feedback/test_feedback_manager_concurrency.py`
- Modify: `tests/unit/infra/test_team_storage.py`
- Modify: `tests/infra/settings/test_settings_service.py`
- Create: `tests/infra/settings/test_settings_pubsub_cache.py`

**Interfaces:**
- Consumes: existing response schemas and settings pub/sub payload.
- Produces: `SettingsService.invalidate_get_all_cache() -> None`; cached `get_all(admin_mode, mask_sensitive)` remains signature-compatible.

- [ ] **Step 1: Write failing feedback concurrency tests**

Use three `asyncio.Event`-backed storage methods and assert each observes the other two started before returning. Also assert one failure propagates and no partial response is returned.

```python
items, total, stats = await asyncio.gather(
    storage.list(...),
    storage.count(...),
    storage.get_stats(...),
)
```

- [ ] **Step 2: Run feedback concurrency tests and verify RED**

Run:

```bash
uv run pytest tests/infra/feedback/test_feedback_manager_concurrency.py -v
```

Expected: FAIL because the three storage methods are awaited serially.

- [ ] **Step 3: Implement concurrent feedback reads**

Start the three storage awaitables together with `asyncio.gather`, then build
the unchanged response only after all three complete.

- [ ] **Step 4: Run feedback concurrency tests and verify GREEN**

Run the Step 2 command.

Expected: PASS, including failure propagation.

- [ ] **Step 5: Replace team count plus page with a failing `$facet` contract test**

Update `tests/unit/infra/test_team_storage.py` to reject `count_documents` and assert one aggregation contains:

```python
{
    "$facet": {
        "metadata": [{"$count": "total"}],
        "items": [{"$sort": expected_sort}, {"$skip": 20}, {"$limit": 10}],
    }
}
```

Assert total/page parsing, pinned/favorite ordering, filters, bounded limit, and empty results.

- [ ] **Step 6: Run team storage tests and verify RED**

Run:

```bash
uv run pytest tests/unit/infra/test_team_storage.py -k 'list_teams' -v
```

Expected: FAIL because storage still calls `count_documents` separately.

- [ ] **Step 7: Implement one team `$facet` aggregation**

Resolve preference arrays first, add preference fields, then facet metadata and items. Parse the single returned document without issuing a second team query.

- [ ] **Step 8: Run team storage tests and verify GREEN**

Run the Step 6 command.

Expected: PASS.

- [ ] **Step 9: Write failing settings cache tests**

Extend `tests/infra/settings/test_settings_service.py` with:

```python
first, second = await asyncio.gather(
    service.get_all(admin_mode=True),
    service.get_all(admin_mode=True),
)
assert storage.get_all_calls == 1
assert first == second
assert first is not second

first["general"][0].value = "mutated"
assert (await service.get_all(admin_mode=True))["general"][0].value != "mutated"
```

Also cover failed-load retry and invalidation after `set`, `reset(key)`, `reset()`, and remote pub/sub receipt.

- [ ] **Step 10: Run settings tests and verify RED**

Run:

```bash
uv run pytest tests/infra/settings/test_settings_service.py tests/infra/settings/test_settings_pubsub_cache.py -v
```

Expected: FAIL because `get_all` always reads storage and no invalidation hook exists.

- [ ] **Step 11: Implement settings snapshot/in-flight cache**

Store results keyed by `(admin_mode, mask_sensitive)` and in-flight tasks under the same key. Return `copy.deepcopy` on every caller boundary. Remove the in-flight entry in `finally`; cache only successful results. Implement synchronous idempotent invalidation and call it after successful local mutations and at the start of remote pub/sub handling.

- [ ] **Step 12: Verify Task 2 and commit**

Run:

```bash
uv run pytest tests/infra/feedback/test_feedback_manager_concurrency.py tests/unit/infra/test_team_storage.py tests/unit/infra/test_team_manager.py tests/infra/settings/test_settings_service.py tests/infra/settings/test_settings_storage.py tests/infra/settings/test_settings_pubsub_cache.py -q
```

Expected: PASS.

Commit:

```bash
git add src/infra/feedback/manager.py src/infra/team/storage.py src/infra/settings/service.py src/infra/settings/pubsub.py tests/infra/feedback/test_feedback_manager_concurrency.py tests/unit/infra/test_team_storage.py tests/infra/settings/test_settings_service.py tests/infra/settings/test_settings_pubsub_cache.py
git commit -m "perf: collapse auxiliary database reads"
```

---

### Task 3: Project active history at the database and compact chat transport

**Files:**
- Create: `src/infra/session/history_compaction.py`
- Modify: `src/infra/session/trace_event_chunks.py`
- Modify: `src/infra/session/trace_storage.py`
- Modify: `src/infra/session/dual_writer.py`
- Modify: `src/api/routes/session.py`
- Modify: `frontend/src/services/api/session.ts`
- Modify: `frontend/src/hooks/useAgent.ts`
- Create: `tests/infra/session/test_history_compaction.py`
- Modify: `tests/infra/session/test_trace_event_chunks.py`
- Modify: `tests/api/routes/test_session_runs.py`
- Modify: `frontend/src/services/api/__tests__/session.test.ts`
- Modify: `frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`
- Modify: `frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts`

**Interfaces:**
- Produces: `compact_consecutive_message_chunks(events: list[dict[str, Any]]) -> list[dict[str, Any]]`.
- Extends: `GET /api/sessions/{id}/events?compact_message_chunks=true` and `sessionApi.getEvents(..., { compact_message_chunks?: boolean })`.
- Preserves: raw events when option is absent/false.

- [ ] **Step 1: Write pure compaction RED tests**

Cover merge and every non-merge boundary:

```python
def test_compacts_only_consecutive_compatible_message_chunks():
    events = [
        chunk("a", seq=1, depth=0, agent_id="main"),
        chunk("b", seq=2, depth=0, agent_id="main"),
        tool_start(seq=3),
        chunk("c", seq=4, depth=0, agent_id="main"),
    ]
    compacted = compact_consecutive_message_chunks(events)
    assert [
        event["data"]["content"] for event in compacted if event["event_type"] == "message:chunk"
    ] == ["ab", "c"]
    assert compacted[0]["seq"] == 2
```

Separate tests assert no merge across trace/run/depth/agent changes, extra unknown data, or semantic events; inputs are not mutated.

- [ ] **Step 2: Run compaction tests and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_history_compaction.py -v
```

Expected: collection error because the helper module does not exist.

- [ ] **Step 3: Implement minimal pure compaction**

Use one forward pass and a compatibility key containing trace ID, run ID, depth, and agent ID. Copy merged dictionaries and retain the final sequence/timestamp.

- [ ] **Step 4: Run compaction tests and verify GREEN**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 5: Write active-projection RED tests**

Extend fake collections to record projections. Build an active trace with 15,000 assistant chunks plus one user event and assert:

```python
snapshot = await storage.get_session_events_snapshot("session-1", active_run_id="run-active")
assert [event["event_type"] for event in snapshot.events] == ["user:message"]
assert trace_collection.requested_active_event_filter == "user:message"
assert chunk_collection.requested_active_event_filter == "user:message"
assert chunk_collection.materialized_non_user_events == 0
```

Retain an exact equality test for terminal legacy/chunk/mixed fixtures.

- [ ] **Step 6: Run projection tests and verify RED**

Run:

```bash
uv run pytest tests/infra/session/test_trace_event_chunks.py -k 'snapshot or projection or complete' -v
```

Expected: FAIL because active parents/chunks are currently fetched with complete event arrays.

- [ ] **Step 7: Implement separate completed and active projections**

After parent status classification, batch-read completed traces unchanged. Read the active legacy array and chunks with Mongo `$filter` projections selecting `event_type == "user:message"`. Preserve legacy prefixes and sequence ordering. Do not filter completed traces.

- [ ] **Step 8: Run projection tests and verify GREEN**

Run the Step 6 command.

Expected: PASS with terminal equality assertions unchanged.

- [ ] **Step 9: Write route and frontend option RED tests**

Assert default false is forwarded as raw behavior, explicit true compacts after limit/filter semantics are applied, and `useAgent.loadHistory` alone sets both:

```typescript
expect(getEvents).toHaveBeenCalledWith("session-1", {
  include_active_user_message: true,
  compact_message_chunks: true,
  signal: expect.any(AbortSignal),
});
```

Build 15,000 raw-equivalent chunks and assert `reconstructMessagesFromEvents(raw)` deep-equals reconstruction from compact input.

- [ ] **Step 10: Run route/frontend tests and verify RED**

Run:

```bash
uv run pytest tests/api/routes/test_session_runs.py tests/infra/session/test_history_compaction.py -q
cd frontend && pnpm test --run src/services/api/__tests__/session.test.ts src/hooks/__tests__/useAgentLoadHistoryRace.test.ts src/hooks/useAgent/__tests__/historyLoader.test.ts
```

Expected: FAIL because the query option and compaction call do not exist.

- [ ] **Step 11: Wire compact transport**

Add the optional query to route/service types. Apply compaction only when requested and after assembling the semantically correct bounded history. Enable it only in `useAgent.loadHistory`.

- [ ] **Step 12: Verify Task 3 and commit**

Run:

```bash
uv run pytest tests/infra/session/test_history_compaction.py tests/infra/session/test_trace_event_chunks.py tests/api/routes/test_session_runs.py -q
cd frontend && pnpm test --run src/services/api/__tests__/session.test.ts src/hooks/__tests__/useAgentLoadHistoryRace.test.ts src/hooks/useAgent/__tests__/historyLoader.test.ts
```

Expected: PASS.

Commit:

```bash
git add src/infra/session/history_compaction.py src/infra/session/trace_event_chunks.py src/infra/session/trace_storage.py src/infra/session/dual_writer.py src/api/routes/session.py frontend/src/services/api/session.ts frontend/src/hooks/useAgent.ts tests/infra/session/test_history_compaction.py tests/infra/session/test_trace_event_chunks.py tests/api/routes/test_session_runs.py frontend/src/services/api/__tests__/session.test.ts frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts frontend/src/hooks/useAgent/__tests__/historyLoader.test.ts
git commit -m "perf: compact full history hydration"
```

---

### Task 4: Remove duplicate and invisible frontend requests

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/hooks/useSettings.ts`
- Modify: `frontend/src/hooks/useSession.ts`
- Modify: `frontend/src/components/sidebar/ProjectItem.tsx`
- Modify: `frontend/src/components/sidebar/RecentChatsDialog.tsx`
- Modify: `frontend/src/__tests__/chatPageSeoIsolation.test.ts`
- Modify: `frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts`
- Create: `frontend/src/hooks/__tests__/useSettingsRequestCoalescing.test.tsx`
- Create: `frontend/src/hooks/__tests__/useSessionRequestCoalescing.test.tsx`
- Create: `frontend/src/components/sidebar/__tests__/sessionListVisibility.test.tsx`

**Interfaces:**
- Consumes: `dispatchSessionTitleUpdated` / `getCachedSessionTitle` / `listenSessionTitleUpdated`.
- Produces: no new public API; request coalescing is local to each owning hook/surface.

- [ ] **Step 1: Write SEO/title RED tests**

Update `chatPageSeoIsolation.test.ts` to assert the `ChatPageSEO` body contains no `sessionApi.get`, no 3000 ms timer, and initializes/updates solely through title cache/events. Extend the history race test to require title dispatch only after the stale check and never for a stale request.

- [ ] **Step 2: Run title tests and verify RED**

Run:

```bash
cd frontend && pnpm test --run src/__tests__/chatPageSeoIsolation.test.ts src/hooks/__tests__/useAgentLoadHistoryRace.test.ts src/utils/__tests__/sessionTitleEvents.test.ts
```

Expected: FAIL because SEO still performs an initial read and polling read.

- [ ] **Step 3: Remove SEO reads and publish the current loaded title**

Remove both `sessionApi.get` paths from `ChatPageSEO`. On a current successful history load, dispatch `sessionData.name` before returning configuration. Keep generated-title dispatch unchanged.

- [ ] **Step 4: Write settings coalescing RED tests**

Mount the hook with a valid token, fire repeated `auth:login` events while the first request is pending, and assert one call. Resolve, advance to a new auth generation, and assert one fresh call. Resolve an older generation after logout/new login and assert it cannot overwrite state.

- [ ] **Step 5: Run settings hook test and verify RED**

Run:

```bash
cd frontend && pnpm test --run src/hooks/__tests__/useSettingsRequestCoalescing.test.tsx
```

Expected: FAIL because mount and login handlers independently call the API.

- [ ] **Step 6: Implement in-flight/generation coalescing in `useSettings`**

Track the active promise and monotonically increasing auth generation in refs. Reuse the promise within one generation; clear it in `finally` only if still current. Gate all state writes on generation equality.

- [ ] **Step 7: Write list visibility/coalescing RED tests**

Assert closed `RecentChatsDialog` and collapsed `ProjectItem` issue zero requests. Assert opening/expanding causes one first-page request. Hold a soft refresh and trigger it again; assert one equivalent request. Hold a next-page request while toggling intersection state; assert one request.

- [ ] **Step 8: Run list tests and verify RED**

Run:

```bash
cd frontend && pnpm test --run src/components/sidebar/__tests__/sessionListVisibility.test.tsx src/hooks/__tests__/useSessionRequestCoalescing.test.tsx
```

Expected: at least one request-count assertion fails under current effects.

- [ ] **Step 9: Implement local visibility and in-flight guards**

Mount/fetch session lists only when their owner is visible. Track reset, soft-refresh, and next-page promises independently; equivalent calls reuse/ignore the current promise, while filter changes invalidate the generation and abort/stale-guard prior results.

- [ ] **Step 10: Verify Task 4 and commit**

Run:

```bash
cd frontend && pnpm test --run src/__tests__/chatPageSeoIsolation.test.ts src/hooks/__tests__/useAgentLoadHistoryRace.test.ts src/hooks/__tests__/useSettingsRequestCoalescing.test.tsx src/hooks/__tests__/useSessionRequestCoalescing.test.tsx src/components/sidebar/__tests__/sessionListVisibility.test.tsx
```

Expected: PASS.

Commit:

```bash
git add frontend/src/App.tsx frontend/src/hooks/useAgent.ts frontend/src/hooks/useSettings.ts frontend/src/hooks/useSession.ts frontend/src/components/sidebar/ProjectItem.tsx frontend/src/components/sidebar/RecentChatsDialog.tsx frontend/src/__tests__/chatPageSeoIsolation.test.ts frontend/src/hooks/__tests__/useAgentLoadHistoryRace.test.ts frontend/src/hooks/__tests__/useSettingsRequestCoalescing.test.tsx frontend/src/hooks/__tests__/useSessionRequestCoalescing.test.tsx frontend/src/components/sidebar/__tests__/sessionListVisibility.test.tsx
git commit -m "perf: remove redundant frontend requests"
```

---

### Task 5: Reveal complete history after initial scroll settle

**Files:**
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.hook.ts`
- Modify: `frontend/src/components/layout/AppContent/ChatView.tsx`
- Modify: `frontend/src/components/layout/AppContent/useMessageScroll.historySettling.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/useMessageScroll.test.ts`
- Modify: `frontend/src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts`

**Interfaces:**
- Consumes: existing `startVirtuosoScrollToBottom` callbacks.
- Produces: overlay lifetime ends at `onInitialSettle`; recovery observation continues until `onComplete`.

- [ ] **Step 1: Reverse the stale source contract and verify RED**

Change the source test to require:

```typescript
expect(hookSource).toMatch(
  /requestScrollToBottom\("history-finalize",\s*\{[\s\S]*onInitialSettle:\s*clearHistoryScrollSettling/,
);
```

Add a behavior test with fake timers asserting `onInitialSettle` clears the overlay before the 2400/3600 ms observation completes, while a late height change still triggers correction.

- [ ] **Step 2: Run scroll tests and verify RED**

Run:

```bash
cd frontend && pnpm test --run src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts src/components/layout/AppContent/__tests__/useMessageScroll.test.ts src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts
```

Expected: FAIL because the overlay is cleared only from `onComplete`.

- [ ] **Step 3: Clear the overlay on initial settle without stopping recovery**

Pass `onInitialSettle: clearHistoryScrollSettling`. Keep `onComplete` for abort/max-attempt cleanup and physical-bottom fallback, but do not re-enable the overlay. Ensure unavailable refs and empty histories retain bounded fallback cleanup.

- [ ] **Step 4: Verify Task 5 and commit**

Run the Step 2 command and expect PASS.

Commit:

```bash
git add frontend/src/components/layout/AppContent/useMessageScroll.hook.ts frontend/src/components/layout/AppContent/ChatView.tsx frontend/src/components/layout/AppContent/useMessageScroll.historySettling.ts frontend/src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts frontend/src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts frontend/src/components/layout/AppContent/__tests__/useMessageScroll.test.ts frontend/src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts
git commit -m "perf: reveal history after initial settle"
```

---

### Task 6: Add safe backend phase timing

**Files:**
- Create: `src/api/server_timing.py`
- Modify: `src/api/middleware/tracing.py`
- Modify: `src/api/routes/session.py`
- Modify: `src/api/routes/feedback.py`
- Modify: `src/api/routes/team.py`
- Modify: `src/api/routes/settings.py`
- Create: `tests/api/test_server_timing.py`
- Create: `tests/api/test_tracing_middleware.py`

**Interfaces:**
- Produces: `record_server_timing(name: Literal[...], duration_ms: float) -> None` and `timed_server_phase(name)` async context manager.
- Response: `Server-Timing` contains only allowlisted metric names and numeric durations; `X-Process-Time` remains unchanged.

- [ ] **Step 1: Write timing collector and middleware RED tests**

Assert stable serialization and secret rejection:

```python
with timed_server_phase("session"):
    await operation()
response = await client.get("/timed")
assert "session;dur=" in response.headers["Server-Timing"]
assert "session-uuid" not in response.headers["Server-Timing"]
assert "X-Process-Time" in response.headers
```

Unknown metric names must raise or be ignored before serialization; user/session/query data must never be accepted as names/descriptions.

- [ ] **Step 2: Run timing tests and verify RED**

Run:

```bash
uv run pytest tests/api/test_server_timing.py tests/api/test_tracing_middleware.py -v
```

Expected: import failure because the collector does not exist.

- [ ] **Step 3: Implement request-local timing and instrument phase boundaries**

Use a `ContextVar[dict[str, float]]` reset by tracing middleware. The async context manager measures `time.perf_counter()` and records only allowlisted phase names. Middleware serializes sorted `name;dur=0.00` values after `call_next`. Wrap route calls, not payload parsing or logging.

- [ ] **Step 4: Verify Task 6 and commit**

Run:

```bash
uv run pytest tests/api/test_server_timing.py tests/api/test_tracing_middleware.py tests/api/routes/test_session_favorites.py tests/api/routes/test_session_runs.py tests/api/test_team_routes.py -q
```

Expected: PASS.

Commit:

```bash
git add src/api/server_timing.py src/api/middleware/tracing.py src/api/routes/session.py src/api/routes/feedback.py src/api/routes/team.py src/api/routes/settings.py tests/api/test_server_timing.py tests/api/test_tracing_middleware.py
git commit -m "feat: expose safe backend phase timing"
```

---

### Task 7: Cross-stack regression and production-ready handoff

**Files:**
- Modify only files required by failures attributable to Tasks 1-6.
- Do not modify or stage unrelated working-tree changes.

**Interfaces:**
- Consumes: all previous task contracts.
- Produces: verified local implementation and a deployment measurement checklist.

- [ ] **Step 1: Run focused backend regression suites**

```bash
uv run pytest tests/api/routes/test_session_favorites.py tests/api/routes/test_session_runs.py tests/api/test_team_routes.py tests/api/test_server_timing.py tests/infra/session tests/infra/feedback tests/infra/settings tests/unit/infra/test_team_storage.py tests/unit/infra/test_team_manager.py -q
```

Expected: PASS. If a failure is outside changed paths, isolate and report it rather than changing unrelated behavior.

- [ ] **Step 2: Run focused frontend regression suites**

```bash
cd frontend && pnpm test --run src/__tests__/chatPageSeoIsolation.test.ts src/services/api/__tests__/session.test.ts src/hooks/__tests__/useAgentLoadHistoryRace.test.ts src/hooks/useAgent/__tests__/historyLoader.test.ts src/hooks/__tests__/useSettingsRequestCoalescing.test.tsx src/hooks/__tests__/useSessionRequestCoalescing.test.tsx src/components/sidebar/__tests__/sessionListVisibility.test.tsx src/components/layout/AppContent/__tests__/useMessageScrollHookSource.test.ts src/components/layout/AppContent/__tests__/useMessageScroll.test.ts src/components/layout/AppContent/__tests__/messageScrollUtils.test.ts src/components/layout/AppContent/__tests__/chatViewScrollbarSource.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint and production build**

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: PASS; record existing non-fatal Vite/Rollup warnings separately.

- [ ] **Step 4: Run full repository verification**

```bash
make check-all
```

Expected: PASS. Report exact passing counts and distinguish focused success from full-suite success.

- [ ] **Step 5: Inspect scope and commit any attributable verification repair**

```bash
git status --short
git diff --check
git diff --stat HEAD~6..HEAD
```

Stage only task files. If verification required a repair, commit it separately:

```bash
git commit -m "test: harden session latency regressions"
```

- [ ] **Step 6: Prepare live verification checklist**

After deployment, capture one authenticated navigation and compare:

1. Network total duration.
2. `X-Process-Time`.
3. `Server-Timing` phases.
4. Count of session detail, settings, list, feedback, and events requests.
5. Time from events completion to real messages visible.

Acceptance: one session-detail request, no SEO poll, no hidden-surface requests, complete history equality, compact events enabled on chat hydration, and the message overlay removed after initial settle. Do not claim production latency improved until this deployment check is performed.
