from types import SimpleNamespace

import pytest

from src.infra.session.trace_storage import TraceStorage


class _FakeTraceCollection:
    def __init__(self, *, has_usage: bool) -> None:
        self.has_usage = has_usage
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        if "events.event_type" in query:
            return SimpleNamespace(modified_count=0 if self.has_usage else 1)
        return SimpleNamespace(modified_count=1)


class _FakeMerger:
    def __init__(self) -> None:
        self.schedule_calls = 0

    def schedule_merge_once(self) -> None:
        self.schedule_calls += 1


class _FakeTraceCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self.sort_args = None
        self.skip_value = None
        self.limit_value = None
        self.to_list_length = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def __aiter__(self):
        self._iter_index = 0
        return self

    async def __anext__(self):
        docs = self._docs
        if self.skip_value:
            docs = docs[self.skip_value :]
        if self.limit_value is not None:
            docs = docs[: self.limit_value]
        if self._iter_index >= len(docs):
            raise StopAsyncIteration
        item = docs[self._iter_index]
        self._iter_index += 1
        return item

    async def to_list(self, length=None):
        self.to_list_length = length
        docs = self._docs
        if self.skip_value:
            docs = docs[self.skip_value :]
        cap = self.limit_value if self.limit_value is not None else length
        if cap is not None:
            docs = docs[:cap]
        return docs


class _FakeRunSummaryCollection:
    def __init__(self):
        self.find_calls = []
        self.cursor = _FakeTraceCursor(
            [
                {"run_id": "skip-1"},
                {"run_id": "skip-2"},
                {"run_id": "skip-3"},
                {"run_id": "skip-4"},
                {"run_id": "skip-5"},
                {
                    "run_id": "run-1",
                    "trace_id": "trace-1",
                    "agent_id": "agent-1",
                    "started_at": "2026-04-25T00:00:00Z",
                    "completed_at": "2026-04-25T00:01:00Z",
                    "status": "completed",
                    "event_count": 3,
                    "first_user_message_preview": {
                        "event_type": "user:message",
                        "data": {"content": "a message longer than twenty chars"},
                    },
                },
            ]
        )

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return self.cursor


class _FakeListTracesCollection:
    def __init__(self):
        self.find_calls = []
        self.cursor = _FakeTraceCursor([])

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return self.cursor


class _FakeTraceSummaryCollection:
    def __init__(self):
        self.find_one_calls = []

    async def find_one(self, query, projection):
        self.find_one_calls.append((query, projection))
        doc = {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "event_count": 10_000,
            "events": [{"event_type": "message:chunk", "data": {"text": "large"}}],
        }
        if projection.get("events") == 0:
            doc.pop("events")
        if projection.get("_id") == 0:
            doc.pop("_id", None)
        return doc


class _FakeSessionEventsAggregationCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self._docs:
            yield doc


class _FakeSessionEventsAggregationCollection:
    def __init__(self):
        self.aggregate_calls = []
        self.find_calls = []
        self.find_one_calls = []
        self.cursor = _FakeTraceCursor(
            [
                {
                    "trace_id": "trace-1",
                    "run_id": "run-1",
                    "started_at": "2026-04-25T00:00:00Z",
                }
            ]
        )

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        return _FakeSessionEventsAggregationCursor(
            [
                {
                    "trace_id": "trace-1",
                    "run_id": "run-1",
                    "event_type": "user:message",
                    "data": {"content": "hello"},
                    "timestamp": "2026-04-25T00:00:00Z",
                },
                {
                    "trace_id": "trace-1",
                    "run_id": "run-1",
                    "event_type": "done",
                    "data": {},
                    "timestamp": "2026-04-25T00:00:01Z",
                },
            ]
        )

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        return self.cursor

    async def find_one(self, query, projection):
        self.find_one_calls.append((query, projection))
        if query.get("trace_id") == "trace-1":
            return {
                "trace_id": "trace-1",
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"content": "hello"},
                        "timestamp": "2026-04-25T00:00:00Z",
                    },
                    {
                        "event_type": "done",
                        "data": {},
                        "timestamp": "2026-04-25T00:00:01Z",
                    },
                ],
            }
        return None


