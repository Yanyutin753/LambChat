"""max_events 预算截断必须保最新事件（旧→新消费预算会丢会话结尾，属数据回归）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.infra.session.trace_storage import TraceStorage

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trace(name: str, order: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "trace_id": name,
        "run_id": name,
        "status": "completed",
        "started_at": _BASE + timedelta(minutes=order),
        "updated_at": _BASE + timedelta(minutes=order),
        "events": events,
    }


def _events(n: int) -> list[dict[str, Any]]:
    return [
        {"event_type": "message:chunk", "data": {"content": f"e{i}"}, "seq": i, "timestamp": _BASE}
        for i in range(1, n + 1)
    ]


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._limit: int | None = None

    def sort(self, *args: Any) -> "_FakeCursor":
        return self

    def limit(self, value: int) -> "_FakeCursor":
        self._limit = value
        return self

    def __aiter__(self) -> "_FakeCursor":
        docs = self._docs if self._limit is None else self._docs[: self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return dict(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeCollection:
    def __init__(self, traces: list[dict[str, Any]], descending: bool) -> None:
        self.traces = traces if not descending else list(reversed(traces))

    def find(self, query: dict[str, Any], projection: Any) -> _FakeCursor:
        session_id = query.get("session_id")
        docs = [t for t in self.traces if t.get("session_id", "s1") == session_id]
        # 模拟 started_at 排序：构造时已按目标方向排好
        return _FakeCursor(docs)


def _storage_with(traces: list[dict[str, Any]], descending: bool) -> TraceStorage:
    storage = TraceStorage()
    for trace in traces:
        trace["session_id"] = "s1"
    storage._collection = _FakeCollection(traces, descending)  # type: ignore[assignment]

    async def _batch_read(traces: list[dict[str, Any]], **kwargs: Any) -> dict[str, list[dict]]:
        return {str(t["trace_id"]): list(t.get("events", [])) for t in traces}

    storage.read_trace_events_batch_compat = _batch_read  # type: ignore[method-assign]
    return storage


@pytest.mark.asyncio
async def test_trace_window_budget_consumes_whole_runs_newest_first() -> None:
    traces = [_trace("t1", 1, _events(3)), _trace("t2", 2, _events(3)), _trace("t3", 3, _events(3))]
    # 窗口模式游标按 started_at 倒序取数
    storage = _storage_with(traces, descending=True)

    snapshot = await storage._assemble_session_events_snapshot("s1", trace_limit=3, max_events=5)

    events = snapshot.events
    # 预算 5：最新整轮 t3(3 条) 纳入后剩 2，装不下 t2 整轮(3 条)→丢弃 t2/t1
    assert [e["trace_id"] for e in events] == ["t3", "t3", "t3"]
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert snapshot.events_truncated is True


@pytest.mark.asyncio
async def test_trace_window_budget_fits_multiple_whole_runs_in_order() -> None:
    traces = [_trace("t1", 1, _events(3)), _trace("t2", 2, _events(3)), _trace("t3", 3, _events(3))]
    storage = _storage_with(traces, descending=True)

    snapshot = await storage._assemble_session_events_snapshot("s1", trace_limit=3, max_events=6)

    # 预算 6 装下 t2+t3 整轮（升序输出）；窗口内还有 t1 被丢弃 → truncated
    assert [e["trace_id"] for e in snapshot.events] == ["t2", "t2", "t2", "t3", "t3", "t3"]
    assert snapshot.events_truncated is True

    snapshot_all = await storage._assemble_session_events_snapshot(
        "s1", trace_limit=3, max_events=9
    )
    assert len(snapshot_all.events) == 9
    assert snapshot_all.events_truncated is False


@pytest.mark.asyncio
async def test_single_newest_run_exceeding_budget_is_returned_complete() -> None:
    traces = [_trace("t1", 1, _events(2)), _trace("t2", 2, _events(6))]
    storage = _storage_with(traces, descending=True)

    snapshot = await storage._assemble_session_events_snapshot("s1", trace_limit=2, max_events=4)

    # 最新单轮(6 条)超预算(4)：仍完整返回，绝不拦腰切断 run
    assert [e["trace_id"] for e in snapshot.events] == ["t2"] * 6
    assert [e["seq"] for e in snapshot.events] == [1, 2, 3, 4, 5, 6]
    assert snapshot.events_truncated is True


@pytest.mark.asyncio
async def test_legacy_mode_budget_consumes_whole_runs_newest_first() -> None:
    traces = [_trace("t1", 1, _events(3)), _trace("t2", 2, _events(3)), _trace("t3", 3, _events(3))]
    # 非 window 路径按 started_at 升序取数
    storage = _storage_with(traces, descending=False)

    events = await storage.get_session_events("s1", max_events=4)

    # 预算 4：t3 整轮纳入后剩 1，装不下 t2 整轮→丢弃；会话结尾完整保留
    assert [e["trace_id"] for e in events] == ["t3", "t3", "t3"]
    assert [e["seq"] for e in events] == [1, 2, 3]
