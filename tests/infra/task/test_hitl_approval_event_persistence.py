"""approval_required 事件必须带 trace_id 双写（Redis + MongoDB）。

线上事故：interrupt 模式挂起后 approval_required 只写 Redis Stream，
未传 trace_id 导致 DualEventWriter 跳过 MongoDB 持久化；
Redis 流过期（终态 60s / TTL 3600s）后历史回放永远缺失审批卡片。
"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.infra.task.hitl import _send_approval_sse, materialize_ask_human_approvals


class DualWriterRecorder:
    """捕获 write_event 调用参数的假 dual writer。"""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def write_event(self, **kwargs: Any) -> bool:
        self.events.append(kwargs)
        return True


def _snapshot_with_ask_human(interrupt_id: str = "intr-1") -> SimpleNamespace:
    intr = SimpleNamespace(
        id=interrupt_id,
        value={"kind": "ask_human", "message": "需要确认", "fields": []},
    )
    task = SimpleNamespace(interrupts=[intr])
    return SimpleNamespace(tasks=[task])


@pytest.fixture
def dual_writer(monkeypatch: pytest.MonkeyPatch) -> DualWriterRecorder:
    recorder = DualWriterRecorder()
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: recorder)
    return recorder


async def test_send_approval_sse_passes_trace_id_to_dual_writer(
    dual_writer: DualWriterRecorder,
) -> None:
    """_send_approval_sse 必须传 trace_id，否则事件不会持久化到 MongoDB。"""
    approval = SimpleNamespace(
        id="approval-1",
        message="需要确认",
        type="form",
        metadata={"tool_call_id": "call-1", "interrupt_id": "intr-1"},
    )

    await _send_approval_sse(approval, [], "session-1", "run-1", trace_id="trace-1")

    assert len(dual_writer.events) == 1
    event = dual_writer.events[0]
    assert event["event_type"] == "approval_required"
    assert event["session_id"] == "session-1"
    assert event["run_id"] == "run-1"
    assert event["trace_id"] == "trace-1"


async def test_materialize_forwards_trace_id_to_approval_event(
    monkeypatch: pytest.MonkeyPatch, dual_writer: DualWriterRecorder
) -> None:
    """materialize 收到的 trace_id 必须透传到 approval_required 双写。"""

    async def fake_create_approval(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            id="approval-2",
            message=kwargs.get("message", ""),
            type="form",
            metadata={},
        )

    fake_storage = SimpleNamespace(list_pending=_no_pending)
    monkeypatch.setattr("src.api.routes.human.create_approval", fake_create_approval)
    monkeypatch.setattr("src.infra.storage.mongodb.get_approval_storage", lambda: fake_storage)

    created = await materialize_ask_human_approvals(
        _snapshot_with_ask_human(),
        session_id="session-1",
        run_id="run-1",
        user_id="user-1",
        trace_id="trace-9",
    )

    assert created == 1
    assert len(dual_writer.events) == 1
    assert dual_writer.events[0]["event_type"] == "approval_required"
    assert dual_writer.events[0]["trace_id"] == "trace-9"


async def _no_pending(**kwargs: Any) -> list:
    return []
