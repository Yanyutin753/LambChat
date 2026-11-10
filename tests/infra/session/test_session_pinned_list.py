"""list_sessions(pinned_only=True) 的查询构造测试。"""

import pytest

from src.infra.session.storage import SessionStorage


class _EmptyCursor:
    def skip(self, _skip):
        return self

    def limit(self, _limit):
        return self

    def sort(self, _spec):
        return self

    async def to_list(self, length=None):
        return []


class _QueryRecordingCollection:
    def __init__(self):
        self.find_queries = []
        self.count_queries = []

    def find(self, query, _projection=None):
        self.find_queries.append(query)
        return _EmptyCursor()

    async def count_documents(self, query):
        self.count_queries.append(query)
        return 0


def _make_storage(monkeypatch: pytest.MonkeyPatch, collection):
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    storage = SessionStorage()
    storage._collection = collection
    return storage


@pytest.mark.asyncio
async def test_pinned_only_filters_on_is_pinned_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    collection = _QueryRecordingCollection()
    storage = _make_storage(monkeypatch, collection)

    sessions, total = await storage.list_sessions(user_id="user-1", pinned_only=True)

    assert sessions == []
    assert total == 0
    assert collection.find_queries, "find() must be called"
    assert collection.find_queries[0].get("metadata.is_pinned") is True
    assert collection.count_queries[0].get("metadata.is_pinned") is True


@pytest.mark.asyncio
async def test_default_list_does_not_filter_on_pin(
    monkeypatch: pytest.MonkeyPatch,
):
    collection = _QueryRecordingCollection()
    storage = _make_storage(monkeypatch, collection)

    await storage.list_sessions(user_id="user-1")

    assert collection.find_queries, "find() must be called"
    assert "metadata.is_pinned" not in collection.find_queries[0]
    assert "metadata.is_pinned" not in collection.count_queries[0]


async def test_companion_filter_applies_before_pagination_and_count(monkeypatch):
    collection = _QueryRecordingCollection()
    storage = _make_storage(monkeypatch, collection)
    await storage.list_sessions(user_id="owner", skip=20, limit=20, exclude_assistants=True)
    for query in [*collection.find_queries, *collection.count_queries]:
        assert query["user_id"] == "owner"
        assert query["metadata.assistant_id"] == {"$in": [None, ""]}
        assert query["metadata.assistant_discussion_id"] == {"$in": [None, ""]}


async def test_global_search_and_explicit_collections_keep_companion_sessions(monkeypatch):
    collection = _QueryRecordingCollection()
    storage = _make_storage(monkeypatch, collection)
    await storage.list_sessions(user_id="owner", search="Chief", favorites_only=True)
    assert "metadata.assistant_id" not in collection.find_queries[0]
