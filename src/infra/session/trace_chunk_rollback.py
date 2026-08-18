"""Rollback helper for reserved chunk sequence ranges.

Split out of ``trace_event_chunks`` to keep that module within the
1000-line backend source limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.infra.session import trace_storage as trace_storage_helpers
from src.infra.utils.datetime import utc_now

ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
TRACE_EVENT_REVISION_FIELD = "event_revision"


class TraceChunkRollbackMixin:
    """Undo reserved chunk sequence ranges after failed append attempts."""

    if TYPE_CHECKING:
        collection: Any
        chunks_collection: Any

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
            {
                "trace_id": trace_id,
                "event_count": reserved_end_count,
                ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
            },
            {
                "$inc": {
                    "event_count": -event_count,
                    TRACE_EVENT_REVISION_FIELD: 1,
                },
                "$set": {"updated_at": now},
            },
        )
