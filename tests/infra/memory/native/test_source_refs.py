from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native import backend as backend_module
from src.infra.memory.client.native import search as search_module
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.kernel.schemas.conversation_history import ConversationSourceRef


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, length):
        return self._docs[:length]


class _Collection:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = None
        self.updated = None

    def find(self, *_args, **_kwargs):
        return _Cursor([])

    async def find_one(self, query, _projection=None):
        if self.existing and query.get("memory_id") == self.existing.get("memory_id"):
            return dict(self.existing)
        return None

    async def insert_one(self, doc):
        self.inserted = dict(doc)

    async def update_one(self, query, payload):
        self.updated = (query, payload)


class _HistoryService:
    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = []

    async def validate_source_refs(self, user_id, refs):
        self.calls.append((user_id, refs))
        allowed_pairs = {(ref.session_id, ref.run_id) for ref in self.allowed}
        return [ref for ref in refs if (ref.session_id, ref.run_id) in allowed_pairs]


def _backend(collection):
    backend = NativeMemoryBackend()
    backend._collection = collection

    async def fake_embed(_text):
        return None

    async def fake_invalidate(_user_id):
        return None

    backend._maybe_embed = fake_embed  # type: ignore[method-assign]
    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]
    return backend


@pytest.mark.asyncio
async def test_retain_validates_and_persists_only_authorized_source_refs(monkeypatch):
    valid = ConversationSourceRef(session_id="session-visible", run_id="run-visible")
    invalid = ConversationSourceRef(session_id="session-other-user", run_id="run-secret")
    service = _HistoryService([valid])
    monkeypatch.setattr(backend_module, "ConversationHistoryService", lambda: service)
    collection = _Collection()

    result = await _backend(collection).retain(
        "user-1",
        "The user prefers raw SQL for analytics workloads.",
        context="user_identity",
        title="SQL preference",
        summary="Prefers raw SQL for analytics.",
        tags=["sql", "analytics"],
        source_refs=[valid, invalid],
    )

    assert result["success"] is True
    assert collection.inserted["source_refs"] == [valid.model_dump()]
    assert service.calls == [("user-1", [valid, invalid])]


@pytest.mark.asyncio
async def test_retain_update_merges_existing_and_new_source_refs(monkeypatch):
    old = ConversationSourceRef(session_id="session-old", run_id="run-old")
    new = ConversationSourceRef(session_id="session-new", run_id="run-new")
    service = _HistoryService([old, new])
    monkeypatch.setattr(backend_module, "ConversationHistoryService", lambda: service)
    collection = _Collection(
        {
            "memory_id": "memory-1",
            "memory_type": "user",
            "summary": "Prefers raw SQL for analytics.",
            "updated_at": datetime.now(timezone.utc),
            "content_storage_mode": "inline",
            "content_store_key": None,
            "source_refs": [old.model_dump()],
        }
    )

    result = await _backend(collection).retain(
        "user-1",
        "The user prefers raw SQL and DuckDB for analytics workloads.",
        context="user_identity",
        title="SQL preference",
        summary="Prefers raw SQL for analytics.",
        tags=["sql", "duckdb"],
        existing_memory_id="memory-1",
        source_refs=[new],
    )

    assert result["updated_existing"] is True
    assert collection.updated[1]["$set"]["source_refs"] == [
        old.model_dump(),
        new.model_dump(),
    ]


@pytest.mark.asyncio
async def test_recall_source_ref_validation_drops_stale_refs_but_keeps_memory(monkeypatch):
    valid = ConversationSourceRef(session_id="session-visible", run_id="run-visible")
    stale = ConversationSourceRef(session_id="session-deleted", run_id="run-deleted")
    service = _HistoryService([valid])
    monkeypatch.setattr(search_module, "ConversationHistoryService", lambda: service)
    memories = [
        {
            "memory_id": "memory-1",
            "source_refs": [valid.model_dump(), stale.model_dump()],
        },
        {"memory_id": "memory-2", "source_refs": []},
    ]

    validated = await search_module.validate_memory_source_refs("user-1", memories)

    assert [memory["memory_id"] for memory in validated] == ["memory-1", "memory-2"]
    assert validated[0]["source_refs"] == [valid.model_dump()]
    assert validated[1]["source_refs"] == []
