"""系统中断（非用户取消）时 executor 不得写终态事件；恢复 run 先发 run:resumed。

优雅关停 / 部署把后台任务 cancel 掉时，取消路径历史上与用户取消完全同型：
写 user:cancel + error + done 事件、终结 trace 为 error、把 Redis Stream TTL 缩到
60s。这会让「同 run_id 无感续跑」不可能：SSE 重放一碰到终态事件就断开，前端也会
把气泡渲染成"你已终止本次回答"。系统中断必须改为只 flush 缓冲、留下可恢复的
running trace，由 manager.shutdown / arq_worker 负责标记 recoverable 元数据。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import cancellation
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
        self.expired: list[dict] = []

    async def _flush_redis_buffer(self, **_kwargs) -> None:
        return None

    async def flush_mongo_buffer(self, **_kwargs) -> None:
        return None

    async def write_event(self, **kwargs) -> None:
        self.written.append(kwargs)

    async def expire_stream(self, **kwargs) -> None:
        self.expired.append(kwargs)


def _executor_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    interrupt_flag: bool,
) -> tuple[TaskExecutor, _RecordingWriter, _FakePresenter, list[str]]:
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    writer = _RecordingWriter()
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: writer)

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)

    async def _check_interrupt(run_id: str) -> None:
        # 权威判定（内存 + Redis）：用户取消时抛 TaskInterruptedError
        if interrupt_flag:
            raise cancellation.TaskInterruptedError(f"Task interrupted: {run_id}")

    monkeypatch.setattr(cancellation.TaskCancellation, "check_interrupt", _check_interrupt)

    status_updates: list[str] = []

    async def _record_status(session_id, status, error=None, run_id=None):
        status_updates.append(status.value if hasattr(status, "value") else str(status))

    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _record_status)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    presenter_holder: dict[str, _FakePresenter] = {}

    original_init = _FakePresenter.__init__

    def _spy_init(self, config):
        original_init(self, config)
        presenter_holder["presenter"] = self

    monkeypatch.setattr(_FakePresenter, "__init__", _spy_init)
    return executor, writer, presenter_holder, status_updates  # type: ignore[return-value]


async def _agent_stream_raising(exc: BaseException):
    async def _stream(*_args, **_kwargs):
        yield {"event": "thinking", "data": {"content": "部分输出"}}
        raise exc

    return _stream


@pytest.mark.asyncio
async def test_shutdown_cancel_writes_no_terminal_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 interrupt 标志的取消（系统关停）：不写终态事件、不终结 trace、不过期 stream。"""
    executor, writer, holder, status_updates = _executor_fixture(monkeypatch, interrupt_flag=False)

    with pytest.raises(asyncio.CancelledError):
        await executor.run_task(
            session_id="session-1",
            run_id="run-1",
            agent_id="search",
            message="hello",
            user_id="user-1",
            executor=await _agent_stream_raising(asyncio.CancelledError()),
            user_message_written=True,
        )

    presenter = holder["presenter"]
    assert presenter.completions == []  # trace 保持 running
    assert writer.written == []  # 没有 user:cancel / error / done 终态事件
    assert writer.expired == []  # stream TTL 不缩短，供恢复后重放
    # 系统中断不更新任务状态；recoverable 元数据由调用方（shutdown/arq_worker）标记
    assert "cancelled" not in status_updates


@pytest.mark.asyncio
async def test_user_cancel_still_writes_terminal_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户取消（interrupt 标志在）保持旧行为：写终态事件并把 trace 终结为 error。"""
    executor, writer, holder, _ = _executor_fixture(monkeypatch, interrupt_flag=True)

    with pytest.raises(asyncio.CancelledError):
        await executor.run_task(
            session_id="session-1",
            run_id="run-1",
            agent_id="search",
            message="hello",
            user_id="user-1",
            executor=await _agent_stream_raising(asyncio.CancelledError()),
            user_message_written=True,
        )

    presenter = holder["presenter"]
    assert presenter.completions == ["error"]
    written_types = [event["event_type"] for event in writer.written]
    assert "user:cancel" in written_types
    assert "error" in written_types


@pytest.mark.asyncio
async def test_interrupted_resume_emits_run_resumed_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """interrupted_resume=True 的恢复 run 在 agent 输出前先落 run:resumed 标记事件。"""
    executor, writer, holder, _ = _executor_fixture(monkeypatch, interrupt_flag=False)

    async def _agent_stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "重新生成"}}

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="（隐藏恢复指令）",
        user_id="user-1",
        executor=_agent_stream,
        user_message_written=True,
        interrupted_resume=True,
    )

    presenter = holder["presenter"]
    first_agent_event_index = next(
        i for i, event in enumerate(presenter.saved_events) if event["event"] == "message:chunk"
    )
    resumed_events = [event for event in presenter.saved_events if event["event"] == "run:resumed"]
    assert len(resumed_events) == 1
    assert presenter.saved_events.index(resumed_events[0]) < first_agent_event_index
    assert resumed_events[0]["data"]["run_id"] == "run-1"
    # 恢复 run 不写新的 user:message（用户消息早已落库）
    assert not any(event["event"] == "user:message" for event in presenter.saved_events)


@pytest.mark.asyncio
async def test_normal_run_without_interrupted_resume_has_no_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通 run 不发 run:resumed。"""
    executor, _, holder, _ = _executor_fixture(monkeypatch, interrupt_flag=False)

    async def _agent_stream(*_args, **_kwargs):
        yield {"event": "message:chunk", "data": {"content": "hi"}}

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_agent_stream,
        user_message_written=True,
    )

    presenter = holder["presenter"]
    assert not any(event["event"] == "run:resumed" for event in presenter.saved_events)
