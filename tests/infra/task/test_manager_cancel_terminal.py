from __future__ import annotations

"""Cancel must be a no-op for sessions whose task already reached a terminal state.

Production symptom: session.metadata.current_run_id stays set after a run
completes. A late stop request (stale tab, replayed click, second device)
resolved to the finished run and the cancellation fallback rewrote session
metadata (task_error_code="cancelled") and published a task:cancel that
flipped the completed trace to error.
"""

from types import SimpleNamespace

import pytest

from src.infra.task.manager import BackgroundTaskManager


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, object]] = []

    async def get_by_session_id(self, session_id: str):
        if self.session and self.session.id == session_id:
            return self.session
        return None

    async def update(self, session_id, session_update) -> None:
        self.updates.append((session_id, session_update))


class _FakeCancellation:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def cancel_run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "cancelled_locally": False,
            "run_id": kwargs.get("run_id"),
            "message": "取消信号已发送，任务将在下次检查点中断",
        }


def _manager_with(session) -> tuple[BackgroundTaskManager, _FakeCancellation, _FakeStorage]:
    storage = _FakeStorage(session)
    manager = BackgroundTaskManager()
    manager._storage = storage
    cancellation = _FakeCancellation()
    manager._cancellation = cancellation
    return manager, cancellation, storage


@pytest.mark.asyncio
@pytest.mark.parametrize("task_status", ["completed", "cancelled", "failed", "expired"])
async def test_cancel_is_noop_when_task_status_terminal(task_status):
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={
            "current_run_id": "run-old",
            "task_status": task_status,
            "agent_id": "search",
            "trace_id": "trace-1",
        },
    )
    manager, cancellation, storage = _manager_with(session)

    result = await manager.cancel("session-1", user_id="user-1")

    assert result["success"] is False
    assert result["run_id"] is None
    assert "没有正在运行的任务" in result["message"]
    assert cancellation.calls == []
    assert storage.updates == []


@pytest.mark.asyncio
@pytest.mark.parametrize("task_status", ["running", "waiting_human", None])
async def test_cancel_proceeds_when_task_active_or_status_missing(task_status):
    metadata = {
        "current_run_id": "run-active",
        "agent_id": "search",
        "trace_id": "trace-1",
    }
    if task_status is not None:
        metadata["task_status"] = task_status
    session = SimpleNamespace(
        id="session-1", user_id="user-1", agent_id="search", metadata=metadata
    )
    manager, cancellation, _storage = _manager_with(session)

    result = await manager.cancel("session-1", user_id="user-1")

    assert result["success"] is True
    assert len(cancellation.calls) == 1
    assert cancellation.calls[0]["run_id"] == "run-active"


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_metadata", [None, {}])
async def test_cancel_reports_no_running_task_when_session_metadata_empty(empty_metadata):
    """新建会话 metadata 为空 dict/None：取消应报"没有正在运行的任务"而非"取消失败"。

    空 metadata 会掉进 fall-through 返回通用失败文案，前端会误展示为系统错误。
    """
    session = SimpleNamespace(
        id="session-1", user_id="user-1", agent_id="search", metadata=empty_metadata
    )
    manager, cancellation, _storage = _manager_with(session)

    result = await manager.cancel("session-1", user_id="user-1")

    assert result["success"] is False
    assert result["run_id"] is None
    assert "没有正在运行的任务" in result["message"]
    assert cancellation.calls == []


def _remote_manager(status="running"):
    from src.infra.task.executor import TaskExecutor

    session = SimpleNamespace(
        id="session-1",
        user_id=None,
        metadata={"current_run_id": "run-active", "task_status": status},
    )
    manager, cancellation, storage = _manager_with(session)

    async def update_for_run(_session_id, run_id, metadata, *, expected_statuses=None):
        if run_id != session.metadata["current_run_id"] or (
            expected_statuses is not None
            and session.metadata["task_status"] not in expected_statuses
        ):
            return False
        session.metadata.update(metadata)
        return True

    storage.update_metadata_for_run = update_for_run
    manager._executor = TaskExecutor(storage, {}, SimpleNamespace())
    manager._executor._schedule_idle_pause_check = lambda _session_id: None
    return manager, cancellation, session


async def test_remote_cancel_signal_keeps_conversation_busy_until_owner_finishes():
    from src.infra.scheduler.conversation import BUSY

    manager, cancellation, session = _remote_manager()
    original_cancel = cancellation.cancel_run

    async def signal(**kwargs):
        assert session.metadata["task_status"] == "cancelling"
        return await original_cancel(**kwargs)

    cancellation.cancel_run = signal
    result = await manager.cancel_run(
        "run-active", run_info_override={"session_id": "session-1", "user_id": "user-1"}
    )
    assert result["success"] is True
    assert result["cancelled_locally"] is False
    assert session.metadata["task_status"] in BUSY
    assert session.metadata["task_status"] == "cancelling"


@pytest.mark.parametrize("terminal", ["cancelled", "completed", "failed"])
@pytest.mark.parametrize("before_signal", [False, True])
async def test_remote_owner_terminal_is_not_overwritten_after_signal(terminal, before_signal):
    manager, cancellation, session = _remote_manager(terminal if before_signal else "running")
    original_cancel = cancellation.cancel_run

    async def signal(**kwargs):
        session.metadata["task_status"] = terminal
        return await original_cancel(**kwargs)

    cancellation.cancel_run = signal
    await manager.cancel_run("run-active", run_info_override={"session_id": "session-1"})
    assert session.metadata["task_status"] == terminal


@pytest.mark.parametrize("status", ["queued", "pending", "waiting_human"])
async def test_cancel_without_executing_graph_can_finish_immediately(status):
    manager, _, session = _remote_manager(status)
    await manager.cancel_run("run-active", run_info_override={"session_id": "session-1"})
    assert session.metadata["task_status"] == "cancelled"


async def test_queued_owner_starting_during_cancel_stays_busy_until_cleanup():
    manager, cancellation, session = _remote_manager("queued")
    original_cancel = cancellation.cancel_run

    async def signal(**kwargs):
        session.metadata["task_status"] = "starting"
        return await original_cancel(**kwargs)

    cancellation.cancel_run = signal
    await manager.cancel_run("run-active", run_info_override={"session_id": "session-1"})
    assert session.metadata["task_status"] == "starting"


async def test_local_owner_finished_by_cancel_can_reach_terminal():
    import asyncio

    manager, _, session = _remote_manager()
    finished = asyncio.get_running_loop().create_future()
    finished.set_result(None)
    manager._tasks["run-active"] = finished
    await manager.cancel_run("run-active", run_info_override={"session_id": "session-1"})
    assert session.metadata["task_status"] == "cancelled"
