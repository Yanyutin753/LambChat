"""MongoDB storage for scheduled tasks and run records."""

from __future__ import annotations

import asyncio
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
    "agent_id": 1,
    "trigger_type": 1,
    "trigger_config": 1,
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
        await c_tasks.create_index("scheduler_revision_pending_operation_id")
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
        await c_runs.create_index("task_id")
        await c_runs.create_index([("task_id", 1), ("created_at", -1)])
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
                "attachment_setup_pending": {"$ne": True},
                "attachment_keys.0": {"$exists": False},
                "pending_attachment_claim_keys.0": {"$exists": False},
                "pending_attachment_release_keys.0": {"$exists": False},
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
    ) -> tuple[list[ScheduledTask], int]:
        """List tasks with pagination, scoped by owner_id."""
        query: dict[str, Any] = {"owner_id": owner_id}
        if status:
            query["status"] = status
        else:
            query["status"] = {"$ne": ScheduledTaskStatus.DELETED}
        if source_session_id:
            query["source_session_id"] = source_session_id
        if created_by:
            query["created_by"] = created_by
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

    async def list_attachment_reconciliation_tasks(self) -> list[ScheduledTask]:
        """List definitions with attachment ownership or interrupted lease work."""
        cursor = self._get_collection(_COLL_TASKS).find(
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
        )
        return [ScheduledTask(**doc) async for doc in cursor]

    async def get_active_tasks_marker(self) -> int:
        """Return an O(1) scheduler-definition revision marker."""
        await self._publish_one_pending_scheduler_definition_revision()
        doc = await self._get_collection(_COLL_METADATA).find_one(
            {"_id": _SCHEDULER_DEFINITION_REVISION_ID}
        )
        if not doc:
            return 0
        return int(doc.get("revision") or 0)

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        updates["updated_at"] = utc_now()
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id, "status": {"$ne": ScheduledTaskStatus.DELETED}},
            {"$set": updates},
        )
        if result.modified_count > 0:
            await self._bump_scheduler_definition_revision()
        return result.modified_count > 0

    async def stage_attachment_claim(
        self,
        task_id: str,
        keys: list[str],
    ) -> Optional[ScheduledTask]:
        """Persist attachment keys that must be claimed before publishing an update."""
        record = await self._get_collection(_COLL_TASKS).find_one_and_update(
            {"_id": task_id, "status": {"$ne": ScheduledTaskStatus.DELETED}},
            [
                {
                    "$set": {
                        "pending_attachment_claim_keys": {
                            "$setUnion": [
                                {"$ifNull": ["$pending_attachment_claim_keys", []]},
                                list(keys),
                            ]
                        },
                        "attachment_commit_operation_id": None,
                        "updated_at": utc_now(),
                    }
                }
            ],
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            return None
        await self._bump_scheduler_definition_revision()
        return ScheduledTask(**record)

    async def commit_attachment_update(
        self,
        task_id: str,
        updates: dict[str, Any],
        attachment_keys: list[str],
    ) -> Optional[ScheduledTask]:
        """Publish claimed attachment keys and durably queue removed keys for release."""
        operation_id = str(uuid4())
        state = dict(updates)
        state.update(
            {
                "attachment_keys": list(attachment_keys),
                "pending_attachment_claim_keys": [],
                "pending_attachment_release_keys": {
                    "$setDifference": [
                        {
                            "$setUnion": [
                                {"$ifNull": ["$pending_attachment_release_keys", []]},
                                {"$ifNull": ["$attachment_keys", []]},
                                {"$ifNull": ["$pending_attachment_claim_keys", []]},
                            ]
                        },
                        list(attachment_keys),
                    ]
                },
                "attachment_setup_pending": False,
                "attachment_commit_operation_id": operation_id,
                "scheduler_revision_pending_operation_id": operation_id,
                "updated_at": utc_now(),
            }
        )
        collection = self._get_collection(_COLL_TASKS)
        try:
            record = await collection.find_one_and_update(
                {"_id": task_id, "status": {"$ne": ScheduledTaskStatus.DELETED}},
                [{"$set": state}],
                return_document=ReturnDocument.AFTER,
            )
        except Exception:
            # A Mongo write can commit and still lose its reply. Only this exact
            # operation identity can turn that ambiguous outcome into success.
            # A failed/mismatched re-read remains fail-closed so callers retain
            # the staged lease for the next serialized reconciliation pass.
            try:
                record = await collection.find_one(
                    {
                        "_id": task_id,
                        "attachment_commit_operation_id": operation_id,
                    }
                )
            except Exception:
                logger.exception(
                    "[ScheduledTaskStorage] failed to verify attachment commit %s",
                    task_id,
                )
                raise
            if record is None:
                raise
        if record is None:
            return None
        committed = ScheduledTask(**record)
        await self._try_publish_scheduler_definition_revision(task_id, operation_id)
        return committed

    async def mark_task_attachment_deletion(
        self,
        task_id: str,
    ) -> Optional[ScheduledTask]:
        """Make a task non-runnable while retaining every possible lease for release."""
        record = await self._get_collection(_COLL_TASKS).find_one_and_update(
            {"_id": task_id},
            [
                {
                    "$set": {
                        "status": ScheduledTaskStatus.DELETED,
                        "enabled": False,
                        "attachment_keys": [],
                        "pending_attachment_claim_keys": [],
                        "pending_attachment_release_keys": {
                            "$setUnion": [
                                {"$ifNull": ["$pending_attachment_release_keys", []]},
                                {"$ifNull": ["$attachment_keys", []]},
                                {"$ifNull": ["$pending_attachment_claim_keys", []]},
                            ]
                        },
                        "attachment_setup_pending": False,
                        "attachment_commit_operation_id": None,
                        "updated_at": utc_now(),
                    }
                }
            ],
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            return None
        await self._bump_scheduler_definition_revision()
        return ScheduledTask(**record)

    async def clear_pending_attachment_claims(
        self,
        task_id: str,
        keys: list[str],
    ) -> bool:
        """Clear claim work only after its task tokens are compensated."""
        return await self._clear_pending_attachment_keys(
            task_id,
            "pending_attachment_claim_keys",
            keys,
        )

    async def clear_pending_attachment_releases(
        self,
        task_id: str,
        keys: list[str],
    ) -> bool:
        """Clear release work only after its task tokens are removed."""
        return await self._clear_pending_attachment_keys(
            task_id,
            "pending_attachment_release_keys",
            keys,
        )

    async def _clear_pending_attachment_keys(
        self,
        task_id: str,
        field: str,
        keys: list[str],
    ) -> bool:
        if not keys:
            return True
        result = await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {
                "$pullAll": {field: list(keys)},
                "$set": {"updated_at": utc_now()},
            },
        )
        return result.modified_count > 0

    async def finalize_deleted_task(self, task_id: str) -> bool:
        """Physically remove a deleted task only after all lease work is complete."""
        result = await self._get_collection(_COLL_TASKS).delete_one(
            {
                "_id": task_id,
                "status": ScheduledTaskStatus.DELETED,
                "attachment_setup_pending": False,
                "attachment_keys.0": {"$exists": False},
                "pending_attachment_claim_keys.0": {"$exists": False},
                "pending_attachment_release_keys.0": {"$exists": False},
            }
        )
        if result.deleted_count > 0:
            await self._bump_scheduler_definition_revision()
        return result.deleted_count > 0

    async def delete_task(self, task_id: str) -> bool:
        """Physically remove a task document so its name is freed immediately."""
        result = await self._get_collection(_COLL_TASKS).delete_one({"_id": task_id})
        if result.deleted_count > 0:
            await self._bump_scheduler_definition_revision()
        return result.deleted_count > 0

    async def update_task_run_stats(self, task_id: str, run_id: str, run_status: RunStatus) -> None:
        """Update task-level run statistics after execution completes."""
        now = utc_now()
        await self._get_collection(_COLL_TASKS).update_one(
            {"_id": task_id},
            {
                "$set": {
                    "last_run_at": now,
                    "last_run_status": run_status,
                    "last_run_id": run_id,
                    "updated_at": now,
                },
                "$inc": {"total_runs": 1},
            },
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

    async def _bump_scheduler_definition_revision(self) -> None:
        await self._get_collection(_COLL_METADATA).update_one(
            {"_id": _SCHEDULER_DEFINITION_REVISION_ID},
            {
                "$inc": {"revision": 1},
                "$set": {"updated_at": utc_now()},
            },
            upsert=True,
        )

    async def _try_publish_scheduler_definition_revision(
        self,
        task_id: str,
        operation_id: str,
    ) -> None:
        """Best-effort publish; the task marker makes any failure durable."""
        try:
            await self._publish_scheduler_definition_revision(task_id, operation_id)
        except Exception:
            logger.exception(
                "[ScheduledTaskStorage] revision publish deferred for attachment commit %s",
                task_id,
            )

    async def _publish_one_pending_scheduler_definition_revision(self) -> None:
        """Publish one durable task revision before returning the shared marker."""
        collection = self._get_collection(_COLL_TASKS)
        pending = await collection.find_one(
            {
                "scheduler_revision_pending_operation_id": {
                    "$type": "string",
                    "$ne": "",
                }
            },
            {"_id": 1, "scheduler_revision_pending_operation_id": 1},
        )
        if pending is None:
            return
        operation_id = pending.get("scheduler_revision_pending_operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise RuntimeError("Invalid pending scheduler definition revision identity")
        await self._publish_scheduler_definition_revision(
            str(pending["_id"]),
            operation_id,
        )

    async def _publish_scheduler_definition_revision(
        self,
        task_id: str,
        operation_id: str,
    ) -> None:
        """Bump the shared marker, then clear only the operation it publishes."""
        await self._bump_scheduler_definition_revision()
        await self._get_collection(_COLL_TASKS).update_one(
            {
                "_id": task_id,
                "scheduler_revision_pending_operation_id": operation_id,
            },
            {"$unset": {"scheduler_revision_pending_operation_id": ""}},
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
