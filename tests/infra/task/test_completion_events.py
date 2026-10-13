from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId, Timestamp
from pymongo.errors import DuplicateKeyError

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from src.infra.utils.datetime import utc_now


@pytest.fixture(autouse=True)
def isolated_outbox(monkeypatch):
    monkeypatch.setattr(
        "src.infra.task.completion_recovery.TaskCompletionOutbox",
        lambda: SimpleNamespace(stage=AsyncMock(), clear=AsyncMock()),
    )


class Collection:
    def __init__(self):
        self.docs = []
        self.indexes = []

    async def create_index(self, fields, **options):
        self.indexes.append((fields, options))

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return deepcopy(doc)
        return None

    async def find_one_and_update(self, query, update, **options):
        for doc in self.docs:
            if all(
                (key not in doc) if value == {"$exists": False} else doc.get(key) == value
                for key, value in query.items()
            ):
                return deepcopy(doc)
        inserted = {key: value for key, value in query.items() if not isinstance(value, dict)}
        inserted.update(update["$setOnInsert"])
        if any(
            doc.get("user_id") == inserted.get("user_id") and doc.get("id") == inserted.get("id")
            for doc in self.docs
        ):
            raise DuplicateKeyError("duplicate completion identity")
        doc = {"_id": ObjectId(), **inserted}
        for key, spec in update.get("$currentDate", {}).items():
            doc[key] = (
                Timestamp(100, len(self.docs) + 1) if spec == {"$type": "timestamp"} else utc_now()
            )
        self.docs.append(doc)
        return deepcopy(doc)

    def find(self, query):
        def matches(doc, conditions):
            for key, value in conditions.items():
                if key == "$or":
                    if not any(matches(doc, child) for child in value):
                        return False
                elif isinstance(value, dict):
                    for operator, expected in value.items():
                        if operator == "$gte" and not doc[key] >= expected:
                            return False
                        if operator == "$gt" and not doc[key] > expected:
                            return False
                elif doc.get(key) != value:
                    return False
            return True

        docs = [deepcopy(doc) for doc in self.docs if matches(doc, query)]

        class Cursor:
            def sort(self, fields):
                docs.sort(key=lambda doc: tuple(doc[key] for key, _ in fields))
                return self

            def limit(self, count):
                self.count = count
                return self

            async def to_list(self, length):
                return docs[: min(length, self.count)]

        return Cursor()


async def test_journal_is_idempotent_private_sanitized_and_ttl_bounded():
    from src.infra.task.completion_events import TaskCompletionStore

    collection = Collection()
    store = TaskCompletionStore(collection)
    data = {
        "session_id": "s",
        "run_id": "r",
        "status": "completed",
        "notification_kind": "run_complete",
        "dedupe_key": "task:r:completed",
        "secret_payload": "never retain",
    }
    first = await store.record("u", data)
    assert await store.record("u", data) == first
    await store.record("other", data)
    assert "secret_payload" not in first
    assert "user_id" not in first
    assert len(collection.docs) == 2
    assert first["id"] != (await store.list_for_user("other"))["items"][0]["id"]
    assert any(options.get("expireAfterSeconds") == 0 for _, options in collection.indexes)
    assert timedelta(days=29) < collection.docs[0]["expires_at"] - utc_now() <= timedelta(days=30)


async def test_catchup_pages_equal_timestamps_without_drops_or_cross_user_leaks(monkeypatch):
    from src.infra.task import completion_events

    now = utc_now()
    monkeypatch.setattr(completion_events, "utc_now", lambda: now)
    store = completion_events.TaskCompletionStore(Collection())
    for index in range(53):
        await store.record(
            "u",
            {
                "session_id": "s",
                "run_id": str(index),
                "status": "completed",
                "notification_kind": "run_complete",
                "dedupe_key": f"task:{index}:completed",
            },
        )
    await store.record(
        "other",
        {
            "session_id": "other",
            "run_id": "foreign",
            "status": "completed",
            "notification_kind": "run_complete",
            "dedupe_key": "task:foreign:completed",
        },
    )
    first = await store.list_for_user("u", limit=500)
    assert len(first["items"]) == 50
    second = await store.list_for_user("u", cursor=first["next_cursor"])
    assert len(second["items"]) == 3
    assert second["cursor"] and second["next_cursor"] is None
    assert len({item["id"] for item in first["items"] + second["items"]}) == 53
    assert all(item["session_id"] == "s" for item in first["items"] + second["items"])
    assert await store.list_for_user("u", cursor=second["cursor"]) == {
        "items": [],
        "cursor": second["cursor"],
        "next_cursor": None,
    }


