from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native.indexing import build_memory_index, choose_index_memories


def test_choose_index_memories_stays_capped_and_prefers_stable_items():
    docs = [
        {
            "memory_id": "m1",
            "source": "manual",
            "access_count": 5,
            "updated_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "summary": "Stable preference",
        },
        {
            "memory_id": "m2",
            "source": "auto_retained",
            "access_count": 0,
            "updated_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "summary": "Very recent but low-value",
        },
        {
            "memory_id": "m3",
            "source": "manual",
            "access_count": 3,
            "updated_at": datetime(2026, 3, 30, tzinfo=timezone.utc),
            "summary": "Another useful preference",
        },
    ]

    chosen = choose_index_memories(
        docs,
        per_type_limit=2,
        now=datetime(2026, 4, 2, tzinfo=timezone.utc),
        staleness_days=30,
    )

    assert [doc["memory_id"] for doc in chosen] == ["m1", "m3"]


@pytest.mark.asyncio
async def test_build_memory_index_orders_string_memory_types_by_configured_priority():
    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def to_list(self, length):
            return self._docs[:length]

    class FakeCollection:
        def __init__(self, docs):
            self._docs = docs

        def find(self, *_args, **_kwargs):
            return FakeCursor(self._docs)

    class FakeBackend:
        _INDEX_CACHE_MAX_SIZE = 10

        def __init__(self, docs):
            self._collection = FakeCollection(docs)
            self._index_cache = {}

    docs = [
        {
            "memory_id": "m-project",
            "memory_type": "project",
            "title": "Project milestone",
            "summary": "Project milestone",
            "updated_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "source": "manual",
            "access_count": 1,
        },
        {
            "memory_id": "m-user",
            "memory_type": "user",
            "title": "User preference",
            "summary": "User preference",
            "updated_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "source": "manual",
            "access_count": 1,
        },
        {
            "memory_id": "m-reference",
            "memory_type": "reference",
            "title": "Reference link",
            "summary": "Reference link",
            "updated_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "source": "manual",
            "access_count": 1,
        },
    ]

    index = await build_memory_index(FakeBackend(docs), user_id="u1")

    user_pos = index.index("## [user]")
    project_pos = index.index("## [project]")
    reference_pos = index.index("## [reference]")

    assert user_pos < project_pos < reference_pos


@pytest.mark.asyncio
async def test_build_memory_index_omits_internal_ids_but_keeps_age_metadata(monkeypatch):
    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def to_list(self, length):
            return self._docs[:length]

    class FakeCollection:
        def __init__(self, docs):
            self._docs = docs

        def find(self, *_args, **_kwargs):
            return FakeCursor(self._docs)

    class FakeBackend:
        _INDEX_CACHE_MAX_SIZE = 10

        def __init__(self, docs):
            self._collection = FakeCollection(docs)
            self._index_cache = {}

    now = datetime(2026, 4, 2, tzinfo=timezone.utc)
    monkeypatch.setattr("src.infra.memory.client.native.indexing.utc_now", lambda: now)
    docs = [
        {
            "memory_id": "fresh-private-id",
            "source_refs": [{"session_id": "private-session-id", "run_id": "private-run-id"}],
            "memory_type": "user",
            "title": "Current preference",
            "summary": "Current preference",
            "updated_at": now,
            "source": "manual",
            "access_count": 1,
        },
        {
            "memory_id": "stale-private-id",
            "memory_type": "user",
            "title": "Older preference",
            "summary": "Older preference",
            "updated_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "source": "manual",
            "access_count": 1,
        },
    ]

    index = await build_memory_index(FakeBackend(docs), user_id="u1")

    assert index == (
        "<memory_index>\n"
        "\n## [user]\n"
        "- Current preference\n"
        "- Older preference (stale:32d)\n"
        "\n</memory_index>"
    )
    assert "private-session-id" not in index
    assert "private-run-id" not in index
