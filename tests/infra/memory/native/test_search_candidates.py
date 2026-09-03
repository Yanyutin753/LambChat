import asyncio

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


@pytest.mark.asyncio
async def test_recall_memories_filters_low_scores_before_hydrating_store_content(
    monkeypatch,
):
    from src.infra.memory.client.native import search as search_module

    async def fake_text_search(*_args, **_kwargs):
        return [
            {
                "memory_id": "low",
                "summary": "low",
                "text": "preview",
                "storage_mode": "store",
                "content_store_key": "memory:low",
                "score": 0.1,
            },
            {
                "memory_id": "high",
                "summary": "high",
                "text": "preview",
                "storage_mode": "store",
                "content_store_key": "memory:high",
                "score": 0.9,
            },
        ]

    hydrated: list[str] = []

    async def fake_hydrate(_backend, memory):
        hydrated.append(memory["memory_id"])
        return memory

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

        async def _update_access_stats(self, memory_ids, user_id=""):
            return None

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "hydrate_formatted_memory", fake_hydrate)
    monkeypatch.setattr(search_module.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)

    result = await search_module.recall_memories(
        FakeBackend(),
        "u1",
        "query",
        max_results=2,
        touch_access=False,
        enable_rerank=False,
    )

    assert [memory["memory_id"] for memory in result["memories"]] == ["high"]
    assert hydrated == ["high"]


@pytest.mark.asyncio
async def test_recall_memories_marks_store_text_complete_when_hydrated(monkeypatch):
    from src.infra.memory.client.native.content import hydrate_formatted_memory

    class Store:
        async def aget(self, namespace, key):
            assert key == "memory:m1"
            return {"text": "完整正文：供应商A报价15元，供应商B报价16元。"}

    backend = type("Backend", (), {"_store": Store()})()
    memory = {
        "memory_id": "m1",
        "user_id": "u1",
        "text": "截断预览...",
        "storage_mode": "store",
        "content_store_key": "memory:m1",
    }

    hydrated = await hydrate_formatted_memory(backend, memory)

    assert hydrated["text"] == "完整正文：供应商A报价15元，供应商B报价16元。"
    assert hydrated["text_complete"] is True
    assert hydrated["preview"] == "截断预览..."


@pytest.mark.asyncio
async def test_recall_memories_marks_store_text_incomplete_when_hydration_falls_back():
    from src.infra.memory.client.native.content import hydrate_formatted_memory

    class Store:
        async def aget(self, namespace, key):
            return None

    backend = type("Backend", (), {"_store": Store()})()
    memory = {
        "memory_id": "m1",
        "user_id": "u1",
        "text": "截断预览...",
        "storage_mode": "store",
        "content_store_key": "memory:m1",
    }

    hydrated = await hydrate_formatted_memory(backend, memory)

    assert hydrated["text"] == "截断预览..."
    assert hydrated["text_complete"] is False
    assert hydrated["text_incomplete_reason"] == "content_store_unavailable"


@pytest.mark.asyncio
async def test_recall_memories_limits_concurrent_hydration(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    active = 0
    max_active = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def fake_text_search(*_args, **_kwargs):
        return [
            {
                "memory_id": f"memory-{index}",
                "summary": "summary",
                "text": "preview",
                "storage_mode": "store",
                "content_store_key": f"memory:{index}",
                "score": 1.0,
            }
            for index in range(5)
        ]

    async def fake_hydrate(_backend, memory):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            started.set()
        await release.wait()
        active -= 1
        return memory

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

        async def _update_access_stats(self, memory_ids, user_id=""):
            return None

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "hydrate_formatted_memory", fake_hydrate)
    monkeypatch.setattr(search_module.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0)
    monkeypatch.setattr(search_module.settings, "NATIVE_MEMORY_HYDRATE_CONCURRENCY", 2)

    task = asyncio.create_task(
        search_module.recall_memories(
            FakeBackend(),
            "u1",
            "query",
            max_results=5,
            touch_access=False,
            enable_rerank=False,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert max_active == 2

    release.set()
    result = await task

    assert len(result["memories"]) == 5


@pytest.mark.asyncio
async def test_recall_memories_caps_requested_max_results(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    seen: dict[str, int] = {}

    async def fake_text_search(
        _collection, _logger, _user_id, _query, limit, _memory_types, context_filter=None
    ):
        seen["text_limit"] = limit
        return [
            {
                "memory_id": f"memory-{index}",
                "summary": "summary",
                "text": "preview",
                "storage_mode": "inline",
                "score": 1.0,
            }
            for index in range(limit)
        ]

    async def fake_hydrate(_backend, memory):
        return memory

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

        async def _update_access_stats(self, memory_ids, user_id=""):
            seen["touched"] = len(memory_ids)

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "hydrate_formatted_memory", fake_hydrate)
    monkeypatch.setattr(search_module.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0)

    result = await search_module.recall_memories(
        FakeBackend(),
        "u1",
        "query",
        max_results=5000,
        touch_access=True,
        enable_rerank=False,
    )

    assert seen["text_limit"] == 40
    assert len(result["memories"]) == 20
    assert seen["touched"] == 20


@pytest.mark.asyncio
async def test_recall_memories_clips_oversized_query_before_search(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    seen: dict[str, str] = {}

    async def fake_text_search(
        _collection, _logger, _user_id, query, _limit, _memory_types, context_filter=None
    ):
        seen["text_query"] = query
        return []

    async def fake_vector_search(
        _backend, _user_id, query, _limit, _memory_types, context_filter=None
    ):
        seen["vector_query"] = query
        return []

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = object()

        async def _update_access_stats(self, memory_ids, user_id=""):
            return None

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "vector_search", fake_vector_search)
    monkeypatch.setattr(search_module, "NATIVE_MEMORY_RECALL_QUERY_MAX_CHARS", 32, raising=False)

    result = await search_module.recall_memories(
        FakeBackend(),
        "u1",
        "x" * 500,
        max_results=5,
        touch_access=False,
        enable_rerank=False,
    )

    assert result["success"] is True
    assert len(seen["text_query"]) <= 32
    assert seen["text_query"] == seen["vector_query"]
    assert result["query"] == seen["text_query"]
