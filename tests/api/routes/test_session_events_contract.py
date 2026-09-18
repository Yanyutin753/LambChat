"""events 接口契约测试：丰富 mock 数据驱动真实路由 + 真实装配。

契约来源（frontend/src/types/session.ts）：
- SessionEventsResponse: events / history_mode / stream_run_id / has_more_traces / trace_window
- SessionTraceWindow: oldest_trace_started_at / oldest_trace_id
- 产品语义：翻页单位是 trace（每页 N 轮），窗口内每个 run 的事件必须完整。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

# 真实模块须在 _load_session_routes_module 注入 stub 之前导入并持有引用
from src.infra.session.dual_writer import DualEventWriter as _RealDualEventWriter
from src.infra.session.trace_storage import TraceStorage as _RealTraceStorage
from tests.api.routes.test_session_runs import _load_session_routes_module


class _ContractSessionManager:
    async def get_session(self, session_id):
        return SimpleNamespace(
            user_id="user-1",
            session_id=session_id,
            metadata={"current_run_id": "run-active"},
        )


def _load_contract_routes_module(monkeypatch):
    """加载路由模块；SessionManager 用带 current_run_id 的版本。"""
    routes = _load_session_routes_module(monkeypatch)
    monkeypatch.setattr(routes, "SessionManager", _ContractSessionManager)
    return routes


_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _run(
    index: int, n_events: int, *, status: str = "completed", run_id: str | None = None
) -> dict:
    rid = run_id or f"run-{index:02d}"
    events: list[dict[str, Any]] = []
    if n_events > 0:
        events.append({"event_type": "user:message", "data": {"content": f"q{index}"}, "seq": 1})
        for i in range(2, n_events):
            events.append(
                {"event_type": "message:chunk", "data": {"content": f"r{index}-{i}"}, "seq": i}
            )
        events.append({"event_type": "done", "data": {}, "seq": n_events})
    return {
        "trace_id": f"trace-{index:02d}",
        "session_id": "session-1",
        "run_id": rid,
        "status": status,
        "started_at": _BASE + timedelta(minutes=index),
        "updated_at": _BASE + timedelta(minutes=index),
        "events": events,
        "event_count": n_events,
        "recommend_questions": ["下一步?"] if index % 5 == 0 else None,
    }


def _rich_traces() -> list[dict[str, Any]]:
    # 25 个完成轮：事件数 1/3/…/49 交错，含空轮(0)与单事件轮
    traces = []
    for i in range(1, 26):
        n = ((i * 7) % 50) + (1 if i == 3 else 0)  # 1..50 变化，i==3 时 0 事件轮由 n=0 构造
        n = 0 if i == 3 else n
        traces.append(_run(i, n))
    # 最新一轮：活跃 running（大轮 80 事件）；updated_at 必须是新鲜时间，
    # 否则会被 stale-running 判定按终态完整展示（写者已死语义）
    active = _run(26, 80, status="running", run_id="run-active")
    now = datetime.now(timezone.utc)
    active["started_at"] = now - timedelta(seconds=30)
    active["updated_at"] = now
    traces.append(active)
    return traces


class _ContractCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._limit: int | None = None

    def sort(self, *args: Any) -> "_ContractCursor":
        return self

    def limit(self, value: int) -> "_ContractCursor":
        self._limit = value
        return self

    def __aiter__(self) -> "_ContractCursor":
        docs = self._docs if self._limit is None else self._docs[: self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return dict(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration from None


def _eval_query(doc: dict[str, Any], cond: dict[str, Any]) -> bool:
    """最小 Mongo 查询求值器：$and / $or / $lt / $in / 平值匹配。"""
    if "$and" in cond:
        return all(_eval_query(doc, sub) for sub in cond["$and"])
    if "$or" in cond:
        return any(_eval_query(doc, sub) for sub in cond["$or"])
    for field, op in cond.items():
        value = doc.get(field)
        if isinstance(op, dict):
            if "$lt" in op and not (value is not None and value < op["$lt"]):
                return False
            if "$in" in op and value not in op["$in"]:
                return False
            if "$ne" in op and value == op["$ne"]:
                return False
        elif value != op:
            return False
    return True


def _match_window(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    return _eval_query(doc, query)


class _ContractCollection:
    """按 started_at 倒序（窗口模式取数方向）返回 trace 文档。"""

    def __init__(self, traces: list[dict[str, Any]]) -> None:
        self._traces = sorted(traces, key=lambda t: t["started_at"], reverse=True)

    def find(self, query: dict[str, Any], projection: Any) -> _ContractCursor:
        return _ContractCursor([t for t in self._traces if _match_window(t, query)])


def _real_dual_writer_with(traces: list[dict[str, Any]]):
    storage = _RealTraceStorage()
    storage._collection = _ContractCollection(traces)
    storage._chunks_collection = _ContractCollection([])

    async def _batch_read(trace_docs: list[dict[str, Any]], **kwargs: Any) -> dict[str, list[dict]]:
        del kwargs
        return {str(t["trace_id"]): list(t.get("events") or []) for t in trace_docs}

    storage.read_trace_events_batch_compat = _batch_read  # type: ignore[method-assign]
    writer = _RealDualEventWriter()
    writer._trace = storage  # type: ignore[assignment]
    return writer


def _events_by_run(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(event["run_id"], []).append(event)
    return grouped


async def _call_events(session_routes, monkeypatch, writer, **overrides):
    # 路由函数内按字符串延迟导入，拿到的是 loader 注入的 sys.modules stub
    monkeypatch.setattr(
        sys.modules["src.infra.session.dual_writer"], "get_dual_writer", lambda: writer
    )
    kwargs = dict(
        event_types=None,
        run_id=None,
        exclude_run_id=None,
        limit=None,
        include_active_user_message=True,
        compact_message_chunks=False,
        user=SimpleNamespace(sub="user-1"),
        trace_limit=20,
    )
    kwargs.update(overrides)
    return await session_routes.get_session_events("session-1", **kwargs)


@pytest.mark.asyncio
async def test_contract_first_page_twenty_runs_every_run_complete(monkeypatch):
    session_routes = _load_contract_routes_module(monkeypatch)
    traces = _rich_traces()
    writer = _real_dual_writer_with(traces)

    response = await _call_events(session_routes, monkeypatch, writer)

    grouped = _events_by_run(response["events"])
    # 窗口 = 最新的 20 轮：活跃轮 + 最新的 19 个完成轮
    assert response["history_mode"] == "active_user_only"
    assert response["stream_run_id"] == "run-active"
    assert len(grouped) == 20
    # 活跃轮只回 user:message（正文等 SSE 重放）
    assert [e["event_type"] for e in grouped["run-active"]] == ["user:message"]
    # 每个完成轮事件完整（含 done 收尾 + 推荐问题合成事件）
    for trace in traces:
        if trace["status"] != "completed":
            continue
        rid = trace["run_id"]
        if rid not in grouped:
            continue
        expected = len(trace["events"])
        if trace.get("recommend_questions"):
            expected += 1  # 合成 recommend:questions
        assert len(grouped[rid]) == expected, f"{rid} 应完整返回"
        types = [e["event_type"] for e in grouped[rid]]
        assert types[-1] in {"done", "recommend:questions"}
        if trace["events"]:
            assert types[0] == "user:message"
    # 窗口边界：最旧的窗口成员是 run-07（active + 19 个最新完成轮）
    assert sorted(set(grouped) - {"run-active"}) == [f"run-{i:02d}" for i in range(7, 26)]
    # 每个事件字段齐备（后端事件契约）
    for event in response["events"]:
        assert {"trace_id", "run_id", "event_type", "data", "timestamp", "seq"} <= set(event)
    # 窗口游标：指向窗口内最旧一条 trace
    assert response["has_more_traces"] is True
    window = response["trace_window"]
    assert window is not None and set(window) == {"oldest_trace_started_at", "oldest_trace_id"}


@pytest.mark.asyncio
async def test_contract_second_page_older_runs_and_terminates(monkeypatch):
    session_routes = _load_contract_routes_module(monkeypatch)
    writer = _real_dual_writer_with(_rich_traces())

    first = await _call_events(session_routes, monkeypatch, writer)
    window = first["trace_window"]

    second = await _call_events(
        session_routes,
        monkeypatch,
        writer,
        trace_limit=None,
        before_trace_started_at=window["oldest_trace_started_at"],
        before_trace_id=window["oldest_trace_id"],
    )

    grouped = _events_by_run(second["events"])
    # 第二页 = 更旧的 6 轮（run-01..06，其中 run-03 为空轮不产生事件）
    expected_runs = {f"run-{i:02d}" for i in range(1, 7)}
    assert set(grouped) == expected_runs - {"run-03"}
    for rid, events in grouped.items():
        assert events, f"{rid} 不应丢事件"
    # 到最早：无更多页，游标为 null（前端类型注释语义）
    assert second["has_more_traces"] is False
    assert second["trace_window"] is None


@pytest.mark.asyncio
async def test_contract_legacy_no_limit_returns_full_history(monkeypatch):
    session_routes = _load_contract_routes_module(monkeypatch)
    traces = _rich_traces()
    writer = _real_dual_writer_with(traces)

    response = await _call_events(
        session_routes, monkeypatch, writer, trace_limit=None, include_active_user_message=False
    )

    grouped = _events_by_run(response["events"])
    # 不传 limit = 全量：每个完成轮整轮完整（running 轮被过滤属 completed_only 语义）
    assert response["events_limited"] is False
    assert response["events_limit"] is None
    for trace in traces:
        if trace["status"] != "completed" or not trace["events"]:
            continue
        rid = trace["run_id"]
        expected = len(trace["events"]) + (1 if trace.get("recommend_questions") else 0)
        assert len(grouped[rid]) == expected, f"{rid} 必须整轮完整"


@pytest.mark.asyncio
async def test_contract_compact_mode_keeps_every_run_represented(monkeypatch):
    session_routes = _load_contract_routes_module(monkeypatch)
    writer = _real_dual_writer_with(_rich_traces())

    response = await _call_events(session_routes, monkeypatch, writer, compact_message_chunks=True)

    grouped = _events_by_run(response["events"])
    # 压缩只合并相邻 chunk：每个 run 仍必须有 user 起点与终点事件
    assert response["history_mode"] == "active_user_only"
    for rid, events in grouped.items():
        if rid == "run-03":
            assert events == []
            continue
        if rid == "run-active":
            # 活跃轮 user-only：正文等 SSE 重放，无终点事件
            assert [e["event_type"] for e in events] == ["user:message"]
            continue
        types = [e["event_type"] for e in events]
        assert "user:message" in types, f"{rid} 缺用户消息"
        assert types[-1] in {"done", "recommend:questions", "message:chunk"}, rid
