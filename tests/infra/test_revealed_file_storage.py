from datetime import datetime, timezone

import pytest

from src.infra.revealed_file.storage import (
    REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX,
    REVEALED_FILE_SESSION_LIST_LIMIT,
    RevealedFileStorage,
    close_revealed_file_storage,
)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]
        self._skip = 0
        self._limit = None

    def sort(self, key, direction=None):
        if isinstance(key, list):
            for field, sort_direction in reversed(key):
                self._docs.sort(key=lambda doc: doc.get(field), reverse=sort_direction < 0)
        else:
            assert direction is not None
            self._docs.sort(key=lambda doc: doc.get(key), reverse=direction < 0)
        return self

    def skip(self, value):
        self._skip = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    async def to_list(self, length=None):
        docs = self._docs[self._skip :]
        if self._limit is not None:
            docs = docs[: self._limit]
        elif length is not None:
            docs = docs[:length]
        return [dict(doc) for doc in docs]


class _FakeAggregateResult:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]
        self._index = 0

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._index]
        self._index += 1
        return dict(item)

    async def to_list(self, length=None):
        if length is None:
            return [dict(doc) for doc in self._docs]
        return [dict(doc) for doc in self._docs[:length]]


class _FakeCollection:
    def __init__(
        self,
        docs=None,
        *,
        session_results=None,
        count_result=None,
        indexes=None,
    ):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.session_results = [dict(doc) for doc in (session_results or [])]
        self.count_result = [dict(doc) for doc in (count_result or [])]
        self.indexes = dict(indexes or {})
        self.update_calls = []
        self.update_many_calls = []
        self.created_indexes = []
        self.dropped_indexes = []
        self.delete_many_calls = []
        self.name = "revealed_files"
        self.find_cursors = []
        self.aggregate_pipelines = []

    async def index_information(self):
        return dict(self.indexes)

    async def drop_index(self, name):
        self.dropped_indexes.append(name)
        self.indexes.pop(name, None)

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, kwargs))
        name = kwargs.get("name", f"idx_{len(self.created_indexes)}")
        self.indexes[name] = {
            "key": list(keys),
            "unique": kwargs.get("unique", False),
        }
        return name

    async def delete_many(self, _query):
        self.delete_many_calls.append(_query)

        class _Result:
            deleted_count = 0

        return _Result()

    async def update_one(self, query, update, upsert=False):
        self.update_calls.append((query, update, upsert))

        class _Result:
            matched_count = 1

        return _Result()

    async def update_many(self, query, update):
        self.update_many_calls.append((query, update))

        class _Result:
            modified_count = 0

        return _Result()

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _matches_query(doc, query)])

    def find(self, query, projection=None):
        matched = [
            _apply_projection(doc, projection) for doc in self.docs if _matches_query(doc, query)
        ]
        cursor = _FakeCursor(matched)
        self.find_cursors.append(cursor)
        return cursor

    def aggregate(self, pipeline):
        self.aggregate_pipelines.append(pipeline)
        if any("$count" in stage for stage in pipeline):
            return _FakeAggregateResult(self.count_result)
        return _FakeAggregateResult(self.session_results)


class _ConcurrentListCollection(_FakeCollection):
    def __init__(self, docs=None):
        super().__init__(docs=docs)
        self.find_called_before_count_await = False

    async def count_documents(self, query):
        assert self.find_called_before_count_await is True
        return await super().count_documents(query)

    def find(self, query, projection=None):
        self.find_called_before_count_await = True
        return super().find(query, projection)


class _FakeMongoClient:
    def __init__(self, sessions):
        self._sessions = [dict(session) for session in sessions]

    def __getitem__(self, _db_name):
        return _FakeMongoDatabase(self._sessions)


class _FakeMongoDatabase:
    def __init__(self, sessions):
        self._sessions = sessions

    def __getitem__(self, _collection_name):
        return _FakeSessionCollection(self._sessions)


class _FakeSessionCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    def find(self, query, projection=None):
        matched = [
            _apply_projection(doc, projection) for doc in self.docs if _matches_query(doc, query)
        ]
        return _FakeCursor(matched)


