from __future__ import annotations

import pytest

from scripts.migrate_trace_events_to_chunks import build_chunk_docs, migrate_trace_doc
from scripts.verify_trace_event_chunks import compare_trace_events, verify_trace


def _event(event_type: str, content: str, seq: int | None = None) -> dict:
    event = {
        "event_type": event_type,
        "data": {"content": content},
        "timestamp": f"t-{content}",
    }
    if seq is not None:
        event["seq"] = seq
    return event


def test_build_chunk_docs_splits_legacy_events_with_continuous_seq() -> None:
    chunks = build_chunk_docs(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "started_at": "started",
        },
        [_event("message", "a"), _event("message", "b"), _event("done", "z")],
        chunk_size=2,
    )

    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1]
    assert [event["seq"] for chunk in chunks for event in chunk["events"]] == [1, 2, 3]
    assert chunks[0]["start_seq"] == 1
    assert chunks[1]["end_seq"] == 3


def test_compare_trace_events_reports_mismatched_counts_and_last_event() -> None:
    mismatches = compare_trace_events(
        [_event("message", "a"), _event("done", "legacy")],
        [_event("message", "a"), _event("done", "chunked"), _event("extra", "x")],
    )

    assert "event_count legacy=2 chunk=3" in mismatches
    assert any(item.startswith("last_event mismatch") for item in mismatches)


@pytest.mark.asyncio
async def test_migrate_trace_doc_dry_run_does_not_write() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.calls = []

        async def replace_trace_events_with_chunks(self, trace_doc, events):
            self.calls.append((trace_doc, events))

    storage = _Storage()
    result = await migrate_trace_doc(
        storage,
        {"trace_id": "trace-1", "events": [_event("message", "a")]},
        dry_run=True,
        remove_legacy_events=False,
    )

    assert result == {"trace_id": "trace-1", "event_count": 1, "dry_run": True}
    assert storage.calls == []


@pytest.mark.asyncio
async def test_migrate_trace_doc_preserves_legacy_events_until_requested() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.calls = []

        async def replace_trace_events_with_chunks(self, trace_doc, events, **kwargs):
            self.calls.append((trace_doc, events, kwargs))

    storage = _Storage()
    result = await migrate_trace_doc(
        storage,
        {"trace_id": "trace-1", "events": [_event("message", "a")]},
        dry_run=False,
        remove_legacy_events=False,
    )

    assert result == {"trace_id": "trace-1", "event_count": 1, "dry_run": False}
    assert storage.calls[0][2] == {"remove_legacy_events": False}


@pytest.mark.asyncio
async def test_verify_trace_reports_missing_chunks_without_legacy_fallback() -> None:
    class _TraceCollection:
        async def find_one(self, query, projection):
            del query, projection
            return {"events": [_event("message", "legacy")]}

    class _ChunkCursor:
        def sort(self, key, direction):
            del key, direction
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _ChunkCollection:
        def find(self, query, projection):
            del query, projection
            return _ChunkCursor()

    class _Storage:
        collection = _TraceCollection()
        chunks_collection = _ChunkCollection()

    mismatches = await verify_trace(_Storage(), "trace-1", [])

    assert "event_count legacy=1 chunk=0" in mismatches
