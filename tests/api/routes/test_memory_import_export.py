from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.responses import StreamingResponse

from src.api.routes import memory as memory_routes
from src.kernel.errors import AppError
from src.kernel.schemas.user import TokenPayload


def _user() -> TokenPayload:
    return TokenPayload(sub="user-1", username="tester", roles=["user"])


@pytest.mark.parametrize("count", [1, 50, 51])
async def test_export_hydrates_contents_in_streaming_batches(monkeypatch, count):
    namespace = ("memories", "user-1", "content")
    store = _FakeStore(
        {(namespace, str(index)): {"text": f"full-{index}"} for index in range(count)}
    )
    backend = _FakeBackend(
        [
            {
                "memory_id": str(index),
                "user_id": "user-1",
                "content": "preview",
                "content_storage_mode": "store",
                "content_store_key": str(index),
            }
            for index in range(count)
        ],
        store,
    )

    async def get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", get_backend)
    response = await memory_routes.export_memories(user=_user())
    chunks = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        chunks.append(text)
        if "memory_id" in text:
            assert backend._collection.last_cursor.read_count == min(count, 50)
            assert len(store.batch_calls) == 1
            break
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    result = json.loads("".join(chunks))
    assert [item["content"] for item in result["memories"]] == [
        f"full-{index}" for index in range(count)
    ]
    assert [len(batch) for batch in store.batch_calls] == ([count] if count <= 50 else [50, 1])
    assert store.point_calls == []


async def test_inline_export_does_not_read_content_store(monkeypatch):
    store = _FakeStore()
    backend = _FakeBackend(
        [{"memory_id": "inline", "user_id": "user-1", "content": "inline"}], store
    )

    async def get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", get_backend)
    response = await memory_routes.export_memories(user=_user())
    async for _chunk in response.body_iterator:
        pass
    assert store.batch_calls == []
    assert store.point_calls == []


def test_memory_import_total_content_limit_setting_default() -> None:
    from src.kernel.config.base import Settings
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS"]

    assert Settings(_env_file=None).NATIVE_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS == 2_000_000
    assert definition["default"] == 2_000_000
    assert definition.get("frontend_visible", False) is False


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = docs
        self.read_count = 0

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self._docs:
            self.read_count += 1
            yield doc


class _FakeStore:
    def __init__(self, values: dict[tuple[tuple[str, ...], str], dict[str, Any]] | None = None):
        self.values = values or {}
        self.batch_calls = []
        self.point_calls = []

    async def abatch(self, ops):
        self.batch_calls.append(list(ops))
        return [
            SimpleNamespace(value=self.values[(op.namespace, op.key)])
            if (op.namespace, op.key) in self.values
            else None
            for op in ops
        ]

    async def aget(self, namespace: tuple[str, ...], key: str) -> Any:
        self.point_calls.append((namespace, key))
        value = self.values.get((namespace, key))
        if value is None:
            return None
        return SimpleNamespace(value=value)

    async def aput(
        self, namespace: tuple[str, ...], key: str, value: dict[str, Any] | None
    ) -> None:
        if value is None:
            self.values.pop((namespace, key), None)
            return
        self.values[(namespace, key)] = value


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]):
        self.docs = docs
        self.atomic_replaces = []

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None) -> _AsyncCursor:
        docs = []
        for doc in self.docs:
            if doc.get("user_id") == query.get("user_id"):
                docs.append(dict(doc))
        self.last_cursor = _AsyncCursor(docs)
        return self.last_cursor

    async def find_one(
        self, query: dict[str, Any], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def find_one_and_replace(
        self, query, replacement, *, upsert, return_document, projection
    ):
        assert upsert is True and return_document == ReturnDocument.BEFORE
        assert projection == {"content_storage_mode": 1, "content_store_key": 1}
        self.atomic_replaces.append(query)
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in query.items()):
                previous = dict(doc)
                self.docs[index] = dict(replacement)
                return previous
        if upsert:
            if any(doc["memory_id"] == replacement["memory_id"] for doc in self.docs):
                raise DuplicateKeyError("memory id reserved")
            self.docs.append(dict(replacement))
        return None


class _FakeBackend:
    def __init__(self, docs: list[dict[str, Any]], store: _FakeStore | None = None):
        self._collection = _FakeCollection(docs)
        self._store = store or _FakeStore()
        self.invalidated_users: list[str] = []

    async def _maybe_embed(self, text: str) -> None:
        return None

    async def _invalidate_cache(self, user_id: str) -> None:
        self.invalidated_users.append(user_id)


