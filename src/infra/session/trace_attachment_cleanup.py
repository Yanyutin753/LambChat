"""Strict attachment-cleanup reads and CAS deletion for trace storage."""

from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from src.infra.session._trace_storage_support import (
    SESSION_EVENT_FILTER_LIST_LIMIT,
    _bounded_unique_strings,
    _event_seq,
)
from src.infra.session.trace_event_chunks import ATTACHMENT_CHUNK_WRITE_FIELD

ATTACHMENT_CLEAR_TERMINAL_STATUSES = ("completed", "error")


class TraceAttachmentCleanupMixin:
    """Destructive attachment-cleanup behavior composed into TraceStorage."""

    if TYPE_CHECKING:
        collection: Any
        chunks_collection: Any

    async def iter_session_events_for_cleanup(
        self,
        session_id: str,
        *,
        event_types: Optional[List[str]] = None,
        cutoff: Any = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Strictly stream session events for destructive lifecycle operations.

        Unlike the legacy read API, this path propagates storage failures so a
        caller cannot mistake an unavailable trace store for an empty session.
        It yields one trace at a time rather than materializing the session's
        complete event history.
        """
        allowed_types = set(_bounded_unique_strings(event_types, SESSION_EVENT_FILTER_LIST_LIMIT))
        query: Dict[str, Any] = {"session_id": session_id}
        if cutoff is not None:
            query["started_at"] = {"$lte": cutoff}
        cursor = self.collection.find(
            query,
            {
                "_id": 0,
                "trace_id": 1,
                "run_id": 1,
                "started_at": 1,
                "events": 1,
            },
        ).sort("started_at", 1)

        async for trace in cursor:
            trace_id = str(trace.get("trace_id") or "")
            if not trace_id:
                continue
            first_chunk = None
            first_chunk_cursor = (
                self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "chunk_index": 1, "start_seq": 1, "events": 1},
                )
                .sort("chunk_index", 1)
                .limit(1)
            )
            async for chunk in first_chunk_cursor:
                first_chunk = chunk
                break

            if first_chunk:
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            _event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
                for index, event in enumerate(trace.get("events", []) or [], start=1):
                    if _event_seq(event, index) >= first_chunk_start_seq:
                        continue
                    if allowed_types and event.get("event_type") not in allowed_types:
                        continue
                    yield {
                        "trace_id": trace_id,
                        "run_id": trace.get("run_id"),
                        "event_type": event.get("event_type"),
                        "data": event.get("data", {}),
                        "timestamp": event.get("timestamp"),
                        **({"seq": event["seq"]} if "seq" in event else {}),
                    }
                async for chunk in self.chunks_collection.find(
                    {"trace_id": trace_id},
                    {"_id": 0, "chunk_index": 1, "events": 1},
                ).sort("chunk_index", 1):
                    for _index, event in sorted(
                        enumerate(chunk.get("events", []) or []),
                        key=lambda item: _event_seq(item[1], item[0]),
                    ):
                        if allowed_types and event.get("event_type") not in allowed_types:
                            continue
                        yield {
                            "trace_id": trace_id,
                            "run_id": trace.get("run_id"),
                            "event_type": event.get("event_type"),
                            "data": event.get("data", {}),
                            "timestamp": event.get("timestamp"),
                            **({"seq": event["seq"]} if "seq" in event else {}),
                        }
                continue
            else:
                events = trace.get("events", []) or []
            for event in events:
                if allowed_types and event.get("event_type") not in allowed_types:
                    continue
                yield {
                    "trace_id": trace_id,
                    "run_id": trace.get("run_id"),
                    "event_type": event.get("event_type"),
                    "data": event.get("data", {}),
                    "timestamp": event.get("timestamp"),
                    **({"seq": event["seq"]} if "seq" in event else {}),
                }

    async def snapshot_session_traces_for_cleanup(
        self, session_id: str, cutoff: Any
    ) -> dict[str, Any]:
        """Capture versioned terminal parents and directly discoverable orphan chunks."""
        eligible_query = {
            "session_id": session_id,
            "status": {"$in": list(ATTACHMENT_CLEAR_TERMINAL_STATUSES)},
            "updated_at": {"$lte": cutoff},
            ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
        }
        cursor = self.collection.find(
            eligible_query,
            {
                "_id": 1,
                "trace_id": 1,
                "run_id": 1,
                "status": 1,
                "updated_at": 1,
                "events": 1,
            },
        )
        parents = await cursor.to_list(length=None)
        all_parent_docs = await self.collection.find(
            {"session_id": session_id},
            {"_id": 1, "trace_id": 1},
        ).to_list(length=None)
        all_parent_trace_ids = {
            str(doc["trace_id"]) for doc in all_parent_docs if doc.get("trace_id")
        }
        trace_ids = [str(doc["trace_id"]) for doc in parents if doc.get("trace_id")]
        chunks = await self.chunks_collection.find(
            {
                "session_id": session_id,
                "updated_at": {"$lte": cutoff},
                "attachment_chunk_staging": {"$ne": True},
            },
            {
                "_id": 1,
                "trace_id": 1,
                "chunk_index": 1,
                "start_seq": 1,
                "updated_at": 1,
                "events": 1,
            },
        ).to_list(length=None)
        events: list[dict] = []
        chunks_by_trace: dict[str, list[dict]] = {}
        for chunk in chunks:
            chunks_by_trace.setdefault(str(chunk.get("trace_id") or ""), []).append(chunk)
        groups: list[dict[str, Any]] = []
        selected_chunk_ids: list[Any] = []
        for parent_index, parent in enumerate(parents):
            trace_id = str(parent.get("trace_id") or "")
            trace_chunks = sorted(
                chunks_by_trace.get(trace_id, []),
                key=lambda chunk: int(chunk.get("chunk_index") or 0),
            )
            parent_group_id = f"parent-{parent_index}"
            parent_events: list[dict]
            if not trace_chunks:
                parent_events = list(parent.get("events") or [])
            else:
                first_chunk = trace_chunks[0]
                first_chunk_start_seq = int(
                    first_chunk.get("start_seq")
                    or min(
                        (
                            _event_seq(event, index + 1)
                            for index, event in enumerate(first_chunk.get("events", []) or [])
                        ),
                        default=1,
                    )
                )
                parent_events = [
                    event
                    for index, event in enumerate(parent.get("events") or [], start=1)
                    if _event_seq(event, index) < first_chunk_start_seq
                ]
            events.extend(parent_events)
            groups.append(
                {
                    "id": parent_group_id,
                    "kind": "parent",
                    "document_id": parent["_id"],
                    "trace_id": trace_id,
                    "updated_at": parent.get("updated_at"),
                    "terminal_status": parent.get("status"),
                    "events": parent_events,
                }
            )
            for chunk_index, chunk in enumerate(trace_chunks):
                chunk_events = [
                    event
                    for _index, event in sorted(
                        enumerate(chunk.get("events") or []),
                        key=lambda item: _event_seq(item[1], item[0]),
                    )
                ]
                events.extend(chunk_events)
                selected_chunk_ids.append(chunk["_id"])
                groups.append(
                    {
                        "id": f"parent-{parent_index}-chunk-{chunk_index}",
                        "kind": "chunk",
                        "document_id": chunk["_id"],
                        "trace_id": trace_id,
                        "updated_at": chunk.get("updated_at"),
                        "parent_group_id": parent_group_id,
                        "events": chunk_events,
                    }
                )

        orphan_index = 0
        eligible_trace_ids = set(trace_ids)
        for chunk in chunks:
            trace_id = str(chunk.get("trace_id") or "")
            if trace_id in eligible_trace_ids or trace_id in all_parent_trace_ids:
                continue
            chunk_events = [
                event
                for _index, event in sorted(
                    enumerate(chunk.get("events") or []),
                    key=lambda item: _event_seq(item[1], item[0]),
                )
            ]
            events.extend(chunk_events)
            selected_chunk_ids.append(chunk["_id"])
            groups.append(
                {
                    "id": f"orphan-chunk-{orphan_index}",
                    "kind": "chunk",
                    "document_id": chunk["_id"],
                    "trace_id": trace_id,
                    "updated_at": chunk.get("updated_at"),
                    "events": chunk_events,
                }
            )
            orphan_index += 1
        return {
            "parent_ids": [doc["_id"] for doc in parents],
            "chunk_ids": selected_chunk_ids,
            "trace_ids": trace_ids,
            "events": events,
            "groups": groups,
        }

    async def delete_session_traces_strict(
        self, session_id: str, *, trace_ids: list[str], cutoff: Any
    ) -> int:
        """Delete all session traces and verify the destructive postcondition."""
        query = {
            "session_id": session_id,
            "trace_id": {"$in": trace_ids},
            "started_at": {"$lte": cutoff},
        }
        cursor = self.collection.find(
            query,
            {"_id": 0, "trace_id": 1},
        )
        trace_docs = await cursor.to_list(length=None)
        trace_ids = [trace.get("trace_id") for trace in trace_docs if trace.get("trace_id")]
        if trace_ids:
            await self.chunks_collection.delete_many({"trace_id": {"$in": trace_ids}})
        await self.chunks_collection.delete_many(
            {"session_id": session_id, "trace_started_at": {"$lte": cutoff}}
        )
        result = await self.collection.delete_many(query)
        if await self.collection.find_one(query, {"_id": 1}):
            raise RuntimeError(f"session_trace_delete_incomplete: {session_id}")
        if await self.chunks_collection.find_one(
            {"session_id": session_id, "trace_started_at": {"$lte": cutoff}}, {"_id": 1}
        ):
            raise RuntimeError(f"session_chunk_delete_incomplete: {session_id}")
        return result.deleted_count

    async def delete_attachment_clear_group(
        self,
        session_id: str,
        group: dict[str, Any],
    ) -> str:
        """CAS-delete one persisted parent or chunk snapshot group."""
        kind = group.get("kind")
        document_id = group.get("document_id")
        updated_at = group.get("updated_at")
        trace_id = str(group.get("trace_id") or "")
        query: dict[str, Any] = {
            "_id": document_id,
            "session_id": session_id,
            "updated_at": updated_at,
        }
        if trace_id:
            query["trace_id"] = trace_id
        if kind == "parent":
            terminal_status = group.get("terminal_status")
            if terminal_status not in ATTACHMENT_CLEAR_TERMINAL_STATUSES:
                raise ValueError("attachment_clear_parent_status_invalid")
            query["status"] = terminal_status
            query[ATTACHMENT_CHUNK_WRITE_FIELD] = {"$exists": False}
            collection = self.collection
        elif kind == "chunk":
            collection = self.chunks_collection
        else:
            raise ValueError("attachment_clear_group_kind_invalid")

        result = await collection.delete_many(query)
        if result.deleted_count > 0:
            return "deleted"
        survivor = await collection.find_one({"_id": document_id}, {"_id": 1})
        return "survivor" if survivor else "deleted"

    async def has_session_trace_documents(self, session_id: str) -> bool:
        """Return whether any parent or directly session-scoped chunk survives."""
        if await self.collection.find_one({"session_id": session_id}, {"_id": 1}):
            return True
        return bool(await self.chunks_collection.find_one({"session_id": session_id}, {"_id": 1}))
