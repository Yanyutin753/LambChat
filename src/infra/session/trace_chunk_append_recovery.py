"""Durable recovery for interrupted trace event chunk appends."""

import hashlib
import uuid
from datetime import timedelta
from typing import Any, Dict, List

from bson import json_util

from src.infra.logging import get_logger
from src.infra.session import trace_storage as trace_storage_helpers
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
TRACE_EVENT_REVISION_FIELD = "event_revision"
APPEND_RECOVERY_TTL = timedelta(minutes=5)


def append_recovery_after() -> Any:
    return utc_now() + APPEND_RECOVERY_TTL


def append_digest(events: List[Dict[str, Any]], start_seq: int) -> str:
    normalized = []
    for offset, event in enumerate(events):
        normalized_event = dict(event)
        normalized_event["seq"] = start_seq + offset
        normalized.append(normalized_event)
    serialized = json_util.dumps(normalized, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def append_marker_fields(*, start_seq: int, event_count: int) -> Dict[str, Any]:
    return {
        "phase": "reserved",
        "start_seq": start_seq,
        "event_count": event_count,
        "reserved_event_count": start_seq + event_count - 1,
        "recovery_after": append_recovery_after(),
    }


def _append_marker_identity(trace_id: str, marker: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trace_id": trace_id,
        TRACE_EVENT_REVISION_FIELD: marker.get("revision"),
        f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": marker.get("id"),
        f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": marker.get("revision"),
    }


def _valid_append_range(marker: Dict[str, Any]) -> tuple[int, int, int] | None:
    start_seq = marker.get("start_seq")
    event_count = marker.get("event_count")
    reserved_event_count = marker.get("reserved_event_count")
    if (
        not isinstance(start_seq, int)
        or start_seq <= 0
        or not isinstance(event_count, int)
        or event_count <= 0
        or not isinstance(reserved_event_count, int)
        or reserved_event_count < start_seq + event_count - 1
    ):
        return None
    return start_seq, event_count, reserved_event_count


def _recovery_is_due(marker: Dict[str, Any], now: Any) -> bool:
    recovery_after = marker.get("recovery_after")
    if recovery_after is None:
        return False
    try:
        return bool(recovery_after <= now)
    except TypeError:
        return True


async def begin_chunk_append(
    storage: Any,
    trace_doc: Dict[str, Any],
    events: List[Dict[str, Any]],
    start_seq: int,
) -> Dict[str, Any] | None:
    """Claim or resume the exact durable reservation for one append batch."""
    trace_id = str(trace_doc.get("trace_id") or "")
    if not trace_id or not events or start_seq <= 0:
        return None
    event_count = len(events)
    reserved_event_count = start_seq + event_count - 1
    digest = append_digest(events, start_seq)
    current = await storage.collection.find_one({"trace_id": trace_id})
    if not current:
        return None
    if (
        trace_doc.get("updated_at") is not None
        and trace_doc.get("updated_at") != current.get("updated_at")
    ):
        return None

    marker = current.get(ATTACHMENT_CHUNK_WRITE_FIELD)
    if isinstance(marker, dict):
        append_range = _valid_append_range(marker)
        if (
            marker.get("kind") != "append"
            or append_range is None
            or append_range[:2] != (start_seq, event_count)
            or marker.get("phase") not in {"reserved", "writing"}
            or (marker.get("digest") is not None and marker.get("digest") != digest)
        ):
            return None
        now = utc_now()
        if _recovery_is_due(marker, now):
            if not await recover_incomplete_chunk_append(storage, current, now=now):
                return None
            retry_doc = dict(trace_doc)
            retry_doc.pop("updated_at", None)
            retry_doc.pop(ATTACHMENT_CHUNK_WRITE_FIELD, None)
            return await begin_chunk_append(storage, retry_doc, events, start_seq)
        phase = str(marker["phase"])
        recovery_after = marker.get("recovery_after")
        claimed = await storage.collection.find_one_and_update(
            {
                **_append_marker_identity(trace_id, marker),
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": phase,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.recovery_after": recovery_after,
            },
            {
                "$set": {
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "writing",
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.digest": digest,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.recovery_after": append_recovery_after(),
                    "updated_at": now,
                }
            },
            return_document=True,
        )
        return claimed
    if marker is not None:
        return None

    raw_revision = current.get(TRACE_EVENT_REVISION_FIELD)
    try:
        expected_revision = int(raw_revision or 0)
        current_event_count = int(current.get("event_count", 0) or 0)
    except (TypeError, ValueError):
        return None
    if current_event_count != start_seq - 1 and current_event_count < reserved_event_count:
        return None
    reserve_event_count = current_event_count == start_seq - 1
    claimed_revision = expected_revision + 1
    now = utc_now()
    operation_id = uuid.uuid4().hex
    marker = {
        "id": operation_id,
        "kind": "append",
        "revision": claimed_revision,
        **append_marker_fields(start_seq=start_seq, event_count=event_count),
        "reserved_event_count": (
            reserved_event_count if reserve_event_count else current_event_count
        ),
        "phase": "writing",
        "digest": digest,
    }
    increments = {TRACE_EVENT_REVISION_FIELD: 1}
    if reserve_event_count:
        increments["event_count"] = event_count
    return await storage.collection.find_one_and_update(
        {
            "trace_id": trace_id,
            "updated_at": current.get("updated_at"),
            "event_count": current_event_count,
            ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
            TRACE_EVENT_REVISION_FIELD: (
                expected_revision if raw_revision is not None else {"$exists": False}
            ),
        },
        {
            "$inc": increments,
            "$set": {
                ATTACHMENT_CHUNK_WRITE_FIELD: marker,
                "updated_at": now,
            },
        },
        return_document=True,
    )


async def heartbeat_chunk_append(
    storage: Any,
    trace_id: str,
    marker: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Extend an exact active append marker without reviving an expired owner."""
    if marker.get("phase") != "writing":
        return None
    now = utc_now()
    if _recovery_is_due(marker, now):
        return None
    recovery_after = marker.get("recovery_after")
    current = await storage.collection.find_one_and_update(
        {
            **_append_marker_identity(trace_id, marker),
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "writing",
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.recovery_after": recovery_after,
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.digest": marker.get("digest"),
        },
        {
            "$set": {
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.recovery_after": append_recovery_after(),
                "updated_at": now,
            }
        },
        return_document=True,
    )
    current_marker = (current or {}).get(ATTACHMENT_CHUNK_WRITE_FIELD)
    return current_marker if isinstance(current_marker, dict) else None


async def _claim_append_rollback(
    storage: Any,
    trace_doc: Dict[str, Any],
    marker: Dict[str, Any],
) -> Dict[str, Any] | None:
    trace_id = str(trace_doc.get("trace_id") or "")
    phase = marker.get("phase")
    if not trace_id or _valid_append_range(marker) is None:
        return None
    if phase == "rolling_back":
        return marker
    if phase not in {"reserved", "writing"}:
        return None

    recovery_after = marker.get("recovery_after")
    claimed = await storage.collection.find_one_and_update(
        {
            **_append_marker_identity(trace_id, marker),
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": phase,
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.recovery_after": recovery_after,
        },
        {
            "$set": {
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "rolling_back",
                "updated_at": utc_now(),
            }
        },
        return_document=True,
    )
    claimed_marker = (claimed or {}).get(ATTACHMENT_CHUNK_WRITE_FIELD)
    return claimed_marker if isinstance(claimed_marker, dict) else None


async def _remove_append_range_from_chunks(
    storage: Any,
    trace_id: str,
    *,
    start_seq: int,
    event_count: int,
) -> None:
    end_seq = start_seq + event_count - 1
    chunk_size = trace_storage_helpers._get_event_chunk_size()
    start_chunk = trace_storage_helpers._event_chunk_index(start_seq)
    end_chunk = trace_storage_helpers._event_chunk_index(end_seq)
    now = utc_now()
    for chunk_index in range(start_chunk, end_chunk + 1):
        chunk_start = chunk_index * chunk_size + 1
        chunk_end = chunk_start + chunk_size - 1
        remove_start = max(start_seq, chunk_start)
        remove_end = min(end_seq, chunk_end)
        seq_range = {"$gte": remove_start, "$lte": remove_end}
        await storage.chunks_collection.update_one(
            {
                "trace_id": trace_id,
                "chunk_index": chunk_index,
                "events": {"$elemMatch": {"seq": seq_range}},
            },
            [
                {
                    "$set": {
                        "events": {
                            "$filter": {
                                "input": {"$ifNull": ["$events", []]},
                                "as": "event",
                                "cond": {
                                    "$not": [
                                        {
                                            "$and": [
                                                {
                                                    "$gte": [
                                                        {"$ifNull": ["$$event.seq", 0]},
                                                        remove_start,
                                                    ]
                                                },
                                                {
                                                    "$lte": [
                                                        {"$ifNull": ["$$event.seq", 0]},
                                                        remove_end,
                                                    ]
                                                },
                                            ]
                                        }
                                    ]
                                },
                            }
                        },
                        "updated_at": now,
                    }
                },
                {
                    "$set": {
                        "event_count": {"$size": "$events"},
                        "start_seq": {"$min": "$events.seq"},
                        "end_seq": {"$max": "$events.seq"},
                    }
                },
            ],
        )
        await storage.chunks_collection.delete_many(
            {
                "trace_id": trace_id,
                "chunk_index": chunk_index,
                "event_count": 0,
            }
        )


async def recover_incomplete_chunk_append(
    storage: Any,
    trace_doc: Dict[str, Any],
    *,
    now: Any | None = None,
) -> bool:
    marker = trace_doc.get(ATTACHMENT_CHUNK_WRITE_FIELD)
    if not isinstance(marker, dict) or marker.get("kind") != "append":
        return False
    now = utc_now() if now is None else now
    if marker.get("phase") != "rolling_back" and not _recovery_is_due(marker, now):
        return False
    claimed_marker = await _claim_append_rollback(storage, trace_doc, marker)
    append_range = _valid_append_range(claimed_marker or {})
    if claimed_marker is None or append_range is None:
        return False
    start_seq, event_count, reserved_event_count = append_range
    trace_id = str(trace_doc.get("trace_id") or "")

    await _remove_append_range_from_chunks(
        storage,
        trace_id,
        start_seq=start_seq,
        event_count=event_count,
    )
    parent_update: Dict[str, Any] = {
        "$inc": {TRACE_EVENT_REVISION_FIELD: 1},
        "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
        "$set": {"updated_at": utc_now()},
    }
    if reserved_event_count == start_seq + event_count - 1:
        parent_update["$inc"]["event_count"] = -event_count
    result = await storage.collection.update_one(
        {
            **_append_marker_identity(trace_id, claimed_marker),
            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "rolling_back",
            "event_count": reserved_event_count,
        },
        parent_update,
    )
    return result.modified_count > 0


async def recover_incomplete_chunk_appends(storage: Any, limit: int = 100) -> int:
    """Roll back expired append reservations without racing their live owner."""
    recovered = 0
    now = utc_now()
    cursor = storage.collection.find(
        {f"{ATTACHMENT_CHUNK_WRITE_FIELD}.kind": "append"}
    ).limit(max(int(limit or 0), 1))
    async for trace_doc in cursor:
        try:
            recovered += int(
                await recover_incomplete_chunk_append(storage, trace_doc, now=now)
            )
        except Exception as exc:
            logger.warning(
                "Failed to recover chunk append for trace %s: %s",
                trace_doc.get("trace_id"),
                exc,
            )
    return recovered
