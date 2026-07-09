"""Chunked trace event storage helpers for TraceStorage."""

from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from src.infra.logging import get_logger
from src.infra.session import trace_storage as trace_storage_helpers
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)


class TraceEventChunkMixin:
    @property
    def collection(self) -> Any:
        raise NotImplementedError

    @property
    def chunks_collection(self) -> Any:
        raise NotImplementedError

    async def _has_event_chunks(self, trace_id: str) -> bool:
        try:
            chunk = await self.chunks_collection.find_one({"trace_id": trace_id}, {"_id": 1})
            return chunk is not None
        except Exception as e:
            logger.debug("Failed to probe trace event chunks for %s: %s", trace_id, e)
            return False

    async def read_trace_events_compat(
        self,
        trace_id: str,
        event_types: Optional[List[str]] = None,
        max_events: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read trace events from chunks when present, otherwise legacy traces.events."""
        event_types = trace_storage_helpers._bounded_unique_strings(
            event_types,
            trace_storage_helpers.SESSION_EVENT_FILTER_LIST_LIMIT,
        )
        allowed_types = set(event_types)
        if max_events is not None:
            max_events = trace_storage_helpers._clamp_event_read_limit(
                max_events,
                default=trace_storage_helpers.TRACE_EVENTS_DEFAULT_LIMIT,
            )
            if max_events <= 0:
                return []

        def _accepts(event: Dict[str, Any]) -> bool:
            return not allowed_types or event.get("event_type") in allowed_types

        events: List[Dict[str, Any]] = []
        if await self._has_event_chunks(trace_id):
            first_chunk = None
            first_chunk_cursor = (
                self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "start_seq": 1, "events.seq": 1},
                )
                .sort("chunk_index", 1)
                .limit(1)
            )
            async for chunk in first_chunk_cursor:
                first_chunk = chunk
                break
            first_chunk_start_seq = 1
            if first_chunk:
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            trace_storage_helpers._event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
            if first_chunk_start_seq > 1:
                trace_doc = await self.collection.find_one(
                    {"trace_id": trace_id},
                    {"_id": 0, "events": 1},
                )
                for index, event in enumerate((trace_doc or {}).get("events", []) or [], start=1):
                    if trace_storage_helpers._event_seq(event, index) >= first_chunk_start_seq:
                        continue
                    if not _accepts(event):
                        continue
                    events.append(event)
                    if max_events is not None and len(events) >= max_events:
                        return events

            cursor = self.chunks_collection.find(
                {"trace_id": trace_id},
                {"_id": 0, "events": 1, "chunk_index": 1},
            ).sort("chunk_index", 1)
            async for chunk in cursor:
                chunk_events = sorted(
                    enumerate(chunk.get("events", []) or []),
                    key=lambda item: trace_storage_helpers._event_seq(item[1], item[0]),
                )
                for _index, event in chunk_events:
                    if not _accepts(event):
                        continue
                    events.append(event)
                    if max_events is not None and len(events) >= max_events:
                        return events
            return events

        trace_doc = await self.collection.find_one(
            {"trace_id": trace_id},
            {"_id": 0, "events": 1},
        )
        for event in (trace_doc or {}).get("events", []) or []:
            if not _accepts(event):
                continue
            events.append(event)
            if max_events is not None and len(events) >= max_events:
                break
        return events

    async def replace_trace_events_with_chunks(
        self,
        trace_doc: Dict[str, Any],
        events: List[Dict[str, Any]],
        *,
        mark_storage_chunked: bool = True,
        remove_legacy_events: bool = True,
    ) -> None:
        """Replace all chunk docs for one trace with normalized event chunks."""
        trace_id = str(trace_doc.get("trace_id") or "")
        if not trace_id:
            return

        now = utc_now()
        chunk_size = trace_storage_helpers._get_event_chunk_size()
        normalized_events: List[Dict[str, Any]] = []
        for index, event in enumerate(events, start=1):
            normalized_event = dict(event)
            normalized_event["seq"] = index
            normalized_events.append(normalized_event)

        await self.chunks_collection.delete_many({"trace_id": trace_id})

        chunk_docs: List[Dict[str, Any]] = []
        for start in range(0, len(normalized_events), chunk_size):
            chunk_events = normalized_events[start : start + chunk_size]
            start_seq = int(chunk_events[0]["seq"])
            end_seq = int(chunk_events[-1]["seq"])
            chunk_docs.append(
                {
                    "trace_id": trace_id,
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

        if chunk_docs:
            await self.chunks_collection.insert_many(chunk_docs)

        first_user_message = next(
            (event for event in normalized_events if event.get("event_type") == "user:message"),
            None,
        )
        update_fields: Dict[str, Any] = {
            "event_count": len(normalized_events),
            "chunk_count": len(chunk_docs),
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

        update_doc: Dict[str, Any] = {"$set": update_fields}
        if remove_legacy_events:
            update_doc["$unset"] = {"events": ""}

        await self.collection.update_one(
            {"trace_id": trace_id},
            update_doc,
        )

    async def reserve_event_sequence_range(
        self,
        trace_id: str,
        event_count: int,
    ) -> Optional[Dict[str, Any]]:
        """Atomically reserve a contiguous event seq range by incrementing event_count."""
        if event_count <= 0:
            return await self.collection.find_one({"trace_id": trace_id}, {"_id": 0})
        now = utc_now()
        return await self.collection.find_one_and_update(
            {"trace_id": trace_id},
            {
                "$inc": {"event_count": event_count},
                "$set": {"updated_at": now},
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )

    async def append_events_to_chunks(
        self,
        trace_doc: Dict[str, Any],
        events: List[Dict[str, Any]],
        start_seq: int,
    ) -> None:
        """Append a reserved event batch to chunk documents."""
        trace_id = str(trace_doc.get("trace_id") or "")
        if not trace_id or not events:
            return

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
            "updated_at": now,
            "metadata.event_storage": "chunked",
        }
        if start_seq == 1:
            update_fields["first_event_preview"] = trace_storage_helpers._event_preview(events[0])
        if start_seq == 1:
            first_user_message = next(
                (event for event in events if event.get("event_type") == "user:message"),
                None,
            )
            if first_user_message is not None:
                update_fields["first_user_message_preview"] = trace_storage_helpers._event_preview(
                    first_user_message
                )

        await self.collection.update_one(
            {"trace_id": trace_id},
            {
                "$set": update_fields,
                "$max": {"chunk_count": max(grouped) + 1},
            },
        )
        await self.collection.update_one(
            {
                "trace_id": trace_id,
                "$or": [
                    {"event_count": {"$lte": end_seq}},
                    {"event_count": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "last_event_preview": trace_storage_helpers._event_preview(events[-1]),
                    "updated_at": now,
                }
            },
        )

    async def rollback_event_sequence_range(
        self,
        trace_doc: Dict[str, Any],
        start_seq: int,
        event_count: int,
    ) -> None:
        """Undo a reserved chunk sequence range after a failed append attempt."""
        trace_id = str(trace_doc.get("trace_id") or "")
        event_count = max(int(event_count or 0), 0)
        if not trace_id or event_count <= 0:
            return

        now = utc_now()
        try:
            reserved_end_count = int(trace_doc.get("event_count", 0))
        except (TypeError, ValueError):
            reserved_end_count = 0
        end_seq = start_seq + event_count - 1
        chunk_size = trace_storage_helpers._get_event_chunk_size()
        start_chunk = trace_storage_helpers._event_chunk_index(start_seq)
        end_chunk = trace_storage_helpers._event_chunk_index(end_seq)
        for chunk_index in range(start_chunk, end_chunk + 1):
            chunk_start_seq = chunk_index * chunk_size + 1
            chunk_end_seq = chunk_start_seq + chunk_size - 1
            remove_start_seq = max(start_seq, chunk_start_seq)
            remove_end_seq = min(end_seq, chunk_end_seq)
            remove_count = remove_end_seq - remove_start_seq + 1
            seq_filter = {"$gte": remove_start_seq, "$lte": remove_end_seq}
            await self.chunks_collection.update_one(
                {
                    "trace_id": trace_id,
                    "chunk_index": chunk_index,
                    "events.seq": seq_filter,
                },
                {
                    "$pull": {"events": {"seq": seq_filter}},
                    "$inc": {"event_count": -remove_count},
                    "$set": {"updated_at": now},
                },
            )
        await self.collection.update_one(
            {"trace_id": trace_id, "event_count": reserved_end_count},
            {
                "$inc": {"event_count": -event_count},
                "$set": {"updated_at": now},
            },
        )
