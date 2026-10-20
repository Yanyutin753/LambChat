from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from src.api.routes import memory as memory_routes
from src.kernel.schemas.conversation_history import ConversationSourceRef
from src.kernel.schemas.user import TokenPayload


def _user() -> TokenPayload:
    return TokenPayload(sub="user-1", username="tester", roles=["user"])


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self.docs:
            yield dict(doc)


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    async def count_documents(self, query):
        return len([doc for doc in self.docs if doc.get("user_id") == query.get("user_id")])

    def find(self, query, _projection=None):
        return _Cursor([doc for doc in self.docs if doc.get("user_id") == query.get("user_id")])

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def find_one_and_update(self, query, replacement, *, upsert, return_document, projection):
        literal, preserved = replacement[0]["$replaceWith"]["$mergeObjects"]
        replacement = literal["$literal"]
        assert (
            preserved["origin_session_ids"]["$setUnion"][1]["$literal"]
            == replacement["origin_session_ids"]
        )
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in query.items()):
                previous = dict(doc)
                self.docs[index] = dict(
                    replacement,
                    origin_session_ids=list(
                        dict.fromkeys(
                            [*doc.get("origin_session_ids", []), *replacement["origin_session_ids"]]
                        )
                    ),
                )
                return previous
        if upsert:
            self.docs.append(dict(replacement))
        return None


class _Backend:
    def __init__(self, docs):
        self._collection = _Collection(docs)
        self._store = None

    async def _maybe_embed(self, _content):
        return None

    async def _invalidate_cache(self, _user_id):
        return None


class _HistoryService:
    async def validate_source_refs(self, user_id, refs, **_kwargs):
        assert user_id == "user-1"
        return [ref for ref in refs if ref.session_id == "visible-session"]


def _doc() -> dict[str, Any]:
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    return {
        "memory_id": "memory-1",
        "user_id": "user-1",
        "title": "Preference",
        "summary": "Prefers raw SQL",
        "memory_type": "user",
        "tags": ["sql"],
        "content": "The user prefers raw SQL.",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "context": "user_identity",
        "source": "manual",
        "created_at": now,
        "updated_at": now,
        "accessed_at": now,
        "access_count": 1,
        "source_refs": [
            {"session_id": "visible-session", "run_id": "visible-run"},
            {"session_id": "deleted-session", "run_id": "deleted-run"},
        ],
    }


@pytest.fixture
def source_ref_backend(monkeypatch):
    backend = _Backend([_doc()])

    async def fake_get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(memory_routes, "ConversationHistoryService", _HistoryService)
    return backend


@pytest.mark.asyncio
async def test_list_and_detail_return_only_authorized_source_refs(source_ref_backend):
    listed = await memory_routes.list_memories(
        memory_type=None, search=None, limit=50, offset=0, user=_user()
    )
    detailed = await memory_routes.get_memory("memory-1", user=_user())

    expected = [{"session_id": "visible-session", "run_id": "visible-run"}]
    assert listed["memories"][0]["source_refs"] == expected
    assert detailed["source_refs"] == expected


@pytest.mark.asyncio
async def test_export_preserves_only_authorized_source_refs(source_ref_backend):
    response = await memory_routes.export_memories(user=_user())
    chunks = [
        chunk if isinstance(chunk, bytes) else chunk.encode()
        async for chunk in response.body_iterator
    ]
    payload = json.loads(b"".join(chunks))

    assert payload["memories"][0]["source_refs"] == [
        {"session_id": "visible-session", "run_id": "visible-run"}
    ]


@pytest.mark.asyncio
async def test_import_revalidates_source_refs_before_storage(monkeypatch):
    backend = _Backend([])

    async def fake_get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", fake_get_backend)
    monkeypatch.setattr(memory_routes, "ConversationHistoryService", _HistoryService)

    result = await memory_routes.import_memories(
        {
            "version": 1,
            "memories": [
                {
                    "memory_id": "imported-memory",
                    "content": "The user prefers raw SQL.",
                    "source_refs": [
                        {"session_id": "visible-session", "run_id": "visible-run"},
                        {"session_id": "other-user-session", "run_id": "secret-run"},
                    ],
                }
            ],
        },
        user=_user(),
    )

    assert result["imported"] == 1
    assert backend._collection.docs[0]["source_refs"] == [
        ConversationSourceRef(session_id="visible-session", run_id="visible-run").model_dump()
    ]


