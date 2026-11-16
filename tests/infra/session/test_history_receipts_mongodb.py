"""History must not decode the cumulative recovery ledger into API memory."""

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.session.trace_storage import TraceStorage
from src.infra.utils.datetime import utc_now


@pytest.mark.skipif(
    not os.environ.get("LAMBCHAT_TEST_MONGODB_URL"), reason="requires isolated MongoDB"
)
@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("active", [False, True])
async def test_history_excludes_receipts_but_recovery_keeps_full_ledger(chunked, active):
    client = AsyncMongoClient(os.environ["LAMBCHAT_TEST_MONGODB_URL"])
    name = "lambchat_history_receipts_test_" + uuid4().hex
    db = client[name]
    storage = TraceStorage()
    storage._collection, storage._chunks_collection = db.traces, db.chunks
    data = {
        "input_tokens": 123,
        "total_cost": 0.125,
        "cost_complete": False,
        "cost_receipts": {"call-1": {"model": "actual-model", "padding": "x" * 100_000}},
    }
    events = [
        {"seq": 1, "event_type": "token:usage", "data": data},
        {"seq": 2, "event_type": "tool:result", "data": {"cost_receipts": "user data"}},
    ]
    try:
        await db.traces.insert_one(
            {
                "trace_id": "trace",
                "session_id": "session",
                "run_id": "run",
                "status": "completed",
                "started_at": utc_now(),
                "updated_at": utc_now(),
                "events": [] if chunked else events,
            }
        )
        if chunked:
            await db.chunks.insert_one(
                {"trace_id": "trace", "chunk_index": 0, "start_seq": 1, "events": events}
            )
        if active:
            active_events = [
                {"seq": 1, "event_type": "user:message", "data": {"content": "new question"}},
                *events,
            ]
            await db.traces.insert_one(
                {
                    "trace_id": "active",
                    "session_id": "session",
                    "run_id": "active-run",
                    "status": "running",
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "events": [] if chunked else active_events,
                }
            )
            if chunked:
                await db.chunks.insert_one(
                    {
                        "trace_id": "active",
                        "chunk_index": 0,
                        "start_seq": 1,
                        "events": active_events,
                    }
                )
        snapshot = await storage.get_session_events_snapshot(
            "session", active_run_id="active-run" if active else None
        )
        if active:
            assert [e["event_type"] for e in snapshot.events if e["run_id"] == "active-run"] == [
                "user:message"
            ]
        usage = next(e for e in snapshot.events if e["event_type"] == "token:usage")
        assert usage["data"] == {k: v for k, v in data.items() if k != "cost_receipts"}
        tool = next(e for e in snapshot.events if e["event_type"] == "tool:result")
        assert tool["data"] == events[1]["data"]
        raw = await storage.read_trace_events_compat("trace")
        assert raw[0]["data"] == data
        batch = await storage.read_trace_events_batch_compat([await db.traces.find_one({})])
        assert batch["trace"][0]["data"] == data
    finally:
        await client.drop_database(name)
        await client.close()
