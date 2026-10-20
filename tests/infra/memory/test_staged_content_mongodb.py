"""Hard process death must leave a recoverable, invisible body reservation."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.cleanup import run_cleanup_pass
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def staged_backend(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_staged_content_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    await db.native_memories.create_index("memory_id", unique=True)
    backend._store = MongoDBStore(client=client, db_name=name)
    backend._invalidate_cache = AsyncMock()
    backend._maybe_embed = AsyncMock(return_value=None)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 20)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    try:
        yield backend, db
    finally:
        await client.drop_database(name)
        await client.close()


async def test_killed_writer_body_is_reclaimed_after_restart(staged_backend):
    backend, db = staged_backend
    code = """import asyncio,json,sys
from pymongo import AsyncMongoClient
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.content import build_content_fields
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.kernel.config import settings
async def main():
 settings.NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS=20
 client=AsyncMongoClient(build_mongo_connection_string(),timeoutMS=10000)
 backend=NativeMemoryBackend();backend._collection=client[sys.argv[1]].native_memories
 backend._store=MongoDBStore(client=client,db_name=sys.argv[1])
 fields=await build_content_fields(backend,'owner','crashed','Synthetic durable workshop details '*20)
 print(json.dumps({"content_store_key":fields["content_store_key"]}),flush=True)
 await asyncio.Event().wait()
asyncio.run(main())
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, db.name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 20)
        assert line, "Owned writer exited before preparing its body"
        fields = json.loads(line)
        namespace = ("memories", "owner", "content")
        assert await backend._store.aget(namespace, fields["content_store_key"]) is not None
        assert await db.native_memories.count_documents({"user_id": "owner"}) == 0
        process.kill()
        await asyncio.to_thread(process.wait, 5)
        assert process.returncode != 0
        await db.native_memories.update_many(
            {"_content_stages": {"$exists": True}},
            {"$set": {"_content_stages.$[].expires": utc_now() - timedelta(seconds=1)}},
        )
        restarted = NativeMemoryBackend()
        restarted._collection, restarted._store = db.native_memories, backend._store
        await run_cleanup_pass(restarted)
        assert await backend._store.aget(namespace, fields["content_store_key"]) is None
        assert await db.native_memories.count_documents({}) == 0
    finally:
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.communicate, timeout=5)


async def _body(backend, memory_id="target", text="Synthetic archive agreement " * 10):
    from src.infra.memory.client.native.content import build_content_fields

    return await build_content_fields(backend, "owner", memory_id, text)


async def _expire(db):
    await db.native_memories.update_many(
        {"_content_stages.0": {"$exists": True}},
        {"$set": {"_content_stages.$[].expires": utc_now() - timedelta(seconds=1)}},
    )


async def test_committed_long_body_survives_restart_cleanup(staged_backend):
    from src.infra.memory.staging import insert_content_memory

    backend, db = staged_backend
    fields = await _body(backend)
    await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **fields})
    await run_cleanup_pass(backend)
    doc = await db.native_memories.find_one({"user_id": "owner"})
    assert doc["content_store_key"] == fields["content_store_key"]
    assert doc["_content_stages"] == []
    assert "_content_stage" not in doc and "_content_stage_owner" not in doc
    assert await backend._store.aget(("memories", "owner", "content"), doc["content_store_key"])


async def test_expired_writer_cannot_commit_after_recovery(staged_backend):
    from src.infra.memory.staging import insert_content_memory
    from src.kernel.errors import AppError

    backend, db = staged_backend
    fields = await _body(backend)
    await _expire(db)
    await run_cleanup_pass(backend)
    with pytest.raises(AppError):
        await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **fields})
    assert await db.native_memories.count_documents({}) == 0


async def test_expired_writer_does_not_borrow_another_writers_fresh_stage(staged_backend):
    from src.infra.memory.staging import insert_content_memory
    from src.kernel.errors import AppError

    backend, db = staged_backend
    expired = await _body(backend)
    await _expire(db)
    fresh = await _body(backend)
    with pytest.raises(AppError):
        await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **expired})
    await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **fresh})
    await run_cleanup_pass(backend)
    namespace = ("memories", "owner", "content")
    assert await backend._store.aget(namespace, expired["content_store_key"]) is None
    assert await backend._store.aget(namespace, fresh["content_store_key"]) is not None
    doc = await db.native_memories.find_one({"user_id": "owner"})
    assert doc["content_store_key"] == fresh["content_store_key"] and not doc["_content_stages"]


