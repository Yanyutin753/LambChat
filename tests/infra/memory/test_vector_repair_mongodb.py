"""Persisted vector repair must survive provider failures and backend restarts."""

import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.api.routes import memory as routes
from src.infra.memory import cleanup
from src.infra.memory.client.native import search, vector_store
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.user import TokenPayload

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def vector_backend(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_vector_repair_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=name)
    backend._maybe_embed = AsyncMock(return_value=[1.0, 0.0])
    backend._invalidate_cache = AsyncMock()
    index = vector_store.QdrantVectorIndex(location=":memory:", dims=2)
    await index.ensure_collection()
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vector_store, "get_vector_index", AsyncMock(return_value=index))
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    try:
        yield backend, db, index
    finally:
        await index.close()
        await client.drop_database(name)
        await client.close()


async def retain(backend, text, memory_id=None):
    return await backend.retain(
        "owner",
        text,
        title="Durable policy",
        summary=text,
        tags=["policy"],
        existing_memory_id=memory_id,
    )


@pytest.mark.parametrize(
    "entry", ["native_create", "native_update", "api_create", "api_update", "api_import"]
)
@pytest.mark.parametrize("failure", [None, OSError, asyncio.CancelledError])
async def test_failed_vector_write_is_repaired_after_restart(
    vector_backend, monkeypatch, entry, failure
):
    backend, db, index = vector_backend
    old_id = None
    if entry.endswith("update"):
        backend._maybe_embed.return_value = [0.0, 1.0]
        old_id = (await retain(backend, "Original policy keeps invoices for seven months."))[
            "memory_id"
        ]
    backend._maybe_embed.return_value = [1.0, 0.0]
    transport = index._client.upsert
    original_write = vector_store.index_write_through
    if failure is not None:
        monkeypatch.setattr(
            vector_store,
            "index_write_through",
            AsyncMock(side_effect=failure("vector interrupted")),
        )
    monkeypatch.setattr(
        index._client, "upsert", AsyncMock(side_effect=OSError("vector transport down"))
    )
    text = "The user keeps signed invoices for thirty seven months."
    user = TokenPayload(sub="owner", username="owner", roles=["user"])

    async def mutate():
        if entry.startswith("native"):
            return await retain(backend, text, old_id)
        elif entry == "api_create":
            return await routes.create_memory({"content": text}, user=user)
        elif entry == "api_update":
            return await routes.update_memory(old_id, {"content": text}, user=user)
        else:
            return await routes.import_memories({"memories": [{"content": text}]}, user=user)

    if failure is None:
        assert (await mutate())["success"] is True
    else:
        with pytest.raises(failure):
            await mutate()
    current = await db.native_memories.find_one({"user_id": "owner"})
    assert current["content"] == text
    assert current.get("_vector_pending"), (
        "Mongo commit must preserve repair state before vector I/O"
    )
    backend._invalidate_cache.assert_awaited_with("owner")
    monkeypatch.setattr(index._client, "upsert", transport)
    monkeypatch.setattr(vector_store, "index_write_through", original_write)
    restarted = NativeMemoryBackend()
    restarted._collection, restarted._store = db.native_memories, backend._store
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    await cleanup.run_cleanup_pass(restarted)
    points = await index.search(vector=[1.0, 0.0], user_id="owner", limit=5)
    assert [point.memory_id for point in points] == [current["memory_id"]]
    assert points[0].score == pytest.approx(1.0)
    assert not (await db.native_memories.find_one({"memory_id": current["memory_id"]})).get(
        "_vector_pending"
    )
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_pending_fresh_memory_beats_a_full_but_stale_ann_result(vector_backend, monkeypatch):
    backend, db, index = vector_backend
    backend._maybe_embed.return_value = [0.7, 0.7]
    prior = await retain(backend, "Another durable policy unrelated to the current question.")
    backend._maybe_embed.return_value = [1.0, 0.0]
    transport = index._client.upsert
    monkeypatch.setattr(
        index._client, "upsert", AsyncMock(side_effect=OSError("vector transport down"))
    )
    fresh = await retain(
        backend, "The user's archive policy keeps invoices for thirty seven months."
    )
    assert fresh["memory_id"] != prior["memory_id"]
    result = await search.vector_search(backend, "owner", "invoice retention", 1, None)
    assert [row["memory_id"] for row in result] == [fresh["memory_id"]]
    monkeypatch.setattr(index._client, "upsert", transport)


