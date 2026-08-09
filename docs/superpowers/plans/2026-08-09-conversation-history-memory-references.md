# Conversation History and Memory References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deferred Agent tools that search and page through the current user's historical final Q&A, while letting native memories retain validated `session_id`/`run_id` source references.

**Architecture:** Materialize a versioned search projection on each completed trace, query those projections through a user-scoped `ConversationHistoryService`, and reconstruct detail responses from persisted events. Reuse the same authorization service to validate memory source references on write and recall; index new runs asynchronously and backfill old traces with a distributed worker.

**Tech Stack:** Python 3.12+, FastAPI, LangChain tools, Pydantic, Motor/PyMongo, Redis distributed locks, pytest/pytest-asyncio.

## Global Constraints

- Only the current authenticated user's sessions are visible to Agent tools.
- Include project and archived sessions; exclude `metadata.hidden_from_conversation_list == true` and sessions with `metadata.scheduled_task_id`.
- Return only user messages and the main AI final answer; never return thinking, tool arguments, tool results, recommendations, or diagnostics.
- Search and session detail both use opaque cursor pagination; default page size is 10 and the hard maximum is 20.
- A memory stores at most 20 unique `(session_id, run_id)` source references.
- Source references never appear in the always-on `<memory_index>` prompt section.
- Both conversation-history tools are deferred internal tools unless an explicit `inline_exposure=true` policy overrides the default.
- New indexing, historical backfill, and automatic memory capture must not block final-answer delivery.
- Preserve existing frontend session-search and session-event API behavior.
- Do not log message bodies, final answers, memory content, or full source-reference lists.

---

## File Structure

- Create `src/kernel/schemas/conversation_history.py`: shared bounded `ConversationSourceRef` model.
- Create `src/infra/session/conversation_history_index.py`: pure extraction, normalization, and index-payload helpers.
- Create `src/infra/session/conversation_history.py`: storage-facing indexing, authorization, cursor pagination, search, detail, and source-reference validation service.
- Create `src/infra/tool/conversation_history_tool.py`: LangChain tool wrappers and JSON result serialization.
- Modify `src/infra/session/trace_storage.py`: trace indexes required by history search and backfill.
- Modify `src/infra/session/trace_storage_writes.py`: schedule best-effort indexing after trace completion.
- Modify `src/infra/session/backfill.py` and `src/api/main.py`: distributed historical trace backfill.
- Modify `src/infra/tool/internal_registry.py`: register the two tools with deferred-by-default exposure.
- Modify `src/infra/memory/client/base.py`, `src/infra/memory/client/native/backend.py`, `src/infra/memory/client/native/search.py`, `src/infra/memory/client/native/consolidation.py`, and `src/infra/memory/tools.py`: persist, merge, validate, recall, and auto-bind source references.
- Modify `src/agents/fast_agent/nodes.py`, `src/agents/search_agent/nodes.py`, and `src/agents/team_agent/nodes.py`: pass the current run reference into detached automatic memory capture.
- Modify `src/api/routes/memory.py`: preserve valid source references in memory list/detail/export/import flows.
- Create focused tests under `tests/infra/session/`, `tests/infra/tool/`, and `tests/infra/memory/`; extend existing lifecycle and API tests only where the existing seam is the behavior under test.

---

### Task 1: Pure Conversation Turn Extraction and Search Projection

**Files:**
- Create: `src/kernel/schemas/conversation_history.py`
- Create: `src/infra/session/conversation_history_index.py`
- Test: `tests/infra/session/test_conversation_history_index.py`

**Interfaces:**
- Consumes: `build_search_terms()` and `normalize_search_text()` from `src.infra.session.search_index`.
- Produces: `ConversationSourceRef`, `ConversationTurnText`, `ConversationSearchPayload`, `extract_conversation_turn(events)`, `build_conversation_search_payload(events)`, and `merge_source_refs(existing, incoming, limit=20)`.

- [ ] **Step 1: Write failing schema, extraction, filtering, and deduplication tests**

