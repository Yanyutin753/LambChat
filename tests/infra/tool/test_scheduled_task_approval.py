from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def approval_storage(monkeypatch: pytest.MonkeyPatch):
    from src.infra.tool.scheduled_task import approval

    storage = SimpleNamespace(
        finish_if_pending=AsyncMock(return_value=True),
        get_response=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(approval, "get_approval_storage", lambda: storage, raising=False)
    return storage


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
        lambda: SimpleNamespace(
            session_id="interactive-1", run_id="r1", user_id="u1", trace_id=None
        ),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    send_called = False

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send(
        *,
        approval_id,
        message,
        session_id,
        run_id,
        timeout,
        expires_at=None,
        trace_id=None,
        preview=None,
    ):
        nonlocal send_called
        send_called = True

    async def fake_wait(*args, **kwargs):
        return None  # timeout path

    async def fake_send_resolved(**kwargs):
        pass

    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send)
    monkeypatch.setattr(approval, "_send_scheduled_task_resolved_event", fake_send_resolved)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    result = await approval._confirm_scheduled_task_creation(
        preview={"name": "t"}, user_id="u1", timeout=1
    )

    assert send_called is True
    assert result["approved"] is False
    assert result["status"] == "timeout"


@pytest.mark.asyncio
async def test_scheduled_task_approval_event_includes_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approval_required 事件必须带 approval_type + preview metadata。

    前端实时路径只从事件 data 取 metadata；缺失时会退回通用 Markdown
    渲染，把确认文案（表格/代码块标记）整段平铺出来。
    """
    from src.infra.session.dual_writer import DualEventWriter  # noqa: F401
    from src.infra.tool.scheduled_task import approval

    write_calls: list[dict] = []

    async def fake_write_event(**kwargs):
        write_calls.append(kwargs)
        return True

    fake_dual_writer = SimpleNamespace(write_event=fake_write_event)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer)

    preview = {"name": "t", "message": "run-me"}
    await approval._send_scheduled_task_approval_event(
        approval_id="ap-1",
        message="msg",
        session_id="session-1",
        run_id="run-1",
        timeout=300,
        expires_at="2026-10-18T00:05:00+00:00",
        trace_id="trace-1",
        preview=preview,
    )

    assert len(write_calls) == 1
    data = write_calls[0]["data"]
    assert data["metadata"]["approval_type"] == "scheduled_task_create"
    assert data["metadata"]["preview"] == preview
    assert data["expires_at"] == "2026-10-18T00:05:00+00:00"


@pytest.mark.asyncio
async def test_confirm_scheduled_task_writes_approval_resolved_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认响应（批准/拒绝/超时）后必须写 approval_resolved 事件。

    前端 approval_required 会生成 ask_human pill；scheduled_task_create 的
    tool:result 与该 pill id 对不上，没有 approval_resolved 会永远转圈。
    """
    from src.infra.logging.context import TraceContext
    from src.infra.session.dual_writer import DualEventWriter  # noqa: F401
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(
            session_id="interactive-1", run_id="r1", user_id="u1", trace_id="trace-ctx"
        ),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send_required(**kwargs):
        pass

    response = SimpleNamespace(approved=True)

    async def fake_wait(*args, **kwargs):
        return response

    write_calls: list[dict] = []

    async def fake_write_event(**kwargs):
        write_calls.append(kwargs)
        return True

    fake_dual_writer = SimpleNamespace(write_event=fake_write_event)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer)
    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send_required)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    result = await approval._confirm_scheduled_task_creation(preview={"name": "t"}, user_id="u1")

    assert result["approved"] is True
    resolved = [c for c in write_calls if c["event_type"] == "approval_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["session_id"] == "interactive-1"
    assert resolved[0]["run_id"] == "r1"
    assert resolved[0]["trace_id"] == "trace-ctx"
    data = resolved[0]["data"]
    assert data["approval_id"] == "ap-1"
    assert data["success"] is True
    assert data["result"]["status"] == "success"


@pytest.mark.asyncio
async def test_confirm_scheduled_task_writes_approval_resolved_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
    approval_storage,
) -> None:
    """超时路径同样要写 approval_resolved（status=timeout），否则 pill 永远转圈。"""
    from src.infra.logging.context import TraceContext
    from src.infra.session.dual_writer import DualEventWriter  # noqa: F401
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(
            session_id="interactive-1", run_id="r1", user_id="u1", trace_id=None
        ),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send_required(**kwargs):
        pass

    async def fake_wait(*args, **kwargs):
        return None  # timeout

    write_calls: list[dict] = []

    async def fake_write_event(**kwargs):
        write_calls.append(kwargs)
        return True

    fake_dual_writer = SimpleNamespace(write_event=fake_write_event)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer)
    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send_required)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    result = await approval._confirm_scheduled_task_creation(preview={"name": "t"}, user_id="u1")

    assert result["approved"] is False
    assert result["status"] == "timeout"
    approval_storage.finish_if_pending.assert_awaited_once_with("ap-1", "timeout")
    resolved = [c for c in write_calls if c["event_type"] == "approval_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["data"]["result"]["status"] == "timeout"
    assert resolved[0]["data"]["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_confirmation_deadline_and_cancellation_close_the_pending_request(
    monkeypatch: pytest.MonkeyPatch, approval_storage, cancelled: bool
) -> None:
    import asyncio

    from src.infra.logging.context import TraceContext
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(session_id="session-1", run_id="run-1", trace_id="trace-1"),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _: "Confirm")
    create = AsyncMock(return_value=SimpleNamespace(id="approval-1"))
    resolved = AsyncMock()
    monkeypatch.setattr(approval, "create_approval", create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", AsyncMock())
    monkeypatch.setattr(approval, "_send_scheduled_task_resolved_event", resolved)
    monkeypatch.setattr(
        approval,
        "wait_for_response",
        AsyncMock(side_effect=asyncio.CancelledError)
        if cancelled
        else AsyncMock(return_value=None),
    )
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await approval._confirm_scheduled_task_creation(preview={}, user_id="u1", timeout=120)
    else:
        result = await approval._confirm_scheduled_task_creation(
            preview={}, user_id="u1", timeout=120
        )
        assert result["status"] == "timeout"
    assert create.call_args.kwargs["ttl"] == 120
    assert create.call_args.kwargs["metadata"]["run_id"] == "run-1"
    approval_storage.finish_if_pending.assert_awaited_once_with(
        "approval-1", "cancelled" if cancelled else "timeout"
    )
    assert resolved.call_args.kwargs["status"] == ("cancelled" if cancelled else "timeout")


@pytest.mark.asyncio
async def test_timeout_does_not_overwrite_a_response_that_won_the_race(
    monkeypatch: pytest.MonkeyPatch,
    approval_storage,
) -> None:
    from src.infra.logging.context import TraceContext
    from src.infra.tool.scheduled_task import approval

    monkeypatch.setattr(
        TraceContext,
        "get_request_context",
        lambda: SimpleNamespace(session_id="session-1", run_id="run-1", trace_id=None),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _: "Confirm")
    monkeypatch.setattr(
        approval, "create_approval", AsyncMock(return_value=SimpleNamespace(id="ap-1"))
    )
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", AsyncMock())
    resolved = AsyncMock()
    monkeypatch.setattr(approval, "_send_scheduled_task_resolved_event", resolved)
    monkeypatch.setattr(approval, "wait_for_response", AsyncMock(return_value=None))
    approval_storage.finish_if_pending.return_value = False
    approval_storage.get_response.return_value = SimpleNamespace(approved=True)

    result = await approval._confirm_scheduled_task_creation(preview={}, user_id="u1")

    assert result["approved"] is True
    assert resolved.call_args.kwargs["status"] == "approved"


def test_approval_message_contains_prompt_exactly_once() -> None:
    """确认文案中完整 prompt 只出现一次（```text 代码块），effect 不再内联。"""
    from src.infra.tool.scheduled_task.approval import _format_approval_message
    from src.infra.tool.scheduled_task.helpers import _build_task_preview
    from src.kernel.schemas.scheduled_task import TriggerType

    prompt = "每天早上 7:30 提醒我记录供应商账，用中文，包含昨日新增条目数"
    preview = _build_task_preview(
        name="每天记供应商账提醒",
        message=prompt,
        trigger_type=TriggerType.CRON,
        trigger_config={"hour": "7", "minute": "30"},
        timezone_name="Asia/Shanghai",
        agent_id="fast",
        description=None,
        timeout_seconds=3600,
        run_on_start=False,
    )

    assert prompt not in preview["effect"]

    message = _format_approval_message(preview)
    assert message.count(prompt) == 1


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
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: fake_dual_writer)

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

    async def fake_send(
        *,
        approval_id,
        message,
        session_id,
        run_id,
        timeout,
        expires_at=None,
        trace_id=None,
        preview=None,
    ):
        captured.append({"trace_id": trace_id})

    async def fake_wait(*args, **kwargs):
        return None

    async def fake_send_resolved(**kwargs):
        pass

    monkeypatch.setattr(approval, "create_approval", fake_create)
    monkeypatch.setattr(approval, "_send_scheduled_task_approval_event", fake_send)
    monkeypatch.setattr(approval, "_send_scheduled_task_resolved_event", fake_send_resolved)
    monkeypatch.setattr(approval, "wait_for_response", fake_wait)

    await approval._confirm_scheduled_task_creation(preview={"name": "t"}, user_id="u1")

    assert captured == [{"trace_id": "trace-ctx"}]
