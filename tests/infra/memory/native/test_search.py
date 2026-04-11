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