```python
from src.infra.session.conversation_history_index import (
    CONVERSATION_SEARCH_INDEX_VERSION,
    build_conversation_search_payload,
    extract_conversation_turn,
    merge_source_refs,
)
from src.kernel.schemas.conversation_history import ConversationSourceRef


def test_extract_conversation_turn_keeps_only_user_and_main_final_text() -> None:
    events = [
        {"event_type": "user:message", "data": {"content": "查一下 parser"}},
        {"event_type": "thinking", "data": {"content": "internal"}},
        {"event_type": "message:chunk", "data": {"content": "子代理", "depth": 1}},
        {"event_type": "tool:end", "data": {"content": "secret result"}},
        {"event_type": "message:chunk", "data": {"content": "最终", "depth": 0}},
        {"event_type": "message:chunk", "data": {"content": "答案"}},
    ]

    turn = extract_conversation_turn(events)

    assert turn.user_text == "查一下 parser"
    assert turn.assistant_final_text == "最终答案"


def test_build_conversation_search_payload_indexes_both_sides() -> None:
    payload = build_conversation_search_payload(
        [
            {"event_type": "user:message", "data": {"content": "compile failure"}},
            {"event_type": "message:chunk", "data": {"content": "修复编译错误"}},
        ]
    )

    assert payload.version == CONVERSATION_SEARCH_INDEX_VERSION
    assert "com" in payload.user_terms
    assert "编译" in payload.assistant_terms
    assert set(payload.terms) == set(payload.user_terms + payload.assistant_terms)


def test_merge_source_refs_deduplicates_and_keeps_newest_twenty() -> None:
    existing = [ConversationSourceRef(session_id="s", run_id=f"old-{i}") for i in range(15)]
    incoming = [
        ConversationSourceRef(session_id="s", run_id="old-14"),
        *[ConversationSourceRef(session_id="s", run_id=f"new-{i}") for i in range(10)],
    ]

    merged = merge_source_refs(existing, incoming)

    assert len(merged) == 20
    assert len({(item.session_id, item.run_id) for item in merged}) == 20
    assert merged[-1].run_id == "new-9"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/infra/session/test_conversation_history_index.py -v`

Expected: FAIL during import because the schema and index modules do not exist.

- [ ] **Step 3: Implement the bounded source-reference schema and pure index helpers**

```python
# src/kernel/schemas/conversation_history.py
from pydantic import BaseModel, Field


class ConversationSourceRef(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
```

```python
# src/infra/session/conversation_history_index.py
from dataclasses import dataclass

from src.infra.session.search_index import build_search_terms, normalize_search_text
from src.kernel.schemas.conversation_history import ConversationSourceRef

CONVERSATION_SEARCH_INDEX_VERSION = 1
CONVERSATION_SEARCH_TEXT_MAX_CHARS = 24_000
MEMORY_SOURCE_REFS_MAX = 20


@dataclass(frozen=True)
class ConversationTurnText:
    user_text: str
    assistant_final_text: str


@dataclass(frozen=True)
class ConversationSearchPayload:
    version: int
    user_text: str
    assistant_final_text: str
    user_terms: list[str]
    assistant_terms: list[str]
    terms: list[str]


def extract_conversation_turn(events: list[dict]) -> ConversationTurnText:
    user_parts: list[str] = []
    assistant_parts: list[str] = []
    for event in events:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("event_type") == "user:message":
            text = data.get("content") or data.get("message")
            if isinstance(text, str) and text:
                user_parts.append(text)
        elif event.get("event_type") == "message:chunk":
            try:
                depth = int(data.get("depth") or 0)
            except (TypeError, ValueError):
                depth = 0
            text = data.get("content")
            if depth <= 0 and isinstance(text, str) and text:
                assistant_parts.append(text)
    return ConversationTurnText(
        user_text=normalize_search_text("\n".join(user_parts)),
        assistant_final_text=normalize_search_text("".join(assistant_parts)),
    )
```

Implement payload construction with full-text term generation, bounded preview text, stable first-seen term deduplication, and source-reference merge semantics matching the tests.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/infra/session/test_conversation_history_index.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/kernel/schemas/conversation_history.py src/infra/session/conversation_history_index.py tests/infra/session/test_conversation_history_index.py
git commit -m "feat(history): build per-run search projections"
```

---

### Task 2: User-Scoped Search, Detail Pagination, and Source Authorization Service

**Files:**
- Create: `src/infra/session/conversation_history.py`
- Modify: `src/infra/session/trace_storage.py`
- Test: `tests/infra/session/test_conversation_history_service.py`

**Interfaces:**
- Consumes: Task 1 payload/extraction helpers, `SessionManager.get_session()`, `SessionManager.get_sessions()`, and trace compatibility readers.
- Produces: `ConversationHistoryService.index_trace(trace_id) -> bool`, `search(user_id, query, limit=10, cursor=None) -> dict`, `get_detail(user_id, session_id, run_id=None, limit=10, cursor=None) -> dict`, `validate_source_refs(user_id, refs) -> list[ConversationSourceRef]`, and `backfill_indexes(batch_size=20) -> int`.

- [ ] **Step 1: Write failing tests for indexing and authorization**

```python
@pytest.mark.asyncio
async def test_index_trace_materializes_completed_turn(fake_history_service) -> None:
    stored = await fake_history_service.index_trace("trace-1")

    assert stored is True
    assert fake_history_service.trace_collection.last_update["$set"][
        "conversation_search.version"
    ] == 1
    assert "parser" in fake_history_service.trace_collection.last_update["$set"][
        "conversation_search.terms"
    ]


