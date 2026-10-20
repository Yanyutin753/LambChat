"""Compaction must transfer authoritative provenance before deleting a duplicate."""

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.compaction_agent import MemoryCompactionAgent
from src.infra.memory.forgetting import source_watermark
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def lineage_backend():
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_compaction_lineage_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    try:
        await db.sessions.insert_many(
            [
                {"session_id": sid, "user_id": "owner"}
                for sid in ["source-a", "source-b", "legacy-job-source"]
            ]
        )
        await db.native_memories.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": mid,
                    "revision_id": mid,
                    "content_storage_mode": "inline",
                    "content": "The weekly digest is sent on Tuesday.",
                    "source": "auto_retained",
                    "origin_session_ids": [sid],
                    "source_refs": [{"session_id": sid, "run_id": f"run-{mid}"}],
                    "scope": "user",
                    "project_id": None,
                    "updated_at": utc_now(),
                    "title": "Digest",
                    "summary": "Tuesday digest",
                    "tags": ["digest"],
                    "context": "user",
                }
                for mid, sid in [("canonical", "source-a"), ("duplicate", "source-b")]
            ]
        )
        await db.memory_extraction_jobs.insert_many(
            [
                {
                    "user_id": "owner",
                    "session_id": "legacy-job-source",
                    "memory_ids": ["duplicate"],
                },
                {"user_id": "other", "session_id": "foreign-source", "memory_ids": ["duplicate"]},
            ]
        )
        yield backend, db
    finally:
        await client.drop_database(name)
        await client.close()


async def tools_for(backend):
    docs = await backend._collection.find({"user_id": "owner"}).to_list(length=20)
    inventory = [dict(row, text_complete=True, updated_at=str(row["updated_at"])) for row in docs]
    return {
        tool.name: tool
        for tool in MemoryCompactionAgent()._build_compaction_tools(
            backend, "owner", inventory=inventory
        )
    }


@pytest.mark.parametrize("update_first", [False, True])
async def test_compaction_then_forget_preserves_every_source_and_owner(
    lineage_backend, update_first
):
    backend, db = lineage_backend
    tools = await tools_for(backend)
    if update_first:
        result = await tools["memory_compaction_update"].ainvoke(
            {
                "memory_id": "canonical",
                "content": "The user requires the weekly digest to be sent on Tuesday.",
            }
        )
        assert result["success"]
    result = await tools["memory_compaction_delete"].ainvoke(
        {"memory_id": "duplicate", "preserved_in": "canonical"}
    )
    assert result["success"]
    assert await db.native_memories.count_documents({"user_id": "owner"}) == 1
    kept = await db.native_memories.find_one({"memory_id": "canonical"})
    assert set(kept["origin_session_ids"]) == {"source-a", "source-b", "legacy-job-source"}
    assert {ref["session_id"] for ref in kept["source_refs"]} == {"source-a", "source-b"}
    assert await source_watermark(db, "owner", "source-b") is None
    assert (await backend.delete("owner", "canonical"))["success"]
    for sid in ["source-a", "source-b", "legacy-job-source"]:
        assert await source_watermark(db, "owner", sid) is not None
        assert await source_watermark(db, "other", sid) is None
    assert await source_watermark(db, "owner", "foreign-source") is None


async def test_redundant_delete_requires_a_preserved_target(lineage_backend):
    backend, db = lineage_backend
    tools = await tools_for(backend)
    result = await tools["memory_compaction_delete"].ainvoke({"memory_id": "duplicate"})
    assert result["success"] is False
    assert await db.native_memories.count_documents({"user_id": "owner"}) == 2
    result = await tools["memory_compaction_delete"].ainvoke(
        {"memory_id": "duplicate", "reason": "non_durable"}
    )
    assert result["success"] is True
    assert await source_watermark(db, "owner", "source-b") is None


@pytest.mark.parametrize("change", ["foreign_owner", "other_project", "manual", "stale", "partial"])
async def test_lineage_never_deletes_into_an_unauthorized_or_changed_target(
    lineage_backend, change
):
    backend, db = lineage_backend
    docs = await db.native_memories.find({"user_id": "owner"}).to_list(length=20)
    inventory = [dict(row, text_complete=True, updated_at=str(row["updated_at"])) for row in docs]
    if change == "partial":
        inventory[0]["text_complete"] = False
    else:
        fields = {
            "foreign_owner": {"user_id": "other"},
            "other_project": {"scope": "project", "project_id": "private-project"},
            "manual": {"source": "manual", "revision_id": "manual-edit"},
            "stale": {"revision_id": "concurrent-edit"},
        }[change]
        await db.native_memories.update_one({"memory_id": "canonical"}, {"$set": fields})
    tools = {
        tool.name: tool
        for tool in MemoryCompactionAgent()._build_compaction_tools(
            backend, "owner", inventory=inventory
        )
    }
    before = await db.native_memories.find_one({"memory_id": "canonical"})
    result = await tools["memory_compaction_delete"].ainvoke(
        {"memory_id": "duplicate", "preserved_in": "canonical"}
    )
    assert result["success"] is False
    assert await db.native_memories.find_one({"memory_id": "duplicate"}) is not None
    assert await db.native_memories.find_one({"memory_id": "canonical"}) == before


