"""Legacy cleanup must use the same durable owner/version guards as explicit deletion."""

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory import cleanup
from src.infra.memory.client.native import vector_store
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def legacy_backend(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_legacy_cleanup_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=name)
    backend._invalidate_cache = AsyncMock()
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    await index.ensure_collection()
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vector_store, "get_vector_index", AsyncMock(return_value=index))
    try:
        yield backend, db, index
    finally:
        await index.close()
        await client.drop_database(name)
        await client.close()


async def seed(backend, index, *, owner="owner", source="session_summary"):
    mid, key = uuid4().hex, uuid4().hex
    namespace = ("memories", owner, "content")
    await backend._store.aput(namespace, key, {"text": "Complete legacy text"})
    await backend._collection.insert_one(
        {
            "memory_id": mid,
            "user_id": owner,
            "revision_id": uuid4().hex,
            "source": source,
            "origin_session_ids": ["original-session"],
            "content_storage_mode": "store",
            "content_store_key": key,
            "embedding": [1.0, 0.0],
            "updated_at": utc_now(),
        }
    )
    assert await index.upsert(
        memory_id=mid,
        user_id=owner,
        vector=[1.0, 0.0],
        memory_type="user",
        context=None,
        updated_at=1,
    )
    return mid, key, namespace


async def test_legacy_cleanup_removes_owned_resources_without_forgetting_sources(legacy_backend):
    backend, db, index = legacy_backend
    first, first_key, first_ns = await seed(backend, index)
    second, second_key, second_ns = await seed(backend, index, owner="another-owner")
    manual, manual_key, manual_ns = await seed(
        backend, index, owner="another-owner", source="manual"
    )
    obsolete = "obsolete-body"
    await backend._store.aput(first_ns, obsolete, {"text": "Old replacement body"})
    await db.native_memories.update_one(
        {"memory_id": first},
        {
            "$set": {
                "_content_cleanup": [{"key": obsolete, "namespace": list(first_ns)}],
            }
        },
    )
    await backend._prune_legacy_session_summaries()
    await cleanup.run_cleanup_pass(backend)
    assert await db.native_memories.count_documents({"source": "session_summary"}) == 0
    assert await backend._store.aget(first_ns, first_key) is None
    assert await backend._store.aget(first_ns, obsolete) is None
    assert await backend._store.aget(second_ns, second_key) is None
    assert await backend._store.aget(manual_ns, manual_key) is not None
    assert await index.search(vector=[1.0, 0.0], user_id="owner", limit=5) == []
    assert [
        point.memory_id
        for point in await index.search(vector=[1.0, 0.0], user_id="another-owner", limit=5)
    ] == [manual]
    assert await db.memory_forget_watermarks.count_documents({}) == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_legacy_cleanup_prepare_failure_preserves_record_and_external_body(
    legacy_backend, monkeypatch
):
    backend, db, index = legacy_backend
    mid, key, namespace = await seed(backend, index)
    original = type(db.memory_resource_cleanup).update_one

    async def fail_journal(collection, *args, **kwargs):
        if collection.name == "memory_resource_cleanup":
            raise OSError("journal unavailable")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(type(db.memory_resource_cleanup), "update_one", fail_journal)
    await backend._prune_legacy_session_summaries()
    assert await db.native_memories.count_documents({"memory_id": mid}) == 1
    assert await backend._store.aget(namespace, key) is not None
    assert (await index.search(vector=[1.0, 0.0], user_id="owner", limit=1))[0].memory_id == mid


async def test_legacy_cleanup_does_not_delete_a_concurrent_manual_replacement(
    legacy_backend, monkeypatch
):
    backend, db, index = legacy_backend
    mid, key, namespace = await seed(backend, index)
    original = type(db.native_memories).find_one_and_delete
    changed = False

    async def replace_before_delete(collection, query, **kwargs):
        nonlocal changed
        if collection.name == "native_memories" and query.get("memory_id") == mid:
            changed = True
            await collection.update_one(
                {"memory_id": mid},
                {
                    "$set": {
                        "source": "manual",
                        "revision_id": "new-manual",
                        "embedding": [0.0, 1.0],
                    }
                },
            )
            await backend._store.aput(namespace, key, {"text": "New manual facts"})
        return await original(collection, query, **kwargs)

    monkeypatch.setattr(type(db.native_memories), "find_one_and_delete", replace_before_delete)
    await backend._prune_legacy_session_summaries()
    assert changed, "Legacy pruning must use the conditional resource-aware deletion path"
    await cleanup.run_cleanup_pass(backend)
    current = await db.native_memories.find_one({"memory_id": mid})
    assert current["source"] == "manual"
    assert (await backend._store.aget(namespace, key)).value["text"] == "New manual facts"
    assert (await index.search(vector=[0.0, 1.0], user_id="owner", limit=1))[
        0
    ].score == pytest.approx(1.0)
    assert await db.memory_forget_watermarks.count_documents({}) == 0