@pytest.mark.parametrize(
    "goal_status,expected",
    [
        ("active", None),
        ("paused", None),
        ("cleared", None),
        ("completed", "completed"),
        ("blocked", "failed"),
        ("budget_limited", "failed"),
    ],
)
async def test_goal_round_notifications_follow_goal_terminal_state(
    monkeypatch, goal_status, expected
):
    from src.infra.task import completion_events

    store = completion_events.TaskCompletionStore(Collection())
    monkeypatch.setattr(completion_events, "TaskCompletionStore", lambda: store)
    metadata = {
        "persistent_goal_id": "g",
        "persistent_goal_version": 3,
        "persistent_goal_status": goal_status,
        "persistent_goal_run_id": "r",
    }
    session = SimpleNamespace(metadata=metadata, user_id="u", unread_count=1)
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_type=AsyncMock(return_value=None)),
    )
    send = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=send),
    )
    await TaskExecutor(None, {}, None)._send_task_notification("s", "r", TaskStatus.COMPLETED, "u")
    page = await store.list_for_user("u")
    if expected is None:
        assert not page["items"]
        send.assert_not_awaited()
    else:
        assert page["items"][0]["status"] == expected
        assert page["items"][0]["notification_kind"] == "goal_terminal"
        assert page["items"][0]["goal_status"] == goal_status
        assert send.call_args.args[1]["data"]["id"] == page["items"][0]["id"]


@pytest.mark.parametrize(
    "status,kind",
    [
        (TaskStatus.COMPLETED, "background_task_complete"),
        (TaskStatus.WAITING_HUMAN, "waiting_human"),
    ],
)
async def test_background_and_attention_are_durable_before_live_delivery(monkeypatch, status, kind):
    from src.infra.task import completion_events

    store = completion_events.TaskCompletionStore(Collection())
    monkeypatch.setattr(completion_events, "TaskCompletionStore", lambda: store)
    metadata = {"background_parent_session_id": "parent"}
    session = SimpleNamespace(metadata=metadata, user_id="u", unread_count=1)
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_type=AsyncMock(return_value=None)),
    )

    async def offline(user, event):
        assert len((await store.list_for_user(user))["items"]) == 1
        raise ConnectionError("offline")

    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=offline),
    )
    await TaskExecutor(None, {}, None)._send_task_notification("child", "r", status, "u")
    item = (await store.list_for_user("u"))["items"][0]
    assert item["notification_kind"] == kind
    assert item["parent_session_id"] == "parent"


async def test_completion_route_uses_authenticated_user_and_validates_cursor(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.deps import get_current_user_required
    from src.api.error_handlers import register_error_handlers
    from src.api.routes import task_completions

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(task_completions.router, prefix="/api")
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(sub="u")
    from src.infra.task.completion_events import TaskCompletionStore

    store = TaskCompletionStore(Collection())
    await store.record(
        "u",
        {
            "session_id": "own",
            "run_id": "r",
            "status": "completed",
            "notification_kind": "run_complete",
            "dedupe_key": "task:r:completed",
        },
    )
    await store.record(
        "other",
        {
            "session_id": "foreign",
            "run_id": "r",
            "status": "completed",
            "notification_kind": "run_complete",
            "dedupe_key": "task:r:completed",
        },
    )
    monkeypatch.setattr(task_completions, "TaskCompletionStore", lambda: store)
    with TestClient(app) as client:
        assert (
            client.get("/api/task-completions?user_id=other").json()["items"][0]["session_id"]
            == "own"
        )
        response = client.get("/api/task-completions?cursor=invalid&user_id=other")
    assert response.status_code == 422


async def test_publish_goal_persists_terminal_scope_and_notifies_without_running_executor(
    monkeypatch,
):
    from src.infra.goal_continuation import publish_goal
    from src.kernel.schemas.persistent_goal import GoalRunAccounting, PersistentGoal

    goal = PersistentGoal(
        id="g",
        session_id="s",
        user_id="u",
        objective="done",
        rubric="tests",
        status="budget_limited",
        version=4,
        run_accounting=[GoalRunAccounting(run_id="r", version=3)],
    )
    update = AsyncMock(return_value=True)
    send = AsyncMock()
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(update_session_metadata=update),
    )
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(write_event=AsyncMock()),
    )
    monkeypatch.setattr(
        "src.infra.task.manager.get_task_manager",
        lambda: SimpleNamespace(
            _ensure_executor=lambda: SimpleNamespace(_send_task_notification=send)
        ),
    )
    await publish_goal(goal)
    metadata = update.call_args.args[1]
    assert metadata["persistent_goal_status"] == "budget_limited"
    assert metadata["persistent_goal_version"] == 4
    assert metadata["persistent_goal_revision"] == goal.revision
    assert metadata["persistent_goal_run_id"] == "r"
    send.assert_awaited_once()


