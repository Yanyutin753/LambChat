"""Byte-bounded, reservation-local trace chunks; readers retain sequence ordering."""

from typing import Any

from bson import BSON

BYTE_CHUNK_LAYOUT = "bytes_v1"
_TARGET_BYTES = 8 * 1024 * 1024
_MAX_BYTES = 15 * 1024 * 1024  # Leave room for MongoDB and replacement metadata.


def byte_chunks(
    context: dict[str, Any], events: list[dict[str, Any]], *, target_bytes: int = _TARGET_BYTES
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    document: dict[str, Any] | None = None
    size = 0
    for event in events:
        seq = int(event["seq"])
        event_size = len(BSON.encode(event))
        if document is None or (document["events"] and size + event_size + 16 > target_bytes):
            document = {
                **context,
                "chunk_index": seq - 1,
                "start_seq": seq,
                "end_seq": seq,
                "event_count": 0,
                "events": [],
            }
            documents.append(document)
            size = len(BSON.encode(document))
        size += event_size + len(str(len(document["events"]))) + 2
        if size > _MAX_BYTES:
            raise ValueError(f"trace_event_document_too_large: seq={seq}, bytes={size}")
        document["events"].append(event)
        document["event_count"] += 1
        document["end_seq"] = seq
    return documents
