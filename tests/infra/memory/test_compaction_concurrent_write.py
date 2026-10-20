"""Final conditional writes must protect edits made after inventory checks."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.compaction_agent import MemoryCompactionAgent


@pytest.mark.parametrize(
    "operation,stored", [("update", False), ("update", True), ("delete", False)]
)
async def test_compaction_cannot_mutate_a_memory_that_became_manual_after_check(
    monkeypatch, operation, stored
):
    now = datetime.now(timezone.utc)
    original_text = "The supplier warranty lasts 37 months."
    latest_text = "The user manually confirmed that the warranty lasts 48 months."

    class Store:
        def __init__(self):
            self.values = {"memory:m1": {"text": original_text}}

        async def aget(self, namespace, key):
            return self.values.get(key)

        async def aput(self, namespace, key, value):
            self.values[key] = value

        async def adelete(self, namespace, key):
            self.values.pop(key, None)

    store = Store()

    class Collection:
        def __init__(self):
            self.reads = 0
            self.doc = {
                "user_id": "owner",
                "memory_id": "m1",
                "memory_type": "user",
                "title": "Warranty",
                "summary": original_text,
                "tags": ["warranty"],
                "context": "user",
                "scope": "user",
                "project_id": None,
                "source": "auto_retained",
                "updated_at": now,
                "source_refs": [],
                "content": original_text,
                "content_storage_mode": "store" if stored else "inline",
                "content_store_key": "memory:m1" if stored else None,
            }

        def manual_edit(self):
            self.doc.update(
                source="manual", updated_at=now + timedelta(seconds=1), content=latest_text
            )
            store.values["memory:m1"] = {"text": latest_text}

        async def find_one(self, query, projection=None):
            self.reads += 1
            observed = deepcopy(self.doc)
            if operation == "update" and self.reads == 2:
                self.manual_edit()
            return observed

        def matches(self, query):
            return all(self.doc.get(key) == value for key, value in query.items())

        async def update_one(self, query, update):
            if not self.matches(query):
                return SimpleNamespace(matched_count=0, modified_count=0)
            self.doc.update(
                {
                    key: value["$literal"]
                    for key, value in update[0]["$set"].items()
                    if key != "_content_cleanup"
                }
            )
            return SimpleNamespace(matched_count=1, modified_count=1)

        async def find_one_and_delete(self, query, projection=None):
            self.manual_edit()
            if not self.matches(query):
                return None
            deleted, self.doc = self.doc, None
            return deleted

    collection = Collection()
    backend = NativeMemoryBackend()
    backend._collection = collection
    backend._store = store
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    write_vector = AsyncMock(return_value=True)
    delete_vector = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "src.infra.memory.client.native.vector_store.index_write_through", write_vector
    )
    monkeypatch.setattr("src.infra.memory.client.native.vector_store.index_delete", delete_vector)
    snapshot = {**deepcopy(collection.doc), "updated_at": str(now), "text_complete": True}
    tools = MemoryCompactionAgent()._build_compaction_tools(backend, "owner", inventory=[snapshot])
    selected = next(tool for tool in tools if tool.name == f"memory_compaction_{operation}")
    arguments = {"memory_id": "m1"}
    if operation == "update":
        arguments["content"] = "Compacted warranty terms remain available. " * (60 if stored else 1)
    else:
        arguments["reason"] = "non_durable"

    result = await selected.ainvoke(arguments)

    assert result["success"] is False
    assert collection.doc["source"] == "manual"
    assert collection.doc["content"] == latest_text
    if stored:
        assert store.values == {"memory:m1": {"text": latest_text}}
    backend._invalidate_cache.assert_not_awaited()
    write_vector.assert_not_awaited()
    delete_vector.assert_not_awaited()
