from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from src.api.routes import persistent_goal as routes
from src.infra.persistent_goal import GoalService
from src.infra.session.storage import SessionStorage
from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_goal_runtime import runtime_redis  # noqa: F401
from tests.infra.agent.test_persistent_goal import Store


class SessionCollection:
    def __init__(self, *, object_id=True):
        self.doc = {
            "_id": ObjectId(),
            "user_id": "u",
            "metadata": {
                "current_run_id": "old",
                "task_status": "waiting_human",
                "trace_id": "old-trace",
            },
        }
        if not object_id:
            self.doc["session_id"] = "session"
        self.race = False

    @property
    def session_id(self):
        return self.doc.get("session_id", str(self.doc["_id"]))

    def matches(self, query):
        for key, expected in query.items():
            actual = self.doc
            for part in key.split("."):
                actual = actual.get(part) if isinstance(actual, dict) else None
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def find_one(self, query, *args, **kwargs):
        return deepcopy(self.doc) if self.matches(query) else None

    def write(self, query, update):
        identity = {key: value for key, value in query.items() if key in {"_id", "session_id"}}
        if self.race and self.matches(identity):
            self.race = False
            self.doc["metadata"].update(
                current_run_id="new-human", task_status="running", trace_id="new-trace"
            )
        if not self.matches(query):
            return False
        for key, value in update["$set"].items():
            if key.startswith("metadata."):
                self.doc["metadata"][key.split(".", 1)[1]] = value
            else:
                self.doc[key] = value
        return True

    async def update_one(self, query, update):
        return SimpleNamespace(matched_count=int(self.write(query, update)))

    async def find_one_and_update(self, query, update, **kwargs):
        return deepcopy(self.doc) if self.write(query, update) else None


def actual_storage(monkeypatch, collection):
    monkeypatch.setattr(SessionStorage, "collection", property(lambda self: collection))
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", AsyncMock())
    return SessionStorage()


@pytest.mark.parametrize("object_id", [False, True])
async def test_terminal_session_update_atomically_fences_new_human_run(monkeypatch, object_id):
    collection = SessionCollection(object_id=object_id)
    storage = actual_storage(monkeypatch, collection)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    monkeypatch.setattr(executor, "_schedule_idle_pause_check", lambda _: None)
    collection.race = True
    await executor._update_session_status(collection.session_id, TaskStatus.CANCELLED, run_id="old")
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert collection.doc["metadata"]["task_status"] == "running"


@pytest.mark.parametrize("action", ["pause", "clear", "replace"])
@pytest.mark.parametrize("new_human_race", [False, True])
async def test_goal_control_seals_only_captured_suspended_run(monkeypatch, action, new_human_race):
    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    session_id = collection.session_id
    service = GoalService(Store())
    await service.create(session_id, "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.attach_user_run(session_id, "u", "old")
    waiting = await service.control(session_id, "u", "waiting_human")
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    monkeypatch.setattr(executor, "_schedule_idle_pause_check", lambda _: None)
    monkeypatch.setattr(executor, "_expire_terminal_stream", AsyncMock())
    task_manager = SimpleNamespace(
        _executor=executor, cancel_run=AsyncMock(return_value={"success": True})
    )
    manager = SimpleNamespace(
        get_session=AsyncMock(
            side_effect=lambda _: SessionStorage._build_session(deepcopy(collection.doc))
        )
    )
    approvals = [
        SimpleNamespace(
            id=identity,
            session_id=session_id,
            user_id="u",
            status="pending",
            metadata={"mode": "interrupt", "run_id": run_id, "trace_id": trace},
        )
        for identity, run_id, trace in [
            ("old-approval", "old", "old-trace"),
            ("new-approval", "new-human", "new-trace"),
            ("unbound", "", "unknown"),
        ]
    ]
    updates = []

    async def update_approval(approval_id, status):
        updates.append((approval_id, status))

    approval_storage = SimpleNamespace(
        list_pending=AsyncMock(return_value=approvals), update_status=update_approval
    )
    events = []

    async def write_event(**event):
        events.append(event)

    async def publish(goal):
        collection.race = new_human_race

    monkeypatch.setattr(routes, "SessionManager", lambda: manager)
    monkeypatch.setattr(routes, "GoalService", lambda: service)
    monkeypatch.setattr(routes, "publish_goal", publish)
    monkeypatch.setattr(routes, "enqueue_goal", AsyncMock())
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: task_manager)
    monkeypatch.setattr("src.infra.storage.mongodb.get_approval_storage", lambda: approval_storage)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(write_event=write_event),
    )
    monkeypatch.setattr("src.infra.task.hitl._acquire_resume_lock", AsyncMock(return_value="lock"))
    monkeypatch.setattr("src.infra.task.hitl._release_resume_lock", AsyncMock())
    if action == "replace":
        await routes.put_goal(
            session_id,
            PersistentGoalCreate(objective="new", rubric="new", expected_revision=waiting.revision),
            user=SimpleNamespace(sub="u"),
        )
    else:
        await routes._control(session_id, SimpleNamespace(sub="u"), action)
    assert updates == [("old-approval", "cancelled")]
    assert [event["event_type"] for event in events] == ["approval_resolved", "user:cancel", "done"]
    assert all(event["run_id"] == reserved.current_run_id for event in events)
    assert all(event["trace_id"] == "old-trace" for event in events)
    assert collection.doc["metadata"]["current_run_id"] == (
        "new-human" if new_human_race else "old"
    )
    assert collection.doc["metadata"]["task_status"] == (
        "running" if new_human_race else "cancelled"
    )
    executor._expire_terminal_stream.assert_awaited_once()
