from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
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


class _StatsTasks:
    def __init__(self):
        self.document = {"total_runs": 0}

    async def update_one(self, query, update):
        def value(expression):
            if isinstance(expression, list):
                return [value(item) for item in expression]
            if isinstance(expression, str) and expression.startswith("$"):
                return self.document.get(expression[1:])
            if not isinstance(expression, dict):
                return expression
            operator, args = next(iter(expression.items()))
            if operator == "$ifNull":
                first = value(args[0])
                return first if first is not None else value(args[1])
            if operator == "$max":
                return max(value(item) for item in args)
            if operator == "$gte":
                return value(args[0]) >= value(args[1])
            if operator == "$cond":
                return value(args[1] if value(args[0]) else args[2])
            raise AssertionError(operator)

        if isinstance(update, list):
            for stage in update:
                self.document.update({key: value(item) for key, item in stage["$set"].items()})
        else:
            self.document.update(update.get("$set", {}))
            for key, amount in update.get("$inc", {}).items():
                self.document[key] = self.document.get(key, 0) + amount
        return _UpdateResult(1)


@pytest.mark.asyncio
async def test_replaying_finalization_does_not_count_a_run_twice():
    from unittest.mock import AsyncMock

    from src.kernel.schemas.scheduled_task import RunStatus

    finished = datetime(2026, 10, 17, tzinfo=timezone.utc)
    summary = {
        "total_runs": 1,
        "last_run_at": finished,
        "last_run_id": "run",
        "last_run_status": "success",
    }
    tasks = _StatsTasks()
    runs = SimpleNamespace(
        aggregate=AsyncMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[summary])))
    )
    storage = ScheduledTaskStorage()
    storage._collections.update(scheduled_tasks=tasks, task_run_records=runs)
    await storage.update_task_run_stats("task", "run", RunStatus.SUCCESS)
    await storage.update_task_run_stats("task", "run", RunStatus.SUCCESS)
    assert tasks.document["total_runs"] == 1
    assert tasks.document["last_run_id"] == "run"


@pytest.mark.asyncio
async def test_late_stats_writer_does_not_overwrite_a_newer_run():
    from unittest.mock import AsyncMock

    from src.kernel.schemas.scheduled_task import RunStatus

    older = datetime(2026, 10, 16, tzinfo=timezone.utc)
    newer = datetime(2026, 10, 17, tzinfo=timezone.utc)
    summaries = [
        [
            {
                "total_runs": 2,
                "last_run_at": newer,
                "last_run_id": "new",
                "last_run_status": "success",
            }
        ],
        [
            {
                "total_runs": 1,
                "last_run_at": older,
                "last_run_id": "old",
                "last_run_status": "failed",
            }
        ],
    ]
    tasks = _StatsTasks()
    runs = SimpleNamespace(
        aggregate=AsyncMock(return_value=SimpleNamespace(to_list=AsyncMock(side_effect=summaries)))
    )
    storage = ScheduledTaskStorage()
    storage._collections.update(scheduled_tasks=tasks, task_run_records=runs)
    await storage.update_task_run_stats("task", "new", RunStatus.SUCCESS)
    await storage.update_task_run_stats("task", "old", RunStatus.FAILED)
    assert tasks.document["total_runs"] == 2
    assert tasks.document["last_run_id"] == "new"
    assert tasks.document["last_run_at"] == newer
    assert tasks.document["last_run_status"] == "success"


@pytest.mark.asyncio
async def test_stats_last_run_has_a_stable_order_when_completion_times_match():
    from unittest.mock import AsyncMock

    from src.kernel.schemas.scheduled_task import RunStatus

    finished = datetime(2026, 10, 17, tzinfo=timezone.utc)
    summaries = [
        [
            {
                "total_runs": 2,
                "last_run_at": finished,
                "last_run_id": "run-b",
                "last_run_status": "success",
            }
        ],
        [
            {
                "total_runs": 1,
                "last_run_at": finished,
                "last_run_id": "run-a",
                "last_run_status": "failed",
            }
        ],
    ]
    tasks = _StatsTasks()
    runs = SimpleNamespace(
        aggregate=AsyncMock(return_value=SimpleNamespace(to_list=AsyncMock(side_effect=summaries)))
    )
    storage = ScheduledTaskStorage()
    storage._collections.update(scheduled_tasks=tasks, task_run_records=runs)
    await storage.update_task_run_stats("task", "run-b", RunStatus.SUCCESS)
    await storage.update_task_run_stats("task", "run-a", RunStatus.FAILED)
    assert tasks.document["last_run_id"] == "run-b"
    assert tasks.document["last_run_status"] == "success"


