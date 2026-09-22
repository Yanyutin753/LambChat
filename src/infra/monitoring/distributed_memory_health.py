"""Distributed memory health snapshot helpers."""

from __future__ import annotations

import json
import os
import socket
import time
from collections import deque
from datetime import date, datetime, timezone
from hashlib import sha1
from typing import Any, Mapping

from src.infra.async_utils.blocking import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
_INSTANCE_KEY_PREFIX = "health:memory:instance:"
_PROCESS_SEED = f"{socket.gethostname()}:{os.getpid()}:{time.time_ns()}"
_INSTANCE_ID = sha1(_PROCESS_SEED.encode("utf-8")).hexdigest()[:12]
CLUSTER_SNAPSHOT_SCAN_LIMIT = 100


def _to_redis_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {str(key): _to_redis_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, deque)):
        return [_to_redis_safe(item) for item in value]
    return str(value)


def _sort_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(snapshots, key=lambda item: str(item.get("instance_id") or ""))


def _normalize_instance_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _is_valid_snapshot_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if _normalize_instance_id(payload.get("instance_id")) is None:
        return False
    summary = payload.get("summary")
    return summary is None or isinstance(summary, Mapping)


def _normalize_row(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return {}


def _normalize_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _normalize_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **snapshot,
        "instance_id": _normalize_instance_id(snapshot.get("instance_id")),
        "summary": _normalize_summary(snapshot.get("summary")),
    }


async def _json_dumps_snapshot(snapshot: Mapping[str, Any]) -> str:
    return await run_long_blocking_io(json.dumps, snapshot)


async def _json_loads_snapshot(raw_value: str) -> Any:
    return await run_long_blocking_io(json.loads, raw_value)


def _captured_at_order_key(snapshot: Mapping[str, Any]) -> tuple[int, float, str]:
    captured_at = snapshot.get("captured_at")
    if isinstance(captured_at, str):
        try:
            parsed = datetime.fromisoformat(captured_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return (2, parsed.timestamp(), captured_at)
        except ValueError:
            return (1, 0.0, captured_at)
    return (0, 0.0, "")


def _normalize_detail_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple, set, deque)):
        return []
    return [_normalize_row(row) for row in value]


def _normalize_details(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "top_growth": _normalize_detail_rows(value.get("top_growth")),
        "top_allocations": _normalize_detail_rows(value.get("top_allocations")),
        "top_object_types": _normalize_detail_rows(value.get("top_object_types")),
        "top_objects": _normalize_detail_rows(value.get("top_objects")),
    }


def _format_mb(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{round(value / 1024 / 1024, 2)}MB"


def _build_memory_overview(summary: Mapping[str, Any]) -> dict[str, Any]:
    status = "unavailable"
    if summary.get("available"):
        status = "suspected_leak" if summary.get("suspected_leak") else "stable"

    return {
        "status": status,
        "rss": _format_mb(summary.get("rss_bytes")),
        "vms": _format_mb(summary.get("vms_bytes")),
        "growth": _format_mb(summary.get("growth_bytes")),
        "threads": summary.get("thread_count"),
        "open_files": summary.get("open_file_count"),
        "history_size": summary.get("history_size"),
        "last_sample_at": summary.get("last_sample_at"),
    }


def _build_highlight_items(
    summary: Mapping[str, Any],
    details: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not summary.get("available"):
        return [{"kind": "unavailable", "reason": summary.get("reason", "unknown")}]

    highlights: list[dict[str, Any]] = [
        {
            "kind": "status",
            "status": "suspected_leak" if summary.get("suspected_leak") else "stable",
            "severity": "warning" if summary.get("suspected_leak") else "info",
        }
    ]

    growth_rows = (details or {}).get("top_growth") or []
    if growth_rows:
        top = _normalize_row(growth_rows[0])
        if top.get("location") is not None and top.get("size_diff_bytes") is not None:
            highlights.append(
                {
                    "kind": "top_growth",
                    "location": top.get("location"),
                    "size_diff": _format_mb(top.get("size_diff_bytes")) or "N/A",
                }
            )

    allocation_rows = (details or {}).get("top_allocations") or []
    if allocation_rows:
        top = _normalize_row(allocation_rows[0])
        if top.get("location") is not None and top.get("size_bytes") is not None:
            highlights.append(
                {
                    "kind": "top_allocation",
                    "location": top.get("location"),
                    "size": _format_mb(top.get("size_bytes")) or "N/A",
                }
            )

    object_rows = (
        (details or {}).get("top_object_types") or (details or {}).get("top_objects") or []
    )
    if object_rows:
        top = _normalize_row(object_rows[0])
        if top.get("type") is not None and top.get("count") is not None:
            highlights.append(
                {
                    "kind": "top_object_type",
                    "type": top.get("type"),
                    "count": top.get("count"),
                }
            )

    return highlights


def _format_growth_rows(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            **row_data,
            "size_diff": _format_mb(row_data.get("size_diff_bytes")),
        }
        for row_data in (_normalize_row(row) for row in (rows or []))
    ]


def _format_allocation_rows(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            **row_data,
            "size": _format_mb(row_data.get("size_bytes")),
        }
        for row_data in (_normalize_row(row) for row in (rows or []))
    ]


