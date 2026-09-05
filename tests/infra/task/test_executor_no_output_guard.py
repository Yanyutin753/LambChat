"""run 正常走到 done 却没有任何主代理正文时，不得假装 completed。

兜底守卫：即使模型空正文被中间件静默放行（或未来回归），executor 也要把
「零正文产出」的 run 终结为 error 而不是 completed，让用户看到明确的失败
（2026-09-05 生产事故：重启续跑后 run 标记 completed 但气泡里没有答案）。
"""

from __future__ import annotations

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
) -> tuple[TaskExecutor, _RecordingWriter, dict, list[str]]:
    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    writer = _RecordingWriter()
    monkeypatch.setattr("src.infra.task.executor.get_dual_writer", lambda: writer)

    async def _no_op(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(cancellation.TaskCancellation, "clear_interrupt", _no_op)

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
    return executor, writer, presenter_holder, status_updates


def _stream_of(events: list[dict]):
    async def _stream(*_args, **_kwargs):
        for event in events:
            yield event

    return _stream


async def test_run_without_assistant_text_fails_instead_of_completing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有 thinking/工具事件、无主代理 message:chunk 的 run 必须进 error 终态。"""
    executor, writer, holder, status_updates = _executor_fixture(monkeypatch)

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="搜索今日新闻",
        user_id="user-1",
        executor=_stream_of(
            [
                {"event": "thinking", "data": {"content": "思考中"}},
                {"event": "tool:start", "data": {"tool": "web_search"}},
                {"event": "tool:result", "data": {"tool": "web_search"}},
                {"event": "token:usage", "data": {"output_tokens": 1}},
                {"event": "done", "data": {"status": "completed"}},
            ]
        ),
        user_message_written=True,
    )

    assert result is None  # error path
    presenter = holder["presenter"]
    assert presenter.completions == ["error"]
    assert "failed" in status_updates
    assert "completed" not in status_updates
    error_events = [e for e in writer.written if e.get("event_type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["data"]["code"] == "model_empty_response"


async def test_run_with_presenter_delivered_text_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """处理器直发路径回归（2026-09-05 生产事故）：正文经 presenter.emit 落库、
    不经过 executor 事件循环，守卫必须读 presenter.produced_main_text 判定，
    不得把交付过内容的 run 误判失败。"""
    executor, writer, holder, status_updates = _executor_fixture(monkeypatch)

    async def _stream_with_direct_delivery(*_args, **kwargs):
        # 模拟 AgentEventProcessor 缓冲 flush：正文直发 presenter，循环里看不到
        kwargs["presenter"].produced_main_text = True
        yield {"event": "thinking", "data": {"content": "思考"}}
        yield {"event": "done", "data": {"status": "completed"}}

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="fast",
        message="hi",
        user_id="user-1",
        executor=_stream_with_direct_delivery,
        user_message_written=True,
    )

    assert result is False  # completed path
    assert holder["presenter"].completions == ["completed"]
    assert "completed" in status_updates
    assert [e for e in writer.written if e.get("event_type") == "error"] == []


async def test_run_with_main_agent_text_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """有主代理 message:chunk 的 run 保持原行为：completed。"""
    executor, writer, holder, status_updates = _executor_fixture(monkeypatch)

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hi",
        user_id="user-1",
        executor=_stream_of(
            [
                {"event": "thinking", "data": {"content": "思考"}},
                {"event": "message:chunk", "data": {"content": "这是最终回答"}},
                {"event": "done", "data": {"status": "completed"}},
            ]
        ),
        user_message_written=True,
    )

    assert result is False  # completed path
    assert holder["presenter"].completions == ["completed"]
    assert "completed" in status_updates
    assert [e for e in writer.written if e.get("event_type") == "error"] == []


async def test_subagent_chunk_does_not_count_as_main_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """子代理（depth>0）的 message:chunk 不算主代理正文，仍判空。"""
    executor, _writer, _holder, status_updates = _executor_fixture(monkeypatch)

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="fast",
        message="hi",
        user_id="user-1",
        executor=_stream_of(
            [
                {
                    "event": "message:chunk",
                    "data": {"content": "子代理输出", "depth": 1, "agent_id": "researcher"},
                },
                {"event": "done", "data": {"status": "completed"}},
            ]
        ),
        user_message_written=True,
    )

    assert result is None
    assert "failed" in status_updates
    assert "completed" not in status_updates


async def test_blank_chunk_does_not_count_as_main_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """纯空白的 message:chunk 不算正文产出。"""
    executor, _writer, _holder, status_updates = _executor_fixture(monkeypatch)

    result = await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="fast",
        message="hi",
        user_id="user-1",
        executor=_stream_of(
            [
                {"event": "message:chunk", "data": {"content": "   "}},
                {"event": "done", "data": {"status": "completed"}},
            ]
        ),
        user_message_written=True,
    )

    assert result is None
    assert "failed" in status_updates