def _apply_projection(doc, projection):
    result = dict(doc)
    if projection and projection.get("project_meta") == 0:
        result.pop("project_meta", None)
    return result


def _matches_query(doc, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches_query(doc, condition) for condition in value):
                return False
            continue
        if isinstance(value, dict):
            if "$in" in value and doc.get(key) not in value["$in"]:
                return False
            if "$ne" in value and doc.get(key) == value["$ne"]:
                return False
            continue
        if doc.get(key) != value:
            return False
    return True


async def _no_op_async():
    return None


@pytest.mark.asyncio
async def test_upsert_by_name_deduplicates_by_file_key_not_name() -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection()
    storage.ensure_indexes_if_needed = _no_op_async

    await storage.upsert_by_name(
        user_id="user-1",
        file_name="demo-app",
        source="reveal_project",
        file_key="revealed_projects/demo-app_abcd1234",
        trace_id="trace-1",
        data={"session_id": "session-1"},
    )

    query, update, upsert = storage.collection.update_calls[0]
    assert query == {
        "user_id": "user-1",
        "dedupe_key": "key:reveal_project:revealed_projects/demo-app_abcd1234",
        "source": "reveal_project",
    }
    assert update["$set"]["file_name"] == "demo-app"
    assert update["$set"]["dedupe_key"] == "key:reveal_project:revealed_projects/demo-app_abcd1234"
    assert upsert is True


@pytest.mark.asyncio
async def test_upsert_by_name_deduplicates_auto_artifacts_by_original_path() -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection()
    storage.ensure_indexes_if_needed = _no_op_async

    await storage.upsert_by_name(
        user_id="user-1",
        file_name="report.pdf",
        source="reveal_file",
        file_key="revealed_files/report_v2.pdf",
        trace_id="trace-2",
        data={
            "session_id": "session-1",
            "delivery_source": "artifact_auto",
            "original_path": "/workspace/report.pdf",
        },
    )

    query, update, upsert = storage.collection.update_calls[0]
    assert query == {
        "user_id": "user-1",
        "dedupe_key": "path:/workspace/report.pdf",
        "source": "reveal_file",
    }
    assert update["$set"]["file_key"] == "revealed_files/report_v2.pdf"
    assert update["$set"]["dedupe_key"] == "path:/workspace/report.pdf"
    assert "is_favorite" not in update["$set"]
    assert upsert is True


@pytest.mark.asyncio
async def test_upsert_by_name_deduplicates_remote_file_urls_ignoring_query() -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection()
    storage.ensure_indexes_if_needed = _no_op_async

    await storage.upsert_by_name(
        user_id="user-1",
        file_name="chart.png",
        source="reveal_file",
        file_key="https://cdn.example.com/assets/chart.png?download=1",
        trace_id="trace-1",
        data={
            "session_id": "session-1",
            "original_path": "https://cdn.example.com/assets/chart.png?download=1",
        },
    )

    query, update, _upsert = storage.collection.update_calls[0]
    assert query == {
        "user_id": "user-1",
        "dedupe_key": "url:https://cdn.example.com/assets/chart.png",
        "source": "reveal_file",
    }
    assert update["$set"]["dedupe_key"] == "url:https://cdn.example.com/assets/chart.png"


@pytest.mark.asyncio
async def test_list_files_keeps_project_meta_for_project_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        docs=[
            {
                "_id": "project-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "demo-app",
                "file_type": "project",
                "source": "reveal_project",
                "file_key": "revealed_projects/demo-app_abcd1234",
                "created_at": now,
                "project_meta": {
                    "template": "react",
                    "files": {"/src/main.tsx": {"url": "/a", "size": 1}},
                },
            },
            {
                "_id": "file-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "notes.txt",
                "file_type": "document",
                "source": "reveal_file",
                "file_key": "revealed_files/notes.txt",
                "created_at": now,
                "project_meta": {"should": "not leak"},
            },
        ]
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([{"session_id": "session-1", "name": "Session One"}]),
    )

    result = await storage.list_files("user-1", limit=20)

    assert result["items"][0]["project_meta"]["template"] == "react"
    assert "project_meta" not in result["items"][1]