async def test_pending_vector_is_not_hidden_by_simulated_stale_atlas_candidates(
    vector_backend, monkeypatch
):
    backend, db, index = vector_backend
    backend._maybe_embed.return_value = [0.7, 0.7]
    old = await retain(backend, "A durable policy about another topic.")
    old_doc = await db.native_memories.find_one({"memory_id": old["memory_id"]})
    backend._maybe_embed.return_value = [1.0, 0.0]
    monkeypatch.setattr(index._client, "upsert", AsyncMock(side_effect=OSError("vector down")))
    fresh = await retain(backend, "The user keeps signed invoices for thirty seven months.")
    monkeypatch.setattr(vector_store, "index_search", AsyncMock(return_value=[]))
    original = backend._collection

    class SimulatedAtlasCursor:
        async def to_list(self, length):
            return [old_doc]

    class SimulatedAtlasCollection:
        def __getattr__(self, name):
            return getattr(original, name)

        async def aggregate(self, pipeline):
            return SimulatedAtlasCursor()

    backend._collection = SimulatedAtlasCollection()
    result = await search.vector_search(backend, "owner", "invoice retention", 1, None)
    assert [row["memory_id"] for row in result] == [fresh["memory_id"]]


@pytest.mark.parametrize(
    "entry", ["native_create", "native_update", "api_create", "api_update", "api_import"]
)
async def test_unknown_metadata_commit_repairs_without_running_foreground_index_helper(
    vector_backend, monkeypatch, entry
):
    backend, db, index = vector_backend
    mid = None
    if entry.endswith("update"):
        backend._maybe_embed.return_value = [0.0, 1.0]
        mid = (await retain(backend, "Original policy keeps invoices for seven months."))[
            "memory_id"
        ]
    backend._maybe_embed.return_value = [1.0, 0.0]
    backend._invalidate_cache.reset_mock()
    method = (
        "update_one"
        if entry.endswith("update")
        else "find_one_and_update"
        if entry == "api_import"
        else "insert_one"
    )
    original = getattr(type(db.native_memories), method)

    async def unknown_commit(collection, *args, **kwargs):
        result = await original(collection, *args, **kwargs)
        if collection.name == "native_memories":
            raise OSError("unknown metadata commit")
        return result

    monkeypatch.setattr(type(db.native_memories), method, unknown_commit)
    text = "The user keeps signed invoices for thirty seven months."
    user = TokenPayload(sub="owner", username="owner", roles=["user"])
    with pytest.raises(OSError, match="unknown metadata commit"):
        if entry.startswith("native"):
            await retain(backend, text, mid)
        elif entry == "api_create":
            await routes.create_memory({"content": text}, user=user)
        elif entry == "api_update":
            await routes.update_memory(mid, {"content": text}, user=user)
        else:
            await routes.import_memories({"memories": [{"content": text}]}, user=user)
    backend._invalidate_cache.assert_awaited_with("owner")
    assert await db.memory_resource_cleanup.count_documents({}) == 0
    monkeypatch.setattr(type(db.native_memories), method, original)
    await cleanup.run_cleanup_pass(backend)
    row = await db.native_memories.find_one({"user_id": "owner"})
    assert not row.get("_vector_pending")
    points = await index.search(vector=[1.0, 0.0], user_id="owner", limit=1)
    assert points[0].memory_id == row["memory_id"]
    assert points[0].score == pytest.approx(1.0)


