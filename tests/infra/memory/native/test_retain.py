import json
from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native import summaries
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.client.native.classification import (
    extract_tags,
    find_existing_memory_match,
    is_manual_memory_worthy,
)
from src.infra.memory.client.native.summaries import build_summary


def test_build_summary_truncates_cjk_content_cleanly():
    content = (
        "这是一个很长的中文句子，用来验证摘要生成逻辑在中文场景下也能正确工作，而且不会依赖空格。"
    )

    summary = build_summary(content, max_len=12)

    assert summary.endswith("...")
    assert len(summary) <= 15


def test_extract_tags_handles_english_and_cjk_content():
    english_tags = extract_tags("User prefers raw SQL and PostgreSQL for analytics workloads.")
    cjk_tags = extract_tags("用户偏好原始SQL，并且项目依赖知识图谱查询能力。")

    assert "postgresql" in english_tags
    assert any(len(tag) >= 2 for tag in cjk_tags)


@pytest.mark.asyncio
async def test_llm_enrich_memory_offloads_json_parsing(monkeypatch):
    calls = []

    class FakeResponse:
        content = json.dumps(
            {
                "title": "SQL preference",
                "summary": "User prefers raw SQL for analytics.",
                "tags": ["sql", "analytics", "preference"],
            }
        )

    class FakeModel:
        async def ainvoke(self, _messages):
            return FakeResponse()

    class FakeBackend:
        async def _get_memory_model(self):
            return FakeModel()

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(summaries, "run_blocking_io", fake_run_blocking_io)

    result = await summaries.llm_enrich_memory(
        FakeBackend(),
        "The user prefers raw SQL for analytics workloads.",
    )

    assert calls == [json.loads]
    assert result["title"] == "SQL preference"


def test_is_manual_memory_worthy_rejects_transient_code_like_content():
    assert not is_manual_memory_worthy("让我先看看 src/app.py 里这个 traceback error")
    assert is_manual_memory_worthy("The user prefers raw SQL for all analytics queries.")


@pytest.mark.asyncio
async def test_find_existing_memory_match_returns_best_existing_match():
    now = datetime.now(timezone.utc)
    candidates = [
        {
            "memory_id": "m1",
            "memory_type": "user",
            "summary": "Prefers raw SQL for analytics work.",
            "updated_at": now,
        },
        {
            "memory_id": "m2",
            "memory_type": "project",
            "summary": "Current release is blocked on migration work.",
            "updated_at": now,
        },
    ]

    async def fake_fetch(*_args, **_kwargs):
        return candidates

    match = await find_existing_memory_match(
        fetch_recent=fake_fetch,
        user_id="u1",
        summary="User prefers raw SQL for analytics queries.",
        memory_type="user",
    )

    assert match is not None
    assert match["memory_id"] == "m1"


@pytest.mark.asyncio
async def test_retain_updates_existing_memory_and_refreshes_embedding():
    now = datetime.now(timezone.utc)
    seen: dict[str, object] = {}

    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, length):
            return self._docs[:length]

    class FakeCollection:
        def find(self, *_args, **_kwargs):
            return FakeCursor(
                [
                    {
                        "memory_id": "m1",
                        "memory_type": "user",
                        "summary": "Prefers raw SQL for analytics work.",
                        "updated_at": now,
                    }
                ]
            )

        async def find_one(self, *_args, **_kwargs):
            return {
                "content_storage_mode": "inline",
                "content_store_key": None,
            }

        async def update_one(self, query, payload):
            seen["query"] = query
            seen["payload"] = payload

    backend = NativeMemoryBackend()
    backend._collection = FakeCollection()

    async def fake_invalidate(_user_id):
        return None

    async def fake_embed(text: str):
        return [float(len(text))]

    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]
    backend._maybe_embed = fake_embed  # type: ignore[method-assign]

    result = await backend.retain(
        "u1",
        "The user now prefers DuckDB for local analytics workloads.",
        context="user_identity",
        title="DuckDB preference",
        summary="Prefers raw SQL for analytics work.",
        tags=["sql", "analytics", "duckdb"],
    )

    assert result["success"] is True
    assert result["updated_existing"] is True
    assert seen["query"] == {"user_id": "u1", "memory_id": "m1"}
    assert seen["payload"]["$set"]["embedding"] == [58.0]


class _RetainFakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length):
        return self._docs[:length]


class _SemanticDedupFakeCollection:
    """find() 按 query 形状分流：含 embedding 键的是语义候选查询，否则是摘要匹配查询。"""

    def __init__(self, summary_docs, semantic_docs):
        self._summary_docs = summary_docs
        self._semantic_docs = semantic_docs
        self.updated: list[tuple[dict, dict]] = []
        self.inserted: list[dict] = []

    def find(self, query, _projection):
        if "embedding" in query:
            return _RetainFakeCursor(self._semantic_docs)
        return _RetainFakeCursor(self._summary_docs)

    async def find_one(self, *_args, **_kwargs):
        return {"content_storage_mode": "inline", "content_store_key": None, "source_refs": []}

    async def update_one(self, query, payload):
        self.updated.append((query, payload))

    async def insert_one(self, doc):
        self.inserted.append(doc)


def _backend_with_collection(collection, embed_value):
    backend = NativeMemoryBackend()

    async def fake_invalidate(_user_id):
        return None

    async def fake_embed(_text):
        return embed_value

    backend._collection = collection
    backend._invalidate_cache = fake_invalidate  # type: ignore[method-assign]
    backend._maybe_embed = fake_embed  # type: ignore[method-assign]
    return backend


@pytest.mark.asyncio
async def test_retain_merges_into_semantically_similar_memory_without_explicit_id():
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "m9",
        "memory_type": "user",
        "summary": "User is writing a book about React.",
        "embedding": [1.0, 0.0, 0.0],
        "updated_at": now,
    }
    collection = _SemanticDedupFakeCollection(summary_docs=[existing], semantic_docs=[existing])
    backend = _backend_with_collection(collection, embed_value=[0.99, 0.141, 0.0])

    result = await backend.retain(
        "u1",
        "The user has been writing a book about React patterns since 2025.",
        context="user_identity",
        title="Writing a React book",
        summary="Third chapter of the book is done.",
        tags=["react", "book"],
    )

    assert result["success"] is True
    assert result["updated_existing"] is True
    assert result["memory_id"] == "m9"
    assert len(collection.updated) == 1
    assert collection.updated[0][0] == {"user_id": "u1", "memory_id": "m9"}
    assert not collection.inserted


@pytest.mark.asyncio
async def test_retain_inserts_new_memory_when_semantically_distinct():
    now = datetime.now(timezone.utc)
    existing = {
        "memory_id": "m9",
        "memory_type": "user",
        "summary": "User is writing a book about React.",
        "embedding": [1.0, 0.0, 0.0],
        "updated_at": now,
    }
    collection = _SemanticDedupFakeCollection(summary_docs=[existing], semantic_docs=[existing])
    backend = _backend_with_collection(collection, embed_value=[0.0, 1.0, 0.0])

    result = await backend.retain(
        "u1",
        "The user keeps three cats and a dog at home.",
        context="user_identity",
        title="Pets at home",
        summary="Has three cats and a dog.",
        tags=["pets"],
    )

    assert result["success"] is True
    assert "updated_existing" not in result
    assert not collection.updated
    assert len(collection.inserted) == 1