class _ListCursor(_AsyncCursor):
    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self


class _ListCollection:
    def __init__(self) -> None:
        self.find_query: dict[str, Any] | None = None

    async def count_documents(self, query: dict[str, Any]) -> int:
        return 0

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> _ListCursor:
        self.find_query = query
        return _ListCursor([])


@pytest.mark.asyncio
async def test_list_memories_escapes_search_regex(monkeypatch: pytest.MonkeyPatch):
    collection = _ListCollection()
    backend = SimpleNamespace(_collection=collection)

    async def fake_get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)

    result = await memory_routes.list_memories(
        memory_type=None,
        search="a+b(c)",
        context=None,
        limit=50,
        offset=0,
        user=_user(),
    )

    assert result == {"memories": [], "total": 0}
    assert collection.find_query is not None
    regex = collection.find_query["$or"][0]["title"]["$regex"]
    assert regex == r"a\+b\(c\)"
    assert {"context": {"$regex": regex, "$options": "i"}} in collection.find_query["$or"]


@pytest.mark.asyncio
async def test_export_memories_includes_hydrated_full_content(monkeypatch: pytest.MonkeyPatch):
    store = _FakeStore(
        {
            (("memories", "user-1", "content"), "memory:stored-1"): {
                "text": "full stored memory text",
                "memory_id": "stored-1",
            }
        }
    )
    backend = _FakeBackend(
        [
            {
                "memory_id": "stored-1",
                "user_id": "user-1",
                "title": "Stored",
                "summary": "Stored summary",
                "memory_type": "user",
                "tags": ["alpha"],
                "content": "full stored...",
                "content_storage_mode": "store",
                "content_store_key": "memory:stored-1",
                "context": "ctx",
                "source": "manual",
                "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
                "access_count": 7,
            },
            {
                "memory_id": "other-user",
                "user_id": "user-2",
                "title": "Hidden",
                "summary": "Hidden",
                "memory_type": "user",
                "tags": [],
                "content": "nope",
            },
        ],
        store,
    )

    async def fake_get_backend() -> _FakeBackend:
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)

    response = await memory_routes.export_memories(user=_user())
    assert isinstance(response, StreamingResponse)
    chunks = [
        chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        async for chunk in response.body_iterator
    ]
    result = json.loads(b"".join(chunks))

    assert result["version"] == 1
    assert len(result["memories"]) == 1
    assert result["memories"][0]["memory_id"] == "stored-1"
    assert result["memories"][0]["content"] == "full stored memory text"
    assert "user_id" not in result["memories"][0]


@pytest.mark.asyncio
async def test_export_memories_offloads_per_memory_json_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    large_content = "x" * (memory_routes._DEFAULT_MEMORY_EXPORT_CONTENT_MAX_CHARS - 1)
    store = _FakeStore(
        {
            (("memories", "user-1", "content"), "memory:stored-large"): {
                "text": large_content,
                "memory_id": "stored-large",
            }
        }
    )
    backend = _FakeBackend(
        [
            {
                "memory_id": "stored-large",
                "user_id": "user-1",
                "title": "Stored large",
                "summary": "Stored summary",
                "memory_type": "user",
                "tags": ["alpha"],
                "content": "full stored...",
                "content_storage_mode": "store",
                "content_store_key": "memory:stored-large",
                "context": "ctx",
                "source": "manual",
            }
        ],
        store,
    )
    encoded_values: list[Any] = []

    async def fake_get_backend() -> _FakeBackend:
        return backend

    async def fake_run_blocking_io(func, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[1], dict):
            encoded_values.append(args[1])
        return func(*args, **kwargs)

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(memory_routes, "run_blocking_io", fake_run_blocking_io, raising=False)

    response = await memory_routes.export_memories(user=_user())
    chunks = [
        chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        async for chunk in response.body_iterator
    ]
    result = json.loads(b"".join(chunks))

    assert result["memories"][0]["content"] == large_content
    assert [value["memory_id"] for value in encoded_values] == ["stored-large"]


