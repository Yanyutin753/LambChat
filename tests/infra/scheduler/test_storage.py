from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.scheduler import storage as storage_module
from src.infra.scheduler.storage import ScheduledTaskStorage
from src.kernel.schemas.scheduled_task import ScheduledTask, ScheduledTaskStatus, TriggerType


def _task_doc(task_id: str) -> dict[str, Any]:
    now = datetime(2026, 4, 25, tzinfo=timezone.utc)
    return {
        "_id": task_id,
        "name": f"Task {task_id}",
        "description": None,
        "agent_id": "agent_1",
        "trigger_type": TriggerType.INTERVAL,
        "trigger_config": {"seconds": 300},
        "input_payload": {"message": "hello"},
        "status": ScheduledTaskStatus.ACTIVE,
        "enabled": True,
        "run_on_start": False,
        "max_retries": 0,
        "timeout_seconds": 600,
        "owner_id": "user_1",
        "source_session_id": None,
        "source_run_id": None,
        "created_by": "user",
        "created_at": now,
        "updated_at": now,
    }


def _task(task_id: str = "task_1", name: str = "Task task_1") -> ScheduledTask:
    return ScheduledTask.model_validate(_task_doc(task_id) | {"name": name})


class _ConcurrentCursor:
    def __init__(self, docs: list[dict[str, Any]], count_started: asyncio.Event) -> None:
        self._docs = docs
        self._count_started = count_started
        self.skip_value: int | None = None
        self.limit_value: int | None = None

    def sort(self, *_args):
        return self

    def skip(self, value: int):
        self.skip_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        self._iter = iter(self._docs[: self.limit_value or None])
        return self

    async def __anext__(self):
        await asyncio.wait_for(self._count_started.wait(), timeout=1)
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _ConcurrentCollection:
    def __init__(self) -> None:
        self.count_started = asyncio.Event()
        self.find_started = asyncio.Event()
        self.cursor: _ConcurrentCursor | None = None

    async def count_documents(self, _query: dict[str, Any]) -> int:
        self.count_started.set()
        await asyncio.wait_for(self.find_started.wait(), timeout=1)
        return 1

    def find(self, _query: dict[str, Any]):
        self.find_started.set()
        self.cursor = _ConcurrentCursor([_task_doc("task_1")], self.count_started)
        return self.cursor


class _FailingMarkerTaskCollection:
    def find(self, *_args, **_kwargs):
        raise AssertionError("marker lookup should not scan scheduled_tasks")


class _MarkerMetadataCollection:
    def __init__(self) -> None:
        self.find_one_query: dict[str, Any] | None = None

    async def find_one(self, query: dict[str, Any]):
        self.find_one_query = query
        return {"_id": "scheduler_definition_revision", "revision": 7}


class _UpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


class _RevisionTaskCollection:
    def __init__(self) -> None:
        self.update_one_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        self.update_one_calls.append((query, update))
        return _UpdateResult(modified_count=1)


class _RevisionMetadataCollection:
    def __init__(self) -> None:
        self.update_one_calls: list[tuple[dict[str, Any], dict[str, Any], bool | None]] = []

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool | None = None,
    ):
        self.update_one_calls.append((query, update, upsert))
        return _UpdateResult(modified_count=1)


class _ExecutionProjectionCollection:
    def __init__(self) -> None:
        self.find_one_query: dict[str, Any] | None = None
        self.find_one_projection: dict[str, int] | None = None

    async def find_one(
        self,
        query: dict[str, Any],
        projection: dict[str, int] | None = None,
    ):
        self.find_one_query = query
        self.find_one_projection = projection
        return _task_doc("task_1")


class _DuplicateThenInsertCollection:
    def __init__(self, *, deleted_count: int = 1) -> None:
        self.deleted_count = deleted_count
        self.inserted_docs: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.insert_attempts = 0

    async def insert_one(self, doc: dict[str, Any]) -> None:
        self.insert_attempts += 1
        if self.insert_attempts == 1:
            raise DuplicateKeyError("duplicate task name")
        self.inserted_docs.append(doc)

    async def delete_one(self, query: dict[str, Any]):
        self.delete_calls.append(query)
        return SimpleNamespace(deleted_count=self.deleted_count)


