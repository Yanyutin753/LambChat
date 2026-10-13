"""Executor admission resolves API-created ObjectId sessions without shadow records."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from src.infra.task.executor import TaskExecutor
from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage


async def test_executor_uses_existing_object_id_session_and_updates_its_metadata(monkeypatch):
    collection = SessionCollection(object_id=True)
    storage = actual_storage(monkeypatch, collection)
    create = AsyncMock()
    monkeypatch.setattr(storage, "create", create)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    await executor.ensure_session(
        collection.session_id, "fast", "u", session_metadata={"model_id": "selected"}
    )
    create.assert_not_awaited()
    assert collection.doc["metadata"]["model_id"] == "selected"
    assert (await storage.get_by_session_id(collection.session_id)).id == collection.session_id


async def test_executor_cannot_shadow_another_users_object_id_session(monkeypatch):
    collection = SessionCollection(object_id=True)
    storage = actual_storage(monkeypatch, collection)
    create = AsyncMock()
    monkeypatch.setattr(storage, "create", create)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    before = deepcopy(collection.doc)
    with pytest.raises(PermissionError):
        await executor.ensure_session(
            collection.session_id, "fast", "foreign", session_metadata={"model_id": "selected"}
        )
    create.assert_not_awaited()
    assert collection.doc == before


async def test_custom_id_match_keeps_priority_over_object_id_collision(monkeypatch):
    collection = SessionCollection(object_id=True)
    original = deepcopy(collection.doc)
    custom = {
        "_id": ObjectId(),
        "session_id": str(original["_id"]),
        "user_id": "custom-owner",
        "metadata": {},
    }

    async def find_one(query, *_args, **_kwargs):
        if query == {"session_id": custom["session_id"]}:
            return deepcopy(custom)
        if query == {"_id": original["_id"]}:
            return deepcopy(original)
        return None

    collection.find_one = find_one
    storage = actual_storage(monkeypatch, collection)
    session = await storage.get_by_session_id(custom["session_id"])
    assert session.user_id == "custom-owner"
    assert session.id == custom["session_id"]


async def test_status_reader_resolves_object_id_session_without_process_cache(monkeypatch):
    from src.infra.task.status import TaskStatus
    from src.infra.task.status_queries import TaskStatusQueries

    collection = SessionCollection(object_id=True)
    collection.doc["metadata"]["task_status"] = "running"
    storage = actual_storage(monkeypatch, collection)
    queries = TaskStatusQueries(storage=storage, run_info={})
    assert await queries.get_status(collection.session_id) == TaskStatus.RUNNING
