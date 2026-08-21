from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_confirm_scheduled_task_creation_rejects_in_unattended_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unattended (sch_) sessions skip HITL and reject fast (issue #197).

    Waiting for interactive confirmation in a scheduled-task session always
    timed out (and MCPToolWithRetry amplified that to ~3x). The fix fails fast.
    """
    from src.infra.logging.context import TraceContext
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(session_id="sch_abc123", run_id="r1", user_id="u1", trace_id=None),
    )

    async def fail_create(*args, **kwargs):
        raise AssertionError("create_approval must not run in unattended context")

    monkeypatch.setattr(approval, "create_approval", fail_create)

    result = await approval._confirm_scheduled_task_creation(preview={"name": "t"}, user_id="u1")

    assert result["approved"] is False
    assert result["status"] == "unattended"
    assert result["approval_id"] is None
    assert "unattended" in result["message"].lower()


@pytest.mark.asyncio
async def test_confirm_scheduled_task_creation_proceeds_in_interactive_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interactive (non-sch_) sessions still go through HITL (issue #197 guard)."""
    from src.infra.logging.context import TraceContext
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(session_id="interactive-1", run_id="r1", user_id="u1", trace_id=None),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    send_called = False

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send(*, approval_id, message, session_id, run_id, timeout, trace_id=None):
        nonlocal send_called
        send_called = True

    async def fake_wait(*args, **kwargs):
        return None  # timeout path

    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    result = await approval._confirm_scheduled_task_creation(
        preview={"name": "t"}, user_id="u1", timeout=1
    )

    assert send_called is True
    assert result["approved"] is False
    assert result["status"] == "timeout"


@pytest.mark.asyncio
async def test_scheduled_task_approval_event_passes_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approval_required 必须带 trace_id 双写，否则 Redis 流过期后历史缺失审批卡片。"""
    from src.infra.session.dual_writer import DualEventWriter  # noqa: F401
    from src.infra.tool.scheduled_task import approval

    write_calls: list[dict] = []

    async def fake_write_event(**kwargs):
        write_calls.append(kwargs)
        return True

    fake_dual_writer = SimpleNamespace(write_event=fake_write_event)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer
    )

    await approval._send_scheduled_task_approval_event(
        approval_id="ap-1",
        message="msg",
        session_id="session-1",
        run_id="run-1",
        timeout=300,
        trace_id="trace-1",
    )

    assert len(write_calls) == 1
    assert write_calls[0]["event_type"] == "approval_required"
    assert write_calls[0]["session_id"] == "session-1"
    assert write_calls[0]["run_id"] == "run-1"
    assert write_calls[0]["trace_id"] == "trace-1"


@pytest.mark.asyncio
async def test_confirm_scheduled_task_forwards_request_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_confirm 应把 TraceContext 的 trace_id 透传给审批事件发送。"""
    from src.infra.logging.context import TraceContext
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(
            session_id="interactive-1", run_id="r1", user_id="u1", trace_id="trace-ctx"
        ),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    captured: list[dict] = []

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send(*, approval_id, message, session_id, run_id, timeout, trace_id=None):
        captured.append({"trace_id": trace_id})

    async def fake_wait(*args, **kwargs):
        return None

    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    await approval._confirm_scheduled_task_creation(preview={"name": "t"}, user_id="u1")

    assert captured == [{"trace_id": "trace-ctx"}]
