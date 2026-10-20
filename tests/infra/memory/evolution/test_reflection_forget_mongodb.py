"""An offline reflection may not resurrect a deleted source or consume foreign events."""

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.evolution import reflector
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.mark.parametrize("pause_at", ["before", "lookup", "model", "embedding", "commit"])
async def test_reflection_cannot_relearn_a_forgotten_source(monkeypatch, pause_at):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_reflection_forget_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(reflector.settings, "MONGODB_DB", database_name)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    entered, release = asyncio.Event(), asyncio.Event()
    lesson = "rule: Keep replies short for routine questions.\nwhy: User prefers a direct answer.\nhow_to_apply: Start with the result."
    response = SimpleNamespace(
        tool_calls=[
            {
                "name": "memory_retain",
                "args": {
                    "content": lesson,
                    "title": "Direct answers",
                    "summary": "Prefers short answers",
                    "tags": ["answers"],
                },
            }
        ]
    )

    async def invoke(*args, **kwargs):
        if pause_at == "model":
            entered.set()
            await release.wait()
        return response

    async def embed(_content):
        if (pause_at == "embedding" and _content == lesson) or (
            pause_at == "lookup" and _content != lesson
        ):
            entered.set()
            await release.wait()
        return None

    backend._get_memory_model = AsyncMock(
        return_value=SimpleNamespace(bind_tools=lambda tools: object())
    )
    backend._maybe_embed = embed
    if pause_at == "lookup":

        async def pending_lookup(*args, **kwargs):
            entered.set()
            await release.wait()
            return {"memories": []}

        monkeypatch.setattr("src.infra.memory.client.native.search.recall_memories", pending_lookup)
    model = AsyncMock(side_effect=invoke)
    monkeypatch.setattr("src.infra.llm.retry.ainvoke_with_retry", model)
    task = None
    try:
        await db.sessions.insert_one({"session_id": "source", "user_id": "owner"})
        await db.traces.insert_one(
            {
                "run_id": "old",
                "session_id": "source",
                "user_id": "owner",
                "started_at": utc_now() - timedelta(minutes=5),
                "status": "completed",
                "events": [
                    {
                        "type": "user:message",
                        "data": {"content": "Give concise answers to routine questions."},
                    },
                    {
                        "type": "message:chunk",
                        "data": {"text_id": "answer", "content": "A very long answer."},
                    },
                ],
            }
        )
        await db.native_memories.insert_many(
            [
                {
                    "user_id": owner,
                    "memory_id": mid,
                    "origin_session_ids": ["source"],
                    "content": lesson,
                    "source": "self_evolved",
                    "content_storage_mode": "inline",
                    "revision_id": mid,
                }
                for owner, mid in [("owner", "delete-me"), ("other", "foreign")]
            ]
        )
        foreign = await db.native_memories.find_one({"memory_id": "foreign"})
        if pause_at == "commit":

            class BarrierCollection:
                database = db

                def __getattr__(self, name):
                    return getattr(db.native_memories, name)

                async def insert_one(self, document):
                    entered.set()
                    await release.wait()
                    return await db.native_memories.insert_one(document)

            backend._collection = BarrierCollection()
        signal = reflector.SignalRun(
            run_id="old", session_id="source", kind="down", comment="Too verbose"
        )
        if pause_at == "before":
            assert (await backend.delete("owner", "delete-me"))["success"]
            outcome = await reflector.reflect_on_run(backend, "owner", signal)
        else:
            task = asyncio.create_task(reflector.reflect_on_run(backend, "owner", signal))
            await asyncio.wait_for(entered.wait(), 5)
            assert (await backend.delete("owner", "delete-me"))["success"]
            release.set()
            outcome = await asyncio.wait_for(task, 10)
        assert outcome == {"stored": 0}
        assert await db.native_memories.count_documents({"user_id": "owner"}) == 0
        assert await db.native_memories.find_one({"memory_id": "foreign"}) == foreign
        if pause_at in {"before", "lookup"}:
            model.assert_not_awaited()
        else:
            assert model.await_count == 1
        calls = model.await_count
        assert await reflector.reflect_on_run(backend, "owner", signal) == {"stored": 0}
        assert model.await_count == calls
        # A genuinely new confirmation after forgetting remains eligible.
        await db.traces.insert_one(
            {
                "run_id": "new",
                "session_id": "source",
                "user_id": "owner",
                "started_at": utc_now() + timedelta(seconds=1),
                "events": [
                    {
                        "type": "user:message",
                        "data": {"content": "I confirm: keep routine answers brief."},
                    },
                ],
            }
        )
        backend._maybe_embed = AsyncMock(return_value=None)
        assert await reflector.reflect_on_run(
            backend,
            "owner",
            reflector.SignalRun(
                run_id="new",
                session_id="source",
                kind="down",
                comment="Please keep this preference",
            ),
        ) == {"stored": 1}
        saved = await db.native_memories.find_one({"user_id": "owner"})
        assert saved["source"] == "self_evolved"
        assert saved["origin_session_ids"] == ["source"]
        calls = model.await_count
        foreign_signal = reflector.SignalRun(
            run_id="new", session_id="source", kind="down", comment="private"
        )
        assert await reflector.reflect_on_run(backend, "other", foreign_signal) == {
            "stored": 0,
            "skipped": True,
        }
        assert model.await_count == calls
    finally:
        release.set()
        if task:
            await asyncio.gather(task, return_exceptions=True)
        await client.drop_database(database_name)
        await client.close()


