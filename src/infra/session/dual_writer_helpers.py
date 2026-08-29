"""Pure batching helpers for the MongoDB side of DualEventWriter."""

from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

MongoBufferItem = tuple[Any, ...]
_ATTACHMENT_CHUNK_WRITE_FIELD = "attachment_chunk_write_operation"
_TRACE_EVENT_REVISION_FIELD = "event_revision"


def _build_mongo_bulk_operations(
    batch: list[MongoBufferItem],
    *,
    now: datetime,
    max_events: int,
) -> list[UpdateOne]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    trace_context: dict[str, tuple[str, Optional[str]]] = {}

    for item in batch:
        if _buffer_item_skip_legacy(item):
            continue
        trace_id, event_type, data, session_id, run_id, timestamp = _buffer_item_base(item)
        grouped[trace_id].append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
        if trace_id not in trace_context:
            trace_context[trace_id] = (session_id, run_id)

    operations: list[UpdateOne] = []
    for trace_id, events in grouped.items():
        session_id, run_id = trace_context.get(trace_id, ("", None))
        operations.append(
            UpdateOne(
                {
                    "trace_id": trace_id,
                    _ATTACHMENT_CHUNK_WRITE_FIELD: {"$exists": False},
                },
                {
                    "$push": {
                        "events": {
                            "$each": events,
                            "$slice": -max_events,
                        }
                    },
                    "$inc": {
                        "event_count": len(events),
                        _TRACE_EVENT_REVISION_FIELD: 1,
                    },
                    "$set": {
                        "updated_at": now,
                        "metadata.merged": False,
                    },
                    "$setOnInsert": {
                        "session_id": session_id,
                        "run_id": run_id or "",
                        "status": "running",
                        "started_at": now,
                    },
                },
                upsert=True,
            )
        )
    return operations


def _buffer_item_base(
    item: MongoBufferItem,
) -> tuple[str, str, dict, str, Optional[str], datetime]:
    trace_id, event_type, data, session_id, run_id, timestamp = item[:6]
    return trace_id, event_type, data, session_id, run_id, timestamp


def _buffer_item_reserved_start_seq(item: MongoBufferItem) -> int | None:
    if len(item) < 7 or item[6] is None:
        return None
    return int(item[6])


def _buffer_item_skip_legacy(item: MongoBufferItem) -> bool:
    return bool(len(item) >= 8 and item[7])


def _buffer_item_skip_chunk(item: MongoBufferItem) -> bool:
    return bool(len(item) >= 9 and item[8])


def _buffer_item_attempts(item: MongoBufferItem) -> int:
    if len(item) < 10 or item[9] is None:
        return 0
    return int(item[9])


def _with_chunk_retry_metadata(
    item: MongoBufferItem,
    *,
    reserved_start_seq: int,
    skip_legacy: bool,
    skip_chunk: bool = False,
) -> MongoBufferItem:
    base = (*_buffer_item_base(item), reserved_start_seq, skip_legacy)
    attempts = _buffer_item_attempts(item) + 1
    return (*base, skip_chunk, attempts)


def _sanitize_event_data_for_mongo(obj: Any) -> Any:
    """Rewrite dict keys that MongoDB update pipelines cannot store.

    Chunked event writes build pipeline ``$set`` updates, which reject field
    names containing '.', leading '$', or empty strings — patterns that occur
    in external tool output (e.g. scraped structured content). Clean subtrees
    are returned as-is (identity preserved) so normal events pay no copy cost.
    """
    if isinstance(obj, dict):
        changed = False
        new_dict: dict[Any, Any] = {}
        for key, value in obj.items():
            safe_key = _sanitize_mongo_key(key)
            new_value = _sanitize_event_data_for_mongo(value)
            changed = changed or safe_key != key or new_value is not value
            new_dict[safe_key] = new_value
        return new_dict if changed else obj
    if isinstance(obj, list):
        changed = False
        items: list[Any] = []
        for value in obj:
            new_value = _sanitize_event_data_for_mongo(value)
            changed = changed or new_value is not value
            items.append(new_value)
        return items if changed else obj
    return obj


def _sanitize_mongo_key(key: Any) -> Any:
    key = key if isinstance(key, str) else str(key)
    safe = key.replace(".", "_")
    if safe.startswith("$"):
        safe = f"_{safe[1:]}"
    return safe or "_"


def _group_mongo_buffer_events(
    batch: list[MongoBufferItem],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in batch:
        trace_id, event_type, data, _session_id, _run_id, timestamp = _buffer_item_base(item)
        grouped[trace_id].append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
    return grouped


def _operation_trace_id(operation: Any) -> str | None:
    try:
        return operation._filter.get("trace_id")  # type: ignore[attr-defined]
    except AttributeError:
        return None


def _failed_bulk_write_trace_ids(
    error: BulkWriteError,
    operations: list[UpdateOne],
) -> set[str] | None:
    failed_trace_ids: set[str] = set()
    for write_error in error.details.get("writeErrors", []) or []:
        try:
            index = int(write_error.get("index"))
        except (TypeError, ValueError):
            return None
        if index < 0 or index >= len(operations):
            return None
        trace_id = _operation_trace_id(operations[index])
        if trace_id is None:
            return None
        failed_trace_ids.add(trace_id)
    return failed_trace_ids or None


def _iter_chunk_write_groups(
    batch: list[MongoBufferItem],
) -> list[tuple[str, list[MongoBufferItem], list[dict[str, Any]], int | None]]:
    groups: list[tuple[str, list[MongoBufferItem], list[dict[str, Any]], int | None]] = []
    current_trace_id: str | None = None
    current_reserved_start_seq: int | None = None
    current_items: list[MongoBufferItem] = []
    current_events: list[dict[str, Any]] = []

    def flush_current() -> None:
        nonlocal current_trace_id, current_reserved_start_seq, current_items, current_events
        if current_trace_id is not None and current_items:
            groups.append(
                (
                    current_trace_id,
                    current_items,
                    current_events,
                    current_reserved_start_seq,
                )
            )
        current_trace_id = None
        current_reserved_start_seq = None
        current_items = []
        current_events = []

    for item in batch:
        if _buffer_item_skip_chunk(item):
            continue
        trace_id, event_type, data, _session_id, _run_id, timestamp = _buffer_item_base(item)
        reserved_start_seq = _buffer_item_reserved_start_seq(item)
        if current_items and (
            trace_id != current_trace_id or reserved_start_seq != current_reserved_start_seq
        ):
            flush_current()
        current_trace_id = trace_id
        current_reserved_start_seq = reserved_start_seq
        current_items.append(item)
        current_events.append(
            {
                "event_type": event_type,
                "data": data,
                "timestamp": timestamp,
            }
        )
    flush_current()
    return groups
