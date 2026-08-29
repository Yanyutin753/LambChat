from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task.executor import TaskExecutor


class _FakeHeartbeat:
    def __init__(self) -> None:
        self.stop_calls: list[str] = []

    async def start(self, run_id: str, *, user_id: str | None = None) -> None:
        return None

    async def stop(self, run_id: str) -> None:
        self.stop_calls.append(run_id)


class _FakePresenter:
    instances: list["_FakePresenter"] = []

    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "generated-trace"
        self._trace_created = False
        self.saved_events: list[dict] = []
        self.completed: list[str] = []
        self.__class__.instances.append(self)

    async def _ensure_trace(self) -> None:
        self._trace_created = True

    async def emit_user_message(self, message: str, **_kwargs) -> None:
        return None

    async def save_event(self, event: dict) -> None:
        self.saved_events.append(event)

    async def complete(self, status: str) -> None:
        self.completed.append(status)


def _executor(monkeypatch: pytest.MonkeyPatch) -> TaskExecutor:
    from src.infra.task import cancellation

    _FakePresenter.instances.clear()
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)

    class _Writer:
        async def flush_mongo_buffer(self, **_kwargs) -> None:
            return None

    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", _Writer)

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)
    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _no_op)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr(executor, "_expire_terminal_stream", _no_op)
    return executor


@pytest.mark.asyncio
async def test_stalled_agent_stream_times_out_to_error_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_EVENT_IDLE_TIMEOUT", 0.05)
    executor = _executor(monkeypatch)

    async def _stalled_stream(*_args, **_kwargs):
        yield {"event": "agent:start", "data": {}}
        await asyncio.sleep(10)
        yield {"event": "never", "data": {}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_stalled_stream,
        existing_trace_id="trace-1",
        user_message_written=True,
    )

    presenter = _FakePresenter.instances[0]
    assert result is None
    assert presenter.saved_events[0]["event"] == "agent:start"
    assert presenter.completed == ["error"]


@pytest.mark.asyncio
async def test_stall_watchdog_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_EVENT_IDLE_TIMEOUT", 0.0)
    executor = _executor(monkeypatch)

    async def _slow_stream(*_args, **_kwargs):
        yield {"event": "agent:start", "data": {}}
        await asyncio.sleep(0.02)
        yield {"event": "agent:done", "data": {}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_slow_stream,
        existing_trace_id="trace-1",
        user_message_written=True,
    )

    presenter = _FakePresenter.instances[0]
    assert result is False
    assert [event["event"] for event in presenter.saved_events] == [
        "agent:start",
        "agent:done",
    ]
    assert presenter.completed == ["completed"]
