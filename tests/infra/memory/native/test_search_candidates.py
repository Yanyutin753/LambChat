import pytest


@pytest.mark.asyncio
async def test_recall_memories_can_skip_llm_rerank(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    async def fake_text_search(*_args, **_kwargs):
        return [
            {"memory_id": "m1", "summary": "a", "text": "a", "storage_mode": "inline"},
            {"memory_id": "m2", "summary": "b", "text": "b", "storage_mode": "inline"},
        ]

    async def fake_hydrate(_backend, memory):
        return memory

    async def fake_update(*_args, **_kwargs):
        raise AssertionError("access stats should not update")

    async def explode_rerank(*_args, **_kwargs):
        raise AssertionError("rerank should not run")

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

        async def _update_access_stats(self, memory_ids):
            await fake_update(memory_ids)

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "hydrate_formatted_memory", fake_hydrate)
    monkeypatch.setattr(search_module, "rerank_candidates", explode_rerank)

    result = await search_module.recall_memories(
        FakeBackend(),
        "u1",
        "duckdb",
        max_results=1,
        touch_access=False,
        enable_rerank=False,
    )

    assert result["success"] is True
    assert len(result["memories"]) == 1


def test_local_rerank_prefers_stronger_term_overlap():
    from src.infra.memory.client.native.search import local_rerank

    candidates = [
        {
            "memory_id": "m1",
            "title": "SQL preference",
            "summary": "Prefers raw SQL for analytics work.",
            "text": "Prefers raw SQL for analytics work.",
            "score": 0.2,
        },
        {
            "memory_id": "m2",
            "title": "Database note",
            "summary": "Uses DuckDB sometimes.",
            "text": "Uses DuckDB sometimes.",
            "score": 0.9,
        },
    ]

    ranked = local_rerank("prefers raw sql analytics", candidates, max_results=2)

    assert [item["memory_id"] for item in ranked] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_recall_memories_uses_rerank_model_when_enabled(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    async def fake_text_search(*_args, **_kwargs):
        return [
            {"memory_id": "m1", "summary": "raw sql", "text": "raw sql", "storage_mode": "inline"},
            {"memory_id": "m2", "summary": "duckdb", "text": "duckdb", "storage_mode": "inline"},
        ]

    async def fake_hydrate(_backend, memory):
        return memory

    async def fake_rerank(query, candidates, max_results):
        assert query == "duckdb"
        return [candidates[1], candidates[0]][:max_results]

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

        async def _update_access_stats(self, memory_ids):
            return None

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "hydrate_formatted_memory", fake_hydrate)
    monkeypatch.setattr(search_module, "rerank_candidates", fake_rerank)

    result = await search_module.recall_memories(
        FakeBackend(),
        "u1",
        "duckdb",
        max_results=1,
        touch_access=False,
        enable_rerank=True,
    )

    assert result["success"] is True
    assert result["memories"][0]["memory_id"] == "m2"