@pytest.mark.parametrize("pause", ["before_commit", "after_commit"])
async def test_cancelled_write_guard_leaves_no_staged_body_or_repaired_vector(
    vector_backend, pause
):
    backend, db, index = vector_backend
    calls = 0

    async def guard():
        nonlocal calls
        calls += 1
        if pause == "after_commit" and calls == 1:
            return True
        if pause == "after_commit":
            await cleanup.run_cleanup_pass(backend)
            assert await index.search(vector=[1.0, 0.0], user_id="owner", limit=1)
        raise asyncio.CancelledError("guard cancelled")

    with pytest.raises(asyncio.CancelledError, match="guard cancelled"):
        await backend.retain(
            "owner",
            "Durable policy with complete details. " * 150,
            title="Invoice policy",
            summary="Durable invoice policy",
            tags=["policy"],
            write_guard=guard,
        )
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    await cleanup.run_cleanup_pass(backend)
    assert await db.native_memories.count_documents({}) == 0
    assert await backend._store.asearch(("memories", "owner", "content"), limit=10) == []
    assert await index.search(vector=[1.0, 0.0], user_id="owner", limit=1) == []


async def test_pending_repair_does_not_reset_existing_backoff(vector_backend, monkeypatch):
    backend, db, index = vector_backend
    failed = AsyncMock(side_effect=OSError("vector transport down"))
    monkeypatch.setattr(index._client, "upsert", failed)
    await retain(backend, "The user keeps signed invoices for thirty seven months.")
    before = await db.memory_resource_cleanup.find_one({})
    assert failed.await_count == 1
    assert (await cleanup.run_cleanup_pass(backend))["checked"] == 0
    after = await db.memory_resource_cleanup.find_one({})
    assert failed.await_count == 1
    for field in ("version", "retry_at", "attempts"):
        assert after[field] == before[field]


async def test_sync_can_repair_but_cannot_acknowledge_a_preparing_deletion(
    vector_backend, monkeypatch
):
    backend, db, index = vector_backend
    transport = index._client.upsert
    monkeypatch.setattr(index._client, "upsert", AsyncMock(side_effect=OSError("vector down")))
    mid = (await retain(backend, "The user keeps signed invoices for thirty seven months."))[
        "memory_id"
    ]
    row = await db.native_memories.find_one({"memory_id": mid})
    await cleanup.prepare_deleted_resources(backend, "owner", mid, row)
    monkeypatch.setattr(index._client, "upsert", transport)
    result = await cleanup.run_cleanup_pass(backend)
    assert result["completed"] == 0
    assert (await db.memory_resource_cleanup.find_one({}))["prepared"] is True
    assert not (await db.native_memories.find_one({"memory_id": mid})).get("_vector_pending")
    assert (await index.search(vector=[1.0, 0.0], user_id="owner", limit=1))[0].memory_id == mid
    assert (await backend.delete("owner", mid))["success"] is True
    assert await index.search(vector=[1.0, 0.0], user_id="owner", limit=1) == []
    assert await db.memory_resource_cleanup.count_documents({}) == 0