def _format_object_rows(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            **row_data,
            "label": (
                f"{row_data.get('type')}={row_data.get('count')}"
                if row_data.get("type") is not None and row_data.get("count") is not None
                else None
            ),
        }
        for row_data in (_normalize_row(row) for row in (rows or []))
    ]


def get_instance_id() -> str:
    """Return a stable instance identifier for the current process."""
    return _INSTANCE_ID


def build_instance_key(instance_id: str) -> str:
    """Build the Redis key for one instance memory snapshot."""
    return f"{_INSTANCE_KEY_PREFIX}{instance_id}"


def calculate_snapshot_ttl(interval_seconds: float) -> int:
    """Derive a Redis TTL from the monitor interval."""
    return max(int(interval_seconds * 2), 120)


def build_instance_snapshot(
    *,
    instance_id: str | None = None,
    captured_at: Any | None = None,
    summary: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Redis-safe snapshot for one process instance."""
    normalized_summary = _normalize_summary(summary)
    normalized_details = _normalize_details(details)
    snapshot = {
        "instance_id": _normalize_instance_id(instance_id) or get_instance_id(),
        "captured_at": captured_at if captured_at is not None else utc_now(),
        "summary": normalized_summary,
        "overview": _build_memory_overview(normalized_summary),
        "highlights": _build_highlight_items(normalized_summary, normalized_details),
        "top_growth": _format_growth_rows(normalized_details.get("top_growth")),
        "top_allocations": _format_allocation_rows(normalized_details.get("top_allocations")),
        "top_objects": _format_object_rows(
            normalized_details.get("top_object_types") or normalized_details.get("top_objects")
        ),
    }
    return _to_redis_safe(snapshot)


async def publish_instance_snapshot(
    snapshot: Mapping[str, Any],
    *,
    interval_seconds: float,
    redis_client: Any | None = None,
) -> dict[str, Any]:
    """Publish one instance snapshot into Redis with a short-lived TTL."""
    client = redis_client or get_redis_client()
    serialized_snapshot = _to_redis_safe(dict(snapshot))
    instance_id = (
        _normalize_instance_id(serialized_snapshot.get("instance_id")) or get_instance_id()
    )
    serialized_snapshot["instance_id"] = instance_id
    payload = await _json_dumps_snapshot(serialized_snapshot)
    await client.set(
        build_instance_key(instance_id),
        payload,
        ex=calculate_snapshot_ttl(interval_seconds),
    )
    return serialized_snapshot


async def _scan_keys(
    client: Any,
    pattern: str,
    *,
    count: int = 100,
    limit: int = CLUSTER_SNAPSHOT_SCAN_LIMIT,
) -> list[str]:
    """Collect matching Redis keys with SCAN to avoid blocking Redis."""
    cursor: int | str = 0
    keys: list[str] = []
    while True:
        cursor, batch = await client.scan(cursor=cursor, match=pattern, count=count)
        for key in batch:
            keys.append(str(key))
            if len(keys) >= limit:
                logger.warning(
                    "[DistributedMemoryHealth] reached cluster snapshot scan limit: %d",
                    limit,
                )
                return keys
        if int(cursor) == 0:
            return keys


async def load_cluster_snapshots(*, redis_client: Any | None = None) -> list[dict[str, Any]]:
    """Load all known instance snapshots from Redis."""
    client = redis_client or get_redis_client()
    try:
        keys = await _scan_keys(client, f"{_INSTANCE_KEY_PREFIX}*")
        snapshots_by_instance_id: dict[str, dict[str, Any]] = {}
        for key in sorted(keys):
            try:
                raw_value = await client.get(key)
            except Exception as exc:
                logger.warning(
                    "[DistributedMemoryHealth] skipping unreadable cluster snapshot key=%s: %s",
                    key,
                    exc,
                )
                continue
            if not raw_value:
                continue
            try:
                if isinstance(raw_value, bytes):
                    raw_value = raw_value.decode("utf-8", errors="replace")
                payload = await _json_loads_snapshot(raw_value)
            except (TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "[DistributedMemoryHealth] skipping malformed cluster snapshot key=%s: %s",
                    key,
                    exc,
                )
                continue
            if _is_valid_snapshot_payload(payload):
                normalized_payload = _normalize_snapshot_payload(payload)
                instance_id = str(normalized_payload["instance_id"])
                existing_payload = snapshots_by_instance_id.get(instance_id)
                if existing_payload is None or _captured_at_order_key(
                    normalized_payload
                ) >= _captured_at_order_key(existing_payload):
                    snapshots_by_instance_id[instance_id] = normalized_payload
            else:
                logger.warning(
                    "[DistributedMemoryHealth] skipping invalid cluster snapshot key=%s",
                    key,
                )
        return _sort_snapshots(list(snapshots_by_instance_id.values()))
    except Exception as exc:
        logger.warning("[DistributedMemoryHealth] failed to load cluster snapshots: %s", exc)
        return []


def select_instance_snapshot(
    snapshots: list[dict[str, Any]],
    *,
    requested_instance_id: str | None = None,
    local_instance_id: str | None = None,
) -> dict[str, Any] | None:
    """Select a specific, local, or deterministic fallback instance snapshot."""
    ordered_snapshots = _sort_snapshots(
        [
            _normalize_snapshot_payload(snapshot)
            for snapshot in snapshots
            if _is_valid_snapshot_payload(snapshot)
        ]
    )
    normalized_requested_id = _normalize_instance_id(requested_instance_id)
    normalized_local_id = _normalize_instance_id(local_instance_id)

    if normalized_requested_id:
        for snapshot in ordered_snapshots:
            if snapshot.get("instance_id") == normalized_requested_id:
                return snapshot

    if normalized_local_id:
        for snapshot in ordered_snapshots:
            if snapshot.get("instance_id") == normalized_local_id:
                return snapshot

    if ordered_snapshots:
        return ordered_snapshots[0]
    return None


def build_cluster_overview(
    snapshots: list[dict[str, Any]],
    *,
    requested_instance_id: str | None = None,
    local_instance_id: str | None = None,
) -> dict[str, Any]:
    """Aggregate instance snapshots into a small cluster overview."""
    normalized_snapshots = [
        _normalize_snapshot_payload(snapshot)
        for snapshot in snapshots
        if _is_valid_snapshot_payload(snapshot)
    ]
    ordered_snapshots = _sort_snapshots(normalized_snapshots)
    selected_snapshot = select_instance_snapshot(
        ordered_snapshots,
        requested_instance_id=requested_instance_id,
        local_instance_id=local_instance_id,
    )

    return {
        "instance_count": len(ordered_snapshots),
        "available_instance_count": sum(
            bool((snapshot.get("summary") or {}).get("available")) for snapshot in ordered_snapshots
        ),
        "suspected_leak_count": sum(
            bool((snapshot.get("summary") or {}).get("suspected_leak"))
            for snapshot in ordered_snapshots
        ),
        "local_instance_id": local_instance_id,
        "selected_instance_id": (
            str(selected_snapshot.get("instance_id")) if selected_snapshot else None
        ),
        "selected_instance": selected_snapshot,
        "instances": ordered_snapshots,
    }
