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
