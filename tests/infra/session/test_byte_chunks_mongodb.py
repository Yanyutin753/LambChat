"""Opt-in real MongoDB regression for the 16 MiB incident (#1238)."""

import hashlib
import os
from uuid import uuid4

import pytest
from bson import BSON
from pymongo import AsyncMongoClient
from pymongo.errors import DocumentTooLarge, OperationFailure

from src.infra.session.trace_storage import TraceStorage, settings
from src.infra.utils.datetime import utc_now


@pytest.mark.skipif(
    not os.environ.get("LAMBCHAT_TEST_MONGODB_URL"),
    reason="requires an isolated MongoDB test service",
)
async def test_byte_chunks_survive_real_bson_limit_retry_read_replace_and_rollback(monkeypatch):
    client = AsyncMongoClient(
        os.environ["LAMBCHAT_TEST_MONGODB_URL"], serverSelectionTimeoutMS=10000
    )
    db_name = "lambchat_byte_chunk_test_" + uuid4().hex
    db = client[db_name]
    storage = TraceStorage()
    storage._collection, storage._chunks_collection = db.traces, db.chunks
    await db.chunks.create_index([("trace_id", 1), ("chunk_index", 1)], unique=True)
    events = [
        {"event_type": "tool:end", "data": {"text": str(i) * (5 * 1024 * 1024)}} for i in range(4)
    ]
    try:
        for trace_id, enabled in [("legacy", False), ("bounded", True)]:
            monkeypatch.setattr(settings, "SESSION_EVENT_BYTE_CHUNKS_ENABLED", enabled)
            await db.traces.insert_one(
                {
                    "trace_id": trace_id,
                    "session_id": "test",
                    "run_id": trace_id,
                    "event_count": 0,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            if not enabled:
                for seq, event in enumerate(events, 1):
                    reserved = await storage.reserve_event_sequence_range(trace_id, 1)
                    if seq < 4:
                        assert await storage.append_events_to_chunks(reserved, [event], seq)
                    else:
                        with pytest.raises((DocumentTooLarge, OperationFailure)) as error:
                            await storage.append_events_to_chunks(reserved, [event], seq)
                        assert (
                            "large" in str(error.value).lower()
                            or "size" in str(error.value).lower()
                        )
                continue
            reserved = await storage.reserve_event_sequence_range(trace_id, len(events))
            assert await storage.append_events_to_chunks(reserved, events, 1)
            current = await db.traces.find_one({"trace_id": trace_id})
            assert await storage.append_events_to_chunks(current, events, 1)
            read = await storage.read_trace_events_compat(trace_id)
            assert [event["seq"] for event in read] == [1, 2, 3, 4]
            assert [hashlib.sha256(event["data"]["text"].encode()).digest() for event in read] == [
                hashlib.sha256(event["data"]["text"].encode()).digest() for event in events
            ]
            current = await db.traces.find_one({"trace_id": trace_id})
            assert await storage.replace_trace_events_with_chunks(current, read)
            documents = await db.chunks.find({"trace_id": trace_id}).to_list()
            assert len(documents) == 4
            assert all(len(BSON.encode(document)) < 16 * 1024 * 1024 for document in documents)
            reserved = await storage.reserve_event_sequence_range(trace_id, 1)
            assert await storage.append_events_to_chunks(
                reserved, [{"event_type": "done", "data": {}}], 5
            )
            await storage.rollback_event_sequence_range(reserved, 5, 1)
            current = await db.traces.find_one({"trace_id": trace_id})
            assert current["event_count"] == 4
            assert current["chunk_count"] == 4
            assert [event["seq"] for event in await storage.read_trace_events_compat(trace_id)] == [
                1,
                2,
                3,
                4,
            ]
    finally:
        await client.drop_database(db_name)
        await client.close()
