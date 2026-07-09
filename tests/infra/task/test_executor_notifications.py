from __future__ import annotations

import pytest

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from src.infra.writer.present import create_presenter


class _FakeWebSocketManager:
    def __init__(self, delivered_count: int) -> None:
        self.delivered_count = delivered_count
        self.sent: list[tuple[str, dict]] = []

    async def send_to_user_with_broadcast(self, user_id: str, message: dict) -> int:
        self.sent.append((user_id, message))
        return self.delivered_count


class _FakeSessionManager:
    async def get_session(self, session_id: str):
        return None


class _FakeLogger:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []

    def info(self, message: str, *args) -> None:
        self.infos.append(message % args if args else message)

    def warning(self, message: str, *args) -> None:
        self.warnings.append(message % args if args else message)


class _FakeDualWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.completed: list[tuple[str, str, dict | None]] = []
        self.expired_streams: list[tuple[str, str, int]] = []

    async def create_trace(self, **kwargs):
        return True

    async def write_event(self, **kwargs):
        self.events.append(kwargs)
        return True

    async def _flush_redis_buffer(self):
        return None

    async def flush_mongo_buffer(self, **kwargs):
        del kwargs
        return None

    async def complete_trace(self, trace_id: str, status: str, metadata=None):
        self.completed.append((trace_id, status, metadata))
        return True

    async def expire_stream(
        self, session_id: str, run_id: str | None = None, ttl_seconds: int = 60
    ):
        self.expired_streams.append((session_id, run_id, ttl_seconds))
        return True


class _FakeStorage:
    def __init__(self, current_run_id: str | None = None) -> None:
        self.updates: list[tuple[str, object]] = []
        self.current_run_id = current_run_id

    async def update(self, session_id: str, update) -> None:
        self.updates.append((session_id, update))

    async def get_by_session_id(self, session_id: str):
        if self.current_run_id is None:
            return None
        return type(
            "Session",
            (),
            {"metadata": {"current_run_id": self.current_run_id}},
        )()


def _presenter():
    return create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )


@pytest.mark.asyncio
async def test_task_notification_warns_when_no_websocket_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_manager = _FakeWebSocketManager(delivered_count=0)
    fake_logger = _FakeLogger()
    monkeypatch.setattr("src.infra.websocket.get_connection_manager", lambda: ws_manager)
    monkeypatch.setattr("src.infra.session.manager.SessionManager", _FakeSessionManager)
    monkeypatch.setattr("src.infra.task.executor.logger", fake_logger)

    executor = TaskExecutor(storage=None, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    await executor._send_task_notification(
        "session-1",
        "run-1",
        TaskStatus.COMPLETED,
        "user-1",
    )

    assert ws_manager.sent
    assert any("delivered=0" in message for message in fake_logger.warnings)


@pytest.mark.asyncio
async def test_update_session_status_uses_cancelled_task_metadata() -> None:
    storage = _FakeStorage()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    await executor._update_session_status(
        "session-1",
        TaskStatus.CANCELLED,
        "Task cancelled",
        run_id="run-1",
    )

    assert storage.updates
    assert storage.updates[0][0] == "session-1"
    metadata = storage.updates[0][1].metadata
    assert metadata["task_status"] == "cancelled"
    assert metadata["task_error"] == "Task cancelled"
    assert metadata["task_error_code"] == "cancelled"
    assert metadata["task_recoverable"] is False
    assert metadata["current_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_stale_cancelled_run_does_not_overwrite_new_current_run() -> None:
    storage = _FakeStorage(current_run_id="run-new")
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    await executor._update_session_status(
        "session-1",
        TaskStatus.CANCELLED,
        "Task cancelled",
        run_id="run-old",
    )

    assert storage.updates == []


@pytest.mark.asyncio
async def test_interrupted_task_uses_cancelled_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]
    presenter = create_presenter(
        session_id="session-1",
        agent_id="search",
        agent_name="Search",
        run_id="run-1",
        trace_id="trace-1",
    )

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)

    await executor._handle_interrupted_error(
        "session-1",
        "run-1",
        "user-1",
        "Task interrupted: run_id=run-1",
        writer,
        None,
    )

    assert storage.updates
    metadata = storage.updates[0][1].metadata
    assert metadata["task_status"] == "cancelled"
    assert metadata["task_error_code"] == "cancelled"
    assert metadata["task_recoverable"] is False


@pytest.mark.asyncio
async def test_cancelled_task_emits_user_cancel_before_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=None, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]
    presenter = _presenter()

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_update_session_status", _no_op)
    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)

    await executor._handle_cancelled_error(
        "session-1",
        "run-1",
        "user-1",
        writer,
        presenter,
    )

    assert [event["event_type"] for event in writer.events] == [
        "token:usage",
        "user:cancel",
        "error",
        "done",
    ]
    assert [event["trace_id"] for event in writer.events] == [
        "trace-1",
        "trace-1",
        "trace-1",
        "trace-1",
    ]
    assert [event["run_id"] for event in writer.events] == [
        "run-1",
        "run-1",
        "run-1",
        "run-1",
    ]
    assert writer.expired_streams == [("session-1", "run-1", 60)]


@pytest.mark.asyncio
async def test_interrupted_task_emits_user_cancel_before_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]
    presenter = _presenter()

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)

    await executor._handle_interrupted_error(
        "session-1",
        "run-1",
        "user-1",
        "Task interrupted: run_id=run-1",
        writer,
        presenter,
    )

    assert [event["event_type"] for event in writer.events] == [
        "token:usage",
        "user:cancel",
        "error",
        "done",
    ]


@pytest.mark.asyncio
async def test_interrupted_task_reorders_previously_recorded_done_after_user_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]
    presenter = _presenter()

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_send_task_notification", _no_op)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)

    await presenter.emit(presenter.done())
    await executor._handle_interrupted_error(
        "session-1",
        "run-1",
        "user-1",
        "Task interrupted: run_id=run-1",
        writer,
        presenter,
    )

    assert [event["event_type"] for event in writer.events] == [
        "token:usage",
        "user:cancel",
        "error",
        "done",
    ]


@pytest.mark.asyncio
async def test_failed_task_shortens_terminal_stream_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    writer = _FakeDualWriter()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(executor, "_send_task_notification", _no_op)

    await executor._handle_generic_error(
        "session-1",
        "run-1",
        "user-1",
        RuntimeError("boom"),
        writer,
        None,
    )

    assert writer.events[-1]["event_type"] == "error"
    assert writer.expired_streams == [("session-1", "run-1", 60)]
