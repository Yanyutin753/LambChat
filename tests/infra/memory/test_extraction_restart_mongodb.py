"""Actual Mongo job/body persistence across extraction worker replacement."""

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
from src.infra.utils.datetime import utc_now


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
async def test_replacement_worker_resumes_persisted_plan_without_model_or_first_write_replay(
    monkeypatch,
):
    database_name = f"memory_resume_{uuid4().hex}"
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    monkeypatch.setattr(extraction.settings, "MONGODB_DB", database_name)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(
        "src.infra.memory.user_pref.user_memory_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("src.infra.usage.quota.user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(
        "src.infra.usage.quota.UsageQuota",
        lambda: SimpleNamespace(
            snapshot=AsyncMock(
                return_value={"five_hour": {"blocked": False}, "weekly": {"blocked": False}}
            ),
        ),
    )
    monkeypatch.setattr(
        "src.infra.memory.distributed.check_auto_retain_daily_limit",
        AsyncMock(return_value="allowed"),
    )
    record = AsyncMock(return_value="counted")
    monkeypatch.setattr("src.infra.memory.distributed.record_auto_retain_usage", record)
    monkeypatch.setattr(
        "src.infra.memory.compaction_agent.get_memory_compaction_agent",
        lambda: SimpleNamespace(
            maybe_compact_after_write=AsyncMock(),
        ),
    )
    monkeypatch.setattr(
        "src.infra.memory.extraction_gate.evaluate_extraction_gate", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("src.infra.memory.extraction_gate.log_context_second_opinion", AsyncMock())
    monkeypatch.setattr(
        "src.infra.session.conversation_history.ConversationHistoryService.validate_source_refs",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        extraction,
        "load_session_transcript",
        AsyncMock(
            return_value=[
                {
                    "run_id": "r1",
                    "user": "Answer preference and studio location",
                    "assistant": "Recorded",
                },
            ]
        ),
    )
    monkeypatch.setattr(extraction, "_get_extraction_model", AsyncMock(return_value=object()))
    invoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {"raw_memory": "The user prefers concise answers.", "context": "user"},
                        {"raw_memory": "The user's studio is based in Osaka.", "context": "user"},
                    ]
                }
            )
        )
    )
    monkeypatch.setattr("src.infra.llm.retry.ainvoke_with_retry", invoke)
    session = {"session_id": "owned-session", "updated_at": utc_now() - timedelta(hours=1)}

    async def claim(db, jobs, user_id, *, limit):
        job = await extraction.claim_session_job(jobs, session, user_id)
        return [(session, job)] if job else []

    monkeypatch.setattr(extraction, "claim_candidate_jobs", claim)

    def backend_for_worker():
        backend = NativeMemoryBackend()
        backend._collection = client[database_name].native_memories
        backend._maybe_embed = AsyncMock(return_value=None)
        backend._invalidate_cache = AsyncMock()
        return backend

    try:
        backend = backend_for_worker()
        original_retain = backend.retain
        calls = 0

        async def interrupted_retain(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("owned test: storage unavailable")
            return await original_retain(*args, **kwargs)

        backend.retain = interrupted_retain
        first = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert first["failed"] == 1 and first["succeeded"] == 0
        db = client[database_name]
        job = await db[extraction.EXTRACTION_JOBS_COLLECTION].find_one(
            {"session_id": "owned-session"}
        )
        first_memory = await db.native_memories.find_one({"user_id": "owned-user"})
        assert job["memory_ids"] == [first_memory["memory_id"]]
        assert job["resume_state"]["next_index"] == 1
        assert record.await_count == 1
        await db[extraction.EXTRACTION_JOBS_COLLECTION].update_one(
            {"_id": job["_id"]},
            {"$set": {"next_retry_at": utc_now() - timedelta(seconds=1)}},
        )
        await client.close()

        client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
        backend = backend_for_worker()
        second = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert second["succeeded"] == 1 and second["failed"] == 0
        db = client[database_name]
        assert await db.native_memories.count_documents({"user_id": "owned-user"}) == 2
        assert (
            await db.native_memories.find_one({"memory_id": first_memory["memory_id"]})
            == first_memory
        )
        job = await db[extraction.EXTRACTION_JOBS_COLLECTION].find_one(
            {"session_id": "owned-session"}
        )
        assert job["attempts"] == 2 and job["status"] == "succeeded"
        assert len(job["memory_ids"]) == 2 and job["resume_state"] is None
        assert record.await_count == 2
        invoke.assert_awaited_once()

        session["updated_at"] = utc_now()
        third = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert third["succeeded_no_output"] == 1
        assert record.await_count == 2
        invoke.assert_awaited_once()

        # A different worker takes the claim while the model is finishing.
        monkeypatch.setattr(
            extraction,
            "load_session_transcript",
            AsyncMock(
                return_value=[
                    {
                        "run_id": "r2",
                        "user": "An updated durable preference",
                        "assistant": "Recorded",
                    },
                ]
            ),
        )
        session["updated_at"] = utc_now() + timedelta(seconds=1)
        response = invoke.return_value

        async def steal_claim(*args, **kwargs):
            await db[extraction.EXTRACTION_JOBS_COLLECTION].update_one(
                {"session_id": "owned-session"},
                {
                    "$inc": {"attempts": 1},
                    "$set": {"lease_expires_at": utc_now() + timedelta(minutes=30)},
                },
            )
            return response

        invoke.side_effect = steal_claim
        backend.retain = AsyncMock(wraps=backend.retain)
        fourth = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert fourth["failed"] == 1 and fourth["succeeded"] == 0
        backend.retain.assert_not_awaited()
        assert record.await_count == 2
        current_job = await db[extraction.EXTRACTION_JOBS_COLLECTION].find_one(
            {"session_id": "owned-session"}
        )
        assert current_job["status"] == "claimed" and current_job.get("error") is None
        # The lease may be stolen later, while embedding is in flight.
        await db[extraction.EXTRACTION_JOBS_COLLECTION].delete_one({"session_id": "owned-session"})
        monkeypatch.setattr(
            extraction,
            "load_session_transcript",
            AsyncMock(
                return_value=[
                    {
                        "run_id": "r3",
                        "user": "The standing packaging budget is 4800 CNY per quarter.",
                        "assistant": "Recorded",
                    },
                ]
            ),
        )
        invoke.side_effect = None
        invoke.return_value = SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {
                            "raw_memory": "The user's standing packaging budget is 4800 CNY per quarter.",
                            "context": "user",
                        }
                    ]
                }
            )
        )

        async def embed_after_claim_takeover(content):
            await db[extraction.EXTRACTION_JOBS_COLLECTION].update_one(
                {"session_id": "owned-session"},
                {"$inc": {"attempts": 1}},
            )
            return None

        backend._maybe_embed = embed_after_claim_takeover
        fifth = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert fifth["failed"] == 1 and fifth["succeeded"] == 0
        assert await db.native_memories.count_documents({"user_id": "owned-user"}) == 2
        assert record.await_count == 2
        # Lease expiry alone must stop writes, even if no replacement has arrived.
        await db[extraction.EXTRACTION_JOBS_COLLECTION].delete_one({"session_id": "owned-session"})
        clock = {"now": utc_now()}
        monkeypatch.setattr(extraction, "utc_now", lambda: clock["now"])
        invoke.return_value = SimpleNamespace(
            content=json.dumps(
                {
                    "memories": [
                        {
                            "raw_memory": "The user's standing packaging budget is 9600 CNY per quarter.",
                            "context": "user",
                        }
                    ]
                }
            )
        )

        async def embed_past_lease_expiry(content):
            clock["now"] += timedelta(seconds=extraction._LEASE_SECONDS + 1)
            return None

        backend._maybe_embed = embed_past_lease_expiry
        sixth = await extraction.run_extraction_pass("owned-user", backend=backend)
        assert sixth["failed"] == 1 and sixth["succeeded"] == 0
        assert await db.native_memories.count_documents({"user_id": "owned-user"}) == 2
        assert record.await_count == 2
    finally:
        await client.drop_database(database_name)
        await client.close()
