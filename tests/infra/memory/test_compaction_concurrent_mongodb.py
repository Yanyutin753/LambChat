"""Real MongoDB/store coverage for conditional memory mutations."""

import asyncio
import os
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.content import (
    hydrate_memory_text_status,
    memory_store_namespace,
)
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1",
    reason="Set TEST_MEMORY_MONGODB=1 for real MongoDB/store concurrency tests",
)


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_real_conditional_mutation_preserves_concurrent_manual_body(operation):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_cas_{uuid4().hex}"
    db = client[database_name]
    collection = db.native_memories
    user_id, memory_id = "owned-memory-test", uuid4().hex
    key = f"memory:{memory_id}"
    original_text = "The supplier warranty lasts 37 months."
    latest_text = "The user manually confirmed that the warranty lasts 48 months."
    store = MongoDBStore(client=client, db_name=database_name)
    backend = NativeMemoryBackend()
    backend._collection = collection
    backend._store = store
    backend._invalidate_cache = AsyncMock()
    entered, release = asyncio.Event(), asyncio.Event()
    task = None
    try:
        await store.aput(memory_store_namespace(user_id), key, {"text": original_text})
        await collection.insert_one(
            {
                "user_id": user_id,
                "memory_id": memory_id,
                "memory_type": "user",
                "title": "Warranty",
                "summary": original_text,
                "tags": ["warranty"],
                "context": "user",
                "scope": "user",
                "project_id": None,
                "source": "auto_retained",
                "updated_at": utc_now(),
                "source_refs": [],
                "content": original_text,
                "content_storage_mode": "store",
                "content_store_key": key,
            }
        )
        original = await collection.find_one({"memory_id": memory_id})
        expected = {
            field: original.get(field)
            for field in ("updated_at", "source", "scope", "project_id", "content_store_key")
        }
        if operation == "update":

            async def embed_after_read(text):
                entered.set()
                await release.wait()
                return None

            backend._maybe_embed = embed_after_read
            task = asyncio.create_task(
                backend.retain(
                    user_id,
                    "Compacted supplier terms. " * 80,
                    context="user",
                    title="Warranty",
                    summary="Compacted terms",
                    tags=["warranty"],
                    existing_memory_id=memory_id,
                    expected_revision=expected,
                )
            )
        else:

            class DeleteBarrier:
                def __getattr__(self, name):
                    return getattr(collection, name)

                async def find_one_and_delete(self, query, projection=None):
                    entered.set()
                    await release.wait()
                    return await collection.find_one_and_delete(query, projection=projection)

            backend._collection = DeleteBarrier()
            task = asyncio.create_task(
                backend.delete(user_id, memory_id, expected_revision=expected)
            )
        await asyncio.wait_for(entered.wait(), timeout=5)
        await store.aput(memory_store_namespace(user_id), key, {"text": latest_text})
        await collection.update_one(
            {"memory_id": memory_id},
            {
                "$set": {
                    "source": "manual",
                    "updated_at": original["updated_at"] + timedelta(seconds=1),
                    "content": latest_text,
                }
            },
        )
        release.set()
        result = await asyncio.wait_for(task, timeout=10)
        assert result["success"] is False
        current = await collection.find_one({"memory_id": memory_id})
        assert current["source"] == "manual"
        assert current["content_store_key"] == key
        assert await hydrate_memory_text_status(backend, current) == (latest_text, True)
        assert await store.collection.count_documents({}) == 1
        backend._invalidate_cache.assert_not_awaited()
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await client.drop_database(database_name)
        await client.close()


async def test_manual_body_survives_cleanup_from_an_earlier_compaction(monkeypatch):
    from src.api.routes import memory as routes
    from src.infra.memory.client.native import backend as backend_module
    from src.infra.memory.client.native.content import delete_memory_content
    from src.kernel.schemas.user import TokenPayload

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_cleanup_{uuid4().hex}"
    db = client[database_name]
    user_id, memory_id = "owned-cleanup-test", uuid4().hex
    old_key = f"memory:{memory_id}"
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=database_name)
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    entered, release = asyncio.Event(), asyncio.Event()
    task = None

    async def delayed_cleanup(target_backend, owner, key):
        if key == old_key:
            entered.set()
            await release.wait()
        await delete_memory_content(target_backend, owner, key)

    monkeypatch.setattr(backend_module, "delete_memory_content", delayed_cleanup)
    try:
        original = "Original supplier terms. " * 100
        await backend._store.aput(memory_store_namespace(user_id), old_key, {"text": original})
        await db.native_memories.insert_one(
            {
                "user_id": user_id,
                "memory_id": memory_id,
                "memory_type": "user",
                "content": original[:1200],
                "content_storage_mode": "store",
                "content_store_key": old_key,
                "source": "auto_retained",
                "scope": "user",
                "project_id": None,
                "title": "Supplier terms",
                "summary": "Original terms",
                "tags": ["supplier"],
                "context": "user",
                "source_refs": [],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        previous = await db.native_memories.find_one({"memory_id": memory_id})
        task = asyncio.create_task(
            backend.retain(
                user_id,
                "Compacted supplier terms. " * 100,
                context="user",
                title="Supplier terms",
                summary="Compacted terms",
                tags=["supplier"],
                existing_memory_id=memory_id,
                expected_revision={
                    key: previous.get(key)
                    for key in ("updated_at", "source", "scope", "project_id", "content_store_key")
                },
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        manual = (
            "The user manually confirms a 48-month warranty and 21-day delivery. " * 100
        ).strip()
        await routes.update_memory(
            memory_id,
            {"content": manual},
            user=TokenPayload(sub=user_id, username="owned-test", roles=["user"]),
        )
        release.set()
        assert (await asyncio.wait_for(task, timeout=10))["success"] is True
        current = await db.native_memories.find_one({"memory_id": memory_id})
        assert current["content_store_key"] != old_key
        assert await hydrate_memory_text_status(backend, current) == (manual, True)
        assert await backend._store.collection.count_documents({}) == 1
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await client.drop_database(database_name)
        await client.close()
