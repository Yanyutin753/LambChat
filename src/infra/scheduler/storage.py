"""MongoDB storage for scheduled tasks and run records."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.scheduled_task import (
    RunStatus,
    ScheduledTask,
    ScheduledTaskStatus,
    TaskRunRecord,
)

logger = get_logger(__name__)

_COLL_TASKS = "scheduled_tasks"
_COLL_RUNS = "task_run_records"
_COLL_METADATA = "scheduled_task_metadata"
_SCHEDULER_DEFINITION_REVISION_ID = "scheduler_definition_revision"

_TASK_EXECUTION_PROJECTION = {
    "_id": 1,
    "name": 1,
    "execution_mode": 1,
    "target_session_id": 1,
    "notification_policy": 1,
    "agent_id": 1,
    "trigger_type": 1,
    "trigger_config": 1,
    "timezone": 1,
    "input_payload": 1,
    "status": 1,
    "enabled": 1,
    "run_on_start": 1,
    "max_retries": 1,
    "timeout_seconds": 1,
    "owner_id": 1,
    "delivery": 1,
    "last_run_at": 1,
    "total_runs": 1,
    "created_at": 1,
}


class ScheduledTaskStorage:
    """MongoDB CRUD for scheduled task definitions and run records."""

    def __init__(self) -> None:
        self._collections: dict[str, Any] = {}
        self._conversation_scan_after: tuple[datetime, str] | None = None
        self._standalone_scan_after: tuple[datetime, str] | None = None

    def _get_collection(self, name: str):
        """Lazy-load a MongoDB collection."""
        if name not in self._collections:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collections[name] = db[name]
        return self._collections[name]

    async def ensure_indexes(self) -> None:
        """Create indexes for scheduled task and run record collections."""
        c_tasks = self._get_collection(_COLL_TASKS)
        await c_tasks.create_index("owner_id")
        await c_tasks.create_index("status")
        await c_tasks.create_index([("status", 1), ("enabled", 1)])
        await c_tasks.create_index(
            [
                ("owner_id", 1),
                ("source_session_id", 1),
                ("status", 1),
                ("created_at", -1),
            ],
            name="owner_source_session_status_created_idx",
        )

        c_runs = self._get_collection(_COLL_RUNS)
        await c_runs.create_index(
            [("task_id", 1)],
            unique=True,
            partialFilterExpression={"conversation_pending": True},
            name="one_pending_conversation_wakeup",
        )
        await c_runs.create_index([("conversation_state", 1), ("created_at", 1)])
        await c_runs.create_index([("finalization_pending", 1), ("created_at", 1)])
        await c_runs.create_index("task_id")
        await c_runs.create_index([("task_id", 1), ("created_at", -1)])
        await c_runs.create_index([("task_id", 1), ("finished_at", -1), ("_id", -1)])
        await c_runs.create_index("session_id")
        await c_runs.create_index("status")
        await c_runs.create_index("started_at")
        logger.info("[ScheduledTaskStorage] indexes created")

    # ── Task CRUD ──────────────────────────────────

    async def create_task(self, task: ScheduledTask) -> ScheduledTask:
        doc = task.model_dump(by_alias=True)
        collection = self._get_collection(_COLL_TASKS)
        try:
            await collection.insert_one(doc)
        except DuplicateKeyError:
            if not await self._delete_deleted_name_collision(task):
                raise
            await collection.insert_one(doc)
        await self._bump_scheduler_definition_revision()
        return task

    async def _delete_deleted_name_collision(self, task: ScheduledTask) -> bool:
        """Remove a historical soft-deleted same-name task so unique indexes stop blocking create."""
        collection = self._get_collection(_COLL_TASKS)
        result = await collection.delete_one(
            {
                "owner_id": task.owner_id,
                "name": task.name,
                "status": ScheduledTaskStatus.DELETED,
            }
        )
        return result.deleted_count > 0

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        doc = await self._get_collection(_COLL_TASKS).find_one({"_id": task_id})
        if not doc:
            return None
        return ScheduledTask(**doc)

    async def get_task_for_execution(self, task_id: str) -> Optional[ScheduledTask]:
        """Read only fields needed to execute a scheduled task."""
        doc = await self._get_collection(_COLL_TASKS).find_one(
            {"_id": task_id},
            _TASK_EXECUTION_PROJECTION,
        )
        if not doc:
            return None
        return ScheduledTask(**doc)

    async def list_tasks(
        self,
        owner_id: Optional[str] = None,
        status: Optional[ScheduledTaskStatus] = None,
    ) -> list[ScheduledTask]:
        query: dict[str, Any] = {}
        if owner_id:
            query["owner_id"] = owner_id
        if status:
            query["status"] = status
        else:
            query["status"] = {"$ne": ScheduledTaskStatus.DELETED}
        cursor = self._get_collection(_COLL_TASKS).find(query).sort("created_at", -1)
        return [ScheduledTask(**doc) async for doc in cursor]

    async def list_tasks_paginated(
        self,
        owner_id: str,
        status: Optional[ScheduledTaskStatus] = None,
        source_session_id: Optional[str] = None,
        created_by: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
    ) -> tuple[list[ScheduledTask], int]:
        """List tasks with pagination, scoped by owner_id."""
        query: dict[str, Any] = {"owner_id": owner_id}
        if status:
            query["status"] = status
        else:
            query["status"] = {"$ne": ScheduledTaskStatus.DELETED}
        if source_session_id:
            query["$and"] = [
                {
                    "$or": [
                        {"source_session_id": source_session_id},
                        {"target_session_id": source_session_id},
                    ]
                }
            ]
        if created_by:
            query["created_by"] = created_by
        if search and search.strip():
            pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
            query["$or"] = [{"name": pattern}, {"description": pattern}]
        collection = self._get_collection(_COLL_TASKS)

        async def _fetch_tasks() -> list[ScheduledTask]:
            cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
            return [ScheduledTask(**doc) async for doc in cursor]

        tasks, total = await asyncio.gather(
            _fetch_tasks(),
            collection.count_documents(query),
        )
        return tasks, total

    async def list_active_tasks(self) -> list[ScheduledTask]:
        """List all active and enabled tasks (used at startup to reload scheduler)."""
        cursor = self._get_collection(_COLL_TASKS).find(
            {"status": ScheduledTaskStatus.ACTIVE, "enabled": True}
        )
        return [ScheduledTask(**doc) async for doc in cursor]

    async def get_active_tasks_marker(self) -> int:
        """Return an O(1) scheduler-definition revision marker."""
        doc = await self._get_collection(_COLL_METADATA).find_one(
            {"_id": _SCHEDULER_DEFINITION_REVISION_ID}
        )
        if not doc:
            return 0
        return int(doc.get("revision") or 0)

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        updates["updated_at"] = utc_now()
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {"$set": updates},
        )
        if result.modified_count > 0:
            await self._bump_scheduler_definition_revision()
        return result.modified_count > 0

    async def pause_completed_date_task(self, task_id, trigger_config, timezone):
        result = await self._get_collection(_COLL_TASKS).update_one(
            {
                "_id": task_id,
                "trigger_type": "date",
                "trigger_config": trigger_config,
                "timezone": timezone,
                "status": "active",
                "enabled": True,
            },
            {"$set": {"status": "paused", "enabled": False, "updated_at": utc_now()}},
        )
        if result.modified_count:
            await self._bump_scheduler_definition_revision()
        return bool(result.modified_count)

    async def delete_task(self, task_id: str) -> bool:
        """Physically remove a task document so its name is freed immediately."""
        result = await self._get_collection(_COLL_TASKS).delete_one({"_id": task_id})
        if result.deleted_count > 0:
            await self._bump_scheduler_definition_revision()
        return result.deleted_count > 0

    async def update_task_run_stats(self, task_id: str, run_id: str, run_status: RunStatus) -> None:
        """Reconcile durable results so retried or competing finalizers cannot double count."""
        summaries = await (
            await self._get_collection(_COLL_RUNS).aggregate(
                [
                    {
                        "$match": {
                            "task_id": task_id,
                            "status": {"$in": ["success", "failed", "skipped", "timeout"]},
                            "finished_at": {"$ne": None},
                        }
                    },
                    {"$sort": {"finished_at": -1, "_id": -1}},
                    {
                        "$group": {
                            "_id": None,
                            "total_runs": {"$sum": 1},
                            "last_run_at": {"$first": "$finished_at"},
                            "last_run_id": {"$first": "$_id"},
                            "last_run_status": {"$first": "$status"},
                        }
                    },
                ]
            )
        ).to_list(length=1)
        if not summaries:
            return
        latest = summaries[0]
        newer = {
            "$gte": [
                [latest["last_run_at"], latest["last_run_id"]],
                [
                    {"$ifNull": ["$last_run_at", datetime(1970, 1, 1, tzinfo=timezone.utc)]},
                    {"$ifNull": ["$last_run_id", ""]},
                ],
            ]
        }
        await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            [
                {
                    "$set": {
                        "total_runs": {
                            "$max": [{"$ifNull": ["$total_runs", 0]}, latest["total_runs"]]
                        },
                        **{
                            key: {"$cond": [newer, latest[key], f"${key}"]}
                            for key in ("last_run_at", "last_run_id", "last_run_status")
                        },
                        "updated_at": utc_now(),
                    }
                }
            ],
        )

    # ── Run Records ────────────────────────────────

    async def create_run(self, record: TaskRunRecord) -> TaskRunRecord:
        doc = record.model_dump(by_alias=True)
        await self._get_collection(_COLL_RUNS).insert_one(doc)
        return record

    async def get_run(self, run_id: str) -> Optional[TaskRunRecord]:
        doc = await self._get_collection(_COLL_RUNS).find_one({"_id": run_id})
        if not doc:
            return None
        return TaskRunRecord(**doc)

    async def update_run(self, run_id: str, updates: dict[str, Any]) -> bool:
        result = await self._get_collection(_COLL_RUNS).update_one(
            {"_id": run_id},
            {"$set": updates},
        )
        return result.modified_count > 0

    async def complete_run_finalization(self, run_id: str) -> None:
        await self._get_collection(_COLL_RUNS).update_one(
            {"_id": run_id, "finalization_pending": True},
            {"$set": {"finalization_pending": False}},
        )

    async def pending_standalone_finalizations(self):
        query: dict[str, Any] = {
            "conversation_state": {"$exists": False},
            "finalization_pending": True,
            "status": {"$in": ["success", "failed", "skipped", "timeout"]},
        }
        if self._standalone_scan_after:
            created_at, run_id = self._standalone_scan_after
            query["$or"] = [
                {"created_at": {"$gt": created_at}},
                {"created_at": created_at, "_id": {"$gt": run_id}},
            ]
        records = (
            await self._get_collection(_COLL_RUNS)
            .find(query)
            .sort([("created_at", 1), ("_id", 1)])
            .limit(100)
            .to_list(length=100)
        )
        self._standalone_scan_after = (
            (records[-1]["created_at"], records[-1]["_id"]) if len(records) == 100 else None
        )
        return records

    async def list_runs(
        self,
        task_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TaskRunRecord], int]:
        query: dict[str, Any] = {"task_id": task_id}
        collection = self._get_collection(_COLL_RUNS)

        async def _fetch_records() -> list[TaskRunRecord]:
            cursor = collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
            return [TaskRunRecord(**doc) async for doc in cursor]

        records, total = await asyncio.gather(
            _fetch_records(),
            collection.count_documents(query),
        )
        return records, total

    async def enqueue_conversation(self, task, trigger_type):
        now = utc_now()
        run_id = f"scheduled-{uuid4()}"
        document = TaskRunRecord(
            id=run_id,
            task_id=task.id,
            agent_id=task.agent_id,
            trigger_type=trigger_type,
            session_id=f"sch_conversation_{task.id}",
            input_snapshot=task.input_payload,
            created_at=now,
        ).model_dump(by_alias=True)
        collection = self._get_collection(_COLL_RUNS)
        try:
            result = await collection.find_one_and_update(
                {"task_id": task.id, "conversation_pending": True},
                {
                    "$setOnInsert": {
                        **document,
                        "conversation_pending": True,
                        "conversation_state": "pending",
                        "owner_id": task.owner_id,
                        "target_session_id": task.target_session_id,
                        "scheduled_trigger_config": task.trigger_config,
                        "scheduled_timezone": task.timezone,
                        "timeout_seconds": task.timeout_seconds,
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            result = await collection.find_one({"task_id": task.id, "conversation_pending": True})
        return result

    async def cancel_pending_conversation_runs(self, task_id):
        await self._get_collection(_COLL_RUNS).update_many(
            {"task_id": task_id, "conversation_state": "pending"},
            {
                "$set": {
                    "conversation_state": "finished",
                    "conversation_pending": False,
                    "status": "skipped",
                    "finished_at": utc_now(),
                    "finalization_pending": True,
                }
            },
        )

    async def mark_conversation_read(self, task_id, owner_id):
        if not task_id:
            return 0
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id, "owner_id": owner_id, "execution_mode": "conversation"},
            {"$set": {"last_read_at": utc_now()}},
        )
        return result.modified_count

    async def conversation_unread_counts(self, owner_id, task_ids):
        if not task_ids:
            return {}
        from datetime import datetime, timezone

        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        pipeline = [
            {
                "$match": {
                    "owner_id": owner_id,
                    "task_id": {"$in": task_ids},
                    "conversation_state": "finished",
                    "quiet": {"$ne": True},
                    "status": {"$in": ["success", "failed", "timeout"]},
                }
            },
            {
                "$lookup": {
                    "from": _COLL_TASKS,
                    "localField": "task_id",
                    "foreignField": "_id",
                    "as": "task",
                }
            },
            {"$unwind": "$task"},
            {
                "$lookup": {
                    "from": settings.MONGODB_SESSIONS_COLLECTION,
                    "let": {"target": {"$ifNull": ["$target_session_id", "$session_id"]}},
                    "pipeline": [
                        {
                            "$match": {
                                "user_id": owner_id,
                                "$expr": {
                                    "$or": [
                                        {"$eq": ["$session_id", "$$target"]},
                                        {"$eq": [{"$toString": "$_id"}, "$$target"]},
                                    ]
                                },
                            }
                        },
                        {"$project": {"last_read_at": 1}},
                    ],
                    "as": "session",
                }
            },
            {"$unwind": "$session"},
            {
                "$match": {
                    "$expr": {
                        "$gt": [
                            "$finished_at",
                            {
                                "$max": [
                                    {"$ifNull": ["$session.last_read_at", epoch]},
                                    {"$ifNull": ["$task.last_read_at", epoch]},
                                ]
                            },
                        ]
                    }
                }
            },
            {"$group": {"_id": "$task_id", "count": {"$sum": 1}}},
        ]
        return {
            item["_id"]: item["count"]
            async for item in await self._get_collection(_COLL_RUNS).aggregate(pipeline)
        }

    async def has_open_conversation_runs(self, task_id):
        return bool(
            await self._get_collection(_COLL_RUNS).find_one(
                {
                    "task_id": task_id,
                    "conversation_state": {"$in": ["pending", "submitting", "submitted"]},
                }
            )
        )

    async def pending_conversation_runs(self):
        query: dict[str, Any] = {
            "$or": [
                {"conversation_state": {"$in": ["pending", "submitting", "submitted"]}},
                {"conversation_state": "finished", "finalization_pending": True},
            ]
        }
        if self._conversation_scan_after:
            created_at, run_id = self._conversation_scan_after
            query = {
                "$and": [
                    query,
                    {
                        "$or": [
                            {"created_at": {"$gt": created_at}},
                            {"created_at": created_at, "_id": {"$gt": run_id}},
                        ]
                    },
                ]
            }
        records = (
            await self._get_collection(_COLL_RUNS)
            .find(query)
            .sort([("created_at", 1), ("_id", 1)])
            .limit(100)
            .to_list(length=100)
        )
        self._conversation_scan_after = (
            (records[-1]["created_at"], records[-1]["_id"]) if len(records) == 100 else None
        )
        return records

    async def claim_conversation_run(self, run_id):
        from datetime import timedelta

        return await self._get_collection(_COLL_RUNS).find_one_and_update(
            {"_id": run_id, "conversation_state": "pending"},
            {
                "$set": {
                    "conversation_state": "submitting",
                    "claim_until": utc_now() + timedelta(seconds=120),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def _bump_scheduler_definition_revision(self) -> None:
        await self._get_collection(_COLL_METADATA).update_one(
            {"_id": _SCHEDULER_DEFINITION_REVISION_ID},
            {
                "$inc": {"revision": 1},
                "$set": {"updated_at": utc_now()},
            },
            upsert=True,
        )


# ── Singleton ──────────────────────────────────────

_storage: Optional[ScheduledTaskStorage] = None


def get_scheduled_task_storage() -> ScheduledTaskStorage:
    """Get the module-level ScheduledTaskStorage singleton."""
    global _storage
    if _storage is None:
        _storage = ScheduledTaskStorage()
    return _storage


def close_scheduled_task_storage() -> None:
    """Release the module-level ScheduledTaskStorage without creating it."""
    global _storage
    _storage = None