@pytest.mark.asyncio
async def test_list_files_preserves_delivery_source_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        docs=[
            {
                "_id": "file-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "puppy.svg",
                "file_type": "image",
                "source": "reveal_file",
                "delivery_source": "artifact_auto",
                "file_key": "revealed_files/puppy.svg",
                "created_at": now,
            },
        ]
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([{"session_id": "session-1", "name": "Session One"}]),
    )

    result = await storage.list_files("user-1", limit=20)

    assert result["items"][0]["delivery_source"] == "artifact_auto"


@pytest.mark.asyncio
async def test_list_files_clamps_storage_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        docs=[
            {
                "_id": f"file-{index}",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": f"file-{index}.txt",
                "file_type": "document",
                "source": "reveal_file",
                "file_key": f"revealed_files/file-{index}.txt",
                "created_at": now,
            }
            for index in range(80)
        ]
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([{"session_id": "session-1", "name": "Session One"}]),
    )

    result = await storage.list_files("user-1", limit=10_000)

    assert len(result["items"]) == 50
    assert result["limit"] == 50
    assert storage.collection.find_cursors[0]._limit == 50


@pytest.mark.asyncio
async def test_list_files_fetches_count_and_page_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _ConcurrentListCollection(
        docs=[
            {
                "_id": "file-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "file.txt",
                "file_type": "document",
                "source": "reveal_file",
                "file_key": "revealed_files/file.txt",
                "created_at": now,
            }
        ]
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([{"session_id": "session-1", "name": "Session One"}]),
    )

    result = await storage.list_files("user-1")

    assert result["total"] == 1
    assert result["items"][0]["file_name"] == "file.txt"


@pytest.mark.asyncio
async def test_list_files_grouped_keeps_project_meta_for_project_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        docs=[
            {
                "_id": "project-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "demo-app",
                "file_type": "project",
                "source": "reveal_project",
                "file_key": "revealed_projects/demo-app_abcd1234",
                "created_at": now,
                "project_meta": {
                    "template": "vue",
                    "files": {"/src/App.vue": {"url": "/a", "size": 2}},
                },
            },
            {
                "_id": "file-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "notes.txt",
                "file_type": "document",
                "source": "reveal_file",
                "file_key": "revealed_files/notes.txt",
                "created_at": now,
                "project_meta": {"should": "not leak"},
            },
        ],
        session_results=[{"_id": "session-1", "file_count": 2, "latest_file_at": now}],
        count_result=[{"total": 1}],
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([{"session_id": "session-1", "name": "Session One"}]),
    )

    result = await storage.list_files_grouped_by_session("user-1", limit=20)

    files = result["sessions"][0]["files"]
    assert files[0]["project_meta"]["template"] == "vue"
    assert "project_meta" not in files[1]


@pytest.mark.asyncio
async def test_list_files_grouped_clamps_session_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        docs=[],
        session_results=[
            {"_id": f"session-{index}", "file_count": 1, "latest_file_at": now}
            for index in range(80)
        ],
        count_result=[{"total": 80}],
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([]),
    )

    result = await storage.list_files_grouped_by_session("user-1", limit=10_000)

    assert result["limit"] == 50
    paginated_pipeline = storage.collection.aggregate_pipelines[1]
    assert {"$limit": 50} in paginated_pipeline


