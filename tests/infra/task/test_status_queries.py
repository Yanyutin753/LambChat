from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.task.status_queries import TaskStatusQueries


class _FakeStorage:
    async def get_by_session_id(self, session_id: str):
        return None


class _FakeFindCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def sort(self, *args: Any, **kwargs: Any):
        return self

    def limit(self, *args: Any, **kwargs: Any):
        return self

    async def to_list(self, length: int):
        return list(self._docs[:length])


class _FakeAggregateCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeTraceCollection:
    def __init__(self) -> None:
        self.find_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.aggregate_pipelines: list[list[dict[str, Any]]] = []

    def find(self, query: dict[str, Any], projection: dict[str, Any]):
        self.find_calls.append((query, projection))
        if projection.get("events"):
            raise AssertionError("get_run_error must not load the full trace events array")
        return _FakeFindCursor([{"metadata": {}}])

    async def aggregate(self, pipeline: list[dict[str, Any]]):
        self.aggregate_pipelines.append(pipeline)
        return _FakeAggregateCursor(
            [{"event_type": "error", "data": {"error": "bounded error"}, "timestamp": "now"}]
        )


@pytest.mark.asyncio
async def test_get_run_error_fetches_single_error_event_without_full_events_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeTraceCollection()
    trace_storage = SimpleNamespace(collection=collection)

    async def _get_last_trace_event(trace_id: str, event_types: list[str]):
        assert trace_id == "trace-1"
        assert event_types == ["error"]
        async for event in await collection.aggregate(
            [
                {"$match": {"trace_id": trace_id}},
                {"$unwind": "$events"},
                {"$match": {"events.event_type": {"$in": event_types}}},
                {"$sort": {"events.seq": -1, "events.timestamp": -1}},
                {"$limit": 1},
            ]
        ):
            return event
        return None

    trace_storage.get_last_trace_event = _get_last_trace_event
    monkeypatch.setattr(
        "src.infra.task.status_queries.get_trace_storage",
        lambda: trace_storage,
    )

    queries = TaskStatusQueries(
        storage=_FakeStorage(),
        run_info={"run-1": {"trace_id": "trace-1"}},
    )

    assert await queries.get_run_error("run-1") == "bounded error"
    assert collection.find_calls == [
        ({"run_id": "run-1"}, {"metadata": 1, "trace_id": 1, "_id": 0})
    ]
    assert collection.aggregate_pipelines
