"""Persist only resource references so failed memory cleanup survives restart."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def owned_backend(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_cleanup_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=name)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    try:
        yield backend, db
    finally:
        await client.drop_database(name)
        await client.close()


async def test_delete_body_outage_can_resume_after_backend_restart(owned_backend):
    backend, db = owned_backend
    namespace = ("memories", "owner", "content")
    key = "memory:old:revision"
    await backend._store.aput(namespace, key, {"text": "PRIVATE FACT MUST NOT ENTER QUEUE"})
    await db.native_memories.insert_one(
        {
            "memory_id": "old",
            "user_id": "owner",
            "revision_id": "r1",
            "origin_session_ids": ["source"],
            "content_storage_mode": "store",
            "content_store_key": key,
        }
    )
    store = backend._store
    backend._store = SimpleNamespace(adelete=AsyncMock(side_effect=OSError("store unavailable")))
    with pytest.raises(OSError):
        await backend.delete("owner", "old")
    assert await db.native_memories.count_documents({}) == 0
    jobs = await db.memory_resource_cleanup.find({}).to_list(length=10)
    assert jobs, "Deleting metadata must not lose the only cleanup reference"
    assert "PRIVATE FACT" not in str(jobs)
    from src.infra.memory.cleanup import run_cleanup_pass

    restarted = NativeMemoryBackend()
    restarted._collection, restarted._store = db.native_memories, store
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    result = await run_cleanup_pass(restarted)
    assert result["completed"] >= 1
    assert await store.aget(namespace, key) is None
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_cleanup_prepare_failure_preserves_the_original_record(owned_backend, monkeypatch):
    backend, db = owned_backend
    await db.native_memories.insert_one(
        {
            "memory_id": "old",
            "user_id": "owner",
            "revision_id": "r1",
            "content_storage_mode": "store",
            "content_store_key": "old-key",
        }
    )
    original = type(db.memory_resource_cleanup).update_one

    async def fail_journal(collection, *args, **kwargs):
        if collection.name == "memory_resource_cleanup":
            raise OSError("journal unavailable")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(type(db.memory_resource_cleanup), "update_one", fail_journal)
    with pytest.raises(OSError, match="journal unavailable"):
        await backend.delete("owner", "old")
    assert await db.native_memories.count_documents({"memory_id": "old"}) == 1


async def test_failed_vector_delete_is_persistent_and_later_retried(owned_backend, monkeypatch):
    backend, db = owned_backend
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    delete = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr("src.infra.memory.client.native.vector_store.index_delete", delete)
    await db.native_memories.insert_one(
        {
            "memory_id": "old",
            "user_id": "owner",
            "revision_id": "r1",
            "content_storage_mode": "inline",
        }
    )
    assert (await backend.delete("owner", "old"))["success"] is True
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    from src.infra.memory.cleanup import run_cleanup_pass

    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await run_cleanup_pass(backend))["completed"] == 1
    assert delete.await_count == 2
    assert await db.memory_resource_cleanup.count_documents({}) == 0


@pytest.mark.parametrize("committed", [True, False])
@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_unknown_delete_commit_keeps_cleanup_intent_and_preserves_live_body(
    owned_backend, monkeypatch, committed, failure
):
    backend, db = owned_backend
    namespace, key = ("memories", "owner", "content"), "memory:unknown"
    await backend._store.aput(namespace, key, {"text": "complete body"})
    await db.native_memories.insert_one(
        {
            "memory_id": "unknown",
            "user_id": "owner",
            "revision_id": "r1",
            "content_storage_mode": "store",
            "content_store_key": key,
        }
    )
    original = type(db.native_memories).find_one_and_delete

    async def uncertain(collection, *args, **kwargs):
        if collection.name == "native_memories":
            if committed:
                await original(collection, *args, **kwargs)
            raise failure("unknown commit")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(type(db.native_memories), "find_one_and_delete", uncertain)
    with pytest.raises(failure, match="unknown commit"):
        await backend.delete("owner", "unknown")
    backend._invalidate_cache.assert_awaited_with("owner")
    from src.infra.memory.cleanup import run_cleanup_pass

    await run_cleanup_pass(backend)
    assert (await backend._store.aget(namespace, key) is None) is committed
    assert await db.memory_resource_cleanup.count_documents({}) == int(not committed)


async def test_cleanup_cannot_drop_a_newly_enqueued_version(owned_backend):
    backend, db = owned_backend
    from src.infra.memory.cleanup import enqueue_content_cleanup, finish_cleanup

    old = await enqueue_content_cleanup(backend, "owner", "same-key")
    new = await enqueue_content_cleanup(backend, "owner", "same-key")
    assert old["version"] != new["version"]
    await finish_cleanup(backend, old, completed=True)
    assert (await db.memory_resource_cleanup.find_one({}))["version"] == new["version"]


async def test_cleanup_preserves_in_use_bodies_and_separates_owner_namespaces(owned_backend):
    backend, db = owned_backend
    from src.infra.memory.cleanup import enqueue_content_cleanup, run_cleanup_pass

    owner_ns, foreign_ns = ("memories", "owner", "content"), ("memories", "foreign", "content")
    await backend._store.aput(owner_ns, "shared-key", {"text": "owned"})
    await backend._store.aput(foreign_ns, "shared-key", {"text": "foreign"})
    await db.native_memories.insert_one(
        {
            "user_id": "owner",
            "memory_id": "live",
            "content_storage_mode": "store",
            "content_store_key": "shared-key",
        }
    )
    await enqueue_content_cleanup(backend, "owner", "shared-key")
    assert (await run_cleanup_pass(backend))["completed"] == 0
    assert await backend._store.aget(owner_ns, "shared-key") is not None
    await db.native_memories.delete_many({})
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await run_cleanup_pass(backend))["completed"] == 1
    assert await backend._store.aget(foreign_ns, "shared-key") is not None


async def test_delete_rechecks_guard_after_preparing_resource_intents(owned_backend, monkeypatch):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    await db.native_memories.insert_one(
        {
            "memory_id": "protected",
            "user_id": "owner",
            "revision_id": "r1",
            "content_storage_mode": "store",
            "content_store_key": "key",
        }
    )
    valid = True
    prepare = cleanup.prepare_deleted_resources

    async def lose_guard(*args):
        nonlocal valid
        await prepare(*args)
        valid = False

    async def guard():
        return valid

    monkeypatch.setattr(cleanup, "prepare_deleted_resources", lose_guard)
    result = await backend.delete(
        "owner", "protected", write_guard=guard, expected_revision={"revision_id": "r1"}
    )
    assert result["success"] is False and result["error"] == "write_guard_rejected"
    assert await db.native_memories.count_documents({"memory_id": "protected"}) == 1


async def test_recreated_memory_vector_is_repaired_instead_of_erased(owned_backend, monkeypatch):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    await db.native_memories.insert_one(
        {"user_id": "owner", "memory_id": "recreated", "revision_id": "old"}
    )
    delete = AsyncMock(return_value=False)
    monkeypatch.setattr(vector_store, "index_delete", delete)
    await backend.delete("owner", "recreated")

    async def late_delete(*args):
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": "recreated",
                "revision_id": "new",
                "embedding": [0.4, 0.6],
                "updated_at": utc_now(),
                "scope": "project",
                "project_id": "alpha",
            }
        )
        return True

    delete.side_effect = late_delete
    write = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_write_through", write)
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["pending"] == 1
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert write.await_args.kwargs["embedding"] == [0.4, 0.6]
    assert write.await_args.kwargs["project_id"] == "alpha"
    assert await db.native_memories.count_documents({"revision_id": "new"}) == 1


async def test_cleanup_scheduler_finishes_explicit_deletion_with_memory_disabled(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.scheduler import RuntimeScheduler

    await cleanup.enqueue_content_cleanup(backend, "owner", "old-key")
    scheduler = RuntimeScheduler()
    monkeypatch.setattr("src.infra.scheduler.get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        "src.infra.memory.client.native.backend.NativeMemoryBackend", lambda: backend
    )
    monkeypatch.setattr(backend, "_ensure_collection", lambda: None)
    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_ENABLED", False)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_AUTO_COMPACT_ENABLED", False)
    cleanup.start_memory_cleanup_agent()
    assert (await scheduler.run_job_now("memory.cleanup"))["completed"] == 1
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_cleanup_rejects_mismatched_owner_namespace(owned_backend):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    foreign_ns = ("memories", "foreign", "content")
    await backend._store.aput(foreign_ns, "key", {"text": "foreign body"})
    task = await cleanup.enqueue_content_cleanup(backend, "owner", "key")
    await db.memory_resource_cleanup.update_one(
        {"_id": task["_id"]}, {"$set": {"namespace": list(foreign_ns)}}
    )
    assert (await cleanup.run_cleanup_pass(backend))["pending"] == 1
    assert await backend._store.aget(foreign_ns, "key") is not None


async def test_cleanup_backoff_and_batch_cap_do_not_starve_later_work(owned_backend):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    for i in range(105):
        task = await cleanup.enqueue_content_cleanup(backend, "owner", f"key-{i}")
        if i < 100:
            await db.memory_resource_cleanup.update_one(
                {"_id": task["_id"]}, {"$set": {"namespace": []}}
            )
    first = await cleanup.run_cleanup_pass(backend)
    assert first == {"checked": 100, "completed": 0, "pending": 100}
    second = await cleanup.run_cleanup_pass(backend)
    assert second == {"checked": 5, "completed": 5, "pending": 0}


async def test_real_qdrant_cleanup_recovers_after_delete_transport_failure(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    mid, foreign_mid = uuid4().hex, uuid4().hex
    vector = [0.2, 0.8]
    try:
        for memory_id, owner in ((mid, "owner"), (foreign_mid, "foreign")):
            assert await index.upsert(
                memory_id=memory_id,
                user_id=owner,
                vector=vector,
                memory_type="user",
                context="user",
                updated_at=1,
            )
        monkeypatch.setattr(vector_store, "get_vector_index", AsyncMock(return_value=index))
        original = index._client.delete
        attempts = 0

        async def fail_once(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("temporary vector transport failure")
            return await original(*args, **kwargs)

        monkeypatch.setattr(index._client, "delete", fail_once)
        await db.native_memories.insert_one(
            {"memory_id": mid, "user_id": "owner", "revision_id": "old"}
        )
        assert (await backend.delete("owner", mid))["success"] is True
        assert await db.memory_resource_cleanup.count_documents({}) == 1
        restarted = NativeMemoryBackend()
        restarted._collection, restarted._store = backend._collection, backend._store
        await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
        assert (await cleanup.run_cleanup_pass(restarted))["completed"] == 1
        assert await index.search(vector=vector, user_id="owner", limit=1) == []
        assert (await index.search(vector=vector, user_id="foreign", limit=1))[
            0
        ].memory_id == foreign_mid
    finally:
        await index.close()


@pytest.mark.parametrize("entry", ["native", "api_update", "api_import"])
async def test_replacement_cleanup_failure_keeps_new_body_index_and_cache_consistent(
    owned_backend, monkeypatch, entry
):
    backend, db = owned_backend
    from src.api.routes import memory as routes
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store
    from src.infra.memory.client.native.content import hydrate_memory_text_status
    from src.kernel.schemas.user import TokenPayload

    old = await backend.retain("owner", "Original complete facts. " * 150)
    mid = old["memory_id"]
    previous = await db.native_memories.find_one({"memory_id": mid})
    store = backend._store

    class FailingDeleteStore:
        def __getattr__(self, name):
            return getattr(store, name)

        async def adelete(self, namespace, key):
            raise OSError("old body cleanup unavailable")

    backend._store = FailingDeleteStore()
    backend._invalidate_cache.reset_mock()
    write_index = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_write_through", write_index)
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    user = TokenPayload(sub="owner", username="owner", roles=["user"])
    new_content = ("Revised complete facts. " * 170).strip()
    with pytest.raises(OSError, match="old body cleanup unavailable"):
        if entry == "native":
            await backend.retain("owner", new_content, existing_memory_id=mid)
        elif entry == "api_update":
            await routes.update_memory(mid, {"content": new_content}, user=user)
        else:
            await routes.import_memories(
                {"memories": [{"memory_id": mid, "content": new_content}]}, user=user
            )
    current = await db.native_memories.find_one({"memory_id": mid})
    assert current["content_store_key"] != previous["content_store_key"]
    backend._invalidate_cache.assert_awaited()
    write_index.assert_awaited()
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    backend._store = store
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert await hydrate_memory_text_status(backend, current) == (new_content, True)
    assert await store.aget(("memories", "owner", "content"), previous["content_store_key"]) is None


async def test_prepared_vector_intent_survives_a_tick_before_metadata_delete(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vector_store, "index_write_through", AsyncMock(return_value=True))
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_delete", delete)
    memory = {"user_id": "owner", "memory_id": "old", "revision_id": "r1"}
    await db.native_memories.insert_one(memory)
    await cleanup.prepare_deleted_resources(backend, "owner", "old", memory)
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    await db.native_memories.delete_many({})
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    delete.assert_awaited_once()


async def test_two_cleanup_workers_cannot_acknowledge_an_inflight_delete(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    entered, release = asyncio.Event(), asyncio.Event()
    original = {"user_id": "owner", "memory_id": "id", "revision_id": "old"}
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    await cleanup.prepare_deleted_resources(backend, "owner", "id", original)

    async def delayed_delete(*args):
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(vector_store, "index_delete", delayed_delete)
    write = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_write_through", write)
    first = asyncio.create_task(cleanup.run_cleanup_pass(backend))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": "id",
                "revision_id": "new",
                "embedding": [0.2, 0.8],
                "updated_at": utc_now(),
            }
        )
        assert (await cleanup.run_cleanup_pass(backend))["completed"] == 0
        assert await db.memory_resource_cleanup.count_documents({}) == 1
    finally:
        release.set()
        await first
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert write.await_count == 1


async def test_late_stale_delete_recreates_repair_work_after_takeover_ack(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from datetime import timedelta

    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    await cleanup.prepare_deleted_resources(backend, "owner", "id", {"revision_id": "old"})
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_delete(*args):
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(vector_store, "index_delete", delayed_delete)
    write = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_write_through", write)
    old = asyncio.create_task(cleanup.run_cleanup_pass(backend))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await db.memory_resource_cleanup.update_many(
            {}, {"$set": {"lease_until": utc_now() - timedelta(seconds=1)}}
        )
        await db.native_memories.insert_one(
            {"user_id": "owner", "memory_id": "id", "revision_id": "new", "embedding": [0.1, 0.9]}
        )
        assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
        assert await db.memory_resource_cleanup.count_documents({}) == 0
    finally:
        release.set()
        await old
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert write.await_count == 2


async def test_cleanup_repair_does_not_overwrite_a_foreign_same_id_point(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    mid = uuid4().hex
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    try:
        await index.upsert(
            memory_id=mid,
            user_id="foreign",
            vector=[0.1, 0.9],
            memory_type="user",
            context="user",
            updated_at=1,
        )
        monkeypatch.setattr(vector_store, "get_vector_index", AsyncMock(return_value=index))
        await db.native_memories.insert_many(
            [
                {"user_id": owner, "memory_id": mid, "revision_id": "new", "embedding": [0.9, 0.1]}
                for owner in ("owner", "foreign")
            ]
        )
        await cleanup._enqueue(
            backend, "owner", "vector", mid, prepared=False, deleted_revision="old"
        )
        assert (await cleanup.run_cleanup_pass(backend))["completed"] == 0
        assert (await index.search(vector=[0.1, 0.9], user_id="foreign", limit=1))[
            0
        ].memory_id == mid
    finally:
        await index.close()


@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_foreground_stale_delete_read_failure_restores_durable_repair(
    owned_backend, monkeypatch, failure
):
    from datetime import timedelta

    backend, db = owned_backend
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import vector_store

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_delete(*args):
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(vector_store, "index_delete", delayed_delete)
    write = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "index_write_through", write)
    foreground = asyncio.create_task(cleanup.delete_memory_vector(backend, "owner", "id"))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await db.memory_resource_cleanup.update_many(
            {}, {"$set": {"lease_until": utc_now() - timedelta(seconds=1)}}
        )
        await db.native_memories.insert_one(
            {"user_id": "owner", "memory_id": "id", "revision_id": "new", "embedding": [0.1, 0.9]}
        )
        assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
        assert await db.memory_resource_cleanup.count_documents({}) == 0
        original = type(db.native_memories).find_one
        fail = True

        async def fail_post_delete_read(collection, *args, **kwargs):
            nonlocal fail
            if collection.name == "native_memories" and fail and len(args) > 1:
                fail = False
                raise failure("post-delete verification unavailable")
            return await original(collection, *args, **kwargs)

        monkeypatch.setattr(type(db.native_memories), "find_one", fail_post_delete_read)
    finally:
        release.set()
    with pytest.raises(failure, match="post-delete verification unavailable"):
        await foreground
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert write.await_count == 2


@pytest.mark.parametrize("entry", ["native", "api_update", "api_import"])
async def test_replacement_interruption_before_cleanup_keeps_atomic_recovery_reference(
    owned_backend, monkeypatch, entry
):
    backend, db = owned_backend
    from src.api.routes import memory as routes
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import backend as backend_module
    from src.infra.memory.client.native import content
    from src.infra.memory.client.native.content import hydrate_memory_text_status
    from src.kernel.schemas.user import TokenPayload

    previous = await backend.retain("owner", "Original durable handbook. " * 150)
    mid = previous["memory_id"]
    before = await db.native_memories.find_one({"memory_id": mid})
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    interrupted = AsyncMock(side_effect=OSError("interrupted before cleanup registration"))
    monkeypatch.setattr(backend_module, "delete_memory_content", interrupted)
    monkeypatch.setattr(content, "delete_memory_content", interrupted)
    user = TokenPayload(sub="owner", username="owner", roles=["user"])
    replacement = ("Replacement durable handbook. " * 170).strip()
    with pytest.raises(OSError, match="before cleanup registration"):
        if entry == "native":
            await backend.retain("owner", replacement, existing_memory_id=mid)
        elif entry == "api_update":
            await routes.update_memory(mid, {"content": replacement}, user=user)
        else:
            await routes.import_memories(
                {"memories": [{"memory_id": mid, "content": replacement}]}, user=user
            )
    current = await db.native_memories.find_one({"memory_id": mid})
    assert current["content_store_key"] != before["content_store_key"]
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    assert before["content_store_key"] in str(current.get("_content_cleanup", [])), (
        "The metadata commit must retain the replaced key before any cleanup helper runs"
    )
    restarted = NativeMemoryBackend()
    restarted._collection, restarted._store = db.native_memories, backend._store
    await cleanup.run_cleanup_pass(restarted)
    assert (
        await backend._store.aget(("memories", "owner", "content"), before["content_store_key"])
        is None
    )
    assert await hydrate_memory_text_status(restarted, current) == (replacement, True)
    after = await db.native_memories.find_one({"memory_id": mid})
    assert not after.get("_content_cleanup")


@pytest.mark.parametrize("entry", ["native", "api_update", "api_import"])
async def test_overlapping_replacements_keep_every_intermediate_body_recoverable(
    owned_backend, monkeypatch, entry
):
    backend, db = owned_backend
    from src.api.routes import memory as routes
    from src.infra.memory import cleanup
    from src.infra.memory.client.native import backend as backend_module
    from src.infra.memory.client.native import content
    from src.kernel.schemas.user import TokenPayload

    previous = await backend.retain("owner", "Original durable policy. " * 150)
    mid = previous["memory_id"]
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    interrupted = AsyncMock(side_effect=OSError("interrupted before cleanup registration"))
    monkeypatch.setattr(backend_module, "delete_memory_content", interrupted)
    monkeypatch.setattr(content, "delete_memory_content", interrupted)
    ready, release = asyncio.Event(), asyncio.Event()
    arrived = 0

    async def embed_after_read(_):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await release.wait()
        return None

    backend._maybe_embed = embed_after_read
    user = TokenPayload(sub="owner", username="owner", roles=["user"])

    async def replace(label):
        body = (f"Durable revised policy {label}. " * 160).strip()
        if entry == "native":
            return await backend.retain("owner", body, existing_memory_id=mid)
        if entry == "api_update":
            return await routes.update_memory(mid, {"content": body}, user=user)
        return await routes.import_memories(
            {"memories": [{"memory_id": mid, "content": body}]}, user=user
        )

    tasks = [asyncio.create_task(replace(label)) for label in ("one", "two")]
    try:
        await asyncio.wait_for(ready.wait(), 5)
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(result, OSError) for result in results)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    current = await db.native_memories.find_one({"memory_id": mid})
    assert len(current.get("_content_cleanup", [])) == 2, (
        "Both overwritten body pointers must survive even when writers read the same old row"
    )
    await cleanup.run_cleanup_pass(backend)
    stored = await backend._store.asearch(("memories", "owner", "content"), limit=10)
    assert [item.key for item in stored] == [current["content_store_key"]]
    assert not (await db.native_memories.find_one({"memory_id": mid})).get("_content_cleanup")


async def test_delete_transfers_all_pending_replacement_references_before_removing_row(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    namespace = ("memories", "owner", "content")
    for key in ("current", "obsolete"):
        await backend._store.aput(namespace, key, {"text": key})
    await db.native_memories.insert_one(
        {
            "user_id": "owner",
            "memory_id": "old",
            "revision_id": "r1",
            "content_storage_mode": "store",
            "content_store_key": "current",
            "_content_cleanup": [{"key": "obsolete", "namespace": list(namespace)}],
        }
    )
    assert (await backend.delete("owner", "old"))["success"] is True
    await cleanup.run_cleanup_pass(backend)
    assert await backend._store.asearch(namespace, limit=10) == []
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_pending_reference_transfer_failure_keeps_references_and_concurrent_append(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    namespace = ["memories", "owner", "content"]
    first = {"key": "obsolete-one", "namespace": namespace}
    second = {"key": "obsolete-two", "namespace": namespace}
    await db.native_memories.insert_one(
        {
            "user_id": "owner",
            "memory_id": "old",
            "_content_cleanup": [first],
        }
    )
    original = type(db.native_memories).update_one
    calls = 0

    async def interrupt_transfer(collection, query, update, **kwargs):
        nonlocal calls
        if collection.name == "native_memories" and "$pull" in update:
            calls += 1
            if calls == 1:
                await original(
                    collection, {"memory_id": "old"}, {"$push": {"_content_cleanup": second}}
                )
                raise OSError("interrupted after enqueue before removing reference")
        return await original(collection, query, update, **kwargs)

    monkeypatch.setattr(type(db.native_memories), "update_one", interrupt_transfer)
    with pytest.raises(OSError, match="after enqueue"):
        await cleanup.run_cleanup_pass(backend)
    row = await db.native_memories.find_one({"memory_id": "old"})
    assert row["_content_cleanup"] == [first, second]
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    await cleanup.run_cleanup_pass(backend)
    assert not (await db.native_memories.find_one({"memory_id": "old"})).get("_content_cleanup")
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_pending_reference_discovery_uses_a_bounded_index_with_50k_unrelated_rows(
    owned_backend,
):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    await db.native_memories.insert_many(
        [
            {"memory_id": f"noise-{i}", "user_id": "foreign", "content": "unrelated"}
            for i in range(50000)
        ]
    )
    await cleanup.run_cleanup_pass(backend)
    explain = await db.command(
        {
            "explain": {
                "find": "native_memories",
                "filter": {"_content_cleanup.0": {"$exists": True}},
                "projection": {"user_id": 1, "_content_cleanup": 1},
                "sort": {"_id": 1},
                "limit": 100,
            },
            "verbosity": "executionStats",
        }
    )
    assert explain["executionStats"]["totalDocsExamined"] <= 5


@pytest.mark.parametrize("entry", ["native", "api_update", "api_import"])
async def test_replacement_pipeline_keeps_dollar_prefixed_user_text_literal(
    owned_backend, monkeypatch, entry
):
    backend, db = owned_backend
    from src.api.routes import memory as routes
    from src.kernel.schemas.user import TokenPayload

    old = await backend.retain("owner", "The user prefers readable SQL queries.")
    mid = old["memory_id"]
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    user = TokenPayload(sub="owner", username="owner", roles=["user"])
    text = "$private_field is a literal name used in the user's durable SQL convention."
    if entry == "native":
        await backend.retain("owner", text, existing_memory_id=mid)
    elif entry == "api_update":
        await routes.update_memory(mid, {"content": text, "title": "$private_field"}, user=user)
    else:
        await routes.import_memories({"memories": [{"memory_id": mid, "content": text}]}, user=user)
    row = await db.native_memories.find_one({"memory_id": mid})
    assert row["content"] == text
    if entry == "api_update":
        assert row["title"] == "$private_field"


async def test_reference_transfer_is_bounded_by_resources_not_just_memory_rows(owned_backend):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    for suffix in ("one", "two"):
        refs = [
            {"key": f"obsolete-{suffix}-{i}", "namespace": ["memories", "owner", "content"]}
            for i in range(61)
        ]
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": suffix,
                "_content_cleanup": refs,
            }
        )
    first = await cleanup.run_cleanup_pass(backend)
    assert first["completed"] == 100
    rows = await db.native_memories.find({}).to_list(length=10)
    assert sum(len(row.get("_content_cleanup", [])) for row in rows) == 22
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 22


@pytest.mark.parametrize("entry", ["native", "api_update", "api_import"])
@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_uncertain_replacement_commit_keeps_recovery_and_invalidates_cache(
    owned_backend, monkeypatch, entry, committed, failure
):
    backend, db = owned_backend
    from src.api.routes import memory as routes
    from src.infra.memory import cleanup
    from src.infra.memory.client.native.content import hydrate_memory_text_status
    from src.kernel.schemas.user import TokenPayload

    original_body = ("Original durable handling instruction. " * 140).strip()
    saved = await backend.retain("owner", original_body)
    mid = saved["memory_id"]
    before = await db.native_memories.find_one({"memory_id": mid})
    backend._invalidate_cache.reset_mock()
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    method = "find_one_and_update" if entry == "api_import" else "update_one"
    original = getattr(type(db.native_memories), method)

    async def unknown_commit(collection, *args, **kwargs):
        if (
            collection.name == "native_memories"
            and args[0].get("memory_id") == mid
            and isinstance(args[1], list)
        ):
            if committed:
                await original(collection, *args, **kwargs)
            raise failure("replacement outcome unknown")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(type(db.native_memories), method, unknown_commit)
    replacement = ("Revised durable handling instruction. " * 150).strip()
    user = TokenPayload(sub="owner", username="owner", roles=["user"])
    with pytest.raises(failure, match="outcome unknown"):
        if entry == "native":
            await backend.retain("owner", replacement, existing_memory_id=mid)
        elif entry == "api_update":
            await routes.update_memory(mid, {"content": replacement}, user=user)
        else:
            await routes.import_memories(
                {"memories": [{"memory_id": mid, "content": replacement}]}, user=user
            )
    backend._invalidate_cache.assert_awaited_with("owner")
    monkeypatch.setattr(type(db.native_memories), method, original)
    await cleanup.run_cleanup_pass(backend)
    current = await db.native_memories.find_one({"memory_id": mid})
    assert await hydrate_memory_text_status(backend, current) == (
        replacement if committed else original_body,
        True,
    )
    old_body = await backend._store.aget(
        ("memories", "owner", "content"), before["content_store_key"]
    )
    assert (old_body is None) is committed


async def test_successful_reference_transfer_preserves_a_concurrent_new_reference(
    owned_backend, monkeypatch
):
    backend, db = owned_backend
    from src.infra.memory import cleanup

    namespace = ["memories", "owner", "content"]
    first = {"key": "obsolete-one", "namespace": namespace}
    second = {"key": "obsolete-two", "namespace": namespace}
    for ref in (first, second):
        await backend._store.aput(tuple(namespace), ref["key"], {"text": ref["key"]})
    await db.native_memories.insert_one(
        {
            "user_id": "owner",
            "memory_id": "old",
            "_content_cleanup": [first],
        }
    )
    original = cleanup._enqueue
    appended = False

    async def append_during_transfer(*args, **kwargs):
        nonlocal appended
        task = await original(*args, **kwargs)
        if not appended:
            appended = True
            await db.native_memories.update_one(
                {"memory_id": "old"}, {"$push": {"_content_cleanup": second}}
            )
        return task

    monkeypatch.setattr(cleanup, "_enqueue", append_during_transfer)
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert (await db.native_memories.find_one({"memory_id": "old"}))["_content_cleanup"] == [second]
    assert await backend._store.aget(tuple(namespace), first["key"]) is None
    assert await backend._store.aget(tuple(namespace), second["key"]) is not None
    assert (await cleanup.run_cleanup_pass(backend))["completed"] == 1
    assert await backend._store.aget(tuple(namespace), second["key"]) is None
