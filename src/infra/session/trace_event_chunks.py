"""Chunked trace event storage helpers for TraceStorage."""

import hashlib
import uuid
from copy import deepcopy
from datetime import timedelta
from typing import Any, Dict, List, Optional

from bson import json_util
from pymongo import ReturnDocument

from src.infra.logging import get_logger
from src.infra.session import trace_storage as trace_storage_helpers
from src.infra.session.trace_chunk_rollback import TraceChunkRollbackMixin
from src.infra.utils.datetime import ensure_utc, utc_now

logger = get_logger(__name__)
ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
TRACE_EVENT_REVISION_FIELD = "event_revision"


def _marker_recovery_expired(recovery_after: Any, now: Any) -> bool:
    """True unless the marker holds an unexpired lease.

    Missing or unparseable ``recovery_after`` values only occur on legacy or
    corrupt markers whose writer cannot be act, so they count as expired.
    """
    if recovery_after is None:
        return True
    try:
        return ensure_utc(recovery_after) <= now
    except (TypeError, ValueError, AttributeError):
        return True


async def _release_claimed_marker(collection: Any, trace_id: str, operation_id: str) -> None:
    """Best-effort release of a marker this coroutine just claimed.

    Task cancellation (user stop button) can land on the claim await after
    the server already installed the marker; the caller never learns the
    claim, so nothing else releases it before the 5-minute lease expires.
    The unset is scoped to our operation id: if the claim never reached the
    server it matches nothing, and a foreign marker is never touched.
    """
    try:
        await collection.update_one(
            {
                "trace_id": trace_id,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
            },
            {
                "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                "$set": {"updated_at": utc_now()},
            },
        )
    except BaseException as exc:  # noqa: BLE001 - best-effort cleanup only
        logger.warning(
            "Failed to release claimed chunk marker for trace %s after cancellation: %s",
            trace_id,
            exc,
        )


