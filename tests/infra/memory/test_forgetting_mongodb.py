"""Explicit deletion must suppress old automatic captures without touching other sources."""

import asyncio
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory import extraction
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.mark.parametrize("pause_at", ["model", "embedding", "commit", "long_commit", "legacy_job"])
async def test_forget_blocks_inflight_old_capture_and_future_old_transcript(monkeypatch, pause_at):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_forget_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=database_name)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(
        "src.infra.session.conversation_history.ConversationHistoryService.validate_source_refs",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "src.infra.memory.extraction_gate.evaluate_extraction_gate", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("src.infra.memory.extraction_gate.log_context_second_opinion", AsyncMock())
    entered, release = asyncio.Event(), asyncio.Event()
    remembered = (
        "Durable archival reference card. " * 200 if pause_at == "long_commit" else ""
    ) + "The user's old locker label was Orchid 731."
    payload = SimpleNamespace(
        content=json.dumps(
            {
                "memories": [
                    {
                        "raw_memory": remembered,
                        "context": "user",
                    }
                ]
            }
        )
    )

    async def model(*args, **kwargs):
        if pause_at in {"model", "legacy_job"}:
            entered.set()
            await release.wait()
        return payload

    async def embed(content):
        if pause_at == "embedding":
            entered.set()
            await release.wait()
        return None

    invoke = AsyncMock(side_effect=model)
    monkeypatch.setattr("src.infra.llm.retry.ainvoke_with_retry", invoke)
    backend._maybe_embed = embed
    task = None
    try:
        now = utc_now()
        await db.sessions.insert_many(
            [
                {"session_id": "source", "user_id": "owner", "name": "Locker", "metadata": {}},
                {
                    "session_id": "unrelated",
                    "user_id": "owner",
                    "name": "Answer preference",
                    "metadata": {},
                },
            ]
        )
        await db.traces.insert_many(
            [
                {
                    "session_id": "source",
                    "user_id": "owner",
                    "run_id": "old-run",
                    "status": "completed",
                    "started_at": now - timedelta(minutes=10),
                    "conversation_search": {
                        "user_text": "Remember my locker label: Orchid 731.",
                        "assistant_final_text": "Recorded.",
                    },
                },
                {
                    "session_id": "unrelated",
                    "user_id": "owner",
                    "run_id": "keep-run",
                    "status": "completed",
                    "started_at": now - timedelta(minutes=10),
                    "conversation_search": {
                        "user_text": "I prefer concise answers.",
                        "assistant_final_text": "Recorded.",
                    },
                },
            ]
        )
        await db.native_memories.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": "delete-me",
                    "content": "Locker label: Orchid 731.",
                    "origin_session_ids": ["source"],
                    "source": "auto_retained",
                    "updated_at": now,
                },
                {
                    "user_id": "owner",
                    "memory_id": "keep-me",
                    "content": "I prefer concise answers.",
                    "origin_session_ids": ["unrelated"],
                    "source": "auto_retained",
                    "updated_at": now,
                },
                {
                    "user_id": "other",
                    "memory_id": "foreign",
                    "content": "Another user's locker label.",
                    "origin_session_ids": ["source"],
                    "source": "auto_retained",
                    "updated_at": now,
                },
            ]
        )
        if pause_at == "legacy_job":
            await db.native_memories.update_one(
                {"memory_id": "delete-me"},
                {
                    "$unset": {"origin_session_ids": ""},
                    "$set": {"source_refs": None},
                },
            )
            await db.memory_extraction_jobs.insert_one(
                {
                    "user_id": "owner",
                    "session_id": "source",
                    "memory_ids": ["delete-me"],
                    "status": "claimed",
                    "attempts": 1,
                    "resume_state": {"payload": {"raw_memory": "Orchid 731"}},
                }
            )
        keep_before = await db.native_memories.find_one({"memory_id": "keep-me"})
        foreign_before = await db.native_memories.find_one({"memory_id": "foreign"})
        if pause_at in {"commit", "long_commit"}:

            class BarrierCollection:
                database = db

                def __getattr__(self, name):
                    return getattr(db.native_memories, name)

                async def insert_one(self, document):
                    entered.set()
                    await release.wait()
                    return await db.native_memories.insert_one(document)

                async def update_one(self, query, update, **kwargs):
                    if isinstance(update, list) and "$replaceWith" in update[0]:
                        entered.set()
                        await release.wait()
                    return await db.native_memories.update_one(query, update, **kwargs)

            backend._collection = BarrierCollection()
        source = {"session_id": "source", "name": "Locker", "metadata": {}}
        task = asyncio.create_task(extraction.extract_session_memory(backend, db, "owner", source))
        await asyncio.wait_for(entered.wait(), 5)
        assert (await backend.delete("owner", "delete-me"))["success"] is True
        if pause_at == "legacy_job":
            job = await db.memory_extraction_jobs.find_one(
                {"user_id": "owner", "session_id": "source"}
            )
            assert job.get("resume_state") is None and job.get("status") != "claimed"
        release.set()
        await asyncio.wait_for(task, 10)
        assert await db.native_memories.count_documents({"user_id": "owner"}) == 1
        assert backend._invalidate_cache.await_count == (
            2 if pause_at in {"commit", "long_commit"} else 1
        )
        if pause_at == "long_commit":
            assert await db.store.count_documents({}) == 0
        before_calls = invoke.await_count
        result = await extraction.extract_session_memory(backend, db, "owner", source)
        assert result.status == "succeeded_no_output"
        assert invoke.await_count == before_calls
        assert await db.native_memories.find_one({"memory_id": "keep-me"}) == keep_before
        assert await db.native_memories.find_one({"memory_id": "foreign"}) == foreign_before
        other_turns = await extraction.load_session_transcript(
            db, "unrelated", "owner", max_chars=1000
        )
        assert other_turns[0]["run_id"] == "keep-run"

        # A fresh user confirmation after deletion may be learned again.
        await db.traces.insert_one(
            {
                "session_id": "source",
                "user_id": "owner",
                "run_id": "new-run",
                "status": "completed",
                "started_at": utc_now() + timedelta(seconds=1),
                "conversation_search": {
                    "user_text": "Remember the new label: Cedar 942.",
                    "assistant_final_text": "Recorded.",
                },
            }
        )
        invoke.side_effect = None
        invoke.return_value = SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {
                            "raw_memory": "The user's new locker label is Cedar 942.",
                            "context": "user",
                        }
                    ]
                }
            )
        )
        backend._maybe_embed = AsyncMock(return_value=None)
        result = await extraction.extract_session_memory(backend, db, "owner", source)
        assert result.status == "succeeded"
        text = str(invoke.await_args.args[1][1].content)
        assert "Cedar 942" in text and "Orchid 731" not in text
    finally:
        release.set()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        await client.drop_database(database_name)
        await client.close()


async def test_compaction_pruning_is_not_forgetting_and_other_saved_facts_survive():
    from src.infra.memory.forgetting import source_watermark

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_forget_scope_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._invalidate_cache = AsyncMock()
    try:
        await db.native_memories.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": name,
                    "origin_session_ids": ["source"],
                    "revision_id": name,
                    "content_storage_mode": "inline",
                    "content": f"Durable {name} fact.",
                }
                for name in ["redundant", "forgotten", "keep"]
            ]
        )
        keep = await db.native_memories.find_one({"memory_id": "keep"})
        result = await backend.delete(
            "owner", "redundant", expected_revision={"revision_id": "redundant"}
        )
        assert result["success"] is True
        assert await source_watermark(db, "owner", "source") is None
        assert (await backend.delete("owner", "forgotten"))["success"] is True
        assert await source_watermark(db, "owner", "source") is not None
        assert await source_watermark(db, "other", "source") is None
        assert await db.native_memories.find_one({"memory_id": "keep"}) == keep
    finally:
        await client.drop_database(database_name)
        await client.close()