class _HardDeleteTaskCollection:
    def __init__(self, *, deleted_count: int) -> None:
        self.deleted_count = deleted_count
        self.delete_calls: list[dict[str, Any]] = []

    async def delete_one(self, query: dict[str, Any]):
        self.delete_calls.append(query)
        return SimpleNamespace(deleted_count=self.deleted_count)


class _AttachmentTransitionCollection:
    def __init__(self, result: dict[str, Any] | None) -> None:
        self.result = result
        self.find_one_and_update_calls: list[tuple[dict, object, dict]] = []

    async def find_one_and_update(self, query: dict, update: object, **kwargs):
        self.find_one_and_update_calls.append((query, update, kwargs))
        return self.result


class _SimpleCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def __aiter__(self):
        self._iterator = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _AttachmentReconciliationCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.find_queries: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]) -> _SimpleCursor:
        self.find_queries.append(query)
        return _SimpleCursor(self.docs)


@pytest.mark.asyncio
async def test_list_tasks_paginated_fetches_rows_and_count_concurrently() -> None:
    storage = ScheduledTaskStorage()
    collection = _ConcurrentCollection()
    storage._collections["scheduled_tasks"] = collection

    tasks, total = await storage.list_tasks_paginated(owner_id="user_1")

    assert total == 1
    assert [task.id for task in tasks] == ["task_1"]


@pytest.mark.asyncio
async def test_get_active_tasks_marker_reads_single_revision_document() -> None:
    storage = ScheduledTaskStorage()
    task_collection = _FailingMarkerTaskCollection()
    metadata_collection = _MarkerMetadataCollection()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    marker = await storage.get_active_tasks_marker()

    assert marker == 7
    assert metadata_collection.find_one_query == {"_id": "scheduler_definition_revision"}


@pytest.mark.asyncio
async def test_update_task_bumps_scheduler_definition_revision() -> None:
    storage = ScheduledTaskStorage()
    task_collection = _RevisionTaskCollection()
    metadata_collection = _RevisionMetadataCollection()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    updated = await storage.update_task("task_1", {"name": "new name"})

    assert updated is True
    assert metadata_collection.update_one_calls
    query, update, upsert = metadata_collection.update_one_calls[-1]
    assert query == {"_id": "scheduler_definition_revision"}
    assert update["$inc"] == {"revision": 1}
    assert upsert is True


@pytest.mark.asyncio
async def test_get_task_for_execution_uses_projection() -> None:
    storage = ScheduledTaskStorage()
    collection = _ExecutionProjectionCollection()
    storage._collections["scheduled_tasks"] = collection

    task = await storage.get_task_for_execution("task_1")

    assert task is not None
    assert task.id == "task_1"
    assert collection.find_one_query == {"_id": "task_1"}
    assert collection.find_one_projection is not None
    assert collection.find_one_projection["input_payload"] == 1
    assert collection.find_one_projection["timeout_seconds"] == 1
    assert "description" not in collection.find_one_projection
    assert "updated_at" not in collection.find_one_projection


@pytest.mark.asyncio
async def test_create_task_deletes_historical_deleted_same_name_collision_and_retries() -> None:
    storage = ScheduledTaskStorage()
    collection = _DuplicateThenInsertCollection()
    metadata_collection = _RevisionMetadataCollection()
    storage._collections["scheduled_tasks"] = collection
    storage._collections["scheduled_task_metadata"] = metadata_collection
    task = _task(task_id="new-task", name="Daily Report")

    created = await storage.create_task(task)

    assert created == task
    assert collection.insert_attempts == 2
    assert collection.inserted_docs == [task.model_dump(by_alias=True)]
    assert collection.delete_calls == [
        {
            "owner_id": "user_1",
            "name": "Daily Report",
            "status": ScheduledTaskStatus.DELETED,
        }
    ]
    assert metadata_collection.update_one_calls  # revision bumped after successful create


@pytest.mark.asyncio
async def test_create_task_reraises_duplicate_when_no_deleted_collision_found() -> None:
    storage = ScheduledTaskStorage()
    collection = _DuplicateThenInsertCollection(deleted_count=0)
    storage._collections["scheduled_tasks"] = collection

    with pytest.raises(DuplicateKeyError):
        await storage.create_task(_task(name="Active Task"))

    assert collection.insert_attempts == 1
    assert collection.inserted_docs == []
    assert collection.delete_calls == [
        {
            "owner_id": "user_1",
            "name": "Active Task",
            "status": ScheduledTaskStatus.DELETED,
        }
    ]


