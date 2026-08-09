from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
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

    async def replace_one(self, query, replacement, upsert=False):
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in query.items()):
                self.docs[index] = dict(replacement)
                return SimpleNamespace(matched_count=1)
        if upsert:
            self.docs.append(dict(replacement))
        return SimpleNamespace(matched_count=0)


class _Backend:
    def __init__(self, docs):
        self._collection = _Collection(docs)
        self._store = None

    async def _maybe_embed(self, _content):
        return None

    async def _invalidate_cache(self, _user_id):
        return None


class _HistoryService:
    async def validate_source_refs(self, user_id, refs):
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
