from types import SimpleNamespace

import pytest

from src.infra.logging.context import TraceContext
from src.infra.task.executor import TaskExecutor


class _FakeHeartbeat:
    async def start(self, run_id: str, user_id: str | None = None) -> None:
        return None

    async def stop(self, run_id: str) -> None:
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
