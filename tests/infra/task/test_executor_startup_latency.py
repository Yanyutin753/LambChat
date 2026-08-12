from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus


class _FakeHeartbeat:
    def __init__(self) -> None:
        self.start_calls: list[tuple[str, str | None]] = []
        self.stop_calls: list[str] = []

    async def start(self, run_id: str, *, user_id: str | None = None) -> None:
        self.start_calls.append((run_id, user_id))

    async def stop(self, run_id: str) -> None:
        self.stop_calls.append(run_id)


class _FakePresenter:
    instances: list["_FakePresenter"] = []

    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "generated-trace"
        self._trace_created = False
        self.ensure_trace_calls = 0
        self.emitted_user_messages: list[str] = []
        self.saved_events: list[dict] = []
        self.completed: list[str] = []
        self.__class__.instances.append(self)

    async def _ensure_trace(self) -> None:
        self.ensure_trace_calls += 1
        self._trace_created = True

    async def emit_user_message(self, message: str, **_kwargs) -> None:
        self.emitted_user_messages.append(message)

    async def save_event(self, event: dict) -> None:
        self.saved_events.append(event)

    async def complete(self, status: str) -> None:
        self.completed.append(status)


async def _empty_agent_stream(*_args, **_kwargs):
    if False:
        yield {}


def _executor(monkeypatch: pytest.MonkeyPatch, heartbeat=None) -> TaskExecutor:
    from src.infra.task import cancellation

    _FakePresenter.instances.clear()
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: SimpleNamespace())

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)
    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=heartbeat or _FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _no_op)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr(executor, "_expire_terminal_stream", _no_op)
    return executor


@pytest.mark.asyncio
async def test_precreated_user_message_trace_skips_duplicate_trace_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _executor(monkeypatch)

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_empty_agent_stream,
        existing_trace_id="trace-1",
        user_message_written=True,
    )

    presenter = _FakePresenter.instances[0]
    assert presenter.ensure_trace_calls == 0
    assert presenter._trace_created is True
    assert presenter.emitted_user_messages == []


@pytest.mark.asyncio
async def test_unproven_existing_trace_still_calls_ensure_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _executor(monkeypatch)

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_empty_agent_stream,
        existing_trace_id="trace-1",
        user_message_written=False,
    )

    presenter = _FakePresenter.instances[0]
    assert presenter.ensure_trace_calls == 1


@pytest.mark.asyncio
async def test_heartbeat_and_running_status_overlap_before_agent_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_started = asyncio.Event()
    running_started = asyncio.Event()
    release = asyncio.Event()
    agent_started = asyncio.Event()

    class _GatedHeartbeat(_FakeHeartbeat):
        async def start(self, run_id: str, *, user_id: str | None = None) -> None:
            await super().start(run_id, user_id=user_id)
            heartbeat_started.set()
            await release.wait()

    executor = _executor(monkeypatch, heartbeat=_GatedHeartbeat())

    async def _update_status(
        _session_id: str,
        status: TaskStatus,
        *_args,
        **_kwargs,
    ) -> None:
        if status == TaskStatus.RUNNING:
            running_started.set()
            await release.wait()

    async def _agent_stream(*_args, **_kwargs):
        agent_started.set()
        if False:
            yield {}

    monkeypatch.setattr(executor, "_update_session_status", _update_status)

    task = asyncio.create_task(
        executor.run_task(
            "session-1",
            "run-1",
            "search",
            "hello",
            "user-1",
            _agent_stream,
            existing_trace_id="trace-1",
            user_message_written=True,
        )
    )
    try:
        await asyncio.wait_for(heartbeat_started.wait(), timeout=1)
        for _ in range(20):
            if running_started.is_set():
                break
            await asyncio.sleep(0)

        assert running_started.is_set() is True
        assert agent_started.is_set() is False
    finally:
        release.set()
        await task

    assert agent_started.is_set() is True