@pytest.mark.parametrize("later", ["update", "delete"])
async def test_late_old_vector_write_cannot_lose_current_repair_intent(
    vector_backend, monkeypatch, later
):
    backend, db, index = vector_backend
    mid = (await retain(backend, "Original policy keeps invoices for seven months."))["memory_id"]
    entered, release = asyncio.Event(), asyncio.Event()
    transport = index._client.upsert

    async def delayed_write(*args, **kwargs):
        entered.set()
        await release.wait()
        return await transport(*args, **kwargs)

    monkeypatch.setattr(index._client, "upsert", delayed_write)
    backend._maybe_embed.return_value = [0.0, 1.0]
    old = asyncio.create_task(
        retain(backend, "First revised policy keeps invoices for eleven months.", mid)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if later == "delete":
            assert (await backend.delete("owner", mid))["success"] is True
        else:
            backend._maybe_embed.return_value = [1.0, 0.0]
            user = TokenPayload(sub="owner", username="owner", roles=["user"])
            assert (
                await routes.update_memory(
                    mid, {"content": "Latest invoice retention is thirty seven months."}, user=user
                )
            )["success"] is True
        release.set()
        assert (await old)["success"] is True
    finally:
        release.set()
        await asyncio.gather(old, return_exceptions=True)
    assert await db.memory_resource_cleanup.count_documents({}) == 1
    if later == "update":
        row = await db.native_memories.find_one({"memory_id": mid})
        assert row.get("_vector_pending")
        assert row["content"].startswith("Latest")
        result = await search.vector_search(backend, "owner", "invoice retention", 1, None)
        assert result[0]["score"] == pytest.approx(1.0)
    monkeypatch.setattr(index._client, "upsert", transport)
    await db.memory_resource_cleanup.update_many({}, {"$set": {"retry_at": utc_now()}})
    await cleanup.run_cleanup_pass(backend)
    points = await index.search(vector=[1.0, 0.0], user_id="owner", limit=1)
    if later == "delete":
        assert points == []
    else:
        assert points[0].score == pytest.approx(1.0)
        assert not (await db.native_memories.find_one({"memory_id": mid})).get("_vector_pending")
    assert await db.memory_resource_cleanup.count_documents({}) == 0


async def test_pending_ranking_preserves_owner_project_type_and_context_filters(
    vector_backend, monkeypatch
):
    backend, db, index = vector_backend
    backend._maybe_embed.return_value = [0.7, 0.7]
    await backend.retain(
        "owner",
        "A durable user preference unrelated to the invoice question.",
        context="invoice",
        title="Other policy",
        summary="Another durable policy",
        tags=["policy"],
    )
    now = utc_now()
    target = uuid4().hex
    rows = []
    for owner, project, kind, context, vector, mid in [
        ("owner", "p", "user", "invoice", [0.99, 0.01], target),
        ("foreign", "p", "user", "invoice", [1.0, 0.0], uuid4().hex),
        ("owner", "other", "user", "invoice", [1.0, 0.0], uuid4().hex),
        ("owner", "p", "feedback", "invoice", [1.0, 0.0], uuid4().hex),
        ("owner", "p", "user", "travel", [1.0, 0.0], uuid4().hex),
    ]:
        rows.append(
            {
                "memory_id": mid,
                "user_id": owner,
                "scope": "project",
                "project_id": project,
                "memory_type": kind,
                "context": context,
                "embedding": vector,
                "content": "Durable invoice rule",
                "summary": "Durable invoice rule",
                "source": "manual",
                "updated_at": now,
                "created_at": now,
                "_vector_pending": uuid4().hex,
            }
        )
    await db.native_memories.insert_many(rows)
    backend._maybe_embed.return_value = [1.0, 0.0]
    result = await search.vector_search(
        backend, "owner", "invoice retention", 1, ["user"], context_filter="invoice", project_id="p"
    )
    assert [row["memory_id"] for row in result] == [target]


async def test_blocked_queued_rows_cannot_starve_a_later_undiscovered_memory(vector_backend):
    backend, db, index = vector_backend
    from datetime import timedelta

    rows = []
    for _ in range(100):
        mid = uuid4().hex
        rows.extend(
            [
                {
                    "user_id": "owner",
                    "memory_id": mid,
                    "embedding": [1.0, 0.0],
                    "_vector_pending": uuid4().hex,
                },
                {"user_id": "foreign", "memory_id": mid, "embedding": [1.0, 0.0]},
            ]
        )
        await cleanup._enqueue(backend, "owner", "vector", mid, prepared=False)
    await db.native_memories.insert_many(rows)
    await db.memory_resource_cleanup.update_many(
        {}, {"$set": {"retry_at": utc_now() + timedelta(minutes=5)}}
    )
    fresh = uuid4().hex
    await db.native_memories.insert_one(
        {
            "user_id": "owner",
            "memory_id": fresh,
            "embedding": [1.0, 0.0],
            "_vector_pending": uuid4().hex,
            "revision_id": uuid4().hex,
            "updated_at": utc_now(),
        }
    )
    for _ in range(2):
        await cleanup.run_cleanup_pass(backend)
    points = await index.search(vector=[1.0, 0.0], user_id="owner", limit=1)
    assert [point.memory_id for point in points] == [fresh]
    assert not (await db.native_memories.find_one({"memory_id": fresh})).get("_vector_pending")


@pytest.mark.parametrize("downgraded", [False, True])
async def test_concurrent_pending_snapshot_replaces_the_same_ann_memory_without_duplicates(
    vector_backend, monkeypatch, downgraded
):
    backend, db, index = vector_backend
    first = (await retain(backend, "Original invoice policy keeps records for seven months."))[
        "memory_id"
    ]
    backend._maybe_embed.return_value = [0.7, 0.7]
    second = (await retain(backend, "A separate durable policy about account backups."))[
        "memory_id"
    ]
    third = None
    if downgraded:
        backend._maybe_embed.return_value = [0.99, 0.01]
        transport = index._client.upsert
        monkeypatch.setattr(index._client, "upsert", AsyncMock(side_effect=OSError("vector down")))
        third = (await retain(backend, "A durable and relevant policy about invoice delivery."))[
            "memory_id"
        ]
        monkeypatch.setattr(index._client, "upsert", transport)
    backend._maybe_embed.return_value = [1.0, 0.0]
    collection = backend._collection
    changed = False

    class HydrationCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        async def to_list(self, length):
            nonlocal changed
            docs = await self.cursor.to_list(length=length)
            if not changed:
                changed = True
                await collection.update_one(
                    {"memory_id": first},
                    {
                        "$set": {
                            "content": "Latest invoice retention is thirty seven months.",
                            "embedding": [0.0, 1.0] if downgraded else [1.0, 0.0],
                            "_vector_pending": uuid4().hex,
                            "revision_id": uuid4().hex,
                        }
                    },
                )
            return docs

    class HydrationCollection:
        def __getattr__(self, name):
            return getattr(collection, name)

        def find(self, query, *args, **kwargs):
            cursor = collection.find(query, *args, **kwargs)
            if query.get("_vector_pending") == {"$exists": False}:
                return HydrationCursor(cursor)
            return cursor

    backend._collection = HydrationCollection()
    result = await search.vector_search(
        backend, "owner", "invoice retention", 1 if downgraded else 2, None
    )
    assert changed
    if downgraded:
        assert [row["memory_id"] for row in result] == [third]
    else:
        assert len(result) == 2
        assert {row["memory_id"] for row in result} == {first, second}
        assert next(row for row in result if row["memory_id"] == first)["text"].startswith("Latest")


async def test_pending_discovery_and_owner_scoring_use_indexes_with_50k_noise(vector_backend):
    backend, db, index = vector_backend
    await cleanup.run_cleanup_pass(backend)
    now = utc_now()
    await db.native_memories.insert_many(
        [{"memory_id": uuid4().hex, "user_id": "foreign", "content": "noise"} for _ in range(50000)]
    )
    await db.native_memories.insert_many(
        [
            {
                "memory_id": uuid4().hex,
                "user_id": owner,
                "_vector_pending": uuid4().hex,
                "embedding": [1.0, 0.0],
                "updated_at": now,
            }
            for owner in ["foreign"] * 200 + ["owner"] * 2
        ]
    )
    discovery = await db.command(
        {
            "explain": {
                "find": "native_memories",
                "filter": {"_vector_pending": {"$exists": True}},
                "projection": {"user_id": 1, "memory_id": 1},
                "sort": {"_id": 1},
                "limit": 100,
            },
            "verbosity": "executionStats",
        }
    )
    owned = await db.command(
        {
            "explain": {
                "find": "native_memories",
                "filter": {
                    "user_id": "owner",
                    "_vector_pending": {"$exists": True},
                    "embedding": {"$exists": True, "$ne": None},
                },
                "projection": {"memory_id": 1, "embedding": 1},
                "sort": {"updated_at": -1},
            },
            "verbosity": "executionStats",
        }
    )
    assert discovery["executionStats"]["totalDocsExamined"] <= 100
    assert owned["executionStats"]["totalDocsExamined"] <= 2
    assert owned["executionStats"]["totalKeysExamined"] <= 3
