"""Restored memory must keep owner-scoped provenance for subsequent forgetting."""

import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient

from src.api.routes import memory as routes
from src.infra.memory import extraction
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.forgetting import source_watermark
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.user import TokenPayload

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.mark.parametrize("mode", ["fresh", "legacy_overwrite", "concurrent_origin"])
async def test_export_restore_then_forget_preserves_the_source_barrier(monkeypatch, mode):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_origin_restore_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=database_name)
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    monkeypatch.setattr(routes.settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    no_model = AsyncMock(side_effect=AssertionError("Suppressed old history must not call a model"))
    monkeypatch.setattr(extraction, "_get_extraction_model", no_model)
    user = TokenPayload(sub="owner", username="owned-restore", roles=["user"])
    try:
        session_oid = ObjectId()
        await db.sessions.insert_one(
            {"_id": session_oid, "session_id": "canonical-source", "user_id": "owner"}
        )
        await db.traces.insert_one(
            {
                "session_id": "canonical-source",
                "user_id": "owner",
                "run_id": "old",
                "started_at": utc_now() - timedelta(hours=1),
                "status": "completed",
                "conversation_search": {
                    "user_text": "Remember my cabinet label: Fern 517.",
                    "assistant_final_text": "Recorded.",
                },
            }
        )
        result = await backend.retain(
            "owner",
            "The cabinet label is Fern 517.",
            title="Cabinet",
            summary="Cabinet label",
            tags=["cabinet"],
            source="auto_retained",
            origin_session_id=str(session_oid),
        )
        memory_id = result["memory_id"]
        exported = await routes.export_memories(user=user)
        backup = json.loads(
            "".join(
                [
                    chunk.decode() if isinstance(chunk, bytes) else chunk
                    async for chunk in exported.body_iterator
                ]
            )
        )
        if mode == "fresh":
            assert backup["memories"][0]["origin_session_ids"] == [str(session_oid)]
            await db.native_memories.delete_many({"user_id": "owner"})
        else:
            backup["memories"][0].pop("origin_session_ids", None)
        original_oid = (await db.native_memories.find_one({"memory_id": memory_id}) or {}).get(
            "_id"
        )
        if mode == "concurrent_origin":

            async def concurrent_embed(_content):
                await db.native_memories.update_one(
                    {"memory_id": memory_id},
                    {
                        "$addToSet": {"origin_session_ids": "concurrent-source"},
                    },
                )
                return None

            backend._maybe_embed = concurrent_embed
            backup["memories"][0]["title"] = "$unchanged_literal"
        await routes.import_memories(backup, user=user)
        restored = await db.native_memories.find_one({"user_id": "owner", "memory_id": memory_id})
        expected_origins = {str(session_oid)}
        if mode == "concurrent_origin":
            expected_origins.add("concurrent-source")
            assert restored["title"] == "$unchanged_literal"
        assert set(restored["origin_session_ids"]) == expected_origins
        if original_oid:
            assert restored["_id"] == original_oid
        assert (await backend.delete("owner", memory_id))["success"] is True
        assert await source_watermark(db, "owner", "canonical-source") is not None
        assert await source_watermark(db, "other", "canonical-source") is None
        outcome = await extraction.extract_session_memory(
            backend, db, "owner", {"session_id": "canonical-source"}
        )
        assert outcome.status == "succeeded_no_output"
        no_model.assert_not_awaited()
    finally:
        await client.drop_database(database_name)
        await client.close()


@pytest.mark.parametrize("collision_owner", [None, "owner", "other"])
async def test_source_aliases_follow_custom_id_priority_without_cross_session_suppression(
    collision_owner,
):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_origin_alias_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._invalidate_cache = AsyncMock()
    try:
        oid = ObjectId()
        await db.sessions.insert_one({"_id": oid, "session_id": "source-a", "user_id": "owner"})
        if collision_owner:
            await db.sessions.insert_one({"session_id": str(oid), "user_id": collision_owner})
        await db.memory_extraction_jobs.insert_many(
            [
                {
                    "user_id": "owner",
                    "session_id": sid,
                    "status": "running",
                    "attempts": 1,
                    "resume_state": {"payload": "stale"},
                }
                for sid in ["source-a", str(oid)]
            ]
        )
        await db.native_memories.insert_one(
            {
                "memory_id": "forget",
                "user_id": "owner",
                "origin_session_ids": ["source-a"],
                "content_storage_mode": "inline",
            }
        )
        assert (await backend.delete("owner", "forget"))["success"] is True
        assert await source_watermark(db, "owner", "source-a") is not None
        alias = await source_watermark(db, "owner", str(oid))
        assert (alias is not None) is (collision_owner is None)
        assert await source_watermark(db, "other", str(oid)) is None
        canonical_job = await db.memory_extraction_jobs.find_one({"session_id": "source-a"})
        alias_job = await db.memory_extraction_jobs.find_one({"session_id": str(oid)})
        assert canonical_job["resume_state"] is None
        assert (alias_job["resume_state"] is None) is (collision_owner is None)
    finally:
        await client.drop_database(database_name)
        await client.close()
