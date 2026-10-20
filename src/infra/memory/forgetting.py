"""Source-only forget barriers; never retain the deleted fact in the barrier."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from bson import ObjectId

from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.config import settings

FORGET_COLLECTION = "memory_forget_watermarks"


def _key(user_id: str, session_id: str) -> str:
    return hashlib.sha256(
        json.dumps([user_id, session_id], ensure_ascii=False).encode()
    ).hexdigest()


async def _source_identity(db: Any, user_id: str, session_id: str) -> tuple[str, set[str]] | None:
    sessions = db[settings.MONGODB_SESSIONS_COLLECTION]
    projection = {"session_id": 1, "user_id": 1}
    doc = await sessions.find_one({"session_id": session_id}, projection)
    if doc is None and ObjectId.is_valid(session_id):
        doc = await sessions.find_one({"_id": ObjectId(session_id)}, projection)
    if doc is None:
        return session_id, {session_id}
    if doc.get("user_id") != user_id:
        return None
    canonical = str(doc.get("session_id") or doc["_id"])
    aliases = {canonical}
    legacy_id = str(doc["_id"])
    if legacy_id != canonical:
        collision = await sessions.find_one({"session_id": legacy_id}, {"_id": 1})
        if collision is None or collision["_id"] == doc["_id"]:
            aliases.add(legacy_id)
    return canonical, aliases


async def source_watermark(db: Any, user_id: str, session_id: str) -> datetime | None:
    identity = await _source_identity(db, user_id, session_id)
    if identity is None:
        return None
    latest = None
    for alias in identity[1]:
        doc = await db[FORGET_COLLECTION].find_one(
            {"_id": _key(user_id, alias), "user_id": user_id},
            {"forgotten_before": 1},
        )
        if doc is not None:
            value = doc.get("forgotten_before")
            if not isinstance(value, datetime):
                raise RuntimeError("memory_source_state_unavailable")
            value = ensure_utc(value)
            latest = max(latest, value) if latest else value
    return latest


def _successful_retain_receipt(event: Any, memory_id: str) -> bool:
    if not isinstance(event, dict) or event.get("event_type") != "tool:result":
        return False
    data = event.get("data")
    if (
        not isinstance(data, dict)
        or data.get("tool") != "memory_retain"
        or data.get("success") is not True
    ):
        return False
    result = data.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return False
    return (
        isinstance(result, dict)
        and result.get("success") is True
        and result.get("memory_id") == memory_id
    )


async def _legacy_foreground_sources(db: Any, user_id: str, memory_id: str) -> set[str]:
    # shortcut: receipt recovery scans owned traces; add a reverse index if bulk deletes dominate.
    encoded_ids = {
        json.dumps(memory_id, ensure_ascii=ascii_only)[1:-1] for ascii_only in (False, True)
    }
    serialized_id = (
        r'"memory_id"\s*:\s*"(?:'
        + "|".join(re.escape(value) for value in sorted(encoded_ids))
        + ')"'
    )
    receipt_query = {
        "event_type": "tool:result",
        "data.tool": "memory_retain",
        "data.success": True,
        "$or": [
            {"data.result.memory_id": memory_id},
            {"data.result": {"$regex": serialized_id}},
        ],
    }
    retained_events = {
        "$filter": {
            "input": {"$ifNull": ["$events", []]},
            "as": "entry",
            "cond": {
                "$and": [
                    {"$eq": ["$$entry.event_type", "tool:result"]},
                    {"$eq": ["$$entry.data.tool", "memory_retain"]},
                    {"$eq": ["$$entry.data.success", True]},
                ]
            },
        }
    }
    cursor = await db[settings.MONGODB_TRACES_COLLECTION].aggregate(
        [
            {"$match": {"user_id": user_id}},
            {
                "$lookup": {
                    "from": settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION,
                    "localField": "trace_id",
                    "foreignField": "trace_id",
                    "pipeline": [
                        {"$match": {"events": {"$elemMatch": receipt_query}}},
                        {"$project": {"_id": 0, "events": retained_events}},
                    ],
                    "as": "_memory_chunks",
                }
            },
            {
                "$match": {
                    "$or": [
                        {"events": {"$elemMatch": receipt_query}},
                        {"_memory_chunks.0": {"$exists": True}},
                    ]
                }
            },
            {
                "$project": {
                    "user_id": 1,
                    "session_id": 1,
                    "events": retained_events,
                    "_memory_chunks.events": 1,
                }
            },
        ]
    )
    sources = set()
    async for trace in cursor:
        if trace.get("user_id") != user_id:
            continue
        events = list(trace.get("events") or [])
        for chunk in trace.get("_memory_chunks") or []:
            events.extend(chunk.get("events") or [])
        session_id = trace.get("session_id")
        if (
            isinstance(session_id, str)
            and session_id
            and any(_successful_retain_receipt(event, memory_id) for event in events)
        ):
            sources.add(session_id)
    return sources


async def memory_source_sessions(backend: Any, user_id: str, memory: dict[str, Any]) -> set[str]:
    origins = memory.get("origin_session_ids")
    sources = (
        {sid for sid in origins if isinstance(sid, str) and sid}
        if isinstance(origins, list)
        else set()
    )
    for ref in memory.get("source_refs") or []:
        if isinstance(ref, dict):
            sid = ref.get("session_id")
            if isinstance(sid, str) and sid:
                sources.add(sid)
    db = getattr(backend._collection, "database", None)
    if db is not None:
        cursor = db["memory_extraction_jobs"].find(
            {
                "user_id": user_id,
                "$or": [{"memory_ids": memory["memory_id"]}, {"memory_id": memory["memory_id"]}],
            },
            {"session_id": 1},
        )
        async for job in cursor:
            if isinstance(job.get("session_id"), str) and job["session_id"]:
                sources.add(job["session_id"])
        # Known sources may be only part of an older memory's history.
        sources.update(await _legacy_foreground_sources(db, user_id, memory["memory_id"]))
    return sources


async def suppress_deleted_sources(backend: Any, user_id: str, memory: dict[str, Any]) -> None:
    sources = await memory_source_sessions(backend, user_id, memory)
    db = getattr(backend._collection, "database", None)
    if not sources:
        return
    if db is None:
        raise RuntimeError("memory_source_state_unavailable")
    now = utc_now()
    identities: dict[str, set[str]] = {}
    for session_id in sources:
        identity = await _source_identity(db, user_id, session_id)
        if identity is not None:
            identities.setdefault(identity[0], set()).update(identity[1])
    for session_id, aliases in identities.items():
        await db[FORGET_COLLECTION].update_one(
            {"_id": _key(user_id, session_id), "user_id": user_id},
            {"$max": {"forgotten_before": now}, "$setOnInsert": {"session_id": session_id}},
            upsert=True,
        )
        await db["memory_extraction_jobs"].update_many(
            {"user_id": user_id, "session_id": {"$in": list(aliases)}},
            {
                "$set": {
                    "status": "succeeded_no_output",
                    "resume_state": None,
                    "input_fingerprint": None,
                    "next_retry_at": None,
                    "extracted_updated_at": now,
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
        )
