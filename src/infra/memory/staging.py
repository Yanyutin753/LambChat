"""Fence external body commits against crash recovery in the metadata document."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode

CONTENT_INDEXES = {
    "staged_content_key": (
        [("_content_stages.key", 1)],
        {"_content_stages.key": {"$exists": True}},
    ),
    "pending_content_stages": (
        [("_content_stages.expires", 1)],
        {"_content_stages.expires": {"$exists": True}},
    ),
    "empty_content_reservations": (
        [("_id", 1), ("_content_stage_owner", 1)],
        {"_content_stage_owner": {"$exists": True}, "_content_stages": []},
    ),
    "stored_content_pointer": (
        [("user_id", 1), ("content_store_key", 1)],
        {"content_storage_mode": "store"},
    ),
}


def owned_content_query(user_id: str, memory_id: str) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "$or": [
            {"user_id": user_id},
            {"_content_stage_owner": user_id, "user_id": {"$exists": False}},
        ],
    }


async def stage_content(backend: Any, user_id: str, memory_id: str, key: str) -> Any:
    if getattr(getattr(backend, "_collection", None), "database", None) is None:
        return None
    # shortcut: puts must settle within the grace period; unbounded late writes need store-side fencing.
    stage = {"key": key, "token": uuid4().hex, "expires": utc_now() + timedelta(minutes=5)}
    await backend._collection.update_one(
        owned_content_query(user_id, memory_id),
        {
            "$setOnInsert": {"memory_id": memory_id, "_content_stage_owner": user_id},
            "$push": {"_content_stages": stage},
        },
        upsert=True,
    )
    return stage


def content_commit_query(user_id: str, memory_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    stage = fields.get("_content_stage")
    if stage is None:
        return {"user_id": user_id, "memory_id": memory_id}
    return {
        **owned_content_query(user_id, memory_id),
        "_content_stages": {
            "$elemMatch": {
                "key": stage["key"],
                "token": stage["token"],
                "expires": {"$gt": utc_now()},
            }
        },
    }


def remaining_content_stages(fields: dict[str, Any]) -> dict[str, Any]:
    stage = fields.get("_content_stage")
    if stage is None:
        return {"$ifNull": ["$_content_stages", []]}
    return {
        "$filter": {
            "input": {"$ifNull": ["$_content_stages", []]},
            "as": "stage",
            "cond": {"$ne": ["$$stage.token", {"$literal": stage["token"]}]},
        }
    }


async def insert_content_memory(backend: Any, doc: dict[str, Any]) -> None:
    if "_content_stage" not in doc:
        await backend._collection.insert_one(doc)
        return
    fields = {key: value for key, value in doc.items() if key != "_content_stage"}
    result = await backend._collection.update_one(
        {
            **content_commit_query(doc["user_id"], doc["memory_id"], doc),
            "user_id": {"$exists": False},
        },
        [
            {
                "$replaceWith": {
                    "$mergeObjects": [
                        {"$literal": fields},
                        {"_id": "$_id", "_content_stages": remaining_content_stages(doc)},
                    ]
                }
            }
        ],
    )
    if not result.matched_count:
        raise AppError(ErrorCode.MEMORY_BACKEND_UNAVAILABLE)


async def retire_content_stage(
    backend: Any, user_id: str, doc_id: Any, stage: dict[str, Any]
) -> bool:
    result = await backend._collection.update_one(
        {
            "_id": doc_id,
            "$or": [
                {"user_id": user_id},
                {"_content_stage_owner": user_id, "user_id": {"$exists": False}},
            ],
            "content_store_key": {"$ne": stage["key"]},
            "_content_stages": {
                "$elemMatch": {
                    "key": stage["key"],
                    "token": stage["token"],
                    "expires": {"$lte": utc_now()},
                }
            },
        },
        {"$pull": {"_content_stages": {"key": stage["key"], "token": stage["token"]}}},
    )
    if not result.matched_count:
        return False
    await backend._collection.delete_one(
        {
            "_id": doc_id,
            "_content_stage_owner": user_id,
            "user_id": {"$exists": False},
            "_content_stages": [],
        }
    )
    return True