async def test_legacy_cleanup_is_bounded_and_registered_job_resumes_the_remainder(
    legacy_backend, monkeypatch
):
    backend, db, index = legacy_backend
    from src.infra.scheduler import RuntimeScheduler

    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    await db.native_memories.insert_many(
        [
            {
                "user_id": "owner",
                "memory_id": uuid4().hex,
                "source": "session_summary",
                "revision_id": uuid4().hex,
            }
            for _ in range(137)
        ]
    )
    await backend._prune_legacy_session_summaries()
    assert await db.native_memories.count_documents({}) == 37
    scheduler = RuntimeScheduler()
    monkeypatch.setattr("src.infra.scheduler.get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        "src.infra.memory.client.native.backend.NativeMemoryBackend", lambda: backend
    )
    monkeypatch.setattr(backend, "_ensure_collection", lambda: None)
    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_ENABLED", False)
    cleanup.start_memory_cleanup_agent()
    await scheduler.run_job_now("memory.cleanup")
    assert await db.native_memories.count_documents({}) == 37
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    await scheduler.run_job_now("memory.cleanup")
    assert await db.native_memories.count_documents({}) == 0


async def test_legacy_cleanup_keeps_records_without_resolvable_owner_or_identity(legacy_backend):
    backend, db, index = legacy_backend
    rows = [
        {"memory_id": uuid4().hex},
        {"user_id": "owner"},
        {"user_id": "", "memory_id": uuid4().hex},
    ]
    for row in rows:
        await db.native_memories.insert_one({**row, "source": "session_summary"})
    await backend._prune_legacy_session_summaries()
    assert await db.native_memories.count_documents({}) == 3


async def test_legacy_discovery_does_not_scan_50k_unrelated_records(legacy_backend):
    backend, db, index = legacy_backend
    await db.native_memories.insert_many(
        [{"user_id": "owner", "memory_id": uuid4().hex, "source": "manual"} for _ in range(50000)]
    )
    await backend._prune_legacy_session_summaries()
    explain = await db.command(
        {
            "explain": {
                "find": "native_memories",
                "filter": {
                    "source": "session_summary",
                    "user_id": {"$type": "string", "$ne": ""},
                    "memory_id": {"$type": "string", "$ne": ""},
                },
                "projection": {"user_id": 1, "memory_id": 1, "revision_id": 1},
                "sort": {"_id": 1},
                "limit": 100,
            },
            "verbosity": "executionStats",
        }
    )
    assert explain["executionStats"]["totalDocsExamined"] <= 5


async def test_legacy_inventory_cannot_delete_a_recreated_row_with_reused_id_and_missing_revision(
    legacy_backend, monkeypatch
):
    backend, db, index = legacy_backend
    mid = uuid4().hex
    old = {"user_id": "owner", "memory_id": mid, "source": "session_summary"}
    old_id = (await db.native_memories.insert_one(old)).inserted_id
    original = backend._delete_matching_memory
    replacement_id = None

    async def replace_inventory_row(owner, memory, query, **kwargs):
        nonlocal replacement_id
        assert replacement_id is None
        await db.native_memories.delete_one({"_id": old_id})
        replacement_id = (
            await db.native_memories.insert_one(
                {
                    "user_id": "owner",
                    "memory_id": mid,
                    "source": "session_summary",
                    "content": "Newly restored legacy content",
                }
            )
        ).inserted_id
        return await original(owner, memory, query, **kwargs)

    monkeypatch.setattr(backend, "_delete_matching_memory", replace_inventory_row)
    await backend._prune_legacy_session_summaries()
    assert replacement_id is not None
    assert await db.native_memories.count_documents({"_id": replacement_id}) == 1