class _NoMaterializeSessionEventsCollection(_FakeSessionEventsAggregationCollection):
    class _Cursor(_FakeTraceCursor):
        async def to_list(self, length=None):
            raise AssertionError("get_session_events should stream trace metadata")

    def __init__(self):
        super().__init__()
        self.cursor = self._Cursor(
            [
                {
                    "trace_id": "trace-1",
                    "run_id": "run-1",
                    "started_at": "2026-04-25T00:00:00Z",
                }
            ]
        )


class _FakeTraceEventAggregationCollection:
    def __init__(self, docs=None):
        self.aggregate_calls = []
        self.find_one_calls = []
        self._docs = docs or [
            {
                "event_type": "user:message",
                "data": {"content": "hello"},
                "timestamp": "2026-04-25T00:00:00Z",
            },
        ]

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        return _FakeSessionEventsAggregationCursor(self._docs)

    async def find_one(self, *args, **kwargs):
        self.find_one_calls.append((args, kwargs))
        return {"trace_id": "trace-1", "events": self._docs}


class _FakeEmptyChunkCollection:
    async def find_one(self, *args, **kwargs):
        return None


def _usage_event_from_pipeline(update):
    return (
        update[0]["$set"]["events"]["$let"]["vars"].get("usage_event")
        or update[0]["$set"]["events"]["$let"]["in"]["$cond"][1]["$concatArrays"][1][0]
    )


@pytest.mark.asyncio
async def test_complete_trace_adds_zero_token_usage_when_missing() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(has_usage=False)

    assert await storage.complete_trace("trace-1", status="error") is True

    usage_query, usage_update = storage.collection.calls[0]
    assert usage_query == {
        "trace_id": "trace-1",
        "events.event_type": {"$ne": "token:usage"},
    }
    usage_event = _usage_event_from_pipeline(usage_update)
    assert usage_event["event_type"] == "token:usage"
    assert usage_event["data"]["input_tokens"] == 0
    assert usage_event["data"]["output_tokens"] == 0
    assert usage_event["data"]["total_tokens"] == 0
    done_branch = usage_update[0]["$set"]["events"]["$let"]["in"]["$cond"][1]
    assert done_branch["$concatArrays"][1] == [usage_event]


@pytest.mark.asyncio
async def test_complete_trace_does_not_duplicate_existing_token_usage() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(has_usage=True)

    assert await storage.complete_trace("trace-1", status="completed") is True

    assert len(storage.collection.calls) == 2
    usage_update = storage.collection.calls[0][1]
    assert _usage_event_from_pipeline(usage_update)["event_type"] == "token:usage"
    assert storage.collection.calls[1][0] == {"trace_id": "trace-1"}


@pytest.mark.asyncio
async def test_complete_trace_can_skip_zero_token_usage_placeholder() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(has_usage=False)

    assert await storage.complete_trace("trace-1", status="error", ensure_token_usage=False) is True

    assert len(storage.collection.calls) == 1
    assert storage.collection.calls[0][0] == {"trace_id": "trace-1"}


@pytest.mark.asyncio
async def test_complete_trace_schedules_immediate_event_merge() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(has_usage=False)
    storage._merger = _FakeMerger()

    assert await storage.complete_trace("trace-1", status="completed") is True

    assert storage._merger.schedule_calls == 1


@pytest.mark.asyncio
async def test_list_run_summaries_uses_first_user_message_preview() -> None:
    storage = TraceStorage()
    storage._collection = _FakeRunSummaryCollection()

    summaries = await storage.list_run_summaries("session-1", limit=10, skip=5)

    assert summaries == [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "agent_id": "agent-1",
            "started_at": "2026-04-25T00:00:00Z",
            "completed_at": "2026-04-25T00:01:00Z",
            "status": "completed",
            "event_count": 3,
            "user_message": "a message longer ...",
        }
    ]
    assert storage.collection.find_calls == [
        (
            {"session_id": "session-1"},
            {
                "_id": 0,
                "run_id": 1,
                "trace_id": 1,
                "agent_id": 1,
                "started_at": 1,
                "completed_at": 1,
                "status": 1,
                "event_count": 1,
                "first_user_message_preview": 1,
            },
        )
    ]
    assert storage.collection.cursor.sort_args == ("started_at", -1)
    assert storage.collection.cursor.skip_value == 5
    assert storage.collection.cursor.limit_value == 10