@pytest.mark.asyncio
async def test_validate_source_refs_filters_cross_user_hidden_scheduled_and_mismatched_runs(
    fake_history_service,
) -> None:
    refs = [
        ConversationSourceRef(session_id="visible", run_id="run-visible"),
        ConversationSourceRef(session_id="other-user", run_id="run-other"),
        ConversationSourceRef(session_id="hidden", run_id="run-hidden"),
        ConversationSourceRef(session_id="scheduled", run_id="run-scheduled"),
        ConversationSourceRef(session_id="visible", run_id="run-from-another-session"),
    ]

    allowed = await fake_history_service.validate_source_refs("user-1", refs)

    assert allowed == [ConversationSourceRef(session_id="visible", run_id="run-visible")]
```

- [ ] **Step 2: Write failing tests for both pagination modes**

```python
@pytest.mark.asyncio
async def test_search_returns_stable_opaque_cursor_and_match_source(fake_history_service) -> None:
    first = await fake_history_service.search("user-1", "编译", limit=2)
    second = await fake_history_service.search(
        "user-1", "编译", limit=2, cursor=first["next_cursor"]
    )

    assert [(item["session_id"], item["run_id"]) for item in first["items"]] == [
        ("session-1", "run-3"),
        ("session-1", "run-2"),
    ]
    assert second["items"][0]["run_id"] == "run-1"
    assert first["items"][0]["match_source"] in {"user", "assistant", "both"}


@pytest.mark.asyncio
async def test_get_detail_pages_session_but_exact_run_is_single_turn(fake_history_service) -> None:
    page = await fake_history_service.get_detail("user-1", "session-1", limit=2)
    exact = await fake_history_service.get_detail(
        "user-1", "session-1", run_id="run-1", limit=20
    )

    assert len(page["turns"]) == 2
    assert page["next_cursor"]
    assert [turn["run_id"] for turn in exact["turns"]] == ["run-1"]
    assert set(exact["turns"][0]) == {
        "run_id",
        "started_at",
        "completed_at",
        "user_message",
        "assistant_final",
    }
```

- [ ] **Step 3: Run the service tests and verify RED**

Run: `uv run pytest tests/infra/session/test_conversation_history_service.py -v`

Expected: FAIL because `ConversationHistoryService` is not implemented.

- [ ] **Step 4: Implement the service with opaque cursor validation and bounded candidate scanning**

Create `ConversationHistoryService` with these exact public signatures:

- `index_trace(self, trace_id: str) -> bool`
- `search(self, user_id: str, query: str, limit: int = 10, cursor: str | None = None) -> dict[str, object]`
- `get_detail(self, user_id: str, session_id: str, run_id: str | None = None, limit: int = 10, cursor: str | None = None) -> dict[str, object]`
- `validate_source_refs(self, user_id: str, refs: list[ConversationSourceRef | dict[str, str]]) -> list[ConversationSourceRef]`
- `backfill_indexes(self, batch_size: int = 20) -> int`

The bounded search query must be constructed as follows before session visibility filtering:

```python
bounded_limit = min(max(int(limit), 1), 20)
query_terms = build_search_query_terms(query)
if not query_terms:
    raise ConversationHistoryInvalidArgument("empty_query")

match: dict[str, object] = {
    "user_id": user_id,
    "status": {"$ne": "running"},
    "conversation_search.version": CONVERSATION_SEARCH_INDEX_VERSION,
    "conversation_search.terms": {"$all": query_terms},
}
if decoded_cursor is not None:
    completed_at, trace_id = decoded_cursor
    match["$or"] = [
        {"completed_at": {"$lt": completed_at}},
        {"completed_at": completed_at, "trace_id": {"$lt": trace_id}},
    ]
