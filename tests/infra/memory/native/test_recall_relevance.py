"""The final recall selection must respect hybrid and local reranking."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.memory.client.native import search


def _candidate(memory_id, score, title):
    return {
        "memory_id": memory_id,
        "score": score,
        "title": title,
        "summary": title,
        "text": title,
        "scope": "user",
        "source": "manual",
    }


async def test_final_selection_preserves_consensus_from_hybrid_routes(monkeypatch):
    weak = _candidate("text-only", 10.0, "An old loosely matching document")
    strong = _candidate("both-routes", 0.9, "The supplier shipping schedule")
    monkeypatch.setattr(search, "text_search", AsyncMock(return_value=[weak, strong]))
    monkeypatch.setattr(search, "vector_search", AsyncMock(return_value=[strong]))
    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    monkeypatch.setattr(
        search, "_hydrate_memories_limited", AsyncMock(side_effect=lambda _, rows: rows)
    )
    monkeypatch.setattr(
        search, "validate_memory_source_refs", AsyncMock(side_effect=lambda _, rows: rows)
    )
    backend = SimpleNamespace(_collection=None, _logger=None, _embedding_fn=object())

    result = await search.recall_memories(
        backend,
        "owner",
        "supplier shipping schedule",
        max_results=1,
        touch_access=False,
        enable_rerank=False,
    )

    assert [memory["memory_id"] for memory in result["memories"]] == ["both-routes"]


async def test_final_selection_preserves_local_rerank_relevance(monkeypatch):
    weak = _candidate("weak", 0.95, "A different unrelated report")
    strong = _candidate("strong", 0.4, "Supplier shipping schedule")
    monkeypatch.setattr(search, "text_search", AsyncMock(return_value=[weak, strong]))
    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RERANK_MODEL", "")
    monkeypatch.setattr(search.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)
    monkeypatch.setattr(
        search, "_hydrate_memories_limited", AsyncMock(side_effect=lambda _, rows: rows)
    )
    monkeypatch.setattr(
        search, "validate_memory_source_refs", AsyncMock(side_effect=lambda _, rows: rows)
    )
    backend = SimpleNamespace(_collection=None, _logger=None, _embedding_fn=None)

    result = await search.recall_memories(
        backend,
        "owner",
        "supplier shipping schedule",
        max_results=1,
        touch_access=False,
        enable_rerank=True,
    )

    assert [memory["memory_id"] for memory in result["memories"]] == ["strong"]