@pytest.mark.asyncio
async def test_export_memories_truncates_oversized_content_before_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    max_chars = memory_routes._DEFAULT_MEMORY_EXPORT_CONTENT_MAX_CHARS
    oversized_content = "x" * (max_chars + 1)
    backend = _FakeBackend(
        [
            {
                "memory_id": "oversized",
                "user_id": "user-1",
                "title": "Oversized",
                "summary": "Stored summary",
                "memory_type": "user",
                "tags": ["alpha"],
                "content": oversized_content,
                "content_storage_mode": "inline",
                "content_store_key": None,
                "context": "ctx",
                "source": "manual",
            }
        ]
    )
    encoded_values: list[Any] = []

    async def fake_get_backend() -> _FakeBackend:
        return backend

    async def fake_run_blocking_io(func, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[1], dict):
            encoded_values.append(args[1])
        return func(*args, **kwargs)

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(memory_routes, "run_blocking_io", fake_run_blocking_io, raising=False)

    response = await memory_routes.export_memories(user=_user())
    chunks = [
        chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        async for chunk in response.body_iterator
    ]
    result = json.loads(b"".join(chunks))

    memory = result["memories"][0]
    assert len(memory["content"]) == max_chars
    assert memory["content_truncated"] is True
    assert memory["content_original_chars"] == max_chars + 1
    assert encoded_values[0]["content"] == "x" * max_chars


@pytest.mark.asyncio
async def test_import_memories_overwrites_matching_memory_id(monkeypatch: pytest.MonkeyPatch):
    backend = _FakeBackend(
        [
            {
                "memory_id": "same-id",
                "user_id": "user-1",
                "title": "Old",
                "summary": "Old summary",
                "memory_type": "user",
                "tags": ["old"],
                "content": "old content",
                "content_storage_mode": "inline",
                "content_store_key": None,
                "source": "manual",
            }
        ]
    )

    async def fake_get_backend() -> _FakeBackend:
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)

    result = await memory_routes.import_memories(
        {
            "version": 1,
            "memories": [
                {
                    "memory_id": "same-id",
                    "title": "New",
                    "summary": "New summary",
                    "memory_type": "project",
                    "tags": ["new"],
                    "content": "new content",
                    "context": "project ctx",
                    "source": "backup",
                    "created_at": "2026-01-02T00:00:00+00:00",
                    "updated_at": "2026-01-03T00:00:00+00:00",
                    "access_count": 3,
                },
                {
                    "memory_id": "fresh-id",
                    "title": "Fresh",
                    "summary": "Fresh summary",
                    "memory_type": "reference",
                    "tags": [],
                    "content": "fresh content",
                },
            ],
        },
        user=_user(),
    )

    assert result == {"success": True, "imported": 2, "created": 1, "overwritten": 1}
    docs = {doc["memory_id"]: doc for doc in backend._collection.docs}
    assert docs["same-id"]["user_id"] == "user-1"
    assert docs["same-id"]["title"] == "New"
    assert docs["same-id"]["memory_type"] == "project"
    assert docs["same-id"]["content"] == "new content"
    assert docs["fresh-id"]["user_id"] == "user-1"
    assert backend.invalidated_users == ["user-1"]


@pytest.mark.parametrize("count", [1, 50])
async def test_import_atomic_replaces_do_not_read_old_documents_separately(monkeypatch, count):
    backend = _FakeBackend([])
    backend._collection.find_one = AsyncMock(side_effect=AssertionError("independent old-key read"))
    monkeypatch.setattr(memory_routes, "_get_backend", AsyncMock(return_value=backend))

    result = await memory_routes.import_memories(
        {
            "memories": [
                {"memory_id": str(index), "content": "inline content"} for index in range(count)
            ]
        },
        user=_user(),
    )

    assert result == {"success": True, "imported": count, "created": count, "overwritten": 0}
    assert len(backend._collection.atomic_replaces) == count
    backend._collection.find_one.assert_not_awaited()