@pytest.mark.asyncio
async def test_pending_scan_retries_finished_runs_with_incomplete_finalization():
    from unittest.mock import AsyncMock, MagicMock

    storage = ScheduledTaskStorage()
    collection = MagicMock()
    collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[]
    )
    storage._collections["task_run_records"] = collection
    await storage.pending_conversation_runs()
    query = collection.find.call_args.args[0]
    assert {"conversation_state": "finished", "finalization_pending": True} in query["$or"]


@pytest.mark.asyncio
async def test_pending_scan_cursor_does_not_drop_finalization_retry_filter():
    from unittest.mock import AsyncMock, MagicMock

    storage = ScheduledTaskStorage()
    storage._conversation_scan_after = (datetime(2026, 10, 17, tzinfo=timezone.utc), "run")
    collection = MagicMock()
    collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[]
    )
    storage._collections["task_run_records"] = collection
    await storage.pending_conversation_runs()
    query = collection.find.call_args.args[0]
    assert {"conversation_state": "finished", "finalization_pending": True} in query["$and"][0][
        "$or"
    ]
    assert query["$and"][1]["$or"][1]["_id"] == {"$gt": "run"}


@pytest.mark.asyncio
async def test_standalone_finalization_scan_never_returns_conversation_runs():
    from unittest.mock import AsyncMock, MagicMock

    storage = ScheduledTaskStorage()
    collection = MagicMock()
    collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[]
    )
    storage._collections["task_run_records"] = collection
    await storage.pending_standalone_finalizations()
    query = collection.find.call_args.args[0]
    assert query["conversation_state"] == {"$exists": False}
    assert query["finalization_pending"] is True


@pytest.mark.asyncio
async def test_date_completion_does_not_pause_a_changed_schedule() -> None:
    from unittest.mock import AsyncMock

    original = {"run_date": "2099-01-01T00:00:00+00:00"}
    current = {
        "_id": "task_1",
        "trigger_type": "interval",
        "trigger_config": {"seconds": 60},
        "timezone": "UTC",
        "status": "active",
        "enabled": True,
    }

    class Tasks:
        async def update_one(self, query, update):
            if not all(current.get(key) == value for key, value in query.items()):
                return _UpdateResult(0)
            current.update(update["$set"])
            return _UpdateResult(1)

    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = Tasks()
    storage._bump_scheduler_definition_revision = AsyncMock()
    assert await storage.pause_completed_date_task("task_1", original, "UTC") is False
    assert current["enabled"] is True
    storage._bump_scheduler_definition_revision.assert_not_awaited()


@pytest.mark.asyncio
async def test_date_completion_pauses_only_its_own_trigger() -> None:
    from unittest.mock import AsyncMock

    collection = SimpleNamespace(update_one=AsyncMock(return_value=_UpdateResult(1)))
    storage = ScheduledTaskStorage()
    storage._collections["scheduled_tasks"] = collection
    storage._bump_scheduler_definition_revision = AsyncMock()
    config = {"run_date": "2099-01-01T00:00:00+00:00"}
    assert await storage.pause_completed_date_task("task_1", config, "UTC") is True
    assert collection.update_one.call_args.args[0] == {
        "_id": "task_1",
        "trigger_type": "date",
        "trigger_config": config,
        "timezone": "UTC",
        "status": "active",
        "enabled": True,
    }
    storage._bump_scheduler_definition_revision.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_task_search_uses_literal_text_for_rows_and_total() -> None:
    from unittest.mock import AsyncMock, MagicMock

    storage = ScheduledTaskStorage()
    collection = MagicMock()
    cursor = collection.find.return_value.sort.return_value.skip.return_value.limit.return_value
    cursor.__aiter__.return_value = []
    collection.count_documents = AsyncMock(return_value=0)
    storage._collections["scheduled_tasks"] = collection

    await storage.list_tasks_paginated(
        owner_id="user_1", status=ScheduledTaskStatus.PAUSED, search="  Daily.*  "
    )

    query = collection.find.call_args.args[0]
    assert query == {
        "owner_id": "user_1",
        "status": ScheduledTaskStatus.PAUSED,
        "$or": [
            {"name": {"$regex": r"Daily\.\*", "$options": "i"}},
            {"description": {"$regex": r"Daily\.\*", "$options": "i"}},
        ],
    }
    collection.count_documents.assert_awaited_once_with(query)