@pytest.mark.asyncio
async def test_list_traces_clamps_storage_limit() -> None:
    storage = TraceStorage()
    storage._collection = _FakeListTracesCollection()

    traces = await storage.list_traces(session_id="session-1", limit=10_000, skip=-5)

    assert traces == []
    assert storage.collection.cursor.skip_value == 0
    assert storage.collection.cursor.limit_value == 100
    assert storage.collection.cursor.to_list_length == 100


@pytest.mark.asyncio
async def test_list_run_summaries_clamps_storage_limit() -> None:
    storage = TraceStorage()
    storage._collection = _FakeRunSummaryCollection()

    await storage.list_run_summaries("session-1", limit=10_000, skip=-5)

    assert storage.collection.cursor.skip_value == 0
    assert storage.collection.cursor.limit_value == 100


@pytest.mark.asyncio
async def test_get_trace_returns_summary_without_events_array_by_default() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceSummaryCollection()

    trace = await storage.get_trace("trace-1")

    assert trace == {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "event_count": 10_000,
    }
    assert storage.collection.find_one_calls == [
        (
            {"trace_id": "trace-1"},
            {"_id": 0, "events": 0},
        )
    ]


@pytest.mark.asyncio
async def test_get_session_events_uses_server_side_limit_when_max_events_is_set() -> None:
    storage = TraceStorage()
    collection = _FakeSessionEventsAggregationCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_session_events(
        "session-1",
        event_types=["user:message", "done"],
        run_ids=["run-1"],
        max_events=2,
    )

    assert events == [
        {
            "trace_id": "trace-1",
            "run_id": "run-1",
            "event_type": "user:message",
            "data": {"content": "hello"},
            "timestamp": "2026-04-25T00:00:00Z",
        },
        {
            "trace_id": "trace-1",
            "run_id": "run-1",
            "event_type": "done",
            "data": {},
            "timestamp": "2026-04-25T00:00:01Z",
        },
    ]
    assert collection.aggregate_calls == []
    assert collection.find_calls == [
        (
            {
                "session_id": "session-1",
                "run_id": {"$in": ["run-1"]},
                "status": {"$ne": "running"},
            },
            {"_id": 0, "trace_id": 1, "run_id": 1, "started_at": 1},
        )
    ]


@pytest.mark.asyncio
async def test_get_session_events_clamps_requested_max_events() -> None:
    storage = TraceStorage()
    collection = _FakeSessionEventsAggregationCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_session_events("session-1", max_events=1)

    assert len(events) == 1


@pytest.mark.asyncio
async def test_get_session_events_does_not_limit_when_max_events_is_unset() -> None:
    storage = TraceStorage()
    collection = _FakeSessionEventsAggregationCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_session_events("session-1")

    assert len(events) == 2
    assert collection.aggregate_calls == []


@pytest.mark.asyncio
async def test_get_session_events_streams_trace_metadata_cursor() -> None:
    storage = TraceStorage()
    collection = _NoMaterializeSessionEventsCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_session_events("session-1", max_events=1)

    assert len(events) == 1


@pytest.mark.asyncio
async def test_get_session_events_bounds_run_ids_and_event_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.session import trace_storage as trace_module

    monkeypatch.setattr(trace_module, "SESSION_EVENT_FILTER_LIST_LIMIT", 2, raising=False)
    storage = TraceStorage()
    collection = _FakeSessionEventsAggregationCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    await storage.get_session_events(
        "session-1",
        event_types=["user:message", "done", "thinking", "done"],
        run_ids=["run-1", "run-2", "run-3", "run-2"],
        max_events=2,
    )

    assert collection.find_calls[0][0] == {
        "session_id": "session-1",
        "run_id": {"$in": ["run-1", "run-2"]},
        "status": {"$ne": "running"},
    }