```

Use URL-safe base64 JSON cursors containing schema version, timestamp, and trace ID. Reject malformed cursors with a local `ConversationHistoryInvalidArgument` exception; return `ConversationHistoryNotFound` for missing or unauthorized resources. Search by `user_id`, current index version, non-running status, and `conversation_search.terms: {"$all": query_terms}`; over-fetch candidates and batch-resolve sessions so hidden/scheduled/foreign records never enter a page. Reconstruct detail turns through `read_trace_events_batch_compat()` and Task 1 extraction so event arrays and chunk storage share one read path.

For legacy traces without `user_id`, `index_trace()` must resolve the owning session and persist its `user_id` together with `conversation_search`; skip traces whose session no longer exists. Indexing may materialize hidden or scheduled traces for lifecycle consistency, but search, source validation, and detail must always filter them at read time.

- [ ] **Step 5: Add trace indexes**

Add these best-effort background indexes in `TraceStorage._ensure_indexes()`:

```python
await collection.create_index(
    [
        ("user_id", 1),
        ("conversation_search.version", 1),
        ("conversation_search.terms", 1),
        ("completed_at", -1),
    ],
    name="user_conversation_terms_completed_idx",
    background=True,
)
await collection.create_index(
    [("conversation_search.version", 1), ("status", 1), ("updated_at", 1)],
    name="conversation_backfill_idx",
    background=True,
)
```

- [ ] **Step 6: Run the service and existing trace tests**

Run: `uv run pytest tests/infra/session/test_conversation_history_service.py tests/infra/session/test_trace_event_chunks.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/infra/session/conversation_history.py src/infra/session/trace_storage.py tests/infra/session/test_conversation_history_service.py
git commit -m "feat(history): search and page authorized conversations"
```

---

### Task 3: Deferred Internal Conversation-History Tools

**Files:**
- Create: `src/infra/tool/conversation_history_tool.py`
- Modify: `src/infra/tool/internal_registry.py`
- Test: `tests/infra/tool/test_conversation_history_tool.py`
- Modify: `tests/infra/tool/test_internal_registry_exposure.py`

**Interfaces:**
- Consumes: Task 2 `ConversationHistoryService` and `get_user_id_from_runtime()`.
- Produces: LangChain tools `search_conversation_history`, `get_conversation_detail`, and `get_conversation_history_tools() -> list[BaseTool]`.

- [ ] **Step 1: Write failing tool-contract tests**

```python
@pytest.mark.asyncio
async def test_search_tool_injects_user_and_returns_paginated_json(monkeypatch) -> None:
    calls = []

    class FakeService:
        async def search(self, user_id, query, limit=10, cursor=None):
            calls.append((user_id, query, limit, cursor))
            return {"success": True, "items": [], "next_cursor": None}

    monkeypatch.setattr(history_tools, "ConversationHistoryService", FakeService)
    result = json.loads(
        await history_tools.search_conversation_history.coroutine(
            "parser", 5, "cursor-1", runtime=_Runtime("user-1")
        )
    )

    assert result["success"] is True
    assert calls == [("user-1", "parser", 5, "cursor-1")]


@pytest.mark.asyncio
async def test_detail_tool_hides_unauthorized_resource_as_not_found(monkeypatch) -> None:
    class FakeService:
        async def get_detail(self, *args, **kwargs):
            raise ConversationHistoryNotFound

    monkeypatch.setattr(history_tools, "ConversationHistoryService", FakeService)
    result = json.loads(
        await history_tools.get_conversation_detail.coroutine(
            "foreign-session", "foreign-run", runtime=_Runtime("user-1")
        )
    )

    assert result == {"success": False, "error": "not_found"}
