"""An expired compactor must not keep mutating memory."""

from unittest.mock import AsyncMock

from src.infra.memory import compaction_agent as compaction


async def test_compaction_refuses_tools_after_lease_takeover(monkeypatch):
    original = {
        "memory_id": "m1",
        "user_id": "owner",
        "source": "auto_retained",
        "content": "The delivery guarantee lasts 48 months.",
        "title": "Warranty",
        "summary": "Delivery warranty",
        "tags": ["warranty"],
        "scope": "user",
        "updated_at": "revision-one",
    }

    class Backend:
        _collection = AsyncMock()
        retain = AsyncMock(return_value={"success": True})
        delete = AsyncMock(return_value={"success": True})

    backend = Backend()
    backend._collection.count_documents.return_value = 3
    backend._collection.find_one.return_value = original
    owner = {"current": True}
    monkeypatch.setattr(
        compaction, "acquire_consolidation_lock", AsyncMock(return_value="acquired")
    )
    monkeypatch.setattr(compaction, "release_consolidation_lock", AsyncMock())

    async def renew(*args):
        return owner["current"]

    monkeypatch.setattr(compaction, "renew_consolidation_lock", renew, raising=False)
    outcomes = []

    def graph(**kwargs):
        tools = {tool.name: tool for tool in kwargs["tools"]}

        class Graph:
            async def ainvoke(self, *args):
                owner["current"] = False
                outcomes.append(
                    await tools["memory_compaction_update"].ainvoke(
                        {"memory_id": "m1", "content": "Delivery warranty is confirmed."}
                    )
                )
                outcomes.append(
                    await tools["memory_compaction_delete"].ainvoke({"memory_id": "m1"})
                )

        return Graph()

    monkeypatch.setattr(compaction, "create_deep_agent", graph)
    agent = compaction.MemoryCompactionAgent()
    agent._get_compaction_model = AsyncMock(return_value="test-model")
    agent._build_inventory = AsyncMock(return_value=[{**original, "text_complete": True}])
    result = await agent.compact_user_memories(backend, "owner")
    assert result.get("reason") == "lease_lost"
    assert len(outcomes) == 2 and all(item.get("success") is False for item in outcomes)
    backend.retain.assert_not_awaited()
    backend.delete.assert_not_awaited()
    backend._collection.bulk_write.assert_not_awaited()


async def test_native_update_checks_lease_again_after_embedding(monkeypatch):
    from types import SimpleNamespace

    from src.infra.memory.client.native.backend import NativeMemoryBackend

    original = {
        "memory_id": "m1",
        "user_id": "owner",
        "source": "auto_retained",
        "content": "The warranty lasts 48 months.",
        "content_storage_mode": "inline",
        "title": "Warranty",
        "summary": "Warranty",
        "tags": ["warranty"],
        "scope": "user",
        "context": "user",
        "source_refs": [],
    }
    backend = NativeMemoryBackend()
    backend._collection = SimpleNamespace(
        find_one=AsyncMock(return_value=original), update_one=AsyncMock()
    )
    backend._invalidate_cache = AsyncMock()
    lease = {"owned": True}

    async def embed(content):
        lease["owned"] = False
        return None

    async def owns_lease():
        return lease["owned"]

    backend._maybe_embed = embed
    result = await backend.retain(
        "owner",
        "The warranty lasts 60 months.",
        context="user",
        title="Warranty",
        summary="Warranty",
        tags=["warranty"],
        existing_memory_id="m1",
        expected_revision={"source": "auto_retained"},
        write_guard=owns_lease,
    )
    assert result["success"] is False and result["error"] == "write_guard_rejected"
    backend._collection.update_one.assert_not_awaited()
    backend._invalidate_cache.assert_not_awaited()


async def test_guard_storage_error_cleans_only_the_uncommitted_staged_body():
    from types import SimpleNamespace

    import pytest

    from src.infra.memory.client.native.backend import NativeMemoryBackend

    original = {
        "memory_id": "m1",
        "user_id": "owner",
        "source": "auto_retained",
        "content": "The warranty lasts 48 months.",
        "content_storage_mode": "inline",
        "title": "Warranty",
        "summary": "Warranty",
        "tags": ["warranty"],
        "scope": "user",
        "context": "user",
        "source_refs": [],
    }

    class Store:
        def __init__(self):
            self.values = {"unrelated": {"text": "Keep this independent body."}}

        async def aput(self, namespace, key, value):
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value

    backend = NativeMemoryBackend()
    backend._store = Store()
    backend._collection = SimpleNamespace(
        find_one=AsyncMock(return_value=original), update_one=AsyncMock()
    )
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    guard = AsyncMock(side_effect=OSError("owned test: job store unavailable"))
    with pytest.raises(OSError, match="job store unavailable"):
        await backend.retain(
            "owner",
            "The warranty policy is durable and requires supplier confirmation. " * 100,
            context="user",
            title="Warranty",
            summary="Warranty",
            tags=["warranty"],
            existing_memory_id="m1",
            expected_revision={"source": "auto_retained"},
            write_guard=guard,
        )
    assert backend._store.values == {"unrelated": {"text": "Keep this independent body."}}
    backend._collection.update_one.assert_not_awaited()
    backend._invalidate_cache.assert_not_awaited()
