"""Project memory ownership follows the canonical custom/Mongo session identity."""

import os
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient

from src.infra.memory import scope
from src.infra.storage.mongodb import build_mongo_connection_string
from src.kernel.config import settings


@pytest.mark.parametrize(
    ("custom_document", "expected_project"),
    [
        (None, "normal"),
        ({"metadata": {"project_id": "custom"}}, "custom"),
        ({"metadata": {}}, None),
    ],
)
async def test_project_lookup_accepts_normal_ids_without_overriding_custom_identity(
    monkeypatch, custom_document, expected_project
):
    mongo_id = ObjectId()
    session_id = str(mongo_id)

    class Sessions:
        async def find_one(self, query, projection):
            assert projection == {"metadata.project_id": 1}
            if query == {"session_id": session_id}:
                return custom_document
            assert query == {"_id": mongo_id}
            return {"metadata": {"project_id": "normal"}}

    monkeypatch.setattr(scope, "_get_sessions_collection", lambda: Sessions())
    scope.invalidate_session_project_cache(session_id)
    try:
        assert await scope.resolve_session_project_id(session_id) == expected_project
    finally:
        scope.invalidate_session_project_cache(session_id)


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Requires local MongoDB")
async def test_real_mongo_project_lookup_custom_precedence_and_move_invalidation(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    name = f"test_scope_identity_{uuid4().hex}"
    collection = client[settings.MONGODB_DB][name]
    mongo_id, custom_id = ObjectId(), ObjectId()
    session_id = str(mongo_id)
    monkeypatch.setattr(scope, "_get_sessions_collection", lambda: collection)
    scope.invalidate_session_project_cache(session_id)
    try:
        await collection.insert_many(
            [
                {"_id": mongo_id, "metadata": {"project_id": "normal"}},
                {"_id": custom_id, "session_id": session_id, "metadata": {"project_id": "custom"}},
            ]
        )
        assert await scope.resolve_session_project_id(session_id) == "custom"
        await collection.update_one({"_id": custom_id}, {"$unset": {"metadata.project_id": ""}})
        scope.invalidate_session_project_cache(session_id)
        assert await scope.resolve_session_project_id(session_id) is None
        await collection.delete_one({"_id": custom_id})
        scope.invalidate_session_project_cache(session_id)
        assert await scope.resolve_session_project_id(session_id) == "normal"
        await collection.update_one({"_id": mongo_id}, {"$set": {"metadata.project_id": "moved"}})
        scope.invalidate_session_project_cache(session_id)
        assert await scope.resolve_session_project_id(session_id) == "moved"
    finally:
        scope.invalidate_session_project_cache(session_id)
        await client[settings.MONGODB_DB].drop_collection(name)
        await client.close()