```

Also assert unauthenticated calls return `not_authenticated`, malformed cursors return `invalid_argument`, storage exceptions return `temporarily_unavailable`, and tool schemas cap `limit` at 20.

- [ ] **Step 2: Run tool tests and verify RED**

Run: `uv run pytest tests/infra/tool/test_conversation_history_tool.py -v`

Expected: FAIL because the tool module is absent.

- [ ] **Step 3: Implement the two wrappers with injected runtime and stable error categories**

```python
@tool
async def search_conversation_history(
    query: Annotated[str, "Text to find in historical user messages or final AI answers"],
    limit: Annotated[int, "Page size, 1-20"] = 10,
    cursor: Annotated[str | None, "Opaque next_cursor from a prior result"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """Search the current user's visible conversation history and return run references."""
```

```python
@tool
async def get_conversation_detail(
    session_id: Annotated[str, "Session ID returned by history search or memory recall"],
    run_id: Annotated[str | None, "Optional exact run ID"] = None,
    limit: Annotated[int, "Session page size, 1-20; ignored for exact run"] = 10,
    cursor: Annotated[str | None, "Opaque next_cursor for session paging"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """Read final user/assistant turns from one authorized historical session."""
```

Serialize with `json.dumps(result, ensure_ascii=False, default=str)` through `run_blocking_io`. Do not interpolate exception bodies into user-visible results or logs.

- [ ] **Step 4: Register the tools and prove default deferred exposure**

Extend `build_internal_tools()` with `get_conversation_history_tools()`. Add a registry test that builds the real tool list with unrelated features disabled, loads no explicit policies, and asserts both history tools land in `deferred`, not `direct`.

- [ ] **Step 5: Run focused tool and deferred-loading tests**

Run: `uv run pytest tests/infra/tool/test_conversation_history_tool.py tests/infra/tool/test_internal_registry_exposure.py tests/agents/test_deferred_system_tools.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/infra/tool/conversation_history_tool.py src/infra/tool/internal_registry.py tests/infra/tool/test_conversation_history_tool.py tests/infra/tool/test_internal_registry_exposure.py
git commit -m "feat(tools): expose deferred conversation history access"
```

---

### Task 4: Nonblocking New-Run Indexing and Distributed Historical Backfill

**Files:**
- Modify: `src/infra/session/conversation_history.py`
- Modify: `src/infra/session/trace_storage_writes.py`
- Modify: `src/infra/session/backfill.py`
- Modify: `src/api/main.py`
- Test: `tests/infra/session/test_conversation_history_lifecycle.py`
- Modify: `tests/infra/session/test_backfill_worker.py`

**Interfaces:**
- Consumes: Task 2 `ConversationHistoryService.index_trace()` and `backfill_indexes()`.
- Produces: `schedule_conversation_trace_index(trace_storage, trace_id) -> None` and `ConversationHistoryBackfillWorker`.

- [ ] **Step 1: Write failing completion-scheduling tests**

```python
@pytest.mark.asyncio
async def test_complete_trace_schedules_index_after_success(monkeypatch, trace_storage) -> None:
    scheduled = []
    monkeypatch.setattr(
        history,
        "schedule_conversation_trace_index",
        lambda storage, trace_id: scheduled.append((storage, trace_id)),
    )

    completed = await trace_storage.complete_trace("trace-1", "completed")

    assert completed is True
    assert scheduled == [(trace_storage, "trace-1")]


@pytest.mark.asyncio
async def test_index_task_failure_is_observed_without_raising(monkeypatch) -> None:
    async def fail(_trace_id):
        raise RuntimeError("database body must not leak")

    service = SimpleNamespace(index_trace=fail)
    schedule_conversation_trace_index(service, "trace-1")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert not history._conversation_index_tasks
```

- [ ] **Step 2: Write failing backfill tests**

```python
@pytest.mark.asyncio
async def test_conversation_backfill_uses_distinct_lock_and_runs_batches() -> None:
    redis_client = _FakeRedis(acquire=True)
    service = _FakeHistoryService([3, 1, 0])
    worker = ConversationHistoryBackfillWorker(
        service=service,
        redis_client=redis_client,
        batch_size=5,
        batch_delay_seconds=0,
    )

    assert await worker.run_until_complete() == 4
    assert service.calls == [5, 5, 5]
    assert redis_client.set_calls[0][0][0] == "conversation:search_backfill:lock"
```

- [ ] **Step 3: Run lifecycle tests and verify RED**

Run: `uv run pytest tests/infra/session/test_conversation_history_lifecycle.py tests/infra/session/test_backfill_worker.py -v`

Expected: FAIL because scheduling and the worker do not exist.

- [ ] **Step 4: Implement bounded background-task ownership and completion hook**

Keep a module-level `set[asyncio.Task]`, add a done callback that removes the task and logs only `type(exception).__name__`, and schedule only after `complete_trace()` modifies a trace. The task reads persisted events after `flush_mongo_buffer(require_empty=True)` has already completed through the Presenter lifecycle.

- [ ] **Step 5: Generalize the existing distributed worker without changing session-backfill behavior**

Refactor the common lock/run loop in `src/infra/session/backfill.py` into a private base that accepts `lock_key` and an async batch callback. Keep `SessionSearchBackfillWorker`'s public constructor and behavior unchanged, then add:

```python
class ConversationHistoryBackfillWorker(_DistributedBackfillWorker):
    def __init__(self, *, service=None, **kwargs):
        self._service = service or ConversationHistoryService()
        super().__init__(
            lock_key="conversation:search_backfill:lock",
            run_batch=self._service.backfill_indexes,
            **kwargs,
        )
```

- [ ] **Step 6: Start the history backfill in the existing delayed startup task**

After session-search backfill completes, run `ConversationHistoryBackfillWorker.run_until_complete()` in the same nonblocking startup coroutine and close both workers in `finally`. Store the task on `app.state` as before; do not create a second startup delay or block `lifespan()`.

- [ ] **Step 7: Run lifecycle, backfill, and startup-source tests**

Run: `uv run pytest tests/infra/session/test_conversation_history_lifecycle.py tests/infra/session/test_backfill_worker.py tests/infra/session/test_search_index.py -v`

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/infra/session/conversation_history.py src/infra/session/trace_storage_writes.py src/infra/session/backfill.py src/api/main.py tests/infra/session/test_conversation_history_lifecycle.py tests/infra/session/test_backfill_worker.py
git commit -m "feat(history): index completed and historical runs"
```

---

### Task 5: Validated Memory Source References and Automatic Current-Run Binding

**Files:**
- Modify: `src/infra/memory/client/base.py`
- Modify: `src/infra/memory/client/native/backend.py`
- Modify: `src/infra/memory/client/native/search.py`
- Modify: `src/infra/memory/tools.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Create: `tests/infra/memory/native/test_source_refs.py`
- Modify: `tests/infra/memory/test_tools.py`
- Modify: `tests/infra/memory/test_backend_interface.py`
- Modify: `tests/infra/memory/native/test_indexing.py`

**Interfaces:**
- Consumes: Task 1 `ConversationSourceRef`/`merge_source_refs()` and Task 2 `validate_source_refs()`.
- Produces: optional `source_refs` on `MemoryBackend.retain()`, `NativeMemoryBackend.auto_retain_from_text()`, `memory_retain`, and `schedule_auto_memory_capture()`; validated refs in `memory_recall` output.

- [ ] **Step 1: Write failing native retain/update/recall tests**

```python
@pytest.mark.asyncio
async def test_retain_validates_and_persists_source_refs(monkeypatch, native_backend) -> None:
    monkeypatch.setattr(
        history_service,
        "validate_source_refs",
        AsyncMock(return_value=[ConversationSourceRef(session_id="s1", run_id="r1")]),
    )

    result = await native_backend.retain(
        "u1",
        "User prefers compact durable answers.",
        title="Answer style",
        summary="Prefers compact durable answers.",
        tags=["answers", "style", "preference"],
        source_refs=[{"session_id": "s1", "run_id": "r1"}, {"session_id": "x", "run_id": "y"}],
    )

    assert result["success"] is True
    doc = native_backend._collection.docs[0]
    assert doc["source_refs"] == [{"session_id": "s1", "run_id": "r1"}]


@pytest.mark.asyncio
async def test_updating_memory_merges_existing_source_refs(native_backend) -> None:
    result = await native_backend.retain(
        "u1",
        "Updated durable preference content.",
        title="Preference",
        summary="Updated durable preference.",
        tags=["preference", "durable", "updated"],
        existing_memory_id="memory-1",
        source_refs=[{"session_id": "s2", "run_id": "r2"}],
    )

    assert result["success"] is True
    assert native_backend._collection.docs[0]["source_refs"] == [
        {"session_id": "s1", "run_id": "r1"},
        {"session_id": "s2", "run_id": "r2"},
    ]


@pytest.mark.asyncio
async def test_recall_filters_stale_refs_but_keeps_memory(monkeypatch, native_backend) -> None:
    result = await native_backend.recall("u1", "preference", 5, None)

    assert len(result["memories"]) == 1
    assert result["memories"][0]["source_refs"] == [
        {"session_id": "visible", "run_id": "run-visible"}
    ]
```

- [ ] **Step 2: Write failing automatic-capture propagation tests**

```python
@pytest.mark.asyncio
async def test_auto_capture_passes_current_source_to_backend(monkeypatch) -> None:
    captured = []

    class FakeBackend:
        async def auto_retain_from_text(self, user_id, text, source_refs=None):
            captured.append((user_id, text, source_refs))
            return {"success": True, "stored": 1, "candidates": 1}

    await memory_tools._auto_retain_user_memory(
        "u1",
        "I prefer concise answers.",
        source_refs=[ConversationSourceRef(session_id="s1", run_id="r1")],
    )

    assert captured[0][2][0].run_id == "r1"
```

Add source-structure assertions for each Agent node so all three call `schedule_auto_memory_capture()` with `TraceContext.get_request_context().session_id/run_id` rather than only `user_id` and text.

Add a regression assertion in `tests/infra/memory/native/test_indexing.py` that `build_memory_index()` contains neither `session_id` nor `run_id` even when stored memories have `source_refs`.

- [ ] **Step 3: Run memory tests and verify RED**

Run: `uv run pytest tests/infra/memory/native/test_source_refs.py tests/infra/memory/test_tools.py tests/infra/memory/test_backend_interface.py tests/infra/memory/native/test_indexing.py -v`

Expected: FAIL because memory interfaces do not accept source references.

- [ ] **Step 4: Extend memory interfaces and retain semantics**

Add the same final optional parameter everywhere:

```python
source_refs: Optional[list[ConversationSourceRef | dict[str, str]]] = None
```

In native `retain()`, validate incoming refs through `ConversationHistoryService`, include `source_refs` in the existing-match projection, merge valid refs with existing refs, store plain `model_dump()` dictionaries, and cap to 20. Invalid refs are dropped; a memory with no valid refs is still valid.

- [ ] **Step 5: Return only currently authorized refs from recall**

Include `source_refs` in every text/vector/fallback projection and `format_memory()`. After ranking/hydration and before returning, flatten refs from selected memories, validate them in one batch, and filter each memory's refs against the allowed pair set. Do not include refs in `build_memory_index()` or its projections.

- [ ] **Step 6: Propagate current-run refs through detached auto capture**

Extend `_auto_retain_user_memory`, `_auto_retain_user_memory_detached`, `schedule_auto_memory_capture`, and `NativeMemoryBackend.auto_retain_from_text`. The detached task receives a copied list of source refs and passes it into `retain()` only when the evaluator actually emits a `memory_retain` tool call.

At each Agent node call site:

```python
request_context = TraceContext.get_request_context()
schedule_auto_memory_capture(
    context.user_id,
    user_input,
    source_refs=[
        ConversationSourceRef(
            session_id=request_context.session_id,
            run_id=request_context.run_id,
        )
    ]
    if request_context.session_id and request_context.run_id
    else None,
)
```

- [ ] **Step 7: Run focused memory and Agent propagation tests**

Run: `uv run pytest tests/infra/memory/native/test_source_refs.py tests/infra/memory/test_tools.py tests/infra/memory/test_backend_interface.py tests/infra/memory/native/test_indexing.py tests/agents/test_disabled_skills_config_propagation.py -v`

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/infra/memory/client/base.py src/infra/memory/client/native/backend.py src/infra/memory/client/native/search.py src/infra/memory/tools.py src/agents/fast_agent/nodes.py src/agents/search_agent/nodes.py src/agents/team_agent/nodes.py tests/infra/memory/native/test_source_refs.py tests/infra/memory/test_tools.py tests/infra/memory/test_backend_interface.py tests/infra/memory/native/test_indexing.py tests/agents/test_disabled_skills_config_propagation.py
git commit -m "feat(memory): retain authorized conversation sources"
```

---

### Task 6: Preserve References Through Consolidation and Memory API Round Trips

**Files:**
- Modify: `src/infra/memory/client/native/consolidation.py`
- Modify: `src/api/routes/memory.py`
- Modify: `tests/infra/memory/native/test_consolidation.py`
- Create: `tests/api/routes/test_memory_source_refs.py`

**Interfaces:**
- Consumes: Task 1 `merge_source_refs()` and Task 2 source validation.
- Produces: consolidation and export/import/list/detail flows that preserve valid source refs without exposing unauthorized refs.

- [ ] **Step 1: Write failing consolidation preservation test**

```python
@pytest.mark.asyncio
async def test_consolidation_preserves_bounded_union_of_source_refs(monkeypatch) -> None:
    memories = [
        {
            "user_id": "u1",
            "content": f"durable preference {index}",
            "source_refs": [{"session_id": "s1", "run_id": f"r{index}"}],
            "created_at": utc_now(),
        }
        for index in range(3)
    ]

    docs = await consolidation._llm_batch_consolidate(backend, memories, "user")

    assert docs
    assert docs[0]["source_refs"] == [
        {"session_id": "s1", "run_id": "r0"},
        {"session_id": "s1", "run_id": "r1"},
        {"session_id": "s1", "run_id": "r2"},
    ]
```

- [ ] **Step 2: Write failing API round-trip tests**

```python
def test_memory_projection_includes_source_refs() -> None:
    assert memory_routes._memory_projection()["source_refs"] == 1


@pytest.mark.asyncio
async def test_export_and_get_return_valid_source_refs(client, seeded_memory) -> None:
    detail = await client.get(f"/api/v1/memories/{seeded_memory['memory_id']}")
    exported = await client.get("/api/v1/memories/export")

    assert detail.json()["source_refs"] == [{"session_id": "s1", "run_id": "r1"}]
    assert exported.json()["memories"][0]["source_refs"] == [
        {"session_id": "s1", "run_id": "r1"}
    ]
```

Add an import test where one valid and one foreign reference are supplied; only the valid reference may be stored.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/infra/memory/native/test_consolidation.py tests/api/routes/test_memory_source_refs.py -v`

Expected: FAIL because consolidation and API projections omit `source_refs`.

- [ ] **Step 4: Preserve refs through consolidation**

Compute one bounded, deduplicated union from the input batch and attach it to every conservative consolidated output. This may over-associate within a batch, but never loses traceability; the 20-ref cap prevents growth. The normal recall-time authorization pass still filters deleted or inaccessible refs.

- [ ] **Step 5: Preserve and validate refs in memory HTTP flows**

Add `source_refs` to `_memory_projection()`, list/detail responses, and export objects. Batch-validate references for list results and validate per document for detail/export before serializing them. During import, normalize the optional list, validate it for `user.sub`, and store only authorized refs. Existing imports without the field remain unchanged.

- [ ] **Step 6: Run consolidation and API tests**

Run: `uv run pytest tests/infra/memory/native/test_consolidation.py tests/api/routes/test_memory_source_refs.py tests/api/routes/test_memory_import_export.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add src/infra/memory/client/native/consolidation.py src/api/routes/memory.py tests/infra/memory/native/test_consolidation.py tests/api/routes/test_memory_source_refs.py
git commit -m "feat(memory): preserve conversation sources across lifecycle"
```

---

### Task 7: Security, Schema Budget, and Full Verification

**Files:**
- Modify only if failures expose a scoped defect in files already listed above.
- Test: all files from Tasks 1-6 plus existing schema-budget and security regression suites.

**Interfaces:**
- Consumes: complete feature from Tasks 1-6.
- Produces: evidence that the feature meets the design without regressing prompt size or unrelated session behavior.

- [ ] **Step 1: Run the complete focused backend suite**

Run:

```bash
uv run pytest \
  tests/infra/session/test_conversation_history_index.py \
  tests/infra/session/test_conversation_history_service.py \
  tests/infra/session/test_conversation_history_lifecycle.py \
  tests/infra/session/test_backfill_worker.py \
  tests/infra/tool/test_conversation_history_tool.py \
  tests/infra/tool/test_internal_registry_exposure.py \
  tests/infra/memory/native/test_source_refs.py \
  tests/infra/memory/test_tools.py \
  tests/infra/memory/native/test_consolidation.py \
  tests/api/routes/test_memory_source_refs.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run prompt/tool exposure regression tests**

Run:

```bash
uv run pytest \
  tests/agents/test_deferred_system_tools.py \
  tests/agents/core/test_system_prompt_budget.py \
  tests/infra/tool/test_internal_tool_schema_budget.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run session and memory regression suites**

Run: `uv run pytest tests/infra/session tests/infra/memory tests/api/routes/test_session_runs.py tests/api/routes/test_memory_import_export.py -v`

Expected: PASS.

- [ ] **Step 4: Run static checks on touched backend code**

Run: `make lint && make typecheck`

Expected: both commands exit 0.

- [ ] **Step 5: Inspect scope and secret safety**

Run:

```bash
git diff --check
git status --short
git diff --stat HEAD~6..HEAD
rg -n "logger\..*(user_text|assistant_final|source_refs|memory.*content)" src/infra/session src/infra/memory src/infra/tool
```

Expected: no whitespace errors; only planned files are changed; the log scan finds no message-body or full-reference logging. The user's pre-existing `frontend/src/components/chat/ChatInput.tsx` and `frontend/src/components/chat/__tests__/chatInputSendShortcut.test.tsx` changes remain untouched and uncommitted.

- [ ] **Step 6: Commit any verification-only fixes**

If and only if verification required scoped fixes, stage exact affected files and commit:

```bash
git add <exact-files-fixed-during-verification>
git commit -m "fix(history): address verification findings"
```

If no fixes were necessary, do not create an empty commit.