async def test_failed_guard_cancels_completed_body_without_leaking_reservation(staged_backend):
    from src.infra.memory.client.native.content import delete_memory_content

    backend, db = staged_backend
    fields = await _body(backend)
    await delete_memory_content(backend, "owner", fields["content_store_key"])
    assert (
        await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])
        is None
    )
    assert await db.native_memories.count_documents({}) == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_active_body_cannot_be_reclaimed_by_cleanup(staged_backend):
    from src.infra.memory.cleanup import enqueue_content_cleanup, process_cleanup
    from src.infra.memory.staging import insert_content_memory

    backend, db = staged_backend
    fields = await _body(backend)
    task = await enqueue_content_cleanup(backend, "owner", fields["content_store_key"])
    assert not await process_cleanup(backend, task)
    assert await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])
    await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **fields})
    assert not await process_cleanup(backend, task)
    assert await db.native_memories.count_documents({"user_id": "owner"}) == 1


async def test_foreign_memory_cannot_be_reserved_or_replaced(staged_backend):
    from pymongo.errors import DuplicateKeyError

    backend, db = staged_backend
    await db.native_memories.insert_one(
        {"user_id": "other", "memory_id": "target", "content": "Private"}
    )
    with pytest.raises(DuplicateKeyError):
        await _body(backend)
    assert (await db.native_memories.find_one({"memory_id": "target"}))["content"] == "Private"
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_commit_between_cleanup_pointer_and_stage_reads_keeps_live_body(
    staged_backend, monkeypatch
):
    from src.infra.memory.cleanup import enqueue_content_cleanup, process_cleanup
    from src.infra.memory.staging import insert_content_memory

    backend, db = staged_backend
    fields = await _body(backend)
    original = type(db.native_memories).find_one
    committed = False

    async def commit_after_pointer_read(collection, query, *args, **kwargs):
        nonlocal committed
        result = await original(collection, query, *args, **kwargs)
        if (
            collection.name == "native_memories"
            and query.get("content_store_key") == fields["content_store_key"]
            and not committed
        ):
            assert result is None
            committed = True
            await insert_content_memory(
                backend, {"memory_id": "target", "user_id": "owner", **fields}
            )
        return result

    monkeypatch.setattr(type(db.native_memories), "find_one", commit_after_pointer_read)
    task = await enqueue_content_cleanup(backend, "owner", fields["content_store_key"])
    assert not await process_cleanup(backend, task)
    assert committed
    assert await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])


@pytest.mark.parametrize("entry", ["create", "update", "import"])
async def test_management_writes_commit_long_body_without_staging_fields(
    staged_backend, monkeypatch, entry
):
    from src.api.routes import memory as routes
    from src.kernel.schemas.user import TokenPayload

    backend, db = staged_backend
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    user = TokenPayload(sub="owner", username="test", roles=["user"])
    text = "Synthetic supplier archive condition. " * 30
    if entry == "create":
        saved = await routes.create_memory({"content": text}, user=user)
        mid = saved["memory_id"]
    elif entry == "update":
        mid = "target"
        await db.native_memories.insert_one(
            {"user_id": "owner", "memory_id": mid, "content": "original"}
        )
        await routes.update_memory(mid, {"content": text}, user=user)
    else:
        mid = "target"
        result = await routes.import_memories(
            {"memories": [{"memory_id": mid, "content": text}]}, user=user
        )
        assert result["created"] == 1 and result["overwritten"] == 0
    await run_cleanup_pass(backend)
    doc = await db.native_memories.find_one({"memory_id": mid, "user_id": "owner"})
    assert doc["content_storage_mode"] == "store"
    assert doc["_content_stages"] == [] and "_content_stage" not in doc
    assert "_content_stage_owner" not in doc
    item = await backend._store.aget(("memories", "owner", "content"), doc["content_store_key"])
    assert item.value["text"] == text.strip()


async def test_inline_import_keeps_another_writers_cleanup_reference(staged_backend, monkeypatch):
    from src.api.routes import memory as routes
    from src.infra.memory.staging import insert_content_memory
    from src.kernel.errors import AppError
    from src.kernel.schemas.user import TokenPayload

    backend, db = staged_backend
    fields = await _body(backend)
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    result = await routes.import_memories(
        {"memories": [{"memory_id": "target", "content": "Short replacement"}]},
        user=TokenPayload(sub="owner", username="test", roles=["user"]),
    )
    assert result["created"] == 1
    doc = await db.native_memories.find_one({"memory_id": "target"})
    assert len(doc["_content_stages"]) == 1
    with pytest.raises(AppError):
        await insert_content_memory(backend, {"memory_id": "target", "user_id": "owner", **fields})
    await _expire(db)
    await run_cleanup_pass(backend)
    doc = await db.native_memories.find_one({"memory_id": "target"})
    assert doc["content"] == "Short replacement" and not doc["_content_stages"]
    assert (
        await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])
        is None
    )


