from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_chunk_docs(
    trace_doc: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    chunk_size: int,
) -> list[dict[str, Any]]:
    trace_id = str(trace_doc.get("trace_id") or "")
    size = max(int(chunk_size or 0), 1)
    now = _utc_now()
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        item = dict(event)
        item["seq"] = index
        normalized.append(item)

    chunks: list[dict[str, Any]] = []
    for offset in range(0, len(normalized), size):
        chunk_events = normalized[offset : offset + size]
        start_seq = int(chunk_events[0]["seq"])
        end_seq = int(chunk_events[-1]["seq"])
        chunks.append(
            {
                "trace_id": trace_id,
                "session_id": trace_doc.get("session_id", ""),
                "run_id": trace_doc.get("run_id", ""),
                "trace_started_at": trace_doc.get("started_at"),
                "chunk_index": (start_seq - 1) // size,
                "start_seq": start_seq,
                "end_seq": end_seq,
                "event_count": len(chunk_events),
                "events": chunk_events,
                "created_at": now,
                "updated_at": now,
            }
        )
    return chunks


async def migrate_trace_doc(
    trace_storage: Any,
    trace_doc: dict[str, Any],
    *,
    dry_run: bool,
    remove_legacy_events: bool,
) -> dict[str, Any]:
    trace_id = str(trace_doc.get("trace_id") or "")
    events = list(trace_doc.get("events") or [])
    result = {"trace_id": trace_id, "event_count": len(events), "dry_run": dry_run}
    if dry_run:
        return result

    await trace_storage.replace_trace_events_with_chunks(
        trace_doc,
        events,
        remove_legacy_events=remove_legacy_events,
    )
    return result


async def run_migration(args: argparse.Namespace) -> None:
    from src.infra.session.trace_storage import get_trace_storage

    storage = get_trace_storage()
    query: dict[str, Any] = {"events": {"$exists": True}}
    if args.trace_id:
        query["trace_id"] = args.trace_id
    if args.session_id:
        query["session_id"] = args.session_id

    cursor = storage.collection.find(query).limit(max(int(args.batch_size), 1))
    migrated = 0
    async for trace_doc in cursor:
        summary = await migrate_trace_doc(
            storage,
            trace_doc,
            dry_run=args.dry_run,
            remove_legacy_events=args.remove_legacy_events,
        )
        migrated += 1
        print(summary)
    print({"migrated": migrated, "dry_run": args.dry_run})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy trace events into chunks.")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--trace-id", default="")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove-legacy-events", action="store_true")
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_migration(parse_args()))


if __name__ == "__main__":
    main()