@pytest.mark.asyncio
async def test_delete_task_physically_deletes_and_bumps_revision() -> None:
    storage = ScheduledTaskStorage()
    task_collection = _HardDeleteTaskCollection(deleted_count=1)
    metadata_collection = _RevisionMetadataCollection()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    deleted = await storage.delete_task("task_1")

    assert deleted is True
    assert task_collection.delete_calls == [{"_id": "task_1"}]
    assert metadata_collection.update_one_calls  # revision bumped


@pytest.mark.asyncio
async def test_delete_task_returns_false_when_document_missing() -> None:
    storage = ScheduledTaskStorage()
    task_collection = _HardDeleteTaskCollection(deleted_count=0)
    metadata_collection = _RevisionMetadataCollection()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    deleted = await storage.delete_task("missing")

    assert deleted is False
    assert not metadata_collection.update_one_calls  # not bumped when nothing changed


def test_scheduled_task_schema_defaults_durable_attachment_state() -> None:
    task = _task()

    assert task.attachment_keys == []
    assert task.pending_attachment_claim_keys == []
    assert task.pending_attachment_release_keys == []
    assert task.attachment_setup_pending is False


@pytest.mark.asyncio
async def test_stage_attachment_claim_persists_keys_before_file_mutation() -> None:
    result_doc = _task_doc("task_1") | {
        "pending_attachment_claim_keys": ["key-a", "key-b"],
    }
    task_collection = _AttachmentTransitionCollection(result_doc)
    metadata_collection = _RevisionMetadataCollection()
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    staged = await storage.stage_attachment_claim(
        "task_1",
        ["key-a", "key-b"],
    )

    assert staged is not None
    assert staged.pending_attachment_claim_keys == ["key-a", "key-b"]
    query, update, kwargs = task_collection.find_one_and_update_calls[0]
    assert query == {"_id": "task_1", "status": {"$ne": ScheduledTaskStatus.DELETED}}
    assert update["$set"]["pending_attachment_claim_keys"] == ["key-a", "key-b"]
    assert kwargs["return_document"] is ReturnDocument.AFTER
    assert metadata_collection.update_one_calls


@pytest.mark.asyncio
async def test_commit_attachment_update_moves_removed_keys_to_pending_release() -> None:
    result_doc = _task_doc("task_1") | {
        "input_payload": {"message": "new", "attachments": [{"key": "key-b"}]},
        "attachment_keys": ["key-b"],
        "pending_attachment_claim_keys": [],
        "pending_attachment_release_keys": ["key-a"],
    }
    task_collection = _AttachmentTransitionCollection(result_doc)
    metadata_collection = _RevisionMetadataCollection()
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    committed = await storage.commit_attachment_update(
        "task_1",
        {"input_payload": result_doc["input_payload"]},
        ["key-b"],
    )

    assert committed is not None
    assert committed.attachment_keys == ["key-b"]
    assert committed.pending_attachment_release_keys == ["key-a"]
    query, update, kwargs = task_collection.find_one_and_update_calls[0]
    assert query == {"_id": "task_1", "status": {"$ne": ScheduledTaskStatus.DELETED}}
    state = update[0]["$set"]
    assert state["input_payload"] == result_doc["input_payload"]
    assert state["attachment_keys"] == ["key-b"]
    assert state["pending_attachment_claim_keys"] == []
    assert state["pending_attachment_release_keys"] == {
        "$setDifference": [
            {
                "$setUnion": [
                    {"$ifNull": ["$pending_attachment_release_keys", []]},
                    {"$ifNull": ["$attachment_keys", []]},
                ]
            },
            ["key-b"],
        ]
    }
    assert kwargs["return_document"] is ReturnDocument.AFTER


