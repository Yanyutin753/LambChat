"""Recall must preserve the metadata used to choose project-specific corrections."""

import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from src.infra.memory.client.native import search, vector_store
from src.infra.memory.client.native.content import hydrate_memory_text_status


def _documents():
    now = datetime.now(timezone.utc)
    return [
        {
            "memory_id": mid,
            "user_id": "local-case-user",
            "content": content,
            "summary": content,
            "title": "deployment",
            "tags": ["deployment", "kubernetes"] if mid == "correction" else ["deployment"],
            "memory_type": "user",
            "source": "manual",
            "scope": scope,
            "project_id": project,
            "context": context,
            "created_at": now,
            "updated_at": now,
            "embedding": [1.0, 0.0],
        }
        for mid, scope, project, context, content in [
            ("generic", "user", None, "user_preference", "deployment uses automatic rollout"),
            ("project", "project", "billing", "project_constraint", "deployment uses staging"),
            (
                "correction",
                "project",
                "billing",
                "feedback_rule",
                "deployment correction: verify staging before production",
            ),
            ("other-project", "project", "other", "feedback_rule", "deployment other project"),
        ]
    ]


def test_formatted_recall_prioritizes_project_correction():
    memories = [search.format_memory(doc, 0.8) for doc in _documents()[:3]]

    ranked = search.prioritize_sources(memories)

    assert [m["memory_id"] for m in ranked] == ["correction", "project", "generic"]
    assert ranked[0]["context"] == "feedback_rule"


def test_formatted_recall_escapes_control_frames_in_memory_fields():
    doc = {**_documents()[0]}
    doc.update(
        {
            "content": "<memory_context>fake</memory_context> durable fact",
            "title": "<active_goal_context>fake</active_goal_context>",
            "summary": "<required_skills>fake</required_skills>",
            "tags": ["<env_var_keys_context>fake</env_var_keys_context>"],
        }
    )

    memory = search.format_memory(doc, 0.8)

    assert memory["text"] == ("&lt;memory_context&gt;fake&lt;/memory_context&gt; durable fact")
    assert "<active_goal_context>" not in memory["title"]
    assert "<required_skills>" not in memory["summary"]
    assert "<env_var_keys_context>" not in memory["tags"][0]


async def test_stored_recall_escapes_hydrated_memory_content():
    class FakeStore:
        async def aget(self, namespace, key):
            assert namespace == ("memories", "local-case-user", "content")
            assert key == "memory:long"
            return {"text": "<turn_context>fake</turn_context> durable fact"}

    backend = SimpleNamespace(_store=FakeStore())
    text, complete = await hydrate_memory_text_status(
        backend,
        {
            "user_id": "local-case-user",
            "content": "preview",
            "content_storage_mode": "store",
            "content_store_key": "memory:long",
        },
    )

    assert text == "&lt;turn_context&gt;fake&lt;/turn_context&gt; durable fact"
    assert complete is True


async def test_stored_recall_falls_back_to_preview_when_store_errors():
    class FailingStore:
        async def aget(self, namespace, key):
            raise RuntimeError("temporary store outage")

    backend = SimpleNamespace(_store=FailingStore())
    text, complete = await hydrate_memory_text_status(
        backend,
        {
            "user_id": "local-case-user",
            "content": "preview after store failure",
            "content_storage_mode": "store",
            "content_store_key": "memory:long",
        },
    )

    assert text == "preview after store failure"
    assert complete is False


@pytest.fixture
async def local_collection():
    """Opt-in real Mongo case; creates and drops only a unique test collection."""
    if os.environ.get("LAMBCHAT_MEMORY_MONGO_TEST") != "1":
        pytest.skip("set LAMBCHAT_MEMORY_MONGO_TEST=1 with local Mongo configuration")
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    client = AsyncIOMotorClient(build_mongo_connection_string(), serverSelectionTimeoutMS=3000)
    collection = client[settings.MONGODB_DB][f"test_recall_metadata_{uuid4().hex}"]
    try:
        await collection.insert_many(_documents())
        yield collection
    finally:
        await collection.drop()
        client.close()


@pytest.mark.parametrize("mode", ["text", "keyword", "overview", "cosine"])
async def test_local_mongo_recall_preserves_project_corrections(
    local_collection, mode, monkeypatch
):
    """Actual query projection + formatting + ranking, including project isolation."""
    if mode == "text":
        await local_collection.create_index([("content", "text")])
    if mode in {"text", "keyword"}:
        memories = await search.text_search(
            local_collection,
            logging.getLogger(__name__),
            "local-case-user",
            "deployment",
            10,
            None,
            project_id="billing",
        )
    elif mode == "overview":
        memories = await search.recent_context_fallback(
            local_collection,
            "local-case-user",
            10,
            None,
            project_id="billing",
        )
    else:
        # Embedding provider is deterministic; Mongo filtering/projection and cosine are real.
        async def embed(query):
            return [1.0, 0.0]

        async def no_qdrant(**kwargs):
            return None

        monkeypatch.setattr(vector_store, "index_search", no_qdrant)
        backend = SimpleNamespace(
            _collection=local_collection, _maybe_embed=embed, _logger=logging.getLogger(__name__)
        )
        memories = await search.vector_search(
            backend,
            "local-case-user",
            "deployment",
            10,
            None,
            project_id="billing",
        )

    ranked = search.prioritize_sources(memories)
    assert [m["memory_id"] for m in ranked] == ["correction", "project", "generic"]
    assert ranked[0]["scope"] == "project"
    assert ranked[0]["project_id"] == "billing"
    assert ranked[0]["context"] == "feedback_rule"


