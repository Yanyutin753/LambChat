"""executor 对 HITL 挂起/恢复的 trace 标记（#583）。

挂起（WAITING_HUMAN）时给 trace 打 metadata.waiting_human=True——等人工
输入期间事件停流，updated_at 不再刷新，全局僵尸清扫据此豁免；恢复
（hitl_resume）时清除标记。标记失败只降级为日志，不得影响主流程。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.infra.session.trace_storage as trace_storage_mod
from src.infra.task.executor import TaskExecutor
from src.kernel.config import settings


class _FakeHeartbeat:
    async def start(self, run_id: str, *, user_id: str | None = None) -> None:
        return None

    async def stop(self, run_id: str) -> None:
        return None


class _FakePresenter:
    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "trace-1"
        self.run_id = config.run_id
        self.hitl_suspended: bool = False
        self.saved_events: list[dict] = []
        self.completed: list[str] = []

    async def _ensure_trace(self) -> None:
        return None

    async def emit_user_message(self, message: str, **_kwargs) -> None:
        return None

    async def save_event(self, event: dict) -> None:
        self.saved_events.append(event)

    async def complete(self, status: str) -> None:
        self.completed.append(status)


class _RecordingWriter:
    async def _flush_redis_buffer(self, **_kwargs) -> None:
        return None

    async def flush_mongo_buffer(self, **_kwargs) -> None:
        return None

    async def write_event(self, **_kwargs) -> None:
        return None

    async def expire_stream(self, *_args, **_kwargs) -> None:
        return None


class _FakeTraceStorage:
    def __init__(self) -> None:
        self.waiting_calls: list[tuple[str, bool]] = []

    async def set_trace_waiting_human(self, trace_id: str, *, waiting: bool) -> bool:
        self.waiting_calls.append((trace_id, waiting))
        return True


def _executor_fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[TaskExecutor, _FakeTraceStorage]:
    from src.infra.task import cancellation

    monkeypatch.setattr(settings, "TASK_RUN_STALL_TIMEOUT", 0)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: _RecordingWriter())

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)

    trace_storage = _FakeTraceStorage()
    monkeypatch.setattr(trace_storage_mod, "get_trace_storage", lambda: trace_storage)

    async def _record_status(session_id, status, error=None, run_id=None):
        return None

    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _record_status)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr(executor, "_expire_terminal_stream", _no_op)
    return executor, trace_storage


@pytest.mark.asyncio
async def test_hitl_suspension_marks_trace_waiting_human(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, trace_storage = _executor_fixture(monkeypatch)

    async def _suspending_stream(*_args, presenter=None, **_kwargs):
        presenter.hitl_suspended = True
        yield {"event": "message:chunk", "data": {"content": "需要审批"}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_suspending_stream,
    )

    assert result is True  # WAITING_HUMAN 挂起路径
    assert ("trace-1", True) in trace_storage.waiting_calls


@pytest.mark.asyncio
async def test_hitl_resume_clears_waiting_human_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, trace_storage = _executor_fixture(monkeypatch)

    async def _resumed_stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "恢复后的回答"}}

    await executor.run_task(
        session_id="session-1",
        run_id="run-2",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_resumed_stream,
        hitl_resume={"approval_resolved": {"id": "approval-1"}},
    )

    assert ("trace-1", False) in trace_storage.waiting_calls


@pytest.mark.asyncio
async def test_normal_run_never_touches_waiting_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, trace_storage = _executor_fixture(monkeypatch)

    async def _normal_stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "普通回答"}}

    await executor.run_task(
        session_id="session-1",
        run_id="run-3",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_normal_stream,
    )

    assert trace_storage.waiting_calls == []
