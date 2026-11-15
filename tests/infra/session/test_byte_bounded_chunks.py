"""Byte limits must protect storage without truncating event payloads."""

import pytest
from bson import BSON


def test_splits_by_encoded_bytes_and_preserves_payloads():
    from src.infra.session.trace_byte_chunks import byte_chunks

    events = [{"seq": i, "data": "字" * 100} for i in range(1, 7)]
    documents = byte_chunks(
        {"trace_id": "trace", "session_id": "session"}, events, target_bytes=1000
    )
    assert len(documents) > 1
    assert [event for doc in documents for event in doc["events"]] == events
    assert all(len(BSON.encode(doc)) <= 1000 for doc in documents)
    assert [doc["chunk_index"] for doc in documents] == [doc["start_seq"] - 1 for doc in documents]


def test_single_large_event_is_kept_intact_and_impossible_document_fails_before_writing():
    from src.infra.session.trace_byte_chunks import byte_chunks

    event = {"seq": 1, "data": "x" * 2000}
    assert byte_chunks({"trace_id": "trace"}, [event], target_bytes=1000)[0]["events"] == [event]
    with pytest.raises(ValueError, match="trace_event_document_too_large"):
        byte_chunks({"trace_id": "trace"}, [{"seq": 1, "data": "x" * (16 * 1024 * 1024)}])


async def test_new_trace_selects_byte_layout_and_retries_do_not_duplicate_events(monkeypatch):
    from src.infra.session.trace_storage import TraceStorage, settings
    from tests.infra.session.test_trace_event_chunks import (
        _FakeChunkCollection,
        _FakeTraceCollection,
        _trace_document,
    )

    monkeypatch.setattr(settings, "SESSION_EVENT_BYTE_CHUNKS_ENABLED", True, raising=False)
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(_trace_document())
    storage._chunks_collection = _FakeChunkCollection()
    trace = await storage.reserve_event_sequence_range("trace-1", 3)
    assert trace["metadata"]["event_chunk_layout"] == "bytes_v1"
    events = [{"event_type": "tool:end", "data": "x" * (5 * 1024 * 1024)} for _ in range(3)]
    assert await storage.append_events_to_chunks(trace, events, 1)
    retry_trace = await storage.collection.find_one({"trace_id": "trace-1"})
    assert await storage.append_events_to_chunks(retry_trace, events, 1)
    docs = sorted(storage.chunks_collection.chunks, key=lambda d: d["chunk_index"])
    assert len(docs) == 3
    assert [e["seq"] for d in docs for e in d["events"]] == [1, 2, 3]
    assert all(len(BSON.encode(d)) < 16 * 1024 * 1024 for d in docs)
    assert storage.collection.trace_doc["chunk_count"] == 3
    assert storage.chunks_collection.find_count == 0


async def test_existing_trace_keeps_legacy_layout_on_activation(monkeypatch):
    from src.infra.session.trace_storage import TraceStorage, settings
    from tests.infra.session.test_trace_event_chunks import _FakeTraceCollection, _trace_document

    monkeypatch.setattr(settings, "SESSION_EVENT_BYTE_CHUNKS_ENABLED", True, raising=False)
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(_trace_document(event_count=500))
    trace = await storage.reserve_event_sequence_range("trace-1", 1)
    assert (trace.get("metadata") or {}).get("event_chunk_layout") is None


async def test_replacement_keeps_byte_layout_and_reader_order():
    from src.infra.session.trace_storage import TraceStorage
    from tests.infra.session.test_trace_event_chunks import (
        _FakeChunkCollection,
        _FakeTraceCollection,
        _trace_document,
    )

    storage = TraceStorage()
    trace = _trace_document(metadata={"event_chunk_layout": "bytes_v1"})
    storage._collection = _FakeTraceCollection(trace)
    storage._chunks_collection = _FakeChunkCollection()
    events = [{"event_type": "tool:end", "data": "x" * (5 * 1024 * 1024)} for _ in range(4)]
    assert await storage.replace_trace_events_with_chunks(trace, events)
    docs = sorted(storage.chunks_collection.chunks, key=lambda d: d["chunk_index"])
    assert len(docs) == 4
    assert [doc["chunk_index"] for doc in docs] == [0, 1, 2, 3]
    assert all(len(BSON.encode(doc)) < 16 * 1024 * 1024 for doc in docs)
    assert storage.collection.trace_doc["chunk_count"] == 4


async def test_byte_layout_rollback_removes_only_reserved_batch():
    from src.infra.session.trace_storage import TraceStorage
    from tests.infra.session.test_trace_event_chunks import (
        _FakeChunkCollection,
        _FakeTraceCollection,
        _trace_document,
    )

    storage = TraceStorage()
    trace = _trace_document(event_count=6, metadata={"event_chunk_layout": "bytes_v1"})
    storage._collection = _FakeTraceCollection(trace)
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": start - 1,
                "start_seq": start,
                "end_seq": start + 1,
                "events": [{"seq": start}, {"seq": start + 1}],
                "event_count": 2,
            }
            for start in [1, 3, 5]
        ]
    )
    await storage.rollback_event_sequence_range(trace, 3, 4)
    assert [doc["start_seq"] for doc in storage.chunks_collection.chunks] == [1]
    assert storage.collection.trace_doc["event_count"] == 2
    assert storage.collection.trace_doc["chunk_count"] == 1


def test_parent_preview_is_bounded_without_truncating_the_stored_event():
    from src.infra.session._trace_storage_support import _event_preview

    event = {
        "event_type": "user:message",
        "seq": 1,
        "data": {"content": "字" * 100000, "attachments": [{"raw": "x" * 100000}]},
    }
    preview = _event_preview(event)
    assert len(BSON.encode(preview)) < 16 * 1024
    assert preview["data"]["content"] == "字" * 4096
    assert len(event["data"]["content"]) == 100000
    assert event["data"]["attachments"][0]["raw"] == "x" * 100000