@pytest.mark.asyncio
async def test_mark_task_attachment_deletion_retains_possible_tokens_until_release() -> None:
    result_doc = _task_doc("task_1") | {
        "status": ScheduledTaskStatus.DELETED,
        "enabled": False,
        "attachment_keys": [],
        "pending_attachment_claim_keys": [],
        "pending_attachment_release_keys": ["key-a", "key-b"],
    }
    task_collection = _AttachmentTransitionCollection(result_doc)
    metadata_collection = _RevisionMetadataCollection()
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    deleted = await storage.mark_task_attachment_deletion("task_1")

    assert deleted is not None
    assert deleted.status == ScheduledTaskStatus.DELETED
    assert deleted.pending_attachment_release_keys == ["key-a", "key-b"]
    query, update, _kwargs = task_collection.find_one_and_update_calls[0]
    assert query == {"_id": "task_1"}
    state = update[0]["$set"]
    assert state["status"] == ScheduledTaskStatus.DELETED
    assert state["enabled"] is False
    assert state["attachment_keys"] == []
    assert state["pending_attachment_claim_keys"] == []
    assert state["pending_attachment_release_keys"] == {
        "$setUnion": [
            {"$ifNull": ["$pending_attachment_release_keys", []]},
            {"$ifNull": ["$attachment_keys", []]},
            {"$ifNull": ["$pending_attachment_claim_keys", []]},
        ]
    }


@pytest.mark.asyncio
async def test_clear_pending_attachment_work_removes_only_completed_keys() -> None:
    task_collection = _RevisionTaskCollection()
    metadata_collection = _RevisionMetadataCollection()
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    claims_cleared = await storage.clear_pending_attachment_claims(
        "task_1", ["key-a"]
    )
    releases_cleared = await storage.clear_pending_attachment_releases(
        "task_1", ["key-b"]
    )

    assert claims_cleared is True
    assert releases_cleared is True
    assert task_collection.update_one_calls == [
        (
            {"_id": "task_1"},
            {
                "$pullAll": {"pending_attachment_claim_keys": ["key-a"]},
                "$set": {"updated_at": ANY},
            },
        ),
        (
            {"_id": "task_1"},
            {
                "$pullAll": {"pending_attachment_release_keys": ["key-b"]},
                "$set": {"updated_at": ANY},
            },
        ),
    ]


@pytest.mark.asyncio
async def test_finalize_deleted_task_requires_all_attachment_work_complete() -> None:
    task_collection = _HardDeleteTaskCollection(deleted_count=1)
    metadata_collection = _RevisionMetadataCollection()
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection
    storage._collections["scheduled_task_metadata"] = metadata_collection

    finalized = await storage.finalize_deleted_task("task_1")

    assert finalized is True
    assert task_collection.delete_calls == [
        {
            "_id": "task_1",
            "status": ScheduledTaskStatus.DELETED,
            "attachment_setup_pending": False,
            "attachment_keys.0": {"$exists": False},
            "pending_attachment_claim_keys.0": {"$exists": False},
            "pending_attachment_release_keys.0": {"$exists": False},
        }
    ]
    assert metadata_collection.update_one_calls


@pytest.mark.asyncio
async def test_list_attachment_reconciliation_tasks_includes_paused_legacy_payloads() -> None:
    task_doc = _task_doc("task_1") | {
        "status": ScheduledTaskStatus.PAUSED,
        "enabled": False,
        "input_payload": {"attachments": [{"key": "key-a"}]},
    }
    task_collection = _AttachmentReconciliationCollection([task_doc])
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = task_collection

    tasks = await storage.list_attachment_reconciliation_tasks()

    assert [task.id for task in tasks] == ["task_1"]
    assert task_collection.find_queries == [
        {
            "$or": [
                {"attachment_setup_pending": True},
                {"pending_attachment_claim_keys.0": {"$exists": True}},
                {"pending_attachment_release_keys.0": {"$exists": True}},
                {
                    "status": {"$ne": ScheduledTaskStatus.DELETED},
                    "input_payload.attachments.0": {"$exists": True},
                },
            ]
        }
    ]


def test_close_scheduled_task_storage_releases_singleton() -> None:
    storage = storage_module.get_scheduled_task_storage()

    storage_module.close_scheduled_task_storage()

    assert storage_module._storage is None
    assert storage_module.get_scheduled_task_storage() is not storage
    storage_module.close_scheduled_task_storage()


def test_close_scheduled_task_storage_does_not_create_singleton_when_unused() -> None:
    storage_module._storage = None

    storage_module.close_scheduled_task_storage()

    assert storage_module._storage is None
