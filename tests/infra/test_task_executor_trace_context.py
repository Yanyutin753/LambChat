from types import SimpleNamespace

import pytest

from src.infra.logging.context import TraceContext
from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from src.kernel.extensions import PluginRuntime, build_agent_team_plugin_manifest


class _FakeHeartbeat:
    def __init__(self) -> None:
        self.started: list[tuple[str, str | None]] = []
        self.stopped: list[str] = []

    async def start(self, run_id: str, user_id: str | None = None) -> None:
        self.started.append((run_id, user_id))
        return None

    async def stop(self, run_id: str) -> None:
        self.stopped.append(run_id)
        return None


class _FakeStorage:
    def __init__(self) -> None:
        self.updates: list[tuple[str, object]] = []

    async def update(self, session_id: str, update) -> None:
        self.updates.append((session_id, update))

    async def get_by_session_id(self, session_id: str):
        return None


class _FakeDualWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def write_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def _flush_redis_buffer(self) -> None:
        return None

    async def flush_mongo_buffer(self) -> None:
        return None

    async def expire_stream(self, *args, **kwargs) -> None:
        return None


class _FakePresenter:
    def __init__(self, config) -> None:
        self.config = config
        self.trace_id = config.trace_id or "trace-run-level"
        self.run_id = config.run_id or "run-1"

    async def _ensure_trace(self) -> None:
        return None

    async def emit_user_message(self, message: str, attachments=None) -> None:
        return None

    async def save_event(self, event) -> None:
        return None

    async def complete(self, status: str) -> None:
        return None


@pytest.mark.asyncio
async def test_task_executor_sets_run_trace_into_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = TaskExecutor(
        storage=SimpleNamespace(),
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )

    async def _no_op(*args, **kwargs) -> None:
        return None

    async def fake_agent_executor(*args, **kwargs):
        assert TraceContext.get().trace_id == "trace-run-level"
        req_ctx = TraceContext.get_request_context()
        assert req_ctx.session_id == "session-1"
        assert req_ctx.run_id == "run-1"
        assert req_ctx.user_id == "user-1"
        assert req_ctx.trace_id == "trace-run-level"
        if False:
            yield None

    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr(
        "src.infra.writer.present.PresenterConfig",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        executor,
        "_update_session_status",
        _no_op,
    )
    monkeypatch.setattr(
        executor,
        "_send_task_notification",
        _no_op,
    )
    monkeypatch.setattr(
        "src.infra.task.executor.get_dual_writer",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "src.infra.task.cancellation.TaskCancellation.clear_interrupt",
        _no_op,
    )

    TraceContext.clear()
    TraceContext.clear_request_context()
    TraceContext.set(trace_id="request-trace", span_id="span-1")

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="agent-1",
        message="hello",
        user_id="user-1",
        executor=fake_agent_executor,
        existing_trace_id="trace-run-level",
    )

    assert TraceContext.get().trace_id is None
    req_ctx = TraceContext.get_request_context()
    assert req_ctx.session_id is None
    assert req_ctx.run_id is None
    assert req_ctx.user_id is None
    assert req_ctx.trace_id is None


@pytest.mark.asyncio
async def test_task_executor_passes_resolved_agent_name_to_presenter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = TaskExecutor(
        storage=SimpleNamespace(),
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )

    async def _no_op(*args, **kwargs) -> None:
        return None

    async def fake_agent_executor(*args, **kwargs):
        presenter = kwargs["presenter"]
        assert presenter.config.agent_name == "Search Agent"
        if False:
            yield None

    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr(
        "src.infra.writer.present.PresenterConfig",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        executor,
        "_update_session_status",
        _no_op,
    )
    monkeypatch.setattr(
        executor,
        "_send_task_notification",
        _no_op,
    )
    monkeypatch.setattr(
        "src.infra.task.executor.get_dual_writer",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "src.infra.task.cancellation.TaskCancellation.clear_interrupt",
        _no_op,
    )

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=fake_agent_executor,
        existing_trace_id="trace-run-level",
    )


@pytest.mark.asyncio
async def test_task_executor_rejects_disabled_plugin_owned_agent_before_executor_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    storage = _FakeStorage()
    heartbeat = _FakeHeartbeat()
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=heartbeat)
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    executor_called = False

    async def _no_op(*args, **kwargs) -> None:
        return None

    async def fake_agent_executor(*args, **kwargs):
        nonlocal executor_called
        executor_called = True
        if False:
            yield None

    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: writer)
    monkeypatch.setattr(
        "src.infra.task.cancellation.TaskCancellation.clear_interrupt",
        _no_op,
    )
    set_plugin_runtime(runtime)

    try:
        await executor.run_task(
            session_id="session-1",
            run_id="run-1",
            agent_id="team",
            message="hello",
            user_id="user-1",
            executor=fake_agent_executor,
            existing_trace_id="trace-run-level",
        )
    finally:
        set_plugin_runtime(None)

    assert executor_called is False
    assert heartbeat.started == []
    assert heartbeat.stopped == ["run-1"]
    assert storage.updates
    assert storage.updates[0][0] == "session-1"
    metadata = storage.updates[0][1].metadata
    assert metadata["task_status"] == TaskStatus.FAILED.value
    assert "agent_team" in metadata["task_error"]
    assert writer.events
    assert writer.events[0]["event_type"] == "error"
