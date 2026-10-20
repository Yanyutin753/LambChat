"""A partial index view must not hide authorized memories in authoritative Mongo."""

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native import search, vector_store
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
@pytest.mark.parametrize("project_id", [None, "p"])
@pytest.mark.parametrize("context_filter", [None, "project"])
async def test_authoritative_scope_ids_avoid_full_vector_scan_with_stale_payloads(
    monkeypatch, project_id, context_filter
):
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=10000)
    name = f"memory_scoped_ann_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._maybe_embed = AsyncMock(return_value=[1.0, 0.0])
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vector_store, "_vector_index", index)
    now = utc_now()
    rows = [
        {
            "memory_id": uuid4().hex,
            "user_id": "owner",
            "scope": scope,
            "project_id": project,
            "embedding": vector,
            "content": "Durable scope instruction.",
            "title": "Instruction",
            "summary": "Instruction",
            "memory_type": "user",
            "context": "project_constraint",
            "source": "manual",
            "created_at": now,
            "updated_at": now,
        }
        for scope, project, vector in [
            ("user", None, [0.8, 0.6]),
            (None, None, [0.7, 0.714]),
            ("project", "p", [0.9, 0.435]),
        ]
    ]
    rows += [
        {
            **rows[0],
            "memory_id": uuid4().hex,
            "scope": "project",
            "project_id": "other",
            "embedding": [1.0, 0.0],
        }
        for _ in range(64)
    ]
    real_cosine = search._mongo_cosine_search

    async def only_pending(backend, base, vector, limit):
        assert base.get("_vector_pending") == {"$exists": True}, "Scope filtering caused full scan"
        return await real_cosine(backend, base, vector, limit)

    monkeypatch.setattr(search, "_mongo_cosine_search", only_pending)
    try:
        await index.ensure_collection()
        await db.native_memories.insert_many(rows)
        for row in rows:
            assert await index.upsert(
                memory_id=row["memory_id"],
                user_id="owner",
                vector=row["embedding"],
                memory_type="stale-type",
                context="stale-context",
                updated_at=1,
                scope="project",
                project_id="stale-project",
            )
        results = await search.vector_search(
            backend,
            "owner",
            "durable constraints",
            2,
            ["user"],
            context_filter=context_filter,
            project_id=project_id,
        )
        expected = (
            [rows[2]["memory_id"], rows[0]["memory_id"]]
            if project_id
            else [rows[0]["memory_id"], rows[1]["memory_id"]]
        )
        assert [row["memory_id"] for row in results] == expected
    finally:
        await index.close()
        await client.drop_database(name)
        await client.close()


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
@pytest.mark.parametrize("gap", ["empty", "foreign_projects", "orphans"])
async def test_index_candidate_gaps_fall_back_to_visible_mongo_memories(monkeypatch, gap):
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=10000)
    name = f"memory_qdrant_gap_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._maybe_embed = AsyncMock(return_value=[1.0, 0.0])
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vector_store, "_vector_index", index)
    now = utc_now()
    rows = [
        {
            "memory_id": uuid4().hex,
            "user_id": "owner",
            "scope": scope,
            "project_id": project,
            "embedding": vector,
            "content": "Durable instruction.",
            "title": "Instruction",
            "summary": "Instruction",
            "memory_type": "user",
            "source": "manual",
            "created_at": now,
            "updated_at": now,
        }
        for scope, project, vector in [
            ("user", None, [1.0, 0.0]),
            ("project", "p", [0.8, 0.6]),
        ]
    ]
    try:
        await index.ensure_collection()
        await db.native_memories.insert_many(rows)
        if gap != "empty":
            for row in rows:
                assert await index.upsert(
                    memory_id=row["memory_id"],
                    user_id="owner",
                    vector=row["embedding"],
                    memory_type="user",
                    context=None,
                    updated_at=int(now.timestamp()),
                    scope=row["scope"],
                    project_id=row["project_id"],
                )
            for _ in range(20):
                mid = uuid4().hex
                if gap == "foreign_projects":
                    await db.native_memories.insert_one(
                        {
                            **rows[1],
                            "_id": mid,
                            "memory_id": mid,
                            "project_id": "other-project",
                            "embedding": [1.0, 0.01],
                        }
                    )
                assert await index.upsert(
                    memory_id=mid,
                    user_id="owner",
                    vector=[1.0, 0.01],
                    memory_type="user",
                    context=None,
                    updated_at=int(now.timestamp()),
                    scope="project",
                    project_id="other-project",
                )
        result = await search.vector_search(
            backend, "owner", "durable constraints", 2, None, project_id="p"
        )
        assert {row["memory_id"] for row in result} == {row["memory_id"] for row in rows}
    finally:
        await index.close()
        await client.drop_database(name)
        await client.close()