@pytest.mark.parametrize("count", [1, 50, 200])
async def test_memory_list_validates_sources_in_bounded_batches(monkeypatch, count):
    docs = [dict(_doc(), memory_id=f"memory-{i}") for i in range(count)]
    calls = []

    class HistoryService(_HistoryService):
        async def validate_source_refs(self, user_id, refs, **kwargs):
            calls.append(len(refs))
            return await super().validate_source_refs(user_id, refs, **kwargs)

    async def get_backend():
        return _Backend(docs)

    monkeypatch.setattr(memory_routes, "_get_backend", get_backend)
    monkeypatch.setattr(memory_routes, "ConversationHistoryService", HistoryService)
    result = await memory_routes.list_memories(
        memory_type=None, search=None, limit=200, offset=0, user=_user()
    )

    assert len(result["memories"]) == count
    assert all(
        doc["source_refs"] == [{"session_id": "visible-session", "run_id": "visible-run"}]
        for doc in result["memories"]
    )
    assert len(calls) == (count + 49) // 50


@pytest.mark.parametrize("operation", ["export", "import"])
async def test_memory_transfer_validates_sources_by_batch(monkeypatch, operation):
    docs = [dict(_doc(), memory_id=f"memory-{i}") for i in range(101)]
    backend = _Backend(docs if operation == "export" else [])
    calls = []

    class HistoryService(_HistoryService):
        async def validate_source_refs(self, user_id, refs, **kwargs):
            calls.append(len(refs))
            return await super().validate_source_refs(user_id, refs, **kwargs)

    async def get_backend():
        return backend

    monkeypatch.setattr(memory_routes, "_get_backend", get_backend)
    monkeypatch.setattr(memory_routes, "ConversationHistoryService", HistoryService)
    if operation == "export":
        response = await memory_routes.export_memories(user=_user())
        chunks = [
            chunk if isinstance(chunk, bytes) else chunk.encode()
            async for chunk in response.body_iterator
        ]
        stored = json.loads(b"".join(chunks))["memories"]
    else:
        result = await memory_routes.import_memories({"memories": docs}, user=_user())
        assert result["imported"] == len(docs)
        stored = backend._collection.docs
    assert len(stored) == len(docs)
    assert len(calls) == 3
    assert all(
        doc["source_refs"] == [{"session_id": "visible-session", "run_id": "visible-run"}]
        for doc in stored
    )


async def test_memory_batch_keeps_twenty_sources_per_memory(monkeypatch):
    calls = []

    class HistoryService(_HistoryService):
        async def validate_source_refs(self, user_id, refs, **kwargs):
            calls.append((len(refs), kwargs["limit"]))
            return await super().validate_source_refs(user_id, refs, **kwargs)

    monkeypatch.setattr(memory_routes, "ConversationHistoryService", HistoryService)
    groups = [
        [{"session_id": "visible-session", "run_id": f"{group}-{i}"} for i in range(25)]
        for group in ["first", "second"]
    ]
    assert await memory_routes._validated_source_ref_docs_batch("user-1", groups) == [
        group[-20:] for group in groups
    ]
    assert calls == [(40, 40)]


async def test_memory_source_stream_buffers_only_the_current_batch(monkeypatch):
    consumed = []

    async def docs():
        for i in range(101):
            consumed.append(i)
            yield dict(_doc(), memory_id=f"memory-{i}")

    monkeypatch.setattr(memory_routes, "ConversationHistoryService", _HistoryService)
    stream = memory_routes._iter_memories_with_source_refs("user-1", docs())
    first, refs = await anext(stream)
    assert first["memory_id"] == "memory-0"
    assert refs == [{"session_id": "visible-session", "run_id": "visible-run"}]
    assert len(consumed) == 50
    await stream.aclose()
