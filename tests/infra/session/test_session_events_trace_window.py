"""按 trace(run) 窗口分页读取会话事件的测试。

长会话首次打开只需最近 N 轮，向上滚动时用游标 (started_at, trace_id)
继续取更早的轮次。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from src.infra.session.trace_storage import TraceStorage

UTC = timezone.utc
BASE = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _trace_doc(
    index: int,
    *,
    session_id: str = "session-1",
    run_id: str | None = None,
    status: str = "completed",
) -> Dict[str, Any]:
    started_at = BASE + timedelta(minutes=index)
    run_id = run_id or f"run-{index}"
    return {
        "trace_id": f"trace-{index:02d}",
        "session_id": session_id,
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "updated_at": started_at + timedelta(seconds=30),
        "completed_at": started_at + timedelta(seconds=30),
        "events": [
            {
                "seq": 1,
                "event_type": "user:message",
                "data": {"content": f"question {index}"},
                "timestamp": started_at.isoformat(),
            },
            {
                "seq": 2,
                "event_type": "message:chunk",
                "data": {"content": f"answer {index}"},
                "timestamp": (started_at + timedelta(seconds=1)).isoformat(),
            },
        ],
    }


def _event_contents(snapshot) -> List[str]:
    return [
        str(event["data"].get("content"))
        for event in snapshot.events
        if event.get("event_type") == "message:chunk"
    ]


class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self._docs = docs
        self._sort_spec: Any = None
        self._limit: int | None = None

    def sort(self, *args: Any) -> "_FakeCursor":
        # 兼容 sort([(f, d), ...])、sort((f, d)) 与 sort(f, d) 三种调用形态
        self._sort_spec = args[0] if len(args) == 1 else tuple(args)
        return self

    def limit(self, value: int) -> "_FakeCursor":
        self._limit = value
        return self

    def _sorted_docs(self) -> List[Dict[str, Any]]:
        docs = list(self._docs)
        if not self._sort_spec:
            return docs
        if isinstance(self._sort_spec, str):
            spec = [(self._sort_spec, 1)]
        elif (
            isinstance(self._sort_spec, tuple)
            and len(self._sort_spec) == 2
            and isinstance(self._sort_spec[0], str)
        ):
            spec = [self._sort_spec]
        else:
            spec = [(str(field), int(direction)) for field, direction in self._sort_spec]
        for field, direction in reversed(spec):
            docs.sort(key=lambda doc: doc.get(field), reverse=direction < 0)
        return docs

    async def __aiter__(self):
        docs = self._sorted_docs()
        if self._limit is not None:
            docs = docs[: self._limit]
        for doc in docs:
            yield doc


def _as_timestamp(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()
    return value


def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for key, condition in query.items():
        if key == "$and":
            if not all(_matches(doc, part) for part in condition):
                return False
            continue
        if key == "$or":
            if not any(_matches(doc, part) for part in condition):
                return False
            continue
        value = doc.get(key)
        if isinstance(condition, dict):
            for operator, target in condition.items():
                if operator == "$ne" and value == target:
                    return False
                if operator == "$in" and value not in target:
                    return False
                if operator == "$lt" and not _as_timestamp(value) < _as_timestamp(target):
                    return False
            continue
        if value != condition:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self.docs = docs
        self.queries: List[Dict[str, Any]] = []
        self.sort_specs: List[Any] = []
        self.limits: List[int | None] = []

    def find(self, query: Dict[str, Any], _projection: Any = None) -> _FakeCursor:
        self.queries.append(query)
        cursor = _FakeCursor([doc for doc in self.docs if _matches(doc, query)])
        original_sort = cursor.sort
        original_limit = cursor.limit

        def _record_sort(*args: Any) -> _FakeCursor:
            self.sort_specs.append(args[0] if len(args) == 1 else tuple(args))
            return original_sort(*args)

        def _record_limit(value: int) -> _FakeCursor:
            self.limits.append(value)
            return original_limit(value)

        cursor.sort = _record_sort  # type: ignore[method-assign]
        cursor.limit = _record_limit  # type: ignore[method-assign]
        return cursor


def _make_storage(collection: _FakeCollection) -> TraceStorage:
    storage = TraceStorage()
    storage._collection = collection
    storage._chunks_collection = _FakeCollection([])
    return storage


@pytest.mark.asyncio
async def test_trace_limit_returns_only_newest_window_with_more_flag_and_cursor() -> None:
    collection = _FakeCollection([_trace_doc(i) for i in range(1, 6)])
    storage = _make_storage(collection)

    snapshot = await storage.get_session_events_snapshot(
        "session-1",
        trace_limit=2,
    )

    # 只返回最新的两轮（trace-04 / trace-05），事件按时间升序
    assert _event_contents(snapshot) == ["answer 4", "answer 5"]
    assert snapshot.has_more_traces is True
    assert snapshot.oldest_trace_id == "trace-04"
    assert snapshot.oldest_trace_started_at == BASE + timedelta(minutes=4)

    # 窗口查询应从新到旧排序并探测 limit+1 条
    assert collection.sort_specs[-1] == [("started_at", -1), ("trace_id", -1)]
    assert collection.limits[-1] == 3


@pytest.mark.asyncio
async def test_before_trace_cursor_pages_backwards_until_exhausted() -> None:
    collection = _FakeCollection([_trace_doc(i) for i in range(1, 6)])
    storage = _make_storage(collection)

    first_page = await storage.get_session_events_snapshot("session-1", trace_limit=2)
    second_page = await storage.get_session_events_snapshot(
        "session-1",
        trace_limit=2,
        before_trace_started_at=first_page.oldest_trace_started_at,
        before_trace_id=first_page.oldest_trace_id,
    )
    assert _event_contents(second_page) == ["answer 2", "answer 3"]
    assert second_page.has_more_traces is True
    assert second_page.oldest_trace_id == "trace-02"

    third_page = await storage.get_session_events_snapshot(
        "session-1",
        trace_limit=2,
        before_trace_started_at=second_page.oldest_trace_started_at,
        before_trace_id=second_page.oldest_trace_id,
    )
    assert _event_contents(third_page) == ["answer 1"]
    assert third_page.has_more_traces is False


@pytest.mark.asyncio
async def test_cursor_with_same_timestamp_uses_trace_id_tiebreak() -> None:
    # started_at 相同的两条 trace：游标必须按 (started_at, trace_id) 严格元组比较
    docs = [_trace_doc(1), _trace_doc(2)]
    for doc in docs:
        doc["started_at"] = BASE
    collection = _FakeCollection(docs)
    storage = _make_storage(collection)

    snapshot = await storage.get_session_events_snapshot(
        "session-1",
        trace_limit=2,
        before_trace_started_at=BASE,
        before_trace_id="trace-02",
    )
    assert _event_contents(snapshot) == ["answer 1"]


@pytest.mark.asyncio
async def test_without_trace_limit_keeps_legacy_full_read() -> None:
    collection = _FakeCollection([_trace_doc(i) for i in range(1, 6)])
    storage = _make_storage(collection)

    snapshot = await storage.get_session_events_snapshot("session-1")

    assert _event_contents(snapshot) == [f"answer {i}" for i in range(1, 6)]
    assert snapshot.has_more_traces is False
    assert snapshot.oldest_trace_id is None
    assert snapshot.oldest_trace_started_at is None
    assert collection.sort_specs[-1] == ("started_at", 1)
    # 未开窗口时不做 limit 探测，保持全量读取
    assert collection.limits == []


@pytest.mark.asyncio
async def test_route_returns_trace_window_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.routes import session as session_routes
    from src.infra.session.trace_storage import SessionEventsSnapshot

    snapshot = SessionEventsSnapshot(
        events=[],
        has_more_traces=True,
        oldest_trace_started_at=BASE,
        oldest_trace_id="trace-04",
    )

    recorded: Dict[str, Any] = {}

    class _DualWriter:
        async def read_session_events_snapshot(self, session_id, *args, **kwargs):
            recorded.update(kwargs)
            return snapshot

    class _MissingSessionManager:
        async def get_session(self, _session_id):
            from types import SimpleNamespace

            return SimpleNamespace(user_id="user-1", session_id="session-1", metadata={})

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: _DualWriter())
    monkeypatch.setattr(session_routes, "SessionManager", _MissingSessionManager)

    response = await session_routes.get_session_events(
        "session-1",
        event_types=None,
        run_id=None,
        exclude_run_id=None,
        limit=None,
        include_active_user_message=False,
        trace_limit=20,
        before_trace_started_at="2026-08-01T12:04:00+00:00",
        before_trace_id="trace-04",
        compact_message_chunks=False,
        user=__import__("types").SimpleNamespace(sub="user-1"),
    )

    assert recorded["trace_limit"] == 20
    assert recorded["before_trace_started_at"] == datetime(2026, 8, 1, 12, 4, tzinfo=UTC)
    assert recorded["before_trace_id"] == "trace-04"
    assert response["has_more_traces"] is True
    assert response["trace_window"] == {
        "oldest_trace_started_at": BASE.isoformat(),
        "oldest_trace_id": "trace-04",
    }