async def test_delayed_insert_is_visible_after_already_saved_cursor(monkeypatch):
    import asyncio

    from src.infra.task import completion_events

    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedCollection(Collection):
        async def find_one_and_update(self, query, update, **options):
            if update["$setOnInsert"]["data"]["run_id"] == "late":
                entered.set()
                await release.wait()
            return await super().find_one_and_update(query, update, **options)

    collection = DelayedCollection()
    store = completion_events.TaskCompletionStore(collection)
    early_clock = utc_now() - timedelta(minutes=5)
    monkeypatch.setattr(completion_events, "utc_now", lambda: early_clock)

    def event(run):
        return {
            "session_id": "s",
            "run_id": run,
            "status": "completed",
            "notification_kind": "run_complete",
            "dedupe_key": f"task:{run}:completed",
        }

    delayed = asyncio.create_task(store.record("u", event("late")))
    try:
        await entered.wait()
        monkeypatch.setattr(completion_events, "utc_now", utc_now)
        await store.record("u", event("first"))
        page = await store.list_for_user("u")
        assert [item["run_id"] for item in page["items"]] == ["first"]
        release.set()
        await delayed
        catchup = await store.list_for_user("u", cursor=page["cursor"])
        assert [item["run_id"] for item in catchup["items"]] == ["late"]
        assert collection.docs[0]["commit_order"] < collection.docs[1]["commit_order"]
    finally:
        release.set()
        await asyncio.gather(delayed, return_exceptions=True)


async def test_duplicate_journal_write_preserves_server_order_and_delivery_authority():
    from src.infra.task.completion_events import TaskCompletionStore

    collection = Collection()
    store = TaskCompletionStore(collection)
    data = {
        "session_id": "s",
        "run_id": "r",
        "status": "completed",
        "notification_kind": "run_complete",
        "dedupe_key": "task:r:completed",
    }
    first, fresh = await store.record_once("u", data)
    assert fresh
    original_order = collection.docs[0]["commit_order"]
    repeated, fresh = await store.record_once("u", data)
    assert not fresh
    assert first == repeated
    assert collection.docs[0]["commit_order"] == original_order


async def test_goal_publish_and_executor_replay_send_only_one_offline_push(monkeypatch):
    from src.infra.task import completion_events

    store = completion_events.TaskCompletionStore(Collection())
    monkeypatch.setattr(completion_events, "TaskCompletionStore", lambda: store)
    metadata = {
        "persistent_goal_id": "g",
        "persistent_goal_version": 3,
        "persistent_goal_status": "completed",
        "persistent_goal_run_id": "r",
    }
    session = SimpleNamespace(metadata=metadata, user_id="u", unread_count=1)
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_type=AsyncMock(return_value=None)),
    )
    send = AsyncMock(return_value=0)
    push = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=send),
    )
    monkeypatch.setattr(
        "src.infra.push.manager.PushManager", lambda: SimpleNamespace(send_push_to_user=push)
    )
    executor = TaskExecutor(None, {}, None)
    await executor._send_task_notification("s", "r", TaskStatus.COMPLETED, "u")
    await executor._send_task_notification("s", "r", TaskStatus.COMPLETED, "u")
    push.assert_awaited_once()
    assert len((await store.list_for_user("u"))["items"]) == 1
