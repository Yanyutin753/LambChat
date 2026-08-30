"""TaskManager 初始用户消息持久化必须携带运行模式（auto/goal）。

staging 实测发现走任务队列路径时 user:message 事件缺失 run_modes：
根因是 BackgroundTaskManager._persist_initial_user_message 未透传运行模式。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.infra.task.manager import BackgroundTaskManager


class _RecordingPresenter:
    calls: list[dict[str, Any]] = []

    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "generated-trace"

    async def _ensure_trace(self) -> None:
        pass

    async def emit_user_message(self, message: str, **kwargs) -> None:
        type(self).calls.append({"message": message, **kwargs})


class _FakeExecutor:
    async def ensure_session(self, *args, **kwargs) -> None:
        return None

    async def _update_session_status(self, *args, **kwargs) -> None:
        return None

    async def run_task(self, *args, **kwargs) -> None:
        return None


async def _executor_fn(*args, **kwargs):
    if False:
        yield None


@pytest.mark.asyncio
async def test_submit_persists_auto_run_mode_on_initial_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    _RecordingPresenter.calls = []
    monkeypatch.setattr(manager, "_executor", _FakeExecutor())  # type: ignore[assignment]

    async def _release_no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(manager, "_release_concurrency", _release_no_op)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _RecordingPresenter)

    await manager.submit(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_executor_fn,
        run_id="run-1",
        trace_id="trace-1",
        auto_mode=True,
        write_user_message_immediately=True,
    )

    await asyncio.sleep(0)

    assert _RecordingPresenter.calls == [
        {
            "message": "hello",
            "attachments": None,
            "enabled_skills": None,
            "attachment_references_claimed": False,
            "schedule_search_index": True,
            "run_modes": ["auto"],
        }
    ]


@pytest.mark.asyncio
async def test_submit_persists_goal_run_mode_on_initial_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    _RecordingPresenter.calls = []
    monkeypatch.setattr(manager, "_executor", _FakeExecutor())  # type: ignore[assignment]

    async def _release_no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(manager, "_release_concurrency", _release_no_op)
    monkeypatch.setattr("src.infra.writer.present.Presenter", _RecordingPresenter)

    await manager.submit(
        session_id="session-2",
        agent_id="search",
        message="with goal",
        user_id="user-1",
        executor=_executor_fn,
        run_id="run-2",
        trace_id="trace-2",
        active_goal={"objective": "ship it"},
        write_user_message_immediately=True,
    )

    await asyncio.sleep(0)

    assert _RecordingPresenter.calls == [
        {
            "message": "with goal",
            "attachments": None,
            "enabled_skills": None,
            "attachment_references_claimed": False,
            "schedule_search_index": True,
            "run_modes": ["goal"],
        }
    ]
