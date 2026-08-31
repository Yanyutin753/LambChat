from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.responses import StreamingResponse

from src.api.routes import memory as memory_routes
from src.kernel.errors import AppError
from src.kernel.schemas.user import TokenPayload


def _user() -> TokenPayload:
    return TokenPayload(sub="user-1", username="tester", roles=["user"])


def test_memory_import_total_content_limit_setting_default() -> None:
    from src.kernel.config._definitions_extra import EXTRA_SETTING_DEFINITIONS
    from src.kernel.config.base import Settings

    definition = EXTRA_SETTING_DEFINITIONS["NATIVE_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS"]

    assert Settings(_env_file=None).NATIVE_MEMORY_IMPORT_TOTAL_CONTENT_MAX_CHARS == 2_000_000
    assert definition["default"] == 2_000_000
    assert definition.get("frontend_visible", False) is False


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = docs

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self._docs:
            yield doc


class _FakeStore:
    def __init__(self, values: dict[tuple[tuple[str, ...], str], dict[str, Any]] | None = None):
        self.values = values or {}

    async def aget(self, namespace: tuple[str, ...], key: str) -> Any:
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

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None) -> _AsyncCursor:
        docs = []
        for doc in self.docs:
            if doc.get("user_id") == query.get("user_id"):
                docs.append(dict(doc))
        return _AsyncCursor(docs)

    async def find_one(
        self, query: dict[str, Any], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def replace_one(
        self, query: dict[str, Any], replacement: dict[str, Any], upsert: bool = False
    ) -> SimpleNamespace:
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in query.items()):
                self.docs[index] = dict(replacement)
                return SimpleNamespace(matched_count=1, upserted_id=None)
        if upsert:
            self.docs.append(dict(replacement))
            return SimpleNamespace(matched_count=0, upserted_id="inserted")
        return SimpleNamespace(matched_count=0, upserted_id=None)


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
        limit=50,
        offset=0,
        user=_user(),
    )

    assert result == {"memories": [], "total": 0}
    assert collection.find_query is not None
    regex = collection.find_query["$or"][0]["title"]["$regex"]
    assert regex == r"a\+b\(c\)"


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
