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
        lambda: SimpleNamespace(session_id="sch_abc123", run_id="r1", user_id="u1"),
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
        lambda: SimpleNamespace(session_id="interactive-1", run_id="r1", user_id="u1"),
    )
    monkeypatch.setattr(approval, "_format_approval_message", lambda _preview: "msg")

    send_called = False

    class _FakeApproval:
        id = "ap-1"

    async def fake_create(*args, **kwargs):
        return _FakeApproval()

    async def fake_send(*, approval_id, message, session_id, run_id, timeout):
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
