"""run 终态时未注入的插话必须落库（steer:undelivered 接线）。

run 在插话入队后、下一次模型调用前结束（典型：单次模型调用直接完成的
任务），插话既没注入也没落库，纯 API 消费者完全静默丢失。executor 在
四个真终态路径（completed / 用户取消 / TaskInterrupted / 通用失败）调用
emit_undelivered_steer_events 补写事件；WAITING_HUMAN 挂起与系统中断
（可续跑）不写——后续恢复还可能注入。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import cancellation
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.executor import TaskExecutor


class _FakeHeartbeat:
    async def start(self, run_id: str, *, user_id: str | None = None) -> None:
        return None

    async def stop(self, run_id: str) -> None:
        return None


class _FakePresenter:
    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "trace-1"
        self.run_id = config.run_id
        self._trace_created = False
        self.hitl_suspended = False
        self.produced_main_text = False
        self.saved_events: list[dict] = []
        self.completions: list[str] = []

    async def _ensure_trace(self) -> None:
        self._trace_created = True

    async def emit_user_message(self, message: str, **_kwargs) -> None:
        self.saved_events.append({"event": "user:message", "data": {"content": message}})

    async def save_event(self, event: dict) -> None:
        self.saved_events.append(event)

    async def emit(self, event: dict) -> dict:
        self.saved_events.append(event)
        return event

    async def complete(self, status: str) -> None:
        self.completions.append(status)

    async def _ensure_token_usage_event(self) -> None:
        return None

    def done(self) -> dict:
        return {"event": "done", "data": {}}


class _RecordingWriter:
    def __init__(self) -> None:
        self.written: list[dict] = []

    async def _flush_redis_buffer(self, **_kwargs) -> None:
        return None

    async def flush_mongo_buffer(self, **_kwargs) -> None:
        return None

    async def write_event(self, **kwargs) -> None:
        self.written.append(kwargs)

    async def expire_stream(self, *_args, **_kwargs) -> None:
        return None


def _fixture(
    monkeypatch: pytest.MonkeyPatch, *, suspended: bool = False
) -> tuple[TaskExecutor, list[tuple]]:
    presenter_cls = _FakePresenter
    if suspended:

        class _SuspendedPresenter(_FakePresenter):  # type: ignore[misc, valid-type]
            def __init__(self, config) -> None:
                super().__init__(config)
                self.hitl_suspended = True

        presenter_cls = _SuspendedPresenter

    monkeypatch.setattr("src.infra.writer.present.Presenter", presenter_cls)
    writer = _RecordingWriter()
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: writer)

    calls: list[tuple] = []

    async def _record_undelivered(session_id, run_id=None, presenter=None, **_kwargs):
        calls.append((session_id, run_id))

    monkeypatch.setattr(
        "src.infra.task.executor.emit_undelivered_steer_events", _record_undelivered
    )

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)

    async def _record_status(session_id, status, error=None, run_id=None):
        return None

    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _record_status)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    return executor, calls


def _stream_of(events: list[dict]):
    async def _stream(*_args, **_kwargs):
        for event in events:
            yield event

    return _stream


def _failing_stream(error: BaseException):
    async def _stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "半截"}}
        raise error
        yield  # pragma: no cover

    return _stream


async def test_completed_run_emits_undelivered_steers(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, calls = _fixture(monkeypatch)

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="fast",
        message="写一篇科幻微小说",
        user_id="user-1",
        executor=_stream_of(
            [
                {"event": "message:chunk", "data": {"content": "正文"}},
                {"event": "token:usage", "data": {"output_tokens": 1}},
                {"event": "done", "data": {"status": "completed"}},
            ]
        ),
        user_message_written=True,
    )

    assert calls == [("session-1", "run-1")]


async def test_user_cancelled_run_emits_undelivered_steers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, calls = _fixture(monkeypatch)

    async def _interrupted(*_args, **_kwargs):
        raise TaskInterruptedError("cancelled")

    monkeypatch.setattr(cancellation.TaskCancellation, "check_interrupt", _interrupted)

    with pytest.raises(asyncio.CancelledError):
        await executor.run_task(
            session_id="session-2",
            run_id="run-2",
            agent_id="fast",
            message="数到 800",
            user_id="user-1",
            executor=_failing_stream(asyncio.CancelledError()),
            user_message_written=True,
        )

    assert calls == [("session-2", "run-2")]


async def test_interrupted_error_run_emits_undelivered_steers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, calls = _fixture(monkeypatch)

    with pytest.raises(TaskInterruptedError):
        await executor.run_task(
            session_id="session-3",
            run_id="run-3",
            agent_id="fast",
            message="数到 800",
            user_id="user-1",
            executor=_failing_stream(TaskInterruptedError("interrupted")),
            user_message_written=True,
        )

    assert calls == [("session-3", "run-3")]


async def test_failed_run_emits_undelivered_steers(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, calls = _fixture(monkeypatch)

    await executor.run_task(
        session_id="session-4",
        run_id="run-4",
        agent_id="fast",
        message="数到 800",
        user_id="user-1",
        executor=_failing_stream(RuntimeError("upstream blew up")),
        user_message_written=True,
    )

    assert calls == [("session-4", "run-4")]


async def test_hitl_suspended_run_does_not_emit_undelivered_steers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAITING_HUMAN 挂起不是终态：恢复后插话仍可能注入，不写 undelivered。"""
    executor, calls = _fixture(monkeypatch, suspended=True)

    async def _suspending_stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "需要审批"}}
        yield {"event": "tool:start", "data": {"tool": "ask_human"}}

    async def _noop_materialize(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("src.infra.task.hitl.materialize_ask_human_approvals", _noop_materialize)

    result = await executor.run_task(
        session_id="session-5",
        run_id="run-5",
        agent_id="fast",
        message="需要审批的任务",
        user_id="user-1",
        executor=_suspending_stream,
        user_message_written=True,
    )

    assert result is True  # WAITING_HUMAN
    assert calls == []
