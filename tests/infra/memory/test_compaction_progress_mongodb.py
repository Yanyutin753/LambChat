"""Durable progress through a large automatic-memory inventory."""

import json
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory import compaction_agent as compaction
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
async def test_compaction_advances_then_skips_unchanged_after_worker_replacement(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_review_{uuid4().hex}"
    collection = client[database_name].native_memories
    backend = NativeMemoryBackend()
    backend._collection = collection
    prompts = []
    monkeypatch.setattr(compaction, "_COMPACTION_INVENTORY_MAX_CHARS", 600)
    monkeypatch.setattr(compaction.settings, "NATIVE_MEMORY_COMPACTION_CONTENT_MAX_CHARS", 300)
    monkeypatch.setattr(
        compaction, "acquire_consolidation_lock", AsyncMock(return_value="acquired")
    )
    monkeypatch.setattr(compaction, "release_consolidation_lock", AsyncMock())
    monkeypatch.setattr(compaction, "renew_consolidation_lock", AsyncMock(return_value=True))

    class Graph:
        async def ainvoke(self, state, config):
            prompts.append(state["messages"][0].content)
            return {"messages": []}

    monkeypatch.setattr(compaction, "create_deep_agent", lambda **kwargs: Graph())
    monkeypatch.setattr(
        compaction.MemoryCompactionAgent,
        "_get_compaction_model",
        AsyncMock(return_value="test-model"),
    )
    try:
        now = utc_now()
        await collection.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": f"m{index}",
                    "source": "auto_retained",
                    "content": f"Durable business policy {index}. " + "x" * 270,
                    "content_storage_mode": "inline",
                    "updated_at": now,
                    "title": f"Policy {index}",
                    "summary": "Unique policy",
                    "scope": "user",
                }
                for index in range(7)
            ]
        )
        await collection.insert_one(
            {
                "user_id": "other",
                "memory_id": "foreign",
                "source": "auto_retained",
                "content": "Do not include this owner's policy.",
                "updated_at": now,
            }
        )
        foreign_before = await collection.find_one({"memory_id": "foreign"})
        # A fresh agent each pass rules out a process-local-only skip gate.
        for _ in range(8):
            await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        seen = [
            item["memory_id"]
            for prompt in prompts
            for item in json.loads(
                prompt.split("BEGIN_UNTRUSTED_MEMORY_INVENTORY_JSON\n", 1)[1].split(
                    "\nEND_UNTRUSTED_MEMORY_INVENTORY_JSON", 1
                )[0]
            )
        ]
        assert set(seen) == {f"m{index}" for index in range(7)}
        assert len(seen) == 7
        assert len(prompts) < 8
        assert await collection.find_one({"memory_id": "foreign"}) == foreign_before
        before = len(prompts)
        await collection.update_one(
            {"memory_id": "m6"},
            {
                "$set": {
                    "updated_at": utc_now(),
                    "content": "Policy six now requires explicit approval.",
                }
            },
        )
        result = await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        assert len(prompts) == before + 1
        assert result["checked"] == 1
        assert "explicit approval" in prompts[-1]
        assert "Do not include" not in "\n".join(prompts)
    finally:
        await client.drop_database(database_name)
        await client.close()


async def test_short_memory_metadata_cannot_overfill_compaction_inventory():
    class Cursor:
        def sort(self, *args):
            return self

        def __aiter__(self):
            async def rows():
                for index in range(50_000):
                    yield {
                        "memory_id": f"m{index}",
                        "content": "Short durable rule.",
                        "title": "t" * 80,
                        "summary": "s" * 300,
                        "tags": ["q" * 20] * 5,
                        "source": "auto_retained",
                    }

            return rows()

    class Collection:
        def find(self, *args, **kwargs):
            return Cursor()

    class Backend:
        _collection = Collection()
        _store = None

    inventory = await compaction.MemoryCompactionAgent._build_inventory(Backend(), "owner")
    assert inventory
    assert len(json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))) <= 80_000
    assert len(inventory) < 500


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
async def test_unavailable_body_is_retried_when_the_store_recovers(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_review_body_{uuid4().hex}"
    backend = NativeMemoryBackend()
    backend._collection = client[database_name].native_memories
    available = {"value": False}
    prompts = []

    class Store:
        async def aget(self, namespace, key):
            return (
                {"text": f"Recovered full warranty for {key}: 48 months."}
                if available["value"]
                else None
            )

    backend._store = Store()
    monkeypatch.setattr(
        compaction, "acquire_consolidation_lock", AsyncMock(return_value="acquired")
    )
    monkeypatch.setattr(compaction, "release_consolidation_lock", AsyncMock())
    monkeypatch.setattr(compaction, "renew_consolidation_lock", AsyncMock(return_value=True))

    class Graph:
        async def ainvoke(self, state, config):
            prompts.append(state["messages"][0].content)
            return {"messages": []}

    monkeypatch.setattr(compaction, "create_deep_agent", lambda **kwargs: Graph())
    monkeypatch.setattr(
        compaction.MemoryCompactionAgent,
        "_get_compaction_model",
        AsyncMock(return_value="test-model"),
    )
    try:
        await backend._collection.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": f"m{index}",
                    "source": "auto_retained",
                    "content": "Incomplete preview",
                    "content_storage_mode": "store",
                    "content_store_key": f"body-{index}",
                    "updated_at": utc_now(),
                }
                for index in range(3)
            ]
        )
        await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        available["value"] = True
        await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        assert any("Recovered full warranty" in prompt for prompt in prompts)
        before = len(prompts)
        await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        assert len(prompts) == before
    finally:
        await client.drop_database(database_name)
        await client.close()


