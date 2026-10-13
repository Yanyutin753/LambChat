from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import persistent_goal as routes
from src.infra.persistent_goal import GoalService
from src.kernel.errors import AppError
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_persistent_goal import Store


async def test_routes_enforce_session_owner_before_goal_lookup(monkeypatch):
    manager = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(user_id="other")))
    monkeypatch.setattr(routes, "SessionManager", lambda: manager)
    with pytest.raises(AppError):
        await routes.get_goal("s", user=SimpleNamespace(sub="u"))


async def test_put_and_control_emit_authoritative_goal_and_schedule(monkeypatch):
    manager = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(user_id="u")))
    service = GoalService(Store())
    enqueue = AsyncMock()
    publish = AsyncMock()
    monkeypatch.setattr(routes, "SessionManager", lambda: manager)
    monkeypatch.setattr(routes, "GoalService", lambda: service)
    monkeypatch.setattr(routes, "enqueue_goal", enqueue)
    monkeypatch.setattr(routes, "publish_goal", publish)
    user = SimpleNamespace(sub="u")
    response = await routes.put_goal(
        "s", PersistentGoalCreate(objective="finish", rubric="tests"), user=user
    )
    assert response["goal"]["status"] == "active"
    assert enqueue.await_count == 1
    paused = await routes.pause_goal("s", user=user)
    assert paused["goal"]["status"] == "paused"
    assert publish.await_count == 2
    resumed = await routes.resume_goal("s", user=user)
    assert resumed["goal"]["status"] == "active"
    assert enqueue.await_count == 2


@pytest.mark.parametrize("action", ["pause", "clear", "replace"])
async def test_goal_control_cancels_captured_run_when_new_human_arrives(monkeypatch, action):
    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    old = await service.reserve("s", "u", created.version)
    snapshot = SimpleNamespace(user_id="u", metadata={"current_run_id": old.current_run_id})
    current_run = old.current_run_id
    manager = SimpleNamespace(get_session=AsyncMock(return_value=snapshot))
    task_manager = SimpleNamespace(cancel=AsyncMock(), cancel_run=AsyncMock())

    async def publish(goal):
        nonlocal current_run
        current_run = "new-human-run"

    monkeypatch.setattr(routes, "SessionManager", lambda: manager)
    monkeypatch.setattr(routes, "GoalService", lambda: service)
    monkeypatch.setattr(routes, "publish_goal", publish)
    monkeypatch.setattr(routes, "enqueue_goal", AsyncMock())
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: task_manager)
    if action == "replace":
        await routes.put_goal(
            "s",
            PersistentGoalCreate(objective="new", rubric="new", expected_revision=old.revision),
            user=SimpleNamespace(sub="u"),
        )
    else:
        await routes._control("s", SimpleNamespace(sub="u"), action)
    assert current_run == "new-human-run"
    task_manager.cancel.assert_not_awaited()
    task_manager.cancel_run.assert_awaited_once()
    assert task_manager.cancel_run.await_args.args[0] == old.current_run_id
    assert "session_id" not in task_manager.cancel_run.await_args.kwargs["run_info_override"]