@pytest.mark.parametrize("pause_at", ["transfer", "delete_guard"])
async def test_changed_canonical_keeps_the_duplicate_and_new_manual_version(
    lineage_backend, pause_at
):
    backend, db = lineage_backend
    original = db.native_memories

    class Collection:
        database = db

        def __getattr__(self, name):
            return getattr(original, name)

        async def update_one(self, query, update):
            if pause_at == "transfer" and query.get("memory_id") == "canonical":
                await original.update_one(
                    {"memory_id": "canonical"},
                    {
                        "$set": {
                            "revision_id": "concurrent-manual",
                            "source": "manual",
                            "content": "User's latest protected answer.",
                        }
                    },
                )
            return await original.update_one(query, update)

        async def find_one(self, query, projection=None):
            if pause_at == "delete_guard" and projection == {"_id": 1}:
                await original.update_one(
                    {"memory_id": "canonical"},
                    {
                        "$set": {
                            "revision_id": "concurrent-manual",
                            "source": "manual",
                            "content": "User's latest protected answer.",
                        }
                    },
                )
            return await original.find_one(query, projection)

    backend._collection = Collection()
    tools = await tools_for(backend)
    result = await tools["memory_compaction_delete"].ainvoke(
        {"memory_id": "duplicate", "preserved_in": "canonical"}
    )
    assert result["success"] is False
    assert await original.find_one({"memory_id": "duplicate"}) is not None
    canonical = await original.find_one({"memory_id": "canonical"})
    assert canonical["source"] == "manual"
    assert canonical["content"] == "User's latest protected answer."


async def test_fifty_thousand_jobs_use_owner_scoped_reverse_lineage_indexes(
    lineage_backend, record_property
):
    from src.infra.memory.extraction import ensure_extraction_job_indexes
    from src.infra.memory.forgetting import memory_source_sessions

    backend, db = lineage_backend
    await db.memory_extraction_jobs.insert_many(
        [
            {
                "user_id": "owner",
                "session_id": f"noise-{index}",
                "memory_ids": [f"unrelated-{index}"],
            }
            for index in range(50_000)
        ]
    )
    await db.memory_extraction_jobs.insert_many(
        [
            {"user_id": "owner", "session_id": "extract-a", "memory_ids": ["canonical"]},
            {"user_id": "owner", "session_id": "extract-b", "memory_id": "canonical"},
            {"user_id": "other", "session_id": "foreign-extract", "memory_ids": ["canonical"]},
        ]
    )
    await ensure_extraction_job_indexes(db.memory_extraction_jobs)
    assert await memory_source_sessions(backend, "owner", {"memory_id": "canonical"}) == {
        "extract-a",
        "extract-b",
    }
    query = {"user_id": "owner", "$or": [{"memory_ids": "canonical"}, {"memory_id": "canonical"}]}
    explained = await db.command(
        "explain", {"find": "memory_extraction_jobs", "filter": query}, verbosity="executionStats"
    )
    assert explained["executionStats"]["nReturned"] == 2
    record_property("lineage_docs_examined", explained["executionStats"]["totalDocsExamined"])
    record_property("lineage_keys_examined", explained["executionStats"]["totalKeysExamined"])
    assert explained["executionStats"]["totalDocsExamined"] <= 4


@pytest.mark.parametrize("committed", [False, True])
async def test_uncertain_lineage_write_keeps_source_and_invalidates_cached_metadata(
    lineage_backend, committed
):
    backend, db = lineage_backend
    original = db.native_memories

    class Collection:
        database = db

        def __getattr__(self, name):
            return getattr(original, name)

        async def update_one(self, query, update):
            if committed:
                await original.update_one(query, update)
            raise OSError("unknown metadata commit result")

    backend._collection = Collection()
    tools = await tools_for(backend)
    with pytest.raises(OSError):
        await tools["memory_compaction_delete"].ainvoke(
            {"memory_id": "duplicate", "preserved_in": "canonical"}
        )
    assert await original.find_one({"memory_id": "duplicate"}) is not None
    assert await original.count_documents({"user_id": "owner"}) == 2
    backend._invalidate_cache.assert_awaited_once_with("owner")


async def test_parallel_duplicates_share_the_canonical_without_losing_lineage(lineage_backend):
    import asyncio

    backend, db = lineage_backend
    original = db.native_memories
    extra = await original.find_one({"memory_id": "duplicate"})
    extra.pop("_id")
    extra.update(memory_id="duplicate-two", revision_id="duplicate-two")
    await original.insert_one(extra)
    release = asyncio.Event()
    reads = 0

    class Collection:
        database = db

        def __getattr__(self, name):
            return getattr(original, name)

        async def find_one(self, query, projection=None):
            nonlocal reads
            doc = await original.find_one(query, projection)
            if (
                query.get("memory_id") == "canonical"
                and projection
                and projection.get("origin_session_ids")
            ):
                reads += 1
                if reads >= 2:
                    release.set()
                try:
                    await asyncio.wait_for(release.wait(), 0.05)
                except TimeoutError:
                    pass
            return doc

    backend._collection = Collection()
    tools = await tools_for(backend)
    results = await asyncio.gather(
        *[
            tools["memory_compaction_delete"].ainvoke(
                {"memory_id": mid, "preserved_in": "canonical"}
            )
            for mid in ["duplicate", "duplicate-two"]
        ]
    )
    assert all(result["success"] for result in results)
    assert await original.count_documents({"user_id": "owner"}) == 1
    canonical = await original.find_one({"memory_id": "canonical"})
    assert set(canonical["origin_session_ids"]) == {"source-a", "source-b", "legacy-job-source"}
