"""Durable resource references for memory cleanup; never persist forgotten facts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

COLLECTION = "memory_resource_cleanup"
VECTOR_PENDING_INDEXES = {
    "pending_vector_sync": [("_id", 1), ("user_id", 1)],
    "pending_vector_user": [("user_id", 1), ("updated_at", -1)],
}


def vector_pending_fields(revision: str) -> dict[str, str]:
    return (
        {"_vector_pending": revision}
        if getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") == "qdrant"
        else {}
    )


def replacement_cleanup_expression(user_id: str, new_key: str | None) -> dict[str, Any]:
    from src.infra.memory.client.native.content import memory_store_namespace

    return {
        "$setUnion": [
            {"$ifNull": ["$_content_cleanup", []]},
            {
                "$cond": [
                    {
                        "$and": [
                            {"$eq": ["$content_storage_mode", "store"]},
                            {"$ne": [{"$ifNull": ["$content_store_key", None]}, None]},
                            {"$ne": ["$content_store_key", {"$literal": new_key}]},
                        ]
                    },
                    [
                        {
                            "key": "$content_store_key",
                            "namespace": {"$literal": list(memory_store_namespace(user_id))},
                        }
                    ],
                    [],
                ]
            },
        ]
    }


def content_update(user_id: str, fields: dict[str, Any]) -> list[dict[str, Any]]:
    from src.infra.memory.staging import remaining_content_stages

    return [
        {
            "$set": {
                **{
                    key: {"$literal": value}
                    for key, value in fields.items()
                    if key != "_content_stage"
                },
                **(
                    {"_content_stages": remaining_content_stages(fields)}
                    if "_content_stage" in fields
                    else {}
                ),
                "_content_cleanup": replacement_cleanup_expression(
                    user_id, fields.get("content_store_key")
                ),
            }
        }
    ]


def _jobs(backend: Any) -> Any:
    database = getattr(backend._collection, "database", None)
    return database[COLLECTION] if database is not None else None


async def _enqueue(
    backend: Any, user_id: str, kind: str, key: str, *, only_if_absent: bool = False, **fields: Any
) -> Any:
    collection = _jobs(backend)
    if collection is None:
        return None
    identity = json.dumps([user_id, kind, key, fields.get("namespace")], sort_keys=True)
    task = {
        "_id": hashlib.sha256(identity.encode()).hexdigest(),
        "version": uuid4().hex,
        "user_id": user_id,
        "kind": kind,
        "key": key,
        "retry_at": utc_now(),
        **fields,
    }
    if only_if_absent:
        return await collection.find_one_and_update(
            {"_id": task["_id"]},
            {"$setOnInsert": {**task, "created_at": utc_now(), "attempts": 0}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    await collection.update_one(
        {"_id": task["_id"]},
        {
            "$set": {k: v for k, v in task.items() if k != "_id"},
            "$setOnInsert": {"created_at": utc_now(), "attempts": 0},
        },
        upsert=True,
    )
    return task


async def enqueue_content_cleanup(backend: Any, user_id: str, key: str) -> Any:
    from src.infra.memory.client.native.content import memory_store_namespace

    return await _enqueue(
        backend,
        user_id,
        "content",
        key,
        namespace=list(memory_store_namespace(user_id)),
        stage_expires=None,
    )


async def prepare_deleted_resources(
    backend: Any, user_id: str, memory_id: str, memory: dict[str, Any]
) -> None:
    if memory.get("content_storage_mode") == "store" and memory.get("content_store_key"):
        await enqueue_content_cleanup(backend, user_id, memory["content_store_key"])
    for reference in memory.get("_content_cleanup") or []:
        await _enqueue(
            backend, user_id, "content", reference["key"], namespace=reference["namespace"]
        )
    from src.infra.memory.client.native.content import memory_store_namespace

    for stage in memory.get("_content_stages") or []:
        await _enqueue(
            backend,
            user_id,
            "content",
            stage["key"],
            namespace=list(memory_store_namespace(user_id)),
            stage_expires=stage["expires"],
        )
    if getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") == "qdrant":
        await _enqueue(
            backend,
            user_id,
            "vector",
            memory_id,
            prepared=True,
            deleted_revision=memory.get("revision_id"),
        )


async def _renew(backend: Any, task: dict[str, Any]) -> bool:
    result = await _jobs(backend).update_one(
        {
            "_id": task["_id"],
            "version": task["version"],
            "lease_token": task["lease_token"],
            "lease_until": {"$gt": utc_now()},
        },
        {"$set": {"lease_until": utc_now() + timedelta(minutes=5)}},
    )
    return bool(result.matched_count)


async def _clean_content(backend: Any, task: dict[str, Any]) -> bool:
    from src.infra.memory.client.native.content import store_delete

    namespace = task.get("namespace")
    if not isinstance(namespace, list) or len(namespace) != 3 or namespace[1] != task["user_id"]:
        raise ValueError("memory_cleanup_namespace_owner_mismatch")
    if (
        await backend._collection.find_one(
            {
                "user_id": task["user_id"],
                "content_storage_mode": "store",
                "content_store_key": task["key"],
            },
            {"_id": 1},
        )
        is not None
    ):
        return False
    # A deleted reservation cannot cancel an in-flight store write before its grace period.
    if task.get("stage_expires") and task["stage_expires"] > utc_now():
        return False
    owner = {
        "$or": [
            {"user_id": task["user_id"]},
            {"_content_stage_owner": task["user_id"], "user_id": {"$exists": False}},
        ],
        "_content_stages.key": task["key"],
    }
    pending = await backend._collection.find_one(owner, {"_content_stages": 1})
    if pending is not None:
        stages = [stage for stage in pending["_content_stages"] if stage["key"] == task["key"]]
        if any(stage["expires"] > utc_now() for stage in stages):
            return False
        from src.infra.memory.staging import retire_content_stage

        if not await retire_content_stage(backend, task["user_id"], pending["_id"], stages[0]):
            return False
    # A commit may remove its stage between the first pointer read and the fence read.
    if (
        await backend._collection.find_one(
            {
                "user_id": task["user_id"],
                "content_storage_mode": "store",
                "content_store_key": task["key"],
            },
            {"_id": 1},
        )
        is not None
    ):
        return False
    if not await _renew(backend, task):
        return False
    await store_delete(backend, tuple(namespace), task["key"])
    return True


async def _clean_vector(backend: Any, task: dict[str, Any]) -> bool:
    from src.infra.memory.client.native.vector_store import index_delete, index_write_through

    query = {"user_id": task["user_id"], "memory_id": task["key"]}
    before = await backend._collection.find_one(query)
    preparing_delete = (
        task.get("prepared") is True
        and before is not None
        and before.get("revision_id") == task.get("deleted_revision")
    )
    if preparing_delete and not before.get("_vector_pending"):
        return False
    if (
        before is not None
        and await backend._collection.find_one(
            {"memory_id": task["key"], "user_id": {"$ne": task["user_id"]}}, {"_id": 1}
        )
        is not None
    ):
        return False
    if not await _renew(backend, task):
        return False
    if before is None:
        ok = await index_delete(task["user_id"], task["key"])
    else:
        updated = before.get("updated_at")
        ok = await index_write_through(
            user_id=task["user_id"],
            memory_id=task["key"],
            embedding=before.get("embedding"),
            memory_type=before.get("memory_type", "user"),
            context=before.get("context"),
            updated_at_ts=int(updated.timestamp())
            if hasattr(updated, "timestamp")
            else int(updated or 0),
            scope=before.get("scope") or "user",
            project_id=before.get("project_id"),
        )
    after = await backend._collection.find_one(query, {"revision_id": 1, "updated_at": 1})
    stable = bool(ok) and (
        (before is None and after is None)
        or (
            before is not None
            and after is not None
            and before.get("revision_id") == after.get("revision_id")
            and before.get("updated_at") == after.get("updated_at")
        )
    )
    if stable and before is not None and before.get("_vector_pending"):
        await backend._collection.update_one(
            {
                **query,
                "revision_id": before.get("revision_id"),
                "_vector_pending": before["_vector_pending"],
            },
            {"$unset": {"_vector_pending": ""}},
        )
    return stable and not preparing_delete


async def finish_cleanup(backend: Any, task: Any, *, completed: bool) -> bool:
    if task is None:
        return False
    collection = _jobs(backend)
    query = {"_id": task["_id"], "version": task["version"], "user_id": task["user_id"]}
    if task.get("lease_token"):
        query["lease_token"] = task["lease_token"]
        query["lease_until"] = {"$gt": utc_now()}
    if completed:
        result = await collection.delete_one(query)
        return bool(result.deleted_count)
    else:
        result = await collection.update_one(
            query,
            {
                "$set": {"retry_at": utc_now() + timedelta(minutes=1)},
                "$inc": {"attempts": 1},
            },
        )
        if not result.matched_count:
            # A late uncertain result must restore repair work if its old intent was acknowledged.
            await collection.update_one(
                {"_id": task["_id"]},
                {
                    "$setOnInsert": {
                        **{
                            k: v
                            for k, v in task.items()
                            if k not in {"_id", "lease_token", "lease_until"}
                        },
                        "version": uuid4().hex,
                        "retry_at": utc_now() + timedelta(minutes=1),
                        "created_at": utc_now(),
                        "attempts": 1,
                    }
                },
                upsert=True,
            )
    return False


async def process_cleanup(backend: Any, task: dict[str, Any]) -> bool:
    collection = _jobs(backend)
    token = uuid4().hex
    claimed = await collection.find_one_and_update(
        {
            "_id": task["_id"],
            "version": task["version"],
            "user_id": task["user_id"],
            "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": utc_now()}}],
        },
        {"$set": {"lease_token": token, "lease_until": utc_now() + timedelta(minutes=5)}},
        return_document=ReturnDocument.AFTER,
    )
    if claimed is None:
        return False
    try:
        if claimed["kind"] == "content":
            done = await _clean_content(backend, claimed)
        elif claimed["kind"] == "vector":
            done = await _clean_vector(backend, claimed)
        else:
            done = False
        acknowledged = await finish_cleanup(backend, claimed, completed=done)
        return done and acknowledged
    except (Exception, asyncio.CancelledError):
        await finish_cleanup(backend, claimed, completed=False)
        raise
    finally:
        await collection.update_one(
            {"_id": task["_id"], "lease_token": token},
            {"$unset": {"lease_token": "", "lease_until": ""}},
        )


async def delete_memory_vector(backend: Any, user_id: str, memory_id: str) -> bool:
    from src.infra.memory.client.native.vector_store import index_delete

    if _jobs(backend) is None:
        return bool(await index_delete(user_id, memory_id))
    if getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") != "qdrant":
        return False
    task = await _enqueue(
        backend, user_id, "vector", memory_id, prepared=False, deleted_revision=None
    )
    return await process_cleanup(backend, task)


async def write_memory_vector(backend: Any, **fields: Any) -> bool:
    from src.infra.memory.client.native.vector_store import index_write_through

    if (
        _jobs(backend) is None
        or getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") != "qdrant"
    ):
        return await index_write_through(**fields)
    task = await _enqueue(
        backend,
        fields["user_id"],
        "vector",
        fields["memory_id"],
        only_if_absent=True,
        prepared=False,
        deleted_revision=None,
    )
    return await process_cleanup(backend, task)


async def run_cleanup_pass(backend: Any) -> dict[str, int]:
    collection = _jobs(backend)
    await backend._collection.create_index(
        [("_id", 1), ("user_id", 1)],
        name="pending_content_cleanup",
        partialFilterExpression={"_content_cleanup.0": {"$exists": True}},
    )
    rows = (
        await backend._collection.find(
            {"_content_cleanup.0": {"$exists": True}}, {"user_id": 1, "_content_cleanup": 1}
        )
        .sort("_id", 1)
        .limit(100)
        .to_list(length=100)
    )
    remaining = 100
    for row in rows:
        references = row["_content_cleanup"][:remaining]
        for reference in references:
            await _enqueue(
                backend,
                row["user_id"],
                "content",
                reference["key"],
                namespace=reference["namespace"],
            )
        if references:
            await backend._collection.update_one(
                {"_id": row["_id"], "user_id": row["user_id"]},
                {"$pull": {"_content_cleanup": {"$in": references}}},
            )
        remaining -= len(references)
        if not remaining:
            break
    from src.infra.memory.staging import CONTENT_INDEXES, retire_content_stage

    for name, (keys, partial) in CONTENT_INDEXES.items():
        await backend._collection.create_index(keys, name=name, partialFilterExpression=partial)
    if remaining:
        from src.infra.memory.client.native.content import memory_store_namespace

        expired = (
            await backend._collection.find(
                {"_content_stages.expires": {"$lte": utc_now()}},
                {"user_id": 1, "_content_stage_owner": 1, "_content_stages": 1},
            )
            .limit(remaining)
            .to_list(length=remaining)
        )
        for row in expired:
            user_id = row.get("user_id") or row["_content_stage_owner"]
            for stage in row["_content_stages"]:
                if stage["expires"] > utc_now():
                    continue
                await _enqueue(
                    backend,
                    user_id,
                    "content",
                    stage["key"],
                    only_if_absent=True,
                    namespace=list(memory_store_namespace(user_id)),
                    stage_expires=stage["expires"],
                )
                await retire_content_stage(backend, user_id, row["_id"], stage)
                remaining -= 1
                if not remaining:
                    break
            if not remaining:
                break
    if remaining:
        empty_query = {
            "_content_stage_owner": {"$exists": True},
            "user_id": {"$exists": False},
            "_content_stages": [],
        }
        empty = (
            await backend._collection.find(
                empty_query,
                {"_content_stage_owner": 1},
            )
            .sort("_id", 1)
            .limit(remaining)
            .to_list(length=remaining)
        )
        for row in empty:
            await backend._collection.delete_one(
                {
                    **empty_query,
                    "_id": row["_id"],
                    "_content_stage_owner": row["_content_stage_owner"],
                }
            )
    if getattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo") == "qdrant":
        for name, keys in VECTOR_PENDING_INDEXES.items():
            await backend._collection.create_index(
                keys,
                name=name,
                partialFilterExpression={"_vector_pending": {"$exists": True}},
            )
        await collection.create_index([("kind", 1), ("user_id", 1), ("key", 1)])
        cursor = await backend._collection.aggregate(
            [
                {"$match": {"_vector_pending": {"$exists": True}}},
                {"$sort": {"_id": 1}},
                {"$project": {"user_id": 1, "memory_id": 1}},
                {
                    "$lookup": {
                        "from": COLLECTION,
                        "let": {"owner": "$user_id", "memory": "$memory_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$user_id", "$$owner"]},
                                            {"$eq": ["$key", "$$memory"]},
                                            {"$eq": ["$kind", "vector"]},
                                        ]
                                    }
                                }
                            },
                            {"$project": {"_id": 1}},
                            {"$limit": 1},
                        ],
                        "as": "_queued_vector",
                    }
                },
                {"$match": {"_queued_vector.0": {"$exists": False}}},
                {"$limit": 100},
            ]
        )
        pending = await cursor.to_list(length=100)
        for row in pending:
            await _enqueue(
                backend,
                row["user_id"],
                "vector",
                row["memory_id"],
                only_if_absent=True,
                prepared=False,
                deleted_revision=None,
            )
    await collection.create_index([("retry_at", 1), ("created_at", 1)])
    tasks = (
        await collection.find(
            {
                "retry_at": {"$lte": utc_now()},
                "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": utc_now()}}],
            }
        )
        .sort([("retry_at", 1), ("created_at", 1)])
        .limit(100)
        .to_list(length=100)
    )
    completed = 0
    for task in tasks:
        try:
            done = await process_cleanup(backend, task)
        except Exception:
            done = False
        completed += int(done)
    return {"checked": len(tasks), "completed": completed, "pending": len(tasks) - completed}


def start_memory_cleanup_agent() -> None:
    from src.infra.scheduler import ScheduledJob, get_runtime_scheduler

    async def cleanup():
        from src.infra.memory.client.native.backend import NativeMemoryBackend

        backend = NativeMemoryBackend()
        backend._ensure_collection()
        if settings.ENABLE_MEMORY:
            await backend._prune_legacy_session_summaries()
        return await run_cleanup_pass(backend)

    # Explicit deletions must finish even if automatic memory maintenance is disabled.
    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="memory.cleanup",
            name="Memory resource cleanup",
            interval_seconds=60,
            handler=cleanup,
        )
    )
