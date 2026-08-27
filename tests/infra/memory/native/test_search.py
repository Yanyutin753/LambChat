from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native.search import (
    build_keyword_clauses,
    format_memory,
)


def test_build_keyword_clauses_supports_cjk_queries_without_spaces():
    clauses = build_keyword_clauses("原始SQL偏好")

    assert clauses
    assert all("$regex" in clause["content"] for clause in clauses if "content" in clause)


def test_build_keyword_clauses_supports_english_queries():
    clauses = build_keyword_clauses("prefers raw sql analytics")

    assert clauses
    assert any("summary" in clause for clause in clauses)


def test_format_memory_sets_staleness_warning_for_old_memories():
    doc = {
        "memory_id": "m1",
        "user_id": "u1",
        "content": "Prefers raw SQL.",
        "summary": "Prefers raw SQL.",
        "title": "SQL preference",
        "memory_type": "user",
        "source": "manual",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    memory = format_memory(doc, score=1.0, now=datetime(2026, 4, 2, tzinfo=timezone.utc))

    assert memory["memory_id"] == "m1"
    assert "staleness_warning" in memory


@pytest.mark.asyncio
async def test_keyword_fallback_uses_generated_clauses(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    seen = {}

    class FakeCursor:
        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def to_list(self, length):
            seen["length"] = length
            return []

    class FakeCollection:
        def find(self, query):
            seen["query"] = query
            return FakeCursor()

    results = await search_module.keyword_fallback(
        collection=FakeCollection(),
        user_id="u1",
        query="原始SQL偏好",
        limit=5,
        memory_types=None,
    )

    assert results == []
    assert "$or" in seen["query"]


@pytest.mark.asyncio
async def test_text_search_applies_context_filter():
    from src.infra.memory.client.native.search import text_search

    seen = {}

    class FakeCursor:
        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return []

    class FakeCollection:
        def find(self, query, *_a, **_k):
            seen["query"] = dict(query)
            return FakeCursor()

    await text_search(
        FakeCollection(),
        None,
        "u1",
        "项目约束",
        5,
        None,
        context_filter="project_constraint",
    )

    assert seen["query"]["context"] == "project_constraint"


@pytest.mark.asyncio
async def test_text_search_without_context_filter_unchanged():
    from src.infra.memory.client.native.search import text_search

    seen = {}

    class FakeCursor:
        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return []

    class FakeCollection:
        def find(self, query, *_a, **_k):
            seen["query"] = dict(query)
            return FakeCursor()

    await text_search(FakeCollection(), None, "u1", "项目约束", 5, None, context_filter=None)

    assert "context" not in seen["query"]


@pytest.mark.asyncio
async def test_recall_memories_threads_context_filter(monkeypatch):
    from src.infra.memory.client.native import search as search_module
    from src.infra.memory.client.native.search import recall_memories

    captured = {}

    async def fake_text_search(
        collection, logger, user_id, query, limit, memory_types, context_filter=None
    ):
        captured["text"] = context_filter
        return []

    async def fake_vector_search(backend, user_id, query, limit, memory_types, context_filter=None):
        captured["vector"] = context_filter
        return []

    async def fake_fallback(collection, user_id, limit, memory_types, context_filter=None):
        captured["fallback"] = context_filter
        return []

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "vector_search", fake_vector_search)
    monkeypatch.setattr(search_module, "recent_context_fallback", fake_fallback)

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

    result = await recall_memories(
        FakeBackend(), "u1", "what should i know", 5, context_filter="project_constraint"
    )

    assert result["success"] is True
    assert captured["text"] == "project_constraint"
    assert captured["fallback"] == "project_constraint"  # overview 查询走 fallback 也带过滤
    assert "vector" not in captured  # 无 embedding 时不调向量检索
