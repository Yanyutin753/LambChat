from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.goal_runtime import restore_goal_for_run
from src.infra.persistent_goal import GoalService
from src.infra.task.recovery import TaskRecoveryService
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_persistent_goal import Store


async def test_recovery_rehydrates_scope_and_rejects_superseded_owner():
    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.reserve("s", "u", goal.version)
    session = SimpleNamespace(id="s", user_id="u", metadata={"persistent_goal_id": goal.id})
    restored = await restore_goal_for_run(session, reserved.current_run_id, service=service)
    assert restored["_persistent_version"] == reserved.version
    assert restored["_persistent_id"] == goal.id
    await service.control("s", "u", "pause")
    with pytest.raises(Exception, match="paused|superseded"):
        await restore_goal_for_run(session, reserved.current_run_id, service=service)


async def test_actual_recovery_submission_carries_goal_enforcement(monkeypatch):
    goal = {
        "objective": "finish",
        "rubric": "tests",
        "_persistent_id": "g",
        "_persistent_version": 1,
    }
    monkeypatch.setattr("src.infra.goal_runtime.restore_goal_for_run", AsyncMock(return_value=goal))
    monkeypatch.setattr("src.infra.task.recovery.get_registered_executor", lambda key: object())
    monkeypatch.setattr("src.infra.task.recovery.settings.TASK_BACKEND", "arq")
    submit = AsyncMock(return_value=("run", "trace"))
    service = TaskRecoveryService(
        storage=object(),
        run_info={},
        heartbeat=object(),
        ensure_executor=lambda: None,
        submit_task=submit,
        submit_arq_task=submit,
        mark_run_failed=AsyncMock(),
    )
    monkeypatch.setattr(service, "get_preferred_language", AsyncMock(return_value="en"))
    session = SimpleNamespace(
        id="s", user_id="u", name="task", metadata={"persistent_goal_id": "g"}
    )
    await service.submit_seamless_resume(session, "run", "trace", "restart")
    assert submit.call_args.kwargs["active_goal"] == goal