async def test_staging_discovery_does_not_scan_fifty_thousand_committed_memories(
    staged_backend, monkeypatch
):
    backend, db = staged_backend
    await db.native_memories.insert_many(
        [
            {"memory_id": f"old-{i}", "user_id": "owner", "content": "Synthetic committed archive"}
            for i in range(50_000)
        ]
    )
    original = type(db.native_memories).find
    plans = []

    class ObservedCursor:
        def __init__(self, cursor, query):
            self.cursor = cursor
            self.request = {"find": "native_memories", "filter": query}

        def sort(self, *args):
            self.request["sort"] = dict([args] if isinstance(args[0], str) else args[0])
            self.cursor = self.cursor.sort(*args)
            return self

        def limit(self, count):
            self.request["limit"] = count
            self.cursor = self.cursor.limit(count)
            return self

        async def to_list(self, length):
            plan = await db.command({"explain": self.request, "verbosity": "executionStats"})
            plans.append(plan["executionStats"])
            return await self.cursor.to_list(length=length)

    def observe(collection, query, *args, **kwargs):
        cursor = original(collection, query, *args, **kwargs)
        if collection.name == "native_memories" and any(
            key.startswith("_content_stages") for key in query
        ):
            return ObservedCursor(cursor, query)
        return cursor

    monkeypatch.setattr(type(db.native_memories), "find", observe)
    await run_cleanup_pass(backend)
    assert plans and all(
        plan["totalDocsExamined"] <= 5 and plan["totalKeysExamined"] <= 5 for plan in plans
    ), plans


async def test_staged_resources_are_handed_off_even_when_cleanup_workers_are_busy(
    staged_backend, monkeypatch
):
    from src.infra.memory import cleanup

    backend, db = staged_backend
    expired = utc_now() - timedelta(minutes=1)
    await db.native_memories.insert_many(
        [
            {
                "memory_id": f"pending-{i}",
                "_content_stage_owner": "owner",
                "_content_stages": [
                    {"key": f"memory:pending-{i}:body", "token": str(i), "expires": expired}
                ],
            }
            for i in range(101)
        ]
    )
    monkeypatch.setattr(cleanup, "process_cleanup", AsyncMock(return_value=False))
    await run_cleanup_pass(backend)
    assert await db.memory_resource_cleanup.count_documents({}) == 100
    await run_cleanup_pass(backend)
    assert await db.memory_resource_cleanup.count_documents({}) == 101
    assert await db.native_memories.count_documents({}) == 0


async def test_logical_deletion_journals_staged_body_before_removing_metadata(staged_backend):
    backend, db = staged_backend
    saved = await backend.retain(
        "owner", "The user prefers detailed warehouse handling instructions. " * 30
    )
    fields = await _body(backend, saved["memory_id"])
    await _expire(db)
    result = await backend.delete("owner", saved["memory_id"])
    assert result["success"]
    assert await db.native_memories.count_documents({}) == 0
    assert await db.memory_resource_cleanup.find_one({"key": fields["content_store_key"]})
    await run_cleanup_pass(backend)
    assert (
        await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])
        is None
    )
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_delete_cannot_erase_a_new_unjournaled_stage(staged_backend, monkeypatch):
    from src.infra.memory import cleanup

    backend, db = staged_backend
    saved = await backend.retain(
        "owner", "The user prefers careful archival handling instructions. " * 30
    )
    prepare = cleanup.prepare_deleted_resources
    pending = None

    async def append_after_snapshot(*args):
        nonlocal pending
        await prepare(*args)
        pending = await _body(backend, saved["memory_id"])

    monkeypatch.setattr(cleanup, "prepare_deleted_resources", append_after_snapshot)
    result = await backend.delete("owner", saved["memory_id"])
    assert not result["success"]
    doc = await db.native_memories.find_one({"memory_id": saved["memory_id"]})
    assert (
        doc["user_id"] == "owner"
        and doc["_content_stages"][0]["key"] == pending["content_store_key"]
    )
    assert await backend._store.aget(("memories", "owner", "content"), doc["content_store_key"])


async def test_restart_reaps_reservation_if_process_died_after_removing_last_stage(staged_backend):
    from src.infra.memory.cleanup import enqueue_content_cleanup

    backend, db = staged_backend
    fields = await _body(backend)
    await enqueue_content_cleanup(backend, "owner", fields["content_store_key"])
    await db.native_memories.update_one({"memory_id": "target"}, {"$set": {"_content_stages": []}})
    restarted = NativeMemoryBackend()
    restarted._collection, restarted._store = db.native_memories, backend._store
    await run_cleanup_pass(restarted)
    assert await db.native_memories.count_documents({}) == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    assert (
        await backend._store.aget(("memories", "owner", "content"), fields["content_store_key"])
        is None
    )