@pytest.mark.parametrize("failure", ["exception", "retryable_result"])
async def test_reflection_storage_failure_does_not_consume_the_signal(monkeypatch, failure):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_reflection_retry_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._get_memory_model = AsyncMock(
        return_value=SimpleNamespace(bind_tools=lambda tools: object())
    )
    backend.retain = (
        AsyncMock(side_effect=OSError("temporary write failure"))
        if failure == "exception"
        else AsyncMock(
            return_value={"success": False, "error": "temporary_storage_failure"},
        )
    )
    monkeypatch.setattr(reflector.settings, "MONGODB_DB", database_name)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr(
        "src.infra.llm.retry.ainvoke_with_retry",
        AsyncMock(
            return_value=SimpleNamespace(
                tool_calls=[
                    {
                        "name": "memory_retain",
                        "args": {
                            "content": "rule: Answer briefly.\nwhy: User requested brevity.\nhow_to_apply: For routine questions."
                        },
                    }
                ],
            )
        ),
    )
    try:
        await db.traces.insert_one(
            {
                "run_id": "run",
                "session_id": "source",
                "user_id": "owner",
                "started_at": utc_now(),
                "events": [{"type": "user:message", "data": {"content": "Be concise"}}],
            }
        )
        result = await reflector.reflect_on_run(
            backend,
            "owner",
            reflector.SignalRun(
                run_id="run",
                session_id="source",
                kind="down",
                comment="Too verbose",
            ),
        )
        assert result == {"stored": 0, "skipped": True}
        backend.retain.assert_awaited_once()
    finally:
        await client.drop_database(database_name)
        await client.close()


@pytest.mark.parametrize("merged", [False, True])
async def test_reflection_reads_authorized_parent_chunks_using_the_real_schema(monkeypatch, merged):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_reflection_chunks_{uuid4().hex}"
    db = client[database_name]
    monkeypatch.setattr(reflector.settings, "MONGODB_DB", database_name)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    try:
        await db.traces.insert_one(
            {"trace_id": "owned-trace", "run_id": "run", "session_id": "source", "user_id": "owner"}
        )
        await db.trace_event_chunks.insert_one(
            {
                "trace_id": "owned-trace",
                "run_id": "run",
                "session_id": "source",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [
                    {
                        "seq": 1,
                        "event_type": "user:message",
                        "data": {"content": "Use a short plain-text answer."},
                    },
                    {
                        "seq": 2,
                        "event_type": "message:chunk",
                        "data": {"text_id": "t", "content": "The actual "},
                    },
                    {
                        "seq": 3,
                        "event_type": "message:chunk",
                        "data": {"text_id": "t", "content": "original answer."},
                    },
                    {
                        "seq": 4,
                        "event_type": "message:chunk",
                        "data": {
                            "text_id": "child",
                            "depth": 1,
                            "content": "Nested private draft.",
                        },
                    },
                ],
            }
        )
        if merged:
            from src.infra.session.history_compaction import compact_history_events

            chunk = await db.trace_event_chunks.find_one({"trace_id": "owned-trace"})
            compacted = compact_history_events(chunk["events"], mark_merges=True)
            assert len(compacted) < len(chunk["events"])
            await db.trace_event_chunks.update_one(
                {"_id": chunk["_id"]}, {"$set": {"events": compacted}}
            )
        assert await reflector._load_exchange("run", "source", "owner") == (
            "Use a short plain-text answer.",
            "The actual original answer.",
        )
        assert await reflector._load_exchange("run", "source", "other") == ("", "")
    finally:
        await client.drop_database(database_name)
        await client.close()
