from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus


class _FakeStorage:
    def __init__(self, active_run_id: str | None = None) -> None:
        self.session = SimpleNamespace(metadata={"active_run_id": active_run_id})
        self.updates: list[dict] = []

    async def update(self, session_id: str, session_update) -> None:
        self.updates.append(session_update.metadata)

    async def update_metadata_if_active_run(self, session_id: str, run_id: str, metadata: dict):
        if self.session.metadata.get("active_run_id") == run_id:
            self.updates.append(metadata)
            return True
        return False


@pytest.mark.asyncio
async def test_pending_status_writes_current_and_active_run() -> None:
    storage = _FakeStorage()
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    await executor._update_session_status("session-1", TaskStatus.PENDING, run_id="run-1")

    assert storage.updates[-1]["current_run_id"] == "run-1"
    assert storage.updates[-1]["active_run_id"] == "run-1"
    assert storage.updates[-1]["last_started_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_failed_status_skips_when_run_is_no_longer_active() -> None:
    storage = _FakeStorage(active_run_id="run-new")
    executor = TaskExecutor(storage=storage, run_info={}, heartbeat_manager=None)  # type: ignore[arg-type]

    await executor._update_session_status("session-1", TaskStatus.FAILED, run_id="run-old")

    assert storage.updates == []
