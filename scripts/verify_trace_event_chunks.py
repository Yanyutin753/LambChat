from __future__ import annotations

import argparse
import asyncio
from typing import Any


def _event_signature(event: dict[str, Any] | None) -> tuple[Any, Any, Any] | None:
    if not event:
        return None
    return (
        event.get("event_type"),
        event.get("data", {}),
        event.get("timestamp"),
    )


def compare_trace_events(
    legacy_events: list[dict[str, Any]],
    chunk_events: list[dict[str, Any]],
    *,
    event_types: list[str] | None = None,
) -> list[str]:
    mismatches: list[str] = []
    if event_types:
        allowed = set(event_types)
        legacy_events = [event for event in legacy_events if event.get("event_type") in allowed]
        chunk_events = [event for event in chunk_events if event.get("event_type") in allowed]

    if len(legacy_events) != len(chunk_events):
        mismatches.append(f"event_count legacy={len(legacy_events)} chunk={len(chunk_events)}")
    if _event_signature(legacy_events[0] if legacy_events else None) != _event_signature(
        chunk_events[0] if chunk_events else None
    ):
        mismatches.append("first_event mismatch")
    if _event_signature(legacy_events[-1] if legacy_events else None) != _event_signature(
        chunk_events[-1] if chunk_events else None
    ):
        mismatches.append("last_event mismatch")
    return mismatches


async def read_chunk_events(trace_storage: Any, trace_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = trace_storage.chunks_collection.find(
        {"trace_id": trace_id},
        {"_id": 0, "events": 1, "chunk_index": 1},
    ).sort("chunk_index", 1)
    async for chunk in cursor:
        chunk_events = sorted(
            enumerate(chunk.get("events", []) or []),
            key=lambda item: item[1].get("seq", item[0]),
        )
        events.extend(event for _index, event in chunk_events)
    return events


async def verify_trace(trace_storage: Any, trace_id: str, event_types: list[str]) -> list[str]:
    trace_doc = await trace_storage.collection.find_one(
        {"trace_id": trace_id},
        {"_id": 0, "events": 1},
    )
    legacy_events = list((trace_doc or {}).get("events") or [])
    chunk_events = await read_chunk_events(trace_storage, trace_id)
    return compare_trace_events(
        legacy_events,
        chunk_events,
        event_types=event_types or None,
    )


async def run_verification(args: argparse.Namespace) -> int:
    from src.infra.session.trace_storage import get_trace_storage

    storage = get_trace_storage()
    event_types = [item for item in args.event_types.split(",") if item]
    mismatches = await verify_trace(storage, args.trace_id, event_types)
    if mismatches:
        print({"trace_id": args.trace_id, "mismatches": mismatches})
        return 1
    print({"trace_id": args.trace_id, "status": "ok"})
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify legacy trace events against chunks.")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--event-types", default="")
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(run_verification(parse_args())))


if __name__ == "__main__":
    main()