@pytest.mark.asyncio
async def test_list_files_grouped_caps_files_per_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    storage = RevealedFileStorage()
    session_ids = ["session-1", "session-2"]
    storage._collection = _FakeCollection(
        docs=[
            {
                "_id": f"{session_id}-file-{index}",
                "user_id": "user-1",
                "session_id": session_id,
                "file_name": f"file-{index:02d}.txt",
                "file_type": "document",
                "source": "reveal_file",
                "file_key": f"revealed_files/{session_id}/file-{index:02d}.txt",
                "created_at": now,
            }
            for session_id in session_ids
            for index in range(REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX + 5)
        ],
        session_results=[
            {
                "_id": session_id,
                "file_count": REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX + 5,
                "latest_file_at": now,
            }
            for session_id in session_ids
        ],
        count_result=[{"total": len(session_ids)}],
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient(
            [{"session_id": session_id, "name": session_id} for session_id in session_ids]
        ),
    )

    result = await storage.list_files_grouped_by_session("user-1", limit=len(session_ids))

    assert [len(session["files"]) for session in result["sessions"]] == [
        REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX,
        REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX,
    ]
    assert [cursor._limit for cursor in storage.collection.find_cursors] == [
        REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX,
        REVEALED_FILE_GROUPED_FILES_PER_SESSION_MAX,
    ]


@pytest.mark.asyncio
async def test_get_user_sessions_limits_grouping_on_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        session_results=[
            {"_id": f"session-{index}", "count": 1}
            for index in range(REVEALED_FILE_SESSION_LIST_LIMIT + 50)
        ],
    )
    storage.ensure_indexes_if_needed = _no_op_async
    monkeypatch.setattr(
        "src.infra.storage.mongodb.get_mongo_client",
        lambda: _FakeMongoClient([]),
    )

    await storage.get_user_sessions("user-1")

    assert {"$limit": REVEALED_FILE_SESSION_LIST_LIMIT} in storage.collection.aggregate_pipelines[0]


@pytest.mark.asyncio
async def test_ensure_indexes_replaces_old_name_based_unique_index() -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        indexes={
            "user_name_source_unique_idx": {
                "key": [("user_id", 1), ("file_name", 1), ("source", 1)]
            },
            "user_key_source_unique_idx": {"key": [("user_id", 1), ("file_key", 1), ("source", 1)]},
        }
    )

    await storage._ensure_indexes()

    assert "user_name_source_unique_idx" in storage.collection.dropped_indexes
    assert "user_key_source_unique_idx" in storage.collection.dropped_indexes
    assert any(
        kwargs.get("name") == "user_dedupe_source_unique_idx"
        and kwargs.get("unique") is True
        and keys == [("user_id", 1), ("dedupe_key", 1), ("source", 1)]
        for keys, kwargs in storage.collection.created_indexes
    )


@pytest.mark.asyncio
async def test_ensure_indexes_deduplicates_without_collecting_duplicate_ids() -> None:
    storage = RevealedFileStorage()
    storage._collection = _FakeCollection(
        session_results=[
            {
                "_id": {
                    "user_id": "user-1",
                    "dedupe_key": "path:/workspace/report.txt",
                    "source": "reveal_file",
                },
                "keep_id": "newest-id",
                "count": 3,
            }
        ]
    )

    await storage._ensure_indexes()

    duplicate_pipeline = storage.collection.aggregate_pipelines[0]
    group_stage = next(stage["$group"] for stage in duplicate_pipeline if "$group" in stage)
    assert "ids" not in group_stage
    assert group_stage["keep_id"] == {"$max": "$_id"}
    assert storage.collection.delete_many_calls == [
        {
            "user_id": "user-1",
            "dedupe_key": "path:/workspace/report.txt",
            "source": "reveal_file",
            "_id": {"$ne": "newest-id"},
        }
    ]


@pytest.mark.asyncio
async def test_close_revealed_file_storage_clears_singleton() -> None:
    from src.infra.revealed_file import storage as storage_module

    storage = RevealedFileStorage()
    storage._collection = object()
    storage_module._revealed_file_storage = storage

    await close_revealed_file_storage()

    assert storage._collection is None
    assert storage_module._revealed_file_storage is None


@pytest.mark.asyncio
async def test_close_revealed_file_storage_does_not_create_singleton_when_unused() -> None:
    from src.infra.revealed_file import storage as storage_module

    storage_module._revealed_file_storage = None

    await close_revealed_file_storage()

    assert storage_module._revealed_file_storage is None
