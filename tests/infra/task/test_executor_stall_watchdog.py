"""Run-level stall watchdog for task executor (issue #293).

Worker 存活但 agent stream 挂死（LLM 首包永不到达等）时，心跳持续刷新、
孤儿接管永不触发，run/trace 停留在 running。watchdog 要求 executor 事件流
按 deadline 持续推进，超时迁移 error 终态。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from src.kernel.config import settings


class _FakeHeartbeat:
    async def start(self, run_id: str, *, user_id: str | None = None) -> None:
        return None

    async def stop(self, run_id: str) -> None:
        return None


class _FakePresenter:
    instances: list["_FakePresenter"] = []

    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "generated-trace"
        self.run_id = config.run_id
        self._trace_created = False
        self.saved_events: list[dict] = []
        self.completed: list[str] = []
        self._last_progress_monotonic = time.monotonic()
        self.__class__.instances.append(self)

    def last_progress_monotonic(self) -> float:
        """镜像真实 Presenter 的进展时间戳契约（save_event 汇聚点刷新）。"""
        return self._last_progress_monotonic

    async def _ensure_trace(self) -> None:
        self._trace_created = True

    async def emit_user_message(self, message: str, **_kwargs) -> None:
        return None

    async def save_event(self, event: dict) -> None:
        self.saved_events.append(event)
        self._last_progress_monotonic = time.monotonic()

    async def complete(self, status: str) -> None:
        self.completed.append(status)


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


def _executor_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stall_timeout: float,
) -> tuple[TaskExecutor, _RecordingWriter, list[tuple[TaskStatus, str | None]]]:
    from src.infra.task import cancellation

    monkeypatch.setattr(settings, "TASK_RUN_STALL_TIMEOUT", stall_timeout)
    _FakePresenter.instances.clear()
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)

    writer = _RecordingWriter()
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: writer)

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)

    status_updates: list[tuple[TaskStatus, str | None]] = []

    async def _record_status(session_id, status, error=None, run_id=None):
        status_updates.append((status, error))

    executor = TaskExecutor(
        storage=SimpleNamespace(),  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=_FakeHeartbeat(),
    )
    monkeypatch.setattr(executor, "_update_session_status", _record_status)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr(executor, "_expire_terminal_stream", _no_op)
    return executor, writer, status_updates


@pytest.mark.asyncio
async def test_stalled_stream_migrates_run_to_error_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, writer, status_updates = _executor_fixture(monkeypatch, stall_timeout=0.05)

    async def _hung_agent_stream(*_args, **_kwargs):
        # 首事件永不到达：睡眠远超 stall 超时，模拟 LLM 首包挂起
        await asyncio.sleep(5)
        if False:
            yield {}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_hung_agent_stream,
    )

    presenter = _FakePresenter.instances[0]
    assert result is None  # error path
    assert presenter.completed == ["error"]
    assert TaskStatus.FAILED in [s for s, _ in status_updates]
    error_events = [w for w in writer.written if w.get("event_type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["data"]["type"] == "TaskStalledError"
    assert error_events[0]["data"]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_stalled_mid_stream_times_out_between_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, writer, _status_updates = _executor_fixture(monkeypatch, stall_timeout=0.05)

    async def _stream_then_hang(*_args, **_kwargs):
        yield {"event": "text", "data": {"content": "first"}}
        await asyncio.sleep(5)  # 第二个事件挂起
        yield {"event": "text", "data": {"content": "never"}}

    await executor.run_task(
        session_id="session-1",
        run_id="run-2",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_stream_then_hang,
    )

    presenter = _FakePresenter.instances[0]
    assert presenter.completed == ["error"]
    saved = [e["event"] for e in presenter.saved_events]
    assert "text" in saved
    error_events = [w for w in writer.written if w.get("event_type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["data"]["type"] == "TaskStalledError"


@pytest.mark.asyncio
async def test_progressing_stream_completes_without_watchdog_interference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, writer, _status_updates = _executor_fixture(monkeypatch, stall_timeout=1.0)

    async def _steady_agent_stream(*_args, **_kwargs):
        for i in range(3):
            await asyncio.sleep(0.01)
            yield {"event": "message:chunk", "data": {"content": f"chunk-{i}"}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-3",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_steady_agent_stream,
    )

    presenter = _FakePresenter.instances[0]
    assert result is False  # completed path
    assert presenter.completed == ["completed"]
    assert len(presenter.saved_events) == 3
    assert not [w for w in writer.written if w.get("event_type") == "error"]


@pytest.mark.asyncio
async def test_presenter_direct_path_progress_prevents_stall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """presenter 直连路径持续落事件时，生成器静默不得误杀（2026-09-12/13 生产事故）。

    Search Agent 深跑的 message:chunk / 子代理事件走 presenter.emit 直连，
    executor 生成器可静默超过整个 stall 超时窗口；run 实际满负荷运行，
    却被「无事件」看门狗判死。探针观察到 presenter 进展即续命。
    """
    executor, writer, _status_updates = _executor_fixture(monkeypatch, stall_timeout=0.05)

    async def _busy_direct_emit_stream(*_args, presenter=None, **_kwargs):
        # 生成器全程不 yield，直到最后才出正文；期间靠直连路径持续产出
        for i in range(5):
            await asyncio.sleep(0.03)  # 直连事件间隔 < stall 超时
            await presenter.save_event(
                {"event": "message:chunk", "data": {"content": f"direct-{i}", "depth": 1}}
            )
        yield {"event": "message:chunk", "data": {"content": "final"}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-5",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_busy_direct_emit_stream,
    )

    presenter = _FakePresenter.instances[0]
    assert result is False  # completed path
    assert presenter.completed == ["completed"]
    assert not [w for w in writer.written if w.get("event_type") == "error"]


@pytest.mark.asyncio
async def test_watchdog_disabled_when_timeout_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, _writer, _status_updates = _executor_fixture(monkeypatch, stall_timeout=0)

    async def _slow_then_done(*_args, **_kwargs):
        await asyncio.sleep(0.1)
        yield {"event": "message:chunk", "data": {"content": "slow"}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-4",
        agent_id="search",
        message="",
        user_id="user-1",
        executor=_slow_then_done,
    )

    assert result is False
    assert _FakePresenter.instances[0].completed == ["completed"]
