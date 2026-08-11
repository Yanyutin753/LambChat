from typing import Any

_MISSING = object()

PARENT_CLEANUP_VERSION_FIELDS = ("event_revision", "updated_at")
CHUNK_CLEANUP_VERSION_FIELDS = (
    "append_fence_revision",
    "event_count",
    "updated_at",
)


async def snapshot_trace_cleanup_documents(
    collection: Any,
    query: dict[str, Any],
    version_fields: tuple[str, ...],
) -> list[dict[str, Any]] | None:
    """Freeze exact Mongo identities and versions for a guarded delete."""
    projection = {
        "_id": 1,
        "session_id": 1,
        "trace_id": 1,
        **dict.fromkeys(version_fields, 1),
    }
    documents = await collection.find(query, projection).to_list(length=None)
    snapshots: list[dict[str, Any]] = []
    for document in documents:
        document_id = document.get("_id", _MISSING)
        session_id = document.get("session_id", _MISSING)
        trace_id = document.get("trace_id", _MISSING)
        if document_id is _MISSING or session_id is _MISSING or trace_id is _MISSING:
            return None
        snapshot = {
            "_id": document_id,
            "session_id": session_id,
            "trace_id": trace_id,
        }
        for field in version_fields:
            snapshot[field] = document[field] if field in document else {"$exists": False}
        snapshots.append(snapshot)
    return snapshots
