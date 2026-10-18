"""Normal MongoDB session IDs must participate in background extraction."""

import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient

from src.infra.memory import extraction
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings


async def test_candidates_normalize_mongo_ids_and_preserve_custom_ids_without_mutation():
    normal_id, custom_id = ObjectId(), ObjectId()
    documents = [{"_id": normal_id}, {"_id": custom_id, "session_id": "custom"}, {}]

    class Cursor:
        def sort(self, *args):
            return self

        def limit(self, *args):
            return self

        async def to_list(self, **kwargs):
            return documents

    database = {settings.MONGODB_SESSIONS_COLLECTION: SimpleNamespace(find=lambda *args: Cursor())}
    found = await extraction.find_candidate_sessions(database, "owner", limit=3)

    assert [item["session_id"] for item in found] == [str(normal_id), "custom"]
    assert found[0]["_id"] == normal_id
    assert "session_id" not in documents[0]
    assert documents[1]["session_id"] == "custom"


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1",
    reason="Set TEST_MEMORY_MONGODB=1 to test against local MongoDB",
)
async def test_real_mongo_normal_sessions_keep_scope_idle_and_running_trace_guards(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    database = client[settings.MONGODB_DB]
    prefix = f"test_extraction_identity_{uuid4().hex}"
    names = [f"{prefix}_{suffix}" for suffix in ("sessions", "traces", "jobs")]
    monkeypatch.setattr(settings, "MONGODB_SESSIONS_COLLECTION", names[0])
    monkeypatch.setattr(settings, "MONGODB_TRACES_COLLECTION", names[1])
    now, normal_id, custom_id = utc_now(), ObjectId(), ObjectId()
    owner = f"identity-owner-{uuid4().hex}"
    base = {
        "user_id": owner,
        "is_active": True,
        "updated_at": now - timedelta(hours=2),
        "metadata": {},
    }
    try:
        await client.admin.command("ping")
        await database[names[0]].insert_many(
            [
                {**base, "_id": normal_id},
                {**base, "_id": custom_id, "session_id": "custom"},
                {**base, "metadata": {"hidden_from_conversation_list": True}},
                {**base, "session_id": "sch_conversation_private"},
                {**base, "user_id": "another-owner"},
                {**base, "updated_at": now},
                {**base, "updated_at": now - timedelta(days=365)},
                {**base, "is_active": False},
            ]
        )
        found = await extraction.find_candidate_sessions(database, owner, limit=20)
        assert {item["session_id"] for item in found} == {str(normal_id), "custom"}
        await database[names[1]].insert_one(
            {"session_id": str(normal_id), "user_id": owner, "status": "running"}
        )
        await extraction.ensure_extraction_job_indexes(database[names[2]])
        claimed = await extraction.claim_candidate_jobs(
            database, database[names[2]], owner, limit=2
        )
        assert [document["session_id"] for document, _ in claimed] == ["custom"]
        await database[names[1]].update_one({}, {"$set": {"status": "completed"}})
        claimed = await extraction.claim_candidate_jobs(
            database, database[names[2]], owner, limit=2
        )
        assert [document["session_id"] for document, _ in claimed] == [str(normal_id)]
        assert claimed[0][1]["session_id"] == str(normal_id)
        assert claimed[0][1]["user_id"] == owner
        assert "session_id" not in await database[names[0]].find_one({"_id": normal_id})
    finally:
        for name in names:
            await database.drop_collection(name)
        await client.close()