@pytest.mark.asyncio
async def test_get_first_trace_event_uses_server_side_limit() -> None:
    storage = TraceStorage()
    collection = _FakeTraceEventAggregationCollection()
    storage._collection = collection

    event = await storage.get_first_trace_event("trace-1", event_types=["user:message"])

    assert event == {
        "event_type": "user:message",
        "data": {"content": "hello"},
        "timestamp": "2026-04-25T00:00:00Z",
    }
    assert collection.find_one_calls == []
    assert collection.aggregate_calls == [
        [
            {"$match": {"trace_id": "trace-1"}},
            {
                "$project": {
                    "events.event_type": 1,
                    "events.data": 1,
                    "events.timestamp": 1,
                }
            },
            {"$unwind": "$events"},
            {"$match": {"events.event_type": {"$in": ["user:message"]}}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "event_type": "$events.event_type",
                    "data": "$events.data",
                    "timestamp": "$events.timestamp",
                }
            },
        ]
    ]


@pytest.mark.asyncio
async def test_get_last_trace_event_uses_server_side_sort_and_limit() -> None:
    storage = TraceStorage()
    collection = _FakeTraceEventAggregationCollection(
        docs=[
            {
                "event_type": "error",
                "data": {"error": "latest"},
                "timestamp": "2026-04-25T00:00:01Z",
            }
        ]
    )
    storage._collection = collection

    event = await storage.get_last_trace_event("trace-1", event_types=["error"])

    assert event == {
        "event_type": "error",
        "data": {"error": "latest"},
        "timestamp": "2026-04-25T00:00:01Z",
    }
    assert collection.find_one_calls == []
    assert collection.aggregate_calls == [
        [
            {"$match": {"trace_id": "trace-1"}},
            {
                "$project": {
                    "events.event_type": 1,
                    "events.data": 1,
                    "events.timestamp": 1,
                    "events.seq": 1,
                }
            },
            {"$unwind": "$events"},
            {"$match": {"events.event_type": {"$in": ["error"]}}},
            {"$sort": {"events.seq": -1, "events.timestamp": -1}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "event_type": "$events.event_type",
                    "data": "$events.data",
                    "timestamp": "$events.timestamp",
                }
            },
        ]
    ]


@pytest.mark.asyncio
async def test_get_trace_events_falls_back_to_legacy_events() -> None:
    storage = TraceStorage()
    collection = _FakeTraceEventAggregationCollection()
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_trace_events("trace-1", event_types=["user:message"])

    assert events == [
        {
            "event_type": "user:message",
            "data": {"content": "hello"},
            "timestamp": "2026-04-25T00:00:00Z",
        }
    ]
    assert collection.aggregate_calls == []
    assert collection.find_one_calls == [(({"trace_id": "trace-1"}, {"_id": 0, "events": 1}), {})]


@pytest.mark.asyncio
async def test_get_trace_events_does_not_limit_by_default() -> None:
    storage = TraceStorage()
    collection = _FakeTraceEventAggregationCollection(
        docs=[
            {"event_type": "message", "data": {"content": "a"}, "timestamp": "t1"},
            {"event_type": "message", "data": {"content": "b"}, "timestamp": "t2"},
        ]
    )
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_trace_events("trace-1")

    assert [event["data"]["content"] for event in events] == ["a", "b"]
    assert collection.aggregate_calls == []


@pytest.mark.asyncio
async def test_get_trace_events_clamps_requested_max_events() -> None:
    storage = TraceStorage()
    collection = _FakeTraceEventAggregationCollection(
        docs=[
            {"event_type": "message", "data": {"content": "a"}, "timestamp": "t1"},
            {"event_type": "message", "data": {"content": "b"}, "timestamp": "t2"},
        ]
    )
    storage._collection = collection
    storage._chunks_collection = _FakeEmptyChunkCollection()

    events = await storage.get_trace_events("trace-1", max_events=1)

    assert [event["data"]["content"] for event in events] == ["a"]