@pytest.mark.parametrize("failure", ["journal", "body"])
async def test_one_legacy_cleanup_failure_does_not_block_another_selected_owner(
    legacy_backend, monkeypatch, failure
):
    backend, db, index = legacy_backend
    first, key, namespace = await seed(backend, index)
    second, second_key, second_ns = await seed(backend, index, owner="another-owner")
    enqueue = cleanup._enqueue
    delete = type(backend._store).adelete

    async def fail_owner_journal(target, owner, *args, **kwargs):
        if owner == "owner":
            raise OSError("first owner journal unavailable")
        return await enqueue(target, owner, *args, **kwargs)

    async def fail_owner_body(store, ns, key):
        if ns[1] == "owner":
            raise OSError("first owner body unavailable")
        return await delete(store, ns, key)

    if failure == "journal":
        monkeypatch.setattr(cleanup, "_enqueue", fail_owner_journal)
    else:
        monkeypatch.setattr(type(backend._store), "adelete", fail_owner_body)
    await backend._prune_legacy_session_summaries()
    assert await db.native_memories.count_documents({"memory_id": second}) == 0
    assert await backend._store.aget(second_ns, second_key) is None
    assert await backend._store.aget(namespace, key) is not None
    assert await db.native_memories.count_documents({"memory_id": first}) == (
        1 if failure == "journal" else 0
    )
    monkeypatch.setattr(cleanup, "_enqueue", enqueue)
    monkeypatch.setattr(type(backend._store), "adelete", delete)
    await backend._prune_legacy_session_summaries()
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    await cleanup.run_cleanup_pass(backend)
    assert await db.native_memories.count_documents({}) == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    assert await backend._store.aget(namespace, key) is None


@pytest.mark.parametrize("committed", [False, True])
async def test_unknown_legacy_delete_outcome_preserves_recoverable_resources(
    legacy_backend, monkeypatch, committed
):
    backend, db, index = legacy_backend
    mid, key, namespace = await seed(backend, index)
    original = type(db.native_memories).find_one_and_delete

    async def unknown_commit(collection, *args, **kwargs):
        if collection.name == "native_memories":
            if committed:
                await original(collection, *args, **kwargs)
            raise OSError("unknown legacy deletion outcome")
        return await original(collection, *args, **kwargs)

    monkeypatch.setattr(type(db.native_memories), "find_one_and_delete", unknown_commit)
    await backend._prune_legacy_session_summaries()
    assert await db.native_memories.count_documents({"memory_id": mid}) == (0 if committed else 1)
    assert await db.memory_resource_cleanup.count_documents({}) == 2
    await cleanup.run_cleanup_pass(backend)
    assert (await backend._store.aget(namespace, key) is None) is committed
    monkeypatch.setattr(type(db.native_memories), "find_one_and_delete", original)
    await backend._prune_legacy_session_summaries()
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    await cleanup.run_cleanup_pass(backend)
    assert await db.native_memories.count_documents({}) == 0
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    assert await index.search(vector=[1.0, 0.0], user_id="owner", limit=1) == []


async def test_disabled_memory_does_not_start_legacy_retirement_but_finishes_explicit_resource_work(
    legacy_backend, monkeypatch
):
    backend, db, index = legacy_backend
    from src.infra.scheduler import RuntimeScheduler

    mid, key, namespace = await seed(backend, index)
    await cleanup.enqueue_content_cleanup(backend, "owner", "previously-deleted-resource")
    scheduler = RuntimeScheduler()
    monkeypatch.setattr("src.infra.scheduler.get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        "src.infra.memory.client.native.backend.NativeMemoryBackend", lambda: backend
    )
    monkeypatch.setattr(backend, "_ensure_collection", lambda: None)
    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    cleanup.start_memory_cleanup_agent()
    result = await scheduler.run_job_now("memory.cleanup")
    assert result["completed"] == 1
    assert await db.native_memories.count_documents({"memory_id": mid}) == 1
    assert await backend._store.aget(namespace, key) is not None
    assert (await index.search(vector=[1.0, 0.0], user_id="owner", limit=1))[0].memory_id == mid
