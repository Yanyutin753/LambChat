"""executor 终态钩子：run 到达终态后安排沙箱空闲暂停检查。

钩子挂在 _update_session_status 的终态分支（completed/failed/cancelled/
expired/waiting_human），非终态不得触发；stale 跳过路径也不触发。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import src.infra.task.executor as executor_mod
from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus


class _FakeStorage:
    def __init__(self, user_id: str | None = "user-1") -> None:
        self.user_id = user_id
        self.metadata: dict = {}

    async def update(self, session_id: str, payload) -> None:
        self.metadata.update(payload.metadata or {})

    async def get_by_session_id(self, session_id: str):
        return SimpleNamespace(user_id=self.user_id, metadata=dict(self.metadata))


def _make_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TaskExecutor, _FakeStorage, list[str]]:
    scheduled: list[str] = []
    monkeypatch.setattr(
        executor_mod, "schedule_idle_pause", lambda user_id: scheduled.append(user_id)
    )

    async def _no_notification(*_args, **_kwargs) -> None:
        return None

    storage = _FakeStorage()
    executor = TaskExecutor(
        storage=storage,  # type: ignore[arg-type]
        run_info={},
        heartbeat_manager=SimpleNamespace(),
    )
    executor._user_id = None  # type: ignore[attr-defined]
    monkeypatch.setattr(executor, "_send_task_notification", _no_notification)
    return executor, storage, scheduled


async def _flush_hook_task() -> None:
    """给钩子内部 create_task 一个事件循环节拍跑到完成。"""
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "expired", "waiting_human"])
async def test_terminal_status_schedules_idle_pause(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    executor, _storage, scheduled = _make_executor(monkeypatch)

    await executor._update_session_status("sess-1", TaskStatus(status), run_id="run-1")
    await _flush_hook_task()

    assert scheduled == ["user-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "starting", "queued", "cancelling"])
async def test_non_terminal_status_does_not_schedule(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    executor, _storage, scheduled = _make_executor(monkeypatch)

    await executor._update_session_status("sess-1", TaskStatus(status), run_id="run-1")
    await _flush_hook_task()

    assert scheduled == []


@pytest.mark.asyncio
async def test_stale_update_does_not_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    executor, storage, scheduled = _make_executor(monkeypatch)
    storage.metadata["current_run_id"] = "run-NEWER"  # 已有更新的 run 在跑

    await executor._update_session_status("sess-1", TaskStatus.COMPLETED, run_id="run-OLD")
    await _flush_hook_task()

    assert scheduled == []


@pytest.mark.asyncio
async def test_prefers_executor_user_id_over_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, storage, scheduled = _make_executor(monkeypatch)
    storage.user_id = "user-from-session"
    executor._user_id = "user-from-run"  # type: ignore[attr-defined]

    await executor._update_session_status("sess-1", TaskStatus.COMPLETED, run_id="run-1")
    await _flush_hook_task()

    assert scheduled == ["user-from-run"]
