from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.infra.task.status import TaskStatus
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
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self._docs = docs if docs is not None else [{"metadata": {}}]
        self.find_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.aggregate_pipelines: list[list[dict[str, Any]]] = []

    def find(self, query: dict[str, Any], projection: dict[str, Any]):
        self.find_calls.append((query, projection))
        if projection.get("events"):
            raise AssertionError("get_run_error must not load the full trace events array")
        return _FakeFindCursor(self._docs)

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


@pytest.fixture
def status_queries(monkeypatch):
    def create(metadata, trace_status=None):
        collection = _FakeTraceCollection(
            [{"status": trace_status}] if trace_status is not None else []
        )
        monkeypatch.setattr(
            "src.infra.task.status_queries.get_trace_storage",
            lambda: SimpleNamespace(collection=collection),
        )
        return TaskStatusQueries(
            storage=SimpleNamespace(
                get_by_session_id=AsyncMock(return_value=SimpleNamespace(metadata=metadata))
            ),
            run_info={},
        )

    return create


@pytest.mark.parametrize("trace_status", [None, "running"])
async def test_current_recoverable_restart_is_projected_as_recovering(status_queries, trace_status):
    queries = status_queries(
        {
            "current_run_id": "r1",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
        },
        trace_status,
    )

    assert await queries.get_run_status("s1", "r1") == TaskStatus.RECOVERING
    assert await queries.get_status("s1") == TaskStatus.RECOVERING


@pytest.mark.parametrize(
    ("trace_status", "expected"),
    [
        ("completed", TaskStatus.COMPLETED),
        ("error", TaskStatus.FAILED),
        ("failed", TaskStatus.FAILED),
        ("cancelled", TaskStatus.CANCELLED),
        ("expired", TaskStatus.EXPIRED),
    ],
)
async def test_terminal_trace_overrides_stale_recoverable_restart_metadata(
    status_queries, trace_status, expected
):
    queries = status_queries(
        {
            "current_run_id": "r1",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
        },
        trace_status,
    )

    assert await queries.get_run_status("s1", "r1") == expected
    assert await queries.get_status("s1") == expected


@pytest.mark.parametrize(
    "override",
    [
        {"task_recoverable": False},
        {"task_recoverable": None},
        {"task_recoverable": 1},
        {"task_recoverable": "True"},
        {"task_error_code": "internal_error"},
        {"task_error_code": None},
    ],
)
async def test_unconfirmed_restart_failures_remain_failed(status_queries, override):
    queries = status_queries(
        {
            "current_run_id": "r1",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
            **override,
        }
    )

    assert await queries.get_run_status("s1", "r1") == TaskStatus.FAILED
    assert await queries.get_status("s1") == TaskStatus.FAILED


@pytest.mark.parametrize("status", ["completed", "cancelled", "expired"])
async def test_true_terminal_session_status_is_not_hidden_by_stale_restart_flags(
    status_queries, status
):
    queries = status_queries(
        {
            "current_run_id": "r1",
            "task_status": status,
            "task_recoverable": True,
            "task_error_code": "server_restart",
        }
    )

    assert await queries.get_run_status("s1", "r1") == TaskStatus(status)
    assert await queries.get_status("s1") == TaskStatus(status)


async def test_restart_projection_cannot_borrow_another_runs_metadata(status_queries):
    queries = status_queries(
        {
            "current_run_id": "r2",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
        },
        "completed",
    )

    assert await queries.get_run_status("s1", "r1") == TaskStatus.COMPLETED