async def test_import_duplicate_ids_preserve_long_inline_long_cleanup_order(monkeypatch):
    monkeypatch.setattr(memory_routes.settings, "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS", 10)
    events = []

    class Store(_FakeStore):
        async def aput(self, namespace, key, value):
            events.append(("delete" if value is None else "put", key))
            await super().aput(namespace, key, value)

    namespace = ("memories", "user-1", "content")
    store = Store({(namespace, "legacy"): {"text": "old long content"}})
    backend = _FakeBackend(
        [
            {
                "memory_id": "same",
                "user_id": "user-1",
                "content_storage_mode": "store",
                "content_store_key": "legacy",
            }
        ],
        store,
    )
    replace = backend._collection.find_one_and_replace

    async def tracked_replace(query, replacement, **kwargs):
        events.append(("replace", replacement["content_storage_mode"]))
        return await replace(query, replacement, **kwargs)

    backend._collection.find_one_and_replace = tracked_replace
    monkeypatch.setattr(memory_routes, "_get_backend", AsyncMock(return_value=backend))
    result = await memory_routes.import_memories(
        {
            "memories": [
                {"memory_id": "same", "content": text} for text in ["a" * 20, "inline", "c" * 20]
            ]
        },
        user=_user(),
    )

    assert result == {"success": True, "imported": 3, "created": 0, "overwritten": 3}
    assert events == [
        ("put", "memory:same"),
        ("replace", "store"),
        ("delete", "legacy"),
        ("replace", "inline"),
        ("delete", "memory:same"),
        ("put", "memory:same"),
        ("replace", "store"),
    ]
    assert store.values == {(namespace, "memory:same"): {"text": "c" * 20, "memory_id": "same"}}
    assert backend.invalidated_users == ["user-1"]


async def test_import_partial_validation_failure_keeps_prior_commit_and_stops(monkeypatch):
    backend = _FakeBackend([])
    monkeypatch.setattr(memory_routes, "_get_backend", AsyncMock(return_value=backend))

    with pytest.raises(AppError):
        await memory_routes.import_memories(
            {
                "memories": [
                    {"memory_id": "first", "content": "saved content"},
                    {"memory_id": "invalid", "content": "tiny"},
                    {"memory_id": "last", "content": "not reached"},
                ]
            },
            user=_user(),
        )
    assert [doc["memory_id"] for doc in backend._collection.docs] == ["first"]
    assert backend.invalidated_users == []


async def test_import_other_user_memory_is_not_overwritten(monkeypatch):
    other = {"memory_id": "shared", "user_id": "user-2", "content": "other user's content"}
    backend = _FakeBackend([dict(other)])
    monkeypatch.setattr(memory_routes, "_get_backend", AsyncMock(return_value=backend))

    with pytest.raises(DuplicateKeyError):
        await memory_routes.import_memories(
            {"memories": [{"memory_id": "shared", "content": "attempted overwrite"}]}, user=_user()
        )
    assert backend._collection.docs == [other]
    assert backend._collection.atomic_replaces == [{"user_id": "user-1", "memory_id": "shared"}]


@pytest.mark.asyncio
async def test_import_memories_rejects_oversized_single_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeBackend([])

    async def fake_get_backend() -> _FakeBackend:
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_routes,
        "_get_memory_import_content_max_chars",
        lambda: 8,
        raising=False,
    )

    with pytest.raises(AppError) as exc:
        await memory_routes.import_memories(
            {
                "version": 1,
                "memories": [
                    {
                        "memory_id": "huge",
                        "title": "Huge",
                        "memory_type": "user",
                        "content": "x" * 9,
                    }
                ],
            },
            user=_user(),
        )

    assert exc.value.error_code.code == "memory_content_too_large"
    assert exc.value.http_status == 400
    assert backend._collection.docs == []


@pytest.mark.asyncio
async def test_import_memories_rejects_oversized_total_content_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeBackend([])

    async def fake_get_backend() -> _FakeBackend:
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(
        memory_routes,
        "_get_memory_import_total_content_max_chars",
        lambda: 20,
        raising=False,
    )

    with pytest.raises(AppError) as exc:
        await memory_routes.import_memories(
            {
                "version": 1,
                "memories": [
                    {
                        "memory_id": "one",
                        "title": "One",
                        "memory_type": "user",
                        "content": "first memory content",
                    },
                    {
                        "memory_id": "two",
                        "title": "Two",
                        "memory_type": "user",
                        "content": "second memory content",
                    },
                ],
            },
            user=_user(),
        )

    assert exc.value.error_code.code == "memory_import_too_large"
    assert exc.value.http_status == 400
    assert backend._collection.docs == []


@pytest.mark.asyncio
async def test_list_memories_filters_source_with_search(monkeypatch: pytest.MonkeyPatch):
    collection = _ListCollection()

    async def fake_get_backend():
        return SimpleNamespace(_collection=collection)

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    await memory_routes.list_memories(
        memory_type="project",
        search="constraint",
        context=None,
        source="manual",
        limit=20,
        offset=0,
        user=_user(),
    )
    assert collection.find_query["user_id"] == "user-1"
    assert collection.find_query["memory_type"] == "project"
    assert collection.find_query["source"] == "manual"
    assert "context" not in collection.find_query
    assert len(collection.find_query["$or"]) == 4