def _replacement_digest(
    events: List[Dict[str, Any]],
    *,
    mark_storage_chunked: bool,
    remove_legacy_events: bool,
    parent_updates: Optional[Dict[str, Any]],
) -> str:
    payload = {
        "events": events,
        "mark_storage_chunked": mark_storage_chunked,
        "remove_legacy_events": remove_legacy_events,
        "parent_updates": parent_updates or {},
    }
    serialized = json_util.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class TraceEventChunkMixin(TraceChunkRollbackMixin):
    @property
    def collection(self) -> Any:
        raise NotImplementedError

    @property
    def chunks_collection(self) -> Any:
        raise NotImplementedError

    async def _claim_chunk_write(
        self,
        trace_doc: Dict[str, Any],
        *,
        kind: str,
        marker_fields: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Dict[str, Any]] | None:
        """Version and fence a parent before any child chunk can be mutated."""
        trace_id = str(trace_doc.get("trace_id") or "")
        if not trace_id:
            return None
        expected_updated_at = trace_doc.get("updated_at")
        if expected_updated_at is None:
            current = await self.collection.find_one(
                {"trace_id": trace_id},
                {
                    "_id": 1,
                    "session_id": 1,
                    "updated_at": 1,
                    TRACE_EVENT_REVISION_FIELD: 1,
                    ATTACHMENT_CHUNK_WRITE_FIELD: 1,
                },
            )
            if not current:
                return None
            trace_doc = {**trace_doc, **current}
        if trace_doc.get(ATTACHMENT_CHUNK_WRITE_FIELD) is not None:
            return None
        raw_revision = trace_doc.get(TRACE_EVENT_REVISION_FIELD)
        try:
            expected_revision = int(raw_revision or 0)
        except (TypeError, ValueError):
            return None
        claimed_revision = expected_revision + 1
        operation_id = uuid.uuid4().hex
        now = utc_now()
        marker = {
            "id": operation_id,
            "kind": kind,
            "revision": claimed_revision,
            **(deepcopy(marker_fields) if marker_fields else {}),
        }
        if kind == "replace":
            marker["staging_trace_id"] = f"{trace_id}:replace:{operation_id}"
            marker["recovery_after"] = now + timedelta(minutes=5)
        # Fence on the monotonic event revision alone. Matching updated_at as
        # well turned every concurrent revision-bumping write (e.g. recommend
        # questions) into a spurious CAS failure, and matching session_id broke
        # claims whenever the buffered session_id diverged from the stored one.
        query: Dict[str, Any] = {
            "trace_id": trace_id,
            ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
        }
        query[TRACE_EVENT_REVISION_FIELD] = (
            expected_revision if raw_revision is not None else {"$exists": False}
        )
        if trace_doc.get("_id") is not None:
            query["_id"] = trace_doc["_id"]
        try:
            claimed = await self.collection.find_one_and_update(
                query,
                {
                    "$inc": {TRACE_EVENT_REVISION_FIELD: 1},
                    "$set": {
                        ATTACHMENT_CHUNK_WRITE_FIELD: marker,
                        "updated_at": now,
                    },
                },
                return_document=ReturnDocument.AFTER,
            )
        except BaseException:
            await _release_claimed_marker(self.collection, trace_id, operation_id)
            raise
        return (operation_id, claimed) if claimed else None

    async def _set_replacement_phase(
        self,
        trace_id: str,
        marker: Dict[str, Any],
        *,
        expected_phase: str,
        phase: str,
    ) -> Dict[str, Any] | None:
        operation_id = marker.get("id")
        revision = marker.get("revision")
        result = await self.collection.find_one_and_update(
            {
                "trace_id": trace_id,
                TRACE_EVENT_REVISION_FIELD: revision,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": expected_phase,
            },
            {
                "$set": {
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": phase,
                    "updated_at": utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if result:
            return result
        current = await self.collection.find_one({"trace_id": trace_id})
        current_marker = (current or {}).get(ATTACHMENT_CHUNK_WRITE_FIELD)
        if (
            isinstance(current_marker, dict)
            and current_marker.get("id") == operation_id
            and current_marker.get("revision") == revision
            and current_marker.get("phase") == phase
        ):
            return current
        return None

    async def _replacement_chunk_count(self, query: Dict[str, Any], expected: int) -> int:
        cursor = self.chunks_collection.find(query, {"_id": 1}).limit(expected + 1)
        documents = await cursor.to_list(length=expected + 1)
        return len(documents)

    async def _run_chunk_replacement(
        self,
        trace_doc: Dict[str, Any],
        marker: Dict[str, Any],
        *,
        staging_docs: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        trace_id = str(trace_doc.get("trace_id") or "")
        operation_id = marker.get("id")
        revision = marker.get("revision")
        staging_trace_id = marker.get("staging_trace_id")
        expected_chunk_count = marker.get("chunk_count")
        if (
            not trace_id
            or not isinstance(operation_id, str)
            or not isinstance(revision, int)
            or not isinstance(staging_trace_id, str)
            or not isinstance(expected_chunk_count, int)
            or expected_chunk_count < 0
        ):
            return False

        phase = marker.get("phase")
        if phase == "staging":
            if staging_docs is None or len(staging_docs) != expected_chunk_count:
                return False
            for document in staging_docs:
                await self.chunks_collection.replace_one(
                    {
                        "trace_id": staging_trace_id,
                        "chunk_index": document["chunk_index"],
                    },
                    document,
                    upsert=True,
                )
            if (
                await self._replacement_chunk_count(
                    {
                        "trace_id": staging_trace_id,
                        "replacement_operation_id": operation_id,
                    },
                    expected_chunk_count,
                )
                != expected_chunk_count
            ):
                raise RuntimeError("trace_chunk_replacement_staging_incomplete")
            current = await self._set_replacement_phase(
                trace_id,
                marker,
                expected_phase="staging",
                phase="staged",
            )
            if not current:
                return False
            marker = current[ATTACHMENT_CHUNK_WRITE_FIELD]
            phase = "staged"

        if phase == "staged":
            await self.chunks_collection.delete_many({"trace_id": trace_id})
            current = await self._set_replacement_phase(
                trace_id,
                marker,
                expected_phase="staged",
                phase="old_deleted",
            )
            if not current:
                return False
            marker = current[ATTACHMENT_CHUNK_WRITE_FIELD]
            phase = "old_deleted"

        if phase == "old_deleted":
            await self.chunks_collection.update_many(
                {
                    "trace_id": staging_trace_id,
                    "replacement_operation_id": operation_id,
                },
                {
                    "$set": {"trace_id": trace_id},
                    "$unset": {"attachment_chunk_staging": ""},
                },
            )
            if (
                await self._replacement_chunk_count(
                    {
                        "trace_id": trace_id,
                        "replacement_operation_id": operation_id,
                    },
                    expected_chunk_count,
                )
                != expected_chunk_count
            ):
                raise RuntimeError("trace_chunk_replacement_install_incomplete")
            current = await self._set_replacement_phase(
                trace_id,
                marker,
                expected_phase="old_deleted",
                phase="installed",
            )
            if not current:
                return False
            marker = current[ATTACHMENT_CHUNK_WRITE_FIELD]
            phase = "installed"

        if phase != "installed":
            return False
        raw_final_update_fields = marker.get("final_update_fields")
        if not isinstance(raw_final_update_fields, list):
            return False
        final_update: Dict[str, Any] = {}
        for item in raw_final_update_fields:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not item["path"]
                or "value" not in item
                or item["path"] in final_update
            ):
                return False
            final_update[item["path"]] = deepcopy(item["value"])
        update_doc: Dict[str, Any] = {
            "$set": {
                **final_update,
                "last_chunk_replace_operation_id": operation_id,
                "last_chunk_replace_digest": marker.get("digest"),
            },
            "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
        }
        if marker.get("remove_legacy_events") is True:
            update_doc["$unset"]["events"] = ""
        result = await self.collection.update_one(
            {
                "trace_id": trace_id,
                TRACE_EVENT_REVISION_FIELD: revision,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "installed",
            },
            update_doc,
        )
        if result.modified_count > 0:
            return True
        current = await self.collection.find_one({"trace_id": trace_id})
        return bool(
            current
            and current.get(ATTACHMENT_CHUNK_WRITE_FIELD) is None
            and current.get("last_chunk_replace_operation_id") == operation_id
            and current.get("last_chunk_replace_digest") == marker.get("digest")
        )

    async def recover_incomplete_chunk_replacements(self, limit: int = 100) -> int:
        """Recover expired durable replacements without touching an active writer."""
        recovered = 0
        now = utc_now()
        cursor = self.collection.find(
            {f"{ATTACHMENT_CHUNK_WRITE_FIELD}.kind": {"$in": ["replace", "append"]}}
        ).limit(max(int(limit or 0), 1))
        async for trace_doc in cursor:
            marker = trace_doc.get(ATTACHMENT_CHUNK_WRITE_FIELD)
            if not isinstance(marker, dict):
                continue
            # A marker with an unexpired lease belongs to a live writer and
            # must never be released here — releasing it would break the
            # append mutual exclusion and let two writers interleave.
            if not _marker_recovery_expired(marker.get("recovery_after"), now):
                continue
            if marker.get("kind") == "append":
                # An expired append marker means its writer is gone. Release
                # the marker so retries, complete_trace and the merger can
                # proceed; the reserved sequence range simply stays reserved.
                operation_id = marker.get("id")
                revision = marker.get("revision")
                if not isinstance(operation_id, str) or not isinstance(revision, int):
                    continue
                result = await self.collection.update_one(
                    {
                        "trace_id": trace_doc.get("trace_id"),
                        TRACE_EVENT_REVISION_FIELD: revision,
                        f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                        f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                    },
                    {
                        "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                        "$set": {"updated_at": utc_now()},
                    },
                )
                if result.modified_count > 0:
                    recovered += 1
                    # The writer is gone, so nothing will ever complete this
                    # trace; flip a lingering running status so the session
                    # read path stops hiding its non-user events behind an
                    # SSE replay that will never come.
                    await self.collection.update_one(
                        {
                            "trace_id": trace_doc.get("trace_id"),
                            "status": "running",
                        },
                        {
                            "$set": {"status": "completed", "updated_at": utc_now()},
                        },
                    )
                continue
            try:
                if marker.get("phase") == "staging":
                    operation_id = marker.get("id")
                    revision = marker.get("revision")
                    staging_trace_id = marker.get("staging_trace_id")
                    if (
                        not isinstance(operation_id, str)
                        or not isinstance(revision, int)
                        or not isinstance(staging_trace_id, str)
                    ):
                        continue
                    await self.chunks_collection.delete_many(
                        {
                            "trace_id": staging_trace_id,
                            "replacement_operation_id": operation_id,
                        }
                    )
                    result = await self.collection.update_one(
                        {
                            "trace_id": trace_doc.get("trace_id"),
                            TRACE_EVENT_REVISION_FIELD: revision,
                            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                            f"{ATTACHMENT_CHUNK_WRITE_FIELD}.phase": "staging",
                        },
                        {
                            "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                            "$set": {"updated_at": utc_now()},
                        },
                    )
                    recovered += int(result.modified_count > 0)
                    continue
                if await self._run_chunk_replacement(trace_doc, marker):
                    recovered += 1
            except Exception as exc:
                logger.warning(
                    "Failed to recover chunk replacement for trace %s: %s",
                    trace_doc.get("trace_id"),
                    exc,
                )
        return recovered

    async def replace_trace_events_with_chunks(
        self,
        trace_doc: Dict[str, Any],
        events: List[Dict[str, Any]],
        *,
        mark_storage_chunked: bool = True,
        remove_legacy_events: bool = True,
        parent_updates: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Replace all chunk docs for one trace with normalized event chunks."""
        trace_id = str(trace_doc.get("trace_id") or "")
        if not trace_id:
            return False

        now = utc_now()
        chunk_size = trace_storage_helpers._get_event_chunk_size()
        normalized_events: List[Dict[str, Any]] = []
        for index, event in enumerate(events, start=1):
            normalized_event = dict(event)
            normalized_event["seq"] = index
            normalized_events.append(normalized_event)

        replacement_digest = _replacement_digest(
            normalized_events,
            mark_storage_chunked=mark_storage_chunked,
            remove_legacy_events=remove_legacy_events,
            parent_updates=parent_updates,
        )
        first_user_message = next(
            (event for event in normalized_events if event.get("event_type") == "user:message"),
            None,
        )
        update_fields: Dict[str, Any] = {
            **(parent_updates or {}),
            "event_count": len(normalized_events),
            "chunk_count": (len(normalized_events) + chunk_size - 1) // chunk_size,
            "first_event_preview": trace_storage_helpers._event_preview(
                normalized_events[0] if normalized_events else None
            ),
            "first_user_message_preview": trace_storage_helpers._event_preview(first_user_message),
            "last_event_preview": trace_storage_helpers._event_preview(
                normalized_events[-1] if normalized_events else None
            ),
            "updated_at": now,
        }
        if mark_storage_chunked:
            update_fields["metadata.event_storage"] = "chunked"

        current = await self.collection.find_one({"trace_id": trace_id})
        current_marker = (current or {}).get(ATTACHMENT_CHUNK_WRITE_FIELD)
        if isinstance(current_marker, dict):
            if current_marker.get("kind") != "replace":
                return False
            if (
                current_marker.get("phase") == "staging"
                and current_marker.get("digest") != replacement_digest
            ):
                return False
            trace_doc = {**trace_doc, **(current or {})}
            marker = current_marker
        else:
            claim_trace_doc = {**(current or {}), **trace_doc}
            if (
                TRACE_EVENT_REVISION_FIELD not in trace_doc
                and current is not None
                and TRACE_EVENT_REVISION_FIELD in current
            ):
                claim_trace_doc[TRACE_EVENT_REVISION_FIELD] = current[TRACE_EVENT_REVISION_FIELD]
            claim = await self._claim_chunk_write(
                claim_trace_doc,
                kind="replace",
                marker_fields={
                    "phase": "staging",
                    "digest": replacement_digest,
                    "chunk_count": update_fields["chunk_count"],
                    "remove_legacy_events": remove_legacy_events,
                    "final_update_fields": [
                        {"path": path, "value": value} for path, value in update_fields.items()
                    ],
                },
            )
            if claim is None:
                return False
            _operation_id, claimed_trace = claim
            trace_doc = {**trace_doc, **claimed_trace}
            marker = claimed_trace[ATTACHMENT_CHUNK_WRITE_FIELD]

        staging_docs: List[Dict[str, Any]] | None = None
        if marker.get("phase") == "staging":
            operation_id = marker["id"]
            staging_trace_id = marker["staging_trace_id"]
            staging_docs = []
            for start in range(0, len(normalized_events), chunk_size):
                chunk_events = normalized_events[start : start + chunk_size]
                start_seq = int(chunk_events[0]["seq"])
                end_seq = int(chunk_events[-1]["seq"])
                staging_docs.append(
                    {
                        "trace_id": staging_trace_id,
                        "replacement_target_trace_id": trace_id,
                        "replacement_operation_id": operation_id,
                        "attachment_chunk_staging": True,
                        "session_id": trace_doc.get("session_id", ""),
                        "run_id": trace_doc.get("run_id", ""),
                        "trace_started_at": trace_doc.get("started_at"),
                        "chunk_index": trace_storage_helpers._event_chunk_index(start_seq),
                        "start_seq": start_seq,
                        "end_seq": end_seq,
                        "event_count": len(chunk_events),
                        "events": chunk_events,
                        "created_at": now,
                        "updated_at": now,
                    }
                )

        return await self._run_chunk_replacement(
            trace_doc,
            marker,
            staging_docs=staging_docs,
        )

    async def reserve_event_sequence_range(
        self,
        trace_id: str,
        event_count: int,
    ) -> Optional[Dict[str, Any]]:
        """Atomically reserve a range and fence its parent before chunk creation."""
        if event_count <= 0:
            return await self.collection.find_one({"trace_id": trace_id}, {"_id": 0})
        current = await self.collection.find_one({"trace_id": trace_id})
        if not current or current.get(ATTACHMENT_CHUNK_WRITE_FIELD) is not None:
            return None
        raw_revision = current.get(TRACE_EVENT_REVISION_FIELD)
        try:
            expected_revision = int(raw_revision or 0)
        except (TypeError, ValueError):
            return None
        claimed_revision = expected_revision + 1
        now = utc_now()
        operation_id = uuid.uuid4().hex
        query: Dict[str, Any] = {
            "trace_id": trace_id,
            ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
            TRACE_EVENT_REVISION_FIELD: (
                expected_revision if raw_revision is not None else {"$exists": False}
            ),
        }
        try:
            return await self.collection.find_one_and_update(
                query,
                {
                    "$inc": {
                        "event_count": event_count,
                        TRACE_EVENT_REVISION_FIELD: 1,
                    },
                    "$set": {
                        ATTACHMENT_CHUNK_WRITE_FIELD: {
                            "id": operation_id,
                            "kind": "append",
                            "revision": claimed_revision,
                            "recovery_after": now + timedelta(minutes=5),
                        },
                        "updated_at": now,
                    },
                },
                projection={"_id": 0},
                return_document=ReturnDocument.AFTER,
            )
        except BaseException:
            await _release_claimed_marker(self.collection, trace_id, operation_id)
            raise

    async def append_events_to_chunks(
        self,
        trace_doc: Dict[str, Any],
        events: List[Dict[str, Any]],
        start_seq: int,
    ) -> bool:
        """Append a reserved event batch to chunk documents."""
        trace_id = str(trace_doc.get("trace_id") or "")
        if not trace_id or not events:
            return False

        marker = trace_doc.get(ATTACHMENT_CHUNK_WRITE_FIELD)
        operation_id = marker.get("id") if isinstance(marker, dict) else None
        revision = marker.get("revision") if isinstance(marker, dict) else None
        marker_kind = marker.get("kind") if isinstance(marker, dict) else None
        if not isinstance(operation_id, str) or marker_kind != "append":
            claim = await self._claim_chunk_write(trace_doc, kind="append")
            if claim is None:
                return False
            operation_id, claimed_trace = claim
            trace_doc = {**trace_doc, **claimed_trace}
            marker = claimed_trace[ATTACHMENT_CHUNK_WRITE_FIELD]
            revision = marker.get("revision")
        if not isinstance(revision, int):
            return False

        now = utc_now()
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for offset, event in enumerate(events):
            seq = start_seq + offset
            normalized_event = dict(event)
            normalized_event["seq"] = seq
            grouped.setdefault(
                trace_storage_helpers._event_chunk_index(seq),
                [],
            ).append(normalized_event)

        try:
            for chunk_index in sorted(grouped):
                chunk_events = grouped[chunk_index]
                start = int(chunk_events[0]["seq"])
                end = int(chunk_events[-1]["seq"])
                existing_events_without_range = {
                    "$filter": {
                        "input": {"$ifNull": ["$events", []]},
                        "as": "event",
                        "cond": {
                            "$not": [
                                {
                                    "$and": [
                                        {"$gte": [{"$ifNull": ["$$event.seq", 0]}, start]},
                                        {"$lte": [{"$ifNull": ["$$event.seq", 0]}, end]},
                                    ]
                                }
                            ]
                        },
                    }
                }
                await self.chunks_collection.update_one(
                    {"trace_id": trace_id, "chunk_index": chunk_index},
                    [
                        {
                            "$set": {
                                "trace_id": trace_id,
                                "session_id": trace_doc.get("session_id", ""),
                                "run_id": trace_doc.get("run_id", ""),
                                "trace_started_at": trace_doc.get("started_at"),
                                "chunk_index": chunk_index,
                                "created_at": {"$ifNull": ["$created_at", now]},
                                "updated_at": now,
                                "start_seq": {
                                    "$min": [
                                        {"$ifNull": ["$start_seq", start]},
                                        start,
                                    ]
                                },
                                "end_seq": {
                                    "$max": [
                                        {"$ifNull": ["$end_seq", end]},
                                        end,
                                    ]
                                },
                                "events": {
                                    "$concatArrays": [
                                        existing_events_without_range,
                                        chunk_events,
                                    ]
                                },
                            }
                        },
                        {"$set": {"event_count": {"$size": "$events"}}},
                    ],
                    upsert=True,
                )

            end_seq = start_seq + len(events) - 1
            update_fields: Dict[str, Any] = {
                "updated_at": utc_now(),
                "metadata.event_storage": "chunked",
                "metadata.merged": False,
            }
            if start_seq == 1:
                update_fields["first_event_preview"] = trace_storage_helpers._event_preview(
                    events[0]
                )
                first_user_message = next(
                    (event for event in events if event.get("event_type") == "user:message"),
                    None,
                )
                if first_user_message is not None:
                    update_fields["first_user_message_preview"] = (
                        trace_storage_helpers._event_preview(first_user_message)
                    )
            try:
                reserved_event_count = int(trace_doc.get("event_count", 0))
            except (TypeError, ValueError):
                reserved_event_count = 0
            if reserved_event_count <= end_seq:
                update_fields["last_event_preview"] = trace_storage_helpers._event_preview(
                    events[-1]
                )

            result = await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    TRACE_EVENT_REVISION_FIELD: revision,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                },
                {
                    "$set": update_fields,
                    "$max": {"chunk_count": max(grouped) + 1},
                    "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                },
            )
            if result.modified_count > 0:
                return True
            # The final update can miss while our marker is still in place
            # (e.g. a concurrent revision bump raced the CAS). Re-check and
            # retry once instead of returning False with the marker left
            # behind, which would deadlock every later writer on this trace.
            current = await self.collection.find_one(
                {"trace_id": trace_id}, {ATTACHMENT_CHUNK_WRITE_FIELD: 1}
            )
            current_marker = (current or {}).get(ATTACHMENT_CHUNK_WRITE_FIELD)
            if (
                not isinstance(current_marker, dict)
                or current_marker.get("id") != operation_id
                or current_marker.get("revision") != revision
            ):
                return False
            retry = await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                },
                {
                    "$set": update_fields,
                    "$max": {"chunk_count": max(grouped) + 1},
                    "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                },
            )
            return retry.modified_count > 0
        except BaseException:
            # Emergency marker release. Match on the marker identity only: a
            # concurrent event_revision bump (complete_trace, recommend
            # questions, legacy appends) must not leave the marker stuck,
            # because a stuck marker fences every later chunk write and blocks
            # complete_trace, leaving the trace in status="running" where the
            # session read path hides all non-user events.
            released = await self.collection.update_one(
                {
                    "trace_id": trace_id,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                    f"{ATTACHMENT_CHUNK_WRITE_FIELD}.revision": revision,
                },
                {
                    "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                    "$set": {"updated_at": utc_now()},
                },
            )
            if getattr(released, "modified_count", 0) == 0:
                await self.collection.update_one(
                    {
                        "trace_id": trace_id,
                        f"{ATTACHMENT_CHUNK_WRITE_FIELD}.id": operation_id,
                    },
                    {
                        "$unset": {ATTACHMENT_CHUNK_WRITE_FIELD: ""},
                        "$set": {"updated_at": utc_now()},
                    },
                )
            raise