async def test_oversized_or_empty_first_entry_does_not_hide_later_memories():
    class Cursor:
        def sort(self, *args):
            return self

        def __aiter__(self):
            async def rows():
                yield {"memory_id": "empty", "content": ""}
                yield {
                    "memory_id": "large",
                    "content": "Unique durable supplier rule.",
                    "summary": "x" * 90_000,
                }
                yield {"memory_id": "valid", "content": "The warranty lasts 48 months."}

            return rows()

    class Backend:
        _store = None

    class Collection:
        def find(self, *args, **kwargs):
            return Cursor()

    backend = Backend()
    backend._collection = Collection()
    inventory = await compaction.MemoryCompactionAgent._build_inventory(backend, "owner")
    assert "valid" in {item["memory_id"] for item in inventory}
    assert len(json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))) <= 80_000


def test_compaction_explains_inventory_is_a_bounded_batch():
    assert "bounded batch" in compaction._COMPACTION_SYSTEM_PROMPT
    prompt = compaction.MemoryCompactionAgent._build_compaction_prompt(
        50_000, [{"memory_id": "m1"}]
    )
    assert "1 of 50000" in prompt


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
@pytest.mark.parametrize("failure", ["raised", "tool_failed", "concurrent_edit"])
async def test_review_markers_do_not_certify_failed_or_concurrently_changed_input(
    monkeypatch, failure
):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    database_name = f"memory_review_fence_{uuid4().hex}"
    backend = NativeMemoryBackend()
    backend._collection = client[database_name].native_memories
    backend.retain = AsyncMock(return_value={"success": False, "error": "storage unavailable"})
    monkeypatch.setattr(
        compaction, "acquire_consolidation_lock", AsyncMock(return_value="acquired")
    )
    monkeypatch.setattr(compaction, "release_consolidation_lock", AsyncMock())
    monkeypatch.setattr(compaction, "renew_consolidation_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(
        compaction.MemoryCompactionAgent,
        "_get_compaction_model",
        AsyncMock(return_value="test-model"),
    )

    def graph(**kwargs):
        tools = {tool.name: tool for tool in kwargs["tools"]}

        class Graph:
            async def ainvoke(self, *args):
                if failure == "raised":
                    raise OSError("owned test: model interrupted")
                if failure == "tool_failed":
                    result = await tools["memory_compaction_update"].ainvoke(
                        {"memory_id": "m0", "content": "The supplier warranty lasts 60 months."}
                    )
                    assert result["success"] is False
                else:
                    await backend._collection.update_one(
                        {"memory_id": "m0"},
                        {
                            "$set": {
                                "source": "manual",
                                "updated_at": utc_now(),
                                "content": "A new pinned supplier contract.",
                            }
                        },
                    )
                return {"messages": []}

        return Graph()

    monkeypatch.setattr(compaction, "create_deep_agent", graph)
    try:
        await backend._collection.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": f"m{index}",
                    "source": "auto_retained",
                    "content": f"The supplier {index} warranty lasts 48 months.",
                    "title": "Warranty",
                    "summary": "Supplier warranty",
                    "tags": ["warranty"],
                    "updated_at": utc_now(),
                }
                for index in range(3)
            ]
        )
        if failure == "raised":
            with pytest.raises(OSError, match="model interrupted"):
                await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        else:
            await compaction.MemoryCompactionAgent().compact_user_memories(backend, "owner")
        marked = await backend._collection.count_documents({"compaction_review": {"$exists": True}})
        assert marked == (2 if failure == "concurrent_edit" else 0)
        if failure == "concurrent_edit":
            current = await backend._collection.find_one({"memory_id": "m0"})
            assert current["content"] == "A new pinned supplier contract."
            assert "compaction_review" not in current
    finally:
        await client.drop_database(database_name)
        await client.close()