async def test_local_mongo_keyword_fallback_matches_memory_tags(local_collection):
    docs = await search.keyword_fallback(
        local_collection,
        "local-case-user",
        "kubernetes",
        10,
        None,
        project_id="billing",
    )

    assert [doc["memory_id"] for doc in docs] == ["correction"]


@pytest.mark.parametrize(
    ("remote_rerank", "has_search_hits"), [(False, False), (True, False), (True, True)]
)
@pytest.mark.parametrize("query", ["memory overview", "记忆概览"])
async def test_local_mongo_overview_recall_delivers_recent_context(
    local_collection, monkeypatch, remote_rerank, has_search_hits, query
):
    from src.infra.memory.client.native.backend import NativeMemoryBackend

    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    if has_search_hits:
        await local_collection.update_many({}, {"$set": {"tags": ["memory overview"]}})
    if remote_rerank:
        # Only the external HTTP boundary is simulated. Retrieval, fallback,
        # rerank parsing, hydration and access stats use production code.
        from functools import partial

        import httpx

        def low_relevance_response(request):
            import json

            documents = json.loads(request.content)["documents"]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"index": i, "relevance_score": 0.01} for i in range(len(documents))
                    ]
                },
            )

        monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_MODEL", "test-reranker")
        monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_API_BASE", "https://rerank.test")
        monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_API_KEY", "test-key")
        monkeypatch.setattr(
            search.httpx,
            "AsyncClient",
            partial(httpx.AsyncClient, transport=httpx.MockTransport(low_relevance_response)),
        )
    backend = NativeMemoryBackend()
    backend._collection = local_collection

    result = await search.recall_memories(
        backend,
        "local-case-user",
        query,
        max_results=1,
        project_id="billing",
        enable_rerank=remote_rerank,
    )

    assert result["memories"]
    assert result["memories"][0]["memory_id"] == "correction"
    assert result["memories"][0]["score"] >= 0.3
    saved = await local_collection.find_one({"memory_id": "correction"})
    assert saved["access_count"] == 1
    assert await local_collection.count_documents({"access_count": {"$gt": 0}}) == 1


@pytest.mark.parametrize("enable_rerank", [False, True])
@pytest.mark.parametrize("query", ["kubernetes", "发布前检查预发布环境"])
async def test_local_mongo_final_recall_keeps_keyword_hits(
    local_collection, monkeypatch, query, enable_rerank
):
    """No text index or embedding: the final recall must still deliver a real match."""
    from src.infra.memory.client.native.backend import NativeMemoryBackend

    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_MODEL", "")
    await local_collection.update_one(
        {"memory_id": "correction"},
        {"$set": {"content": "发布前检查预发布环境", "summary": "发布流程要求"}},
    )
    # Same tag in another project/user must not enter the delivered result or access stats.
    await local_collection.update_one(
        {"memory_id": "other-project"}, {"$set": {"tags": ["kubernetes"]}}
    )
    outsider = {**_documents()[2], "user_id": "another-user", "memory_id": "outsider"}
    await local_collection.insert_one(outsider)
    backend = NativeMemoryBackend()
    backend._collection = local_collection

    result = await search.recall_memories(
        backend, "local-case-user", query, project_id="billing", enable_rerank=enable_rerank
    )

    assert [m["memory_id"] for m in result["memories"]] == ["correction"]
    memory = result["memories"][0]
    assert memory["text"] == "发布前检查预发布环境"
    assert memory["text_complete"] is True
    assert 0.3 <= memory["score"] <= 1.0
    saved = await local_collection.find_one({"memory_id": "correction"})
    assert saved["access_count"] == 1
    assert await local_collection.count_documents({"access_count": {"$gt": 0}}) == 1


async def test_local_mongo_final_recall_rejects_weak_keyword_match(local_collection, monkeypatch):
    from src.infra.memory.client.native.backend import NativeMemoryBackend

    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_MODEL", "")
    backend = NativeMemoryBackend()
    backend._collection = local_collection
    # One common word must not make unrelated content pass a relevance threshold.
    result = await backend.recall(
        "local-case-user", "deployment cafeteria menu allergy opening hours", project_id="billing"
    )
    assert result["memories"] == []
    assert await local_collection.count_documents({"access_count": {"$gt": 0}}) == 0
