"""Old foreground memories need source recovery from successful owned tool receipts."""

import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory import extraction
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.forgetting import source_watermark
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

require_mongo = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@require_mongo
@pytest.mark.parametrize("memory_id", ["legacy-memory", 'legacy"memory', "記憶\\memory"])
@pytest.mark.parametrize("layout", ["inline", "chunked", "serialized", "serialized_utf8"])
@pytest.mark.parametrize("lineage", ["empty", "partial"])
async def test_legacy_foreground_receipt_blocks_old_source_relearning(
    monkeypatch, layout, memory_id, lineage
):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_legacy_source_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._invalidate_cache = AsyncMock()
    no_model = AsyncMock(side_effect=AssertionError("Forgotten old source must not call a model"))
    monkeypatch.setattr(extraction, "_get_extraction_model", no_model)
    old = utc_now() - timedelta(hours=1)
    result = {"success": True, "memory_id": memory_id}
    event = {
        "event_type": "tool:result",
        "data": {
            "tool": "memory_retain",
            "success": True,
            "result": json.dumps(result, ensure_ascii=layout != "serialized_utf8")
            if layout.startswith("serialized")
            else result,
        },
    }
    try:
        await db.sessions.insert_many(
            [
                {"user_id": owner, "session_id": sid}
                for owner, sid in [
                    ("owner", "old-source"),
                    ("foreign", "foreign-source"),
                    ("owner", "quoted-source"),
                    ("owner", "failed-source"),
                    ("owner", "known-origin"),
                    ("owner", "known-reference"),
                    ("owner", "known-job"),
                ]
            ]
        )
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": memory_id,
                "revision_id": "r1",
                "content_storage_mode": "inline",
                "content": "Cabinet label: Fern 517.",
                "source": "auto_retained",
                "origin_session_ids": ["known-origin"] if lineage == "partial" else [],
                "source_refs": [{"session_id": "known-reference", "run_id": "known-run"}]
                if lineage == "partial"
                else [],
            }
        )
        if lineage == "partial":
            await db.memory_extraction_jobs.insert_one(
                {"user_id": "owner", "session_id": "known-job", "memory_ids": [memory_id]}
            )
        await db[settings.MONGODB_TRACES_COLLECTION].insert_one(
            {
                "user_id": "owner",
                "trace_id": "old-trace",
                "session_id": "old-source",
                "status": "completed",
                "run_id": "old-run",
                "started_at": old,
                "conversation_search": {
                    "user_text": "Remember cabinet label Fern 517.",
                    "assistant_final_text": "Recorded.",
                },
                "events": [] if layout == "chunked" else [event],
            }
        )
        if layout == "chunked":
            await db[settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION].insert_one(
                {
                    "trace_id": "old-trace",
                    "chunk_index": 0,
                    "events": [event],
                }
            )
        await db[settings.MONGODB_TRACES_COLLECTION].insert_many(
            [
                {
                    "user_id": "foreign",
                    "trace_id": "foreign-trace",
                    "session_id": "foreign-source",
                    "events": [event],
                },
                {
                    "user_id": "owner",
                    "trace_id": "quoted-trace",
                    "session_id": "quoted-source",
                    "events": [
                        {"event_type": "user:message", "data": {"content": json.dumps(result)}}
                    ],
                },
                {
                    "user_id": "owner",
                    "trace_id": "failed-trace",
                    "session_id": "failed-source",
                    "events": [
                        {
                            "event_type": "tool:result",
                            "data": {"tool": "memory_retain", "success": False, "result": result},
                        }
                    ],
                },
            ]
        )
        assert (await backend.delete("owner", memory_id))["success"]
        assert await source_watermark(db, "owner", "old-source") is not None
        for known in ("known-origin", "known-reference", "known-job"):
            assert (await source_watermark(db, "owner", known) is not None) is (
                lineage == "partial"
            )
        assert await source_watermark(db, "foreign", "foreign-source") is None
        assert await source_watermark(db, "owner", "quoted-source") is None
        assert await source_watermark(db, "owner", "failed-source") is None
        outcome = await extraction.extract_session_memory(
            backend, db, "owner", {"session_id": "old-source"}
        )
        assert outcome.status == "succeeded_no_output"
        no_model.assert_not_awaited()
        watermarks = await db.memory_forget_watermarks.find({}).to_list(length=10)
        assert all("Fern" not in json.dumps(row, default=str) for row in watermarks)
    finally:
        await client.drop_database(name)
        await client.close()


@pytest.mark.parametrize(
    "change",
    [
        "valid",
        "serialized",
        "numeric_event_success",
        "numeric_result_success",
        "wrong_tool",
        "wrong_id",
        "quoted_id",
        "invalid_json",
    ],
)
def test_only_exact_successful_retain_receipts_establish_a_source(change):
    from src.infra.memory.forgetting import _successful_retain_receipt

    result = {"success": True, "memory_id": "memory"}
    data = {"tool": "memory_retain", "success": True, "result": result}
    if change == "serialized":
        data["result"] = json.dumps(result)
    elif change == "numeric_event_success":
        data["success"] = 1
    elif change == "numeric_result_success":
        result["success"] = 1
    elif change == "wrong_tool":
        data["tool"] = "memory_recall"
    elif change == "wrong_id":
        result["memory_id"] = "memory-copy"
    elif change == "quoted_id":
        data["result"] = json.dumps({"success": True, "content": json.dumps(result)})
    elif change == "invalid_json":
        data["result"] = "not JSON"
    event = {"event_type": "tool:result", "data": data}
    assert _successful_retain_receipt(event, "memory") is (change in {"valid", "serialized"})


@require_mongo
async def test_failed_legacy_source_lookup_keeps_the_memory(monkeypatch):
    from src.infra.memory import forgetting

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_legacy_source_error_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(
        forgetting,
        "_legacy_foreground_sources",
        AsyncMock(side_effect=RuntimeError("source lookup unavailable")),
    )
    try:
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": "legacy",
                "content_storage_mode": "inline",
                "content": "Retained body",
                "revision_id": "r1",
            }
        )
        with pytest.raises(RuntimeError, match="source lookup unavailable"):
            await backend.delete("owner", "legacy")
        assert await db.native_memories.count_documents({"memory_id": "legacy"}) == 1
        assert await db.memory_forget_watermarks.count_documents({}) == 0
        backend._invalidate_cache.assert_not_awaited()
    finally:
        await client.drop_database(name)
        await client.close()
