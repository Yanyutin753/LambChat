"""Behavior regressions for destructive deduplication and recall quality.

These tests exercise current shared entry points. Model/provider I/O is replaced
only where deterministic regression checks must not make paid requests.
"""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.search import prioritize_sources


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("甲供应商的标准零件报价为每件120元", "乙供应商的标准零件报价为每件120元"),
        ("甲供应商的标准零件报价为每件120元", "甲供应商的标准零件报价为每件125元"),
        (
            "The user allows sharing reports with external vendors.",
            "The user does not allow sharing reports with external vendors.",
        ),
        (
            "Supplier Alder quoted 120 EUR per standard part.",
            "Supplier Birch quoted 120 EUR per standard part.",
        ),
        (
            "取引先アルファの標準部品の価格は一個120円です。",
            "取引先ベータの標準部品の価格は一個120円です。",
        ),
        (
            "알파 공급업체의 표준 부품 가격은 개당 120원입니다.",
            "베타 공급업체의 표준 부품 가격은 개당 120원입니다.",
        ),
        (
            "Поставщик Альфа предлагает стандартную деталь за 120 рублей.",
            "Поставщик Бета предлагает стандартную деталь за 120 рублей.",
        ),
    ],
)
async def test_fuzzy_summary_match_cannot_replace_a_different_fact(monkeypatch, old, new):
    now = datetime.now(timezone.utc)
    original = {
        "memory_id": "existing",
        "user_id": "owner",
        "memory_type": "project",
        "content": old,
        "title": "Supplier terms",
        "summary": old,
        "tags": ["supplier"],
        "context": "project_constraint",
        "scope": "user",
        "project_id": None,
        "source": "manual",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "source_refs": [],
        "updated_at": now,
    }

    class Cursor:
        async def to_list(self, length):
            return [deepcopy(original)]

    class Collection:
        def __init__(self):
            self.inserted = []
            self.updated = []

        def find(self, query, projection):
            assert query["user_id"] == "owner"
            return Cursor()

        async def find_one(self, query, projection=None):
            return deepcopy(original)

        async def insert_one(self, doc):
            self.inserted.append(deepcopy(doc))

        async def update_one(self, query, update):
            self.updated.append((query, deepcopy(update)))

    collection = Collection()
    backend = NativeMemoryBackend()
    backend._collection = collection
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(
        "src.infra.memory.client.native.vector_store.index_write_through",
        AsyncMock(return_value=False),
    )

    result = await backend.retain(
        "owner",
        new,
        context="project_constraint",
        title="Supplier terms",
        summary=new,
        tags=["supplier"],
    )

    assert result["success"] is True
    assert result["memory_id"] != "existing"
    assert collection.updated == []
    assert len(collection.inserted) == 1
    assert collection.inserted[0]["content"] == new


async def test_saving_unchanged_memory_does_not_repeat_embedding_or_invalidation(monkeypatch):
    now = datetime.now(timezone.utc)
    original = {
        "memory_id": "existing",
        "user_id": "owner",
        "memory_type": "user",
        "content": "The user prefers concise answers.",
        "title": "Answer preference",
        "summary": "The user prefers concise answers.",
        "tags": ["answers"],
        "context": "user_preference",
        "scope": "user",
        "project_id": None,
        "source": "manual",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "source_refs": [],
        "embedding": [1.0, 0.0],
        "updated_at": now,
    }

    class Collection:
        async def find_one(self, query, projection=None):
            return deepcopy(original)

        update_one = AsyncMock()

    collection = Collection()
    backend = NativeMemoryBackend()
    backend._collection = collection
    backend._maybe_embed = AsyncMock(return_value=[1.0, 0.0])
    backend._invalidate_cache = AsyncMock()
    index_write = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "src.infra.memory.client.native.vector_store.index_write_through", index_write
    )

    result = await backend.retain(
        "owner",
        original["content"],
        context=original["context"],
        title=original["title"],
        summary=original["summary"],
        tags=original["tags"],
        existing_memory_id="existing",
    )

    assert result["success"] is True
    assert result["memory_id"] == "existing"
    backend._maybe_embed.assert_not_awaited()
    collection.update_one.assert_not_awaited()
    backend._invalidate_cache.assert_not_awaited()
    index_write.assert_not_awaited()


@pytest.mark.parametrize(
    ("strong", "weak"),
    [
        ({"scope": "user", "source": "auto_retained"}, {"scope": "user", "source": "manual"}),
        (
            {"scope": "user", "source": "manual", "context": "user_preference"},
            {"scope": "user", "source": "auto_retained", "context": "feedback_rule"},
        ),
        (
            {"scope": "user", "source": "manual"},
            {"scope": "project", "source": "manual", "project_id": "current"},
        ),
    ],
)
def test_clearly_relevant_result_is_not_displaced_by_weak_metadata_priority(strong, weak):
    memories = [
        {**weak, "memory_id": "weak", "score": 0.31},
        {**strong, "memory_id": "strong", "score": 0.95},
    ]

    ranked = prioritize_sources(memories)

    assert ranked[0]["memory_id"] == "strong"


def test_equal_relevance_retains_project_priority():
    memories = [
        {"memory_id": "personal", "scope": "user", "source": "manual", "score": 0.8},
        {"memory_id": "project", "scope": "project", "source": "manual", "score": 0.8},
    ]

    assert prioritize_sources(memories)[0]["memory_id"] == "project"
