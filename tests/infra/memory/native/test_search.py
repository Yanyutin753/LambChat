from datetime import datetime, timezone

import pytest

from src.infra.memory.client.native.search import (
    build_keyword_clauses,
    format_memory,
)


def test_build_keyword_clauses_supports_cjk_queries_without_spaces():
    clauses = build_keyword_clauses("原始SQL偏好")

    assert clauses
    assert all("$regex" in clause["content"] for clause in clauses if "content" in clause)


def test_build_keyword_clauses_supports_english_queries():
    clauses = build_keyword_clauses("prefers raw sql analytics")

    assert clauses
    assert any("summary" in clause for clause in clauses)


def test_format_memory_sets_staleness_warning_for_old_memories():
    doc = {
        "memory_id": "m1",
        "user_id": "u1",
        "content": "Prefers raw SQL.",
        "summary": "Prefers raw SQL.",
        "title": "SQL preference",
        "memory_type": "user",
        "source": "manual",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    memory = format_memory(doc, score=1.0, now=datetime(2026, 4, 2, tzinfo=timezone.utc))

    assert memory["memory_id"] == "m1"
    assert "staleness_warning" in memory


@pytest.mark.asyncio
async def test_keyword_fallback_uses_generated_clauses(monkeypatch):
    from src.infra.memory.client.native import search as search_module

    seen = {}

    class FakeCursor:
        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        async def to_list(self, length):
            seen["length"] = length
            return []

    class FakeCollection:
        def find(self, query):
            seen["query"] = query
            return FakeCursor()

    results = await search_module.keyword_fallback(
        collection=FakeCollection(),
        user_id="u1",
        query="原始SQL偏好",
        limit=5,
        memory_types=None,
    )

    assert results == []
    assert "$or" in seen["query"]


@pytest.mark.asyncio
async def test_text_search_applies_context_filter():
    from src.infra.memory.client.native.search import text_search

    seen = {}

    class FakeCursor:
        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return []

    class FakeCollection:
        def find(self, query, *_a, **_k):
            seen["query"] = dict(query)
            return FakeCursor()

    await text_search(
        FakeCollection(),
        None,
        "u1",
        "项目约束",
        5,
        None,
        context_filter="project_constraint",
    )

    clause = seen["query"]["context"]
    # context 过滤按家族前缀匹配：'project' 应覆盖 project/project_status/...
    assert isinstance(clause, dict)
    assert clause.get("$regex") == "^project_constraint"


@pytest.mark.asyncio
async def test_text_search_without_context_filter_unchanged():
    from src.infra.memory.client.native.search import text_search

    seen = {}

    class FakeCursor:
        def sort(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        async def to_list(self, length):
            return []

    class FakeCollection:
        def find(self, query, *_a, **_k):
            seen["query"] = dict(query)
            return FakeCursor()

    await text_search(FakeCollection(), None, "u1", "项目约束", 5, None, context_filter=None)

    assert "context" not in seen["query"]


@pytest.mark.asyncio
async def test_recall_memories_threads_context_filter(monkeypatch):
    from src.infra.memory.client.native import search as search_module
    from src.infra.memory.client.native.search import recall_memories

    captured = {}

    async def fake_text_search(
        collection, logger, user_id, query, limit, memory_types, context_filter=None
    ):
        captured["text"] = context_filter
        return []

    async def fake_vector_search(backend, user_id, query, limit, memory_types, context_filter=None):
        captured["vector"] = context_filter
        return []

    async def fake_fallback(collection, user_id, limit, memory_types, context_filter=None):
        captured["fallback"] = context_filter
        return []

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "vector_search", fake_vector_search)
    monkeypatch.setattr(search_module, "recent_context_fallback", fake_fallback)

    class FakeBackend:
        _collection = None
        _logger = None
        _embedding_fn = None

    result = await recall_memories(
        FakeBackend(), "u1", "what should i know", 5, context_filter="project_constraint"
    )

    assert result["success"] is True
    assert captured["text"] == "project_constraint"
    assert captured["fallback"] == "project_constraint"  # overview 查询走 fallback 也带过滤
    assert "vector" not in captured  # 无 embedding 时不调向量检索


# ---------------------------------------------------------------------------
# Qdrant 索引分支（issue #278 补测：水合排序 / 空结果权威 / None 回退）
# ---------------------------------------------------------------------------

from types import SimpleNamespace


def _mem_doc(mid: str, content: str = "内容", embedding=None) -> dict:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return {
        "memory_id": mid,
        "user_id": "u1",
        "content": content,
        "summary": content,
        "title": content[:10],
        "memory_type": "user",
        "source": "manual",
        "content_storage_mode": "inline",
        "content_store_key": None,
        "created_at": now,
        "updated_at": now,
        "embedding": embedding,
    }


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self

    async def to_list(self, length=None):
        return self._docs


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs
        self.find_queries: list = []

    def find(self, query, projection=None):
        self.find_queries.append(query)
        return _FakeCursor(list(self.docs))

    def aggregate(self, pipeline):
        raise RuntimeError("aggregate unavailable in fake")


@pytest.mark.asyncio
async def test_vector_search_qdrant_hits_hydrate_in_score_order(monkeypatch):
    from src.infra.memory.client.native import search, vector_store
    from src.infra.memory.client.native.vector_store import VectorHit

    async def fake_index_search(**kw):
        return [VectorHit(memory_id="b" * 32, score=0.9), VectorHit(memory_id="a" * 32, score=0.5)]

    monkeypatch.setattr(vector_store, "index_search", fake_index_search)

    col = _FakeCollection([_mem_doc("a" * 32, "低分"), _mem_doc("b" * 32, "高分")])

    async def embed(_q):
        return [1.0, 0.0]

    backend = SimpleNamespace(_maybe_embed=embed, _collection=col)

    out = await search.vector_search(backend, "u1", "查询", 5, None)

    assert [d["memory_id"] for d in out] == ["b" * 32, "a" * 32]  # 高分在前
    assert out[0]["score"] == 0.9
    # 水合查询带 user 过滤 + id 集合 + 排除 session_summary
    q = col.find_queries[0]
    assert q["user_id"] == "u1"
    assert set(q["memory_id"]["$in"]) == {"a" * 32, "b" * 32}
    assert q["source"] == {"$ne": "session_summary"}


@pytest.mark.asyncio
async def test_vector_search_qdrant_empty_is_authoritative(monkeypatch):
    from src.infra.memory.client.native import search, vector_store

    async def fake_index_search(**kw):
        return []

    monkeypatch.setattr(vector_store, "index_search", fake_index_search)
    col = _FakeCollection([_mem_doc("a" * 32)])

    async def embed(_q):
        return [1.0, 0.0]

    backend = SimpleNamespace(_maybe_embed=embed, _collection=col)

    out = await search.vector_search(backend, "u1", "查询", 5, None)
    assert out == []
    assert col.find_queries == []  # 权威空：不再回退打 Mongo


@pytest.mark.asyncio
async def test_vector_search_qdrant_none_falls_back_to_cosine(monkeypatch):
    from src.infra.memory.client.native import search, vector_store

    async def fake_index_search(**kw):
        return None  # 未启用/故障 → 走既有链路

    monkeypatch.setattr(vector_store, "index_search", fake_index_search)

    docs = [
        _mem_doc("a" * 32, "正交", embedding=[0.0, 1.0]),
        _mem_doc("b" * 32, "同向", embedding=[1.0, 0.0]),
    ]
    col = _FakeCollection(docs)

    async def embed(_q):
        return [1.0, 0.0]

    backend = SimpleNamespace(
        _maybe_embed=embed,
        _collection=col,
        _logger=SimpleNamespace(debug=lambda *a, **k: None),
    )

    out = await search.vector_search(backend, "u1", "查询", 5, None)
    # 余弦兜底：同向高分在前、正交低分在后（按相似度降序）
    assert [d["memory_id"] for d in out] == ["b" * 32, "a" * 32]
    assert out[0]["score"] == pytest.approx(1.0)
    assert out[1]["score"] == pytest.approx(0.0)
    assert col.find_queries  # 走了 Mongo find 兜底


def test_rrf_merge_keeps_higher_score_dict_for_same_memory():
    """同一记忆被文本(keyword 兜底 score=0)与向量(cosine 0.6)同时命中时，
    合并结果必须保留高分字典——否则 0 分被下游 min_score(0.3) 全部过滤，
    召回凭查询措辞随机失效（staging 实测定位）。"""
    from src.infra.memory.client.native.search import rrf_merge

    text_hit = {"memory_id": "m1", "title": "t", "score": 0.0}
    vector_hit = {"memory_id": "m1", "title": "t", "score": 0.602}
    other = {"memory_id": "m2", "title": "o", "score": 0.5}

    merged = rrf_merge([text_hit], [vector_hit, other], max_results=5)

    by_id = {m["memory_id"]: m for m in merged}
    assert by_id["m1"]["score"] == 0.602, "文本兜底的 0 分不得覆盖向量相似度"


def test_rrf_merge_text_score_beats_zero_vector_keeps_text():
    from src.infra.memory.client.native.search import rrf_merge

    text_hit = {"memory_id": "m1", "score": 1.2}
    vector_hit = {"memory_id": "m1", "score": 0.4}

    merged = rrf_merge([text_hit], [vector_hit], max_results=5)

    assert merged[0]["score"] == 1.2


def test_build_context_clause_anchors_family_prefix():
    from src.infra.memory.client.native.search import build_context_clause

    clause = build_context_clause("project")
    assert clause == {"$regex": "^project"}
    # 精确细粒度值仍是前缀匹配的特例（只命中自身）
    assert build_context_clause("project_status") == {"$regex": "^project_status"}
    # 正则元字符需转义
    assert build_context_clause("a.b") == {"$regex": "^a\\.b"}


@pytest.mark.asyncio
async def test_vector_search_resolves_context_family_for_qdrant(monkeypatch):
    """Qdrant payload 只存具体 context；家族前缀（'project'）必须先在 Mongo
    解析为具体值列表再下推 MatchAny——否则 context='project' 会漏掉全部
    project_status 记忆（生产 6650ea0e 会话实测）。"""
    from types import SimpleNamespace

    from src.infra.memory.client.native import search, vector_store
    from src.infra.memory.client.native.vector_store import VectorHit

    captured_kwargs: dict = {}

    async def fake_index_search(**kw):
        captured_kwargs.update(kw)
        return [VectorHit(memory_id="a" * 32, score=0.9)]

    monkeypatch.setattr(vector_store, "index_search", fake_index_search)

    class FakeCol(_FakeCollection):
        def __init__(self):
            super().__init__([_mem_doc("a" * 32)])
            self.distinct_queries: list = []

        async def distinct(self, key, query):
            self.distinct_queries.append((key, query))
            return ["project", "project_status", "project_constraint"]

    col = FakeCol()

    async def embed(_q):
        return [1.0, 0.0]

    backend = SimpleNamespace(_maybe_embed=embed, _collection=col)

    out = await search.vector_search(backend, "u1", "查询", 5, None, context_filter="project")

    assert [d["memory_id"] for d in out] == ["a" * 32]
    # 家族解析下推给 Qdrant 的是具体值列表
    assert captured_kwargs.get("context_values") == [
        "project",
        "project_constraint",
        "project_status",
    ]
    assert col.distinct_queries[0][1]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_vector_search_context_family_with_no_matches_returns_empty(monkeypatch):
    from types import SimpleNamespace

    from src.infra.memory.client.native import search, vector_store

    async def fake_index_search(**kw):
        raise AssertionError("家族无命中时不应再查 Qdrant")

    monkeypatch.setattr(vector_store, "index_search", fake_index_search)

    class FakeCol(_FakeCollection):
        async def distinct(self, key, query):
            return []

    async def embed(_q):
        return [1.0, 0.0]

    backend = SimpleNamespace(_maybe_embed=embed, _collection=FakeCol([]))

    out = await search.vector_search(backend, "u1", "查询", 5, None, context_filter="nomatch")
    assert out == []


@pytest.mark.asyncio
async def test_vector_search_context_prefetch_failure_degrades_not_empties(monkeypatch):
    """distinct 瞬时故障 ≠ 家族为空：跳过 Qdrant 预过滤、走 Mongo 家族正则回退，
    不得把带 context 的向量召回整路判成权威空。"""
    from types import SimpleNamespace

    from src.infra.memory.client.native import search, vector_store

    async def unexpected_index_search(**kw):
        raise AssertionError("distinct 失败时不得带未解析的 context 下推 Qdrant")

    monkeypatch.setattr(vector_store, "index_search", unexpected_index_search)

    class FakeCol(_FakeCollection):
        def __init__(self, docs):
            super().__init__(docs)
            self.distinct_calls = 0

        async def distinct(self, key, query):
            self.distinct_calls += 1
            raise RuntimeError("mongo transient error")

    docs = [_mem_doc("a" * 32, "同向", embedding=[1.0, 0.0])]
    col = FakeCol(docs)

    async def embed(_q):
        return [1.0, 0.0]

    import logging

    backend = SimpleNamespace(
        _maybe_embed=embed, _collection=col, _logger=logging.getLogger("test")
    )

    out = await search.vector_search(
        backend, "u1", "查询", 5, None, context_filter="project"
    )

    assert col.distinct_calls == 1
    assert [d["memory_id"] for d in out] == ["a" * 32]  # 回退命中，而非权威空
    # 回退查询带家族正则过滤，语义不丢
    assert col.find_queries[0]["context"] == search.build_context_clause("project")


@pytest.mark.asyncio
async def test_recall_memories_filters_min_score_before_truncation(monkeypatch):
    """min_score 过滤必须先于 top-N 截断：低分占位不得挤掉可达标的候选。"""
    from src.infra.memory.client.native import search as search_module
    from src.infra.memory.client.native.search import recall_memories

    async def fake_text_search(collection, logger, user_id, query, limit, memory_types, context_filter=None):
        return []

    async def fake_vector_search(backend, user_id, query, limit, memory_types, context_filter=None):
        return []

    async def fake_recent_context_fallback(collection, user_id, limit, memory_types, context_filter=None):
        return []

    async def fake_hydrate(backend, memories):
        return memories

    async def fake_validate(user_id, memories):
        return memories

    monkeypatch.setattr(search_module, "text_search", fake_text_search)
    monkeypatch.setattr(search_module, "vector_search", fake_vector_search)
    monkeypatch.setattr(search_module, "recent_context_fallback", fake_recent_context_fallback)
    monkeypatch.setattr(search_module, "_hydrate_memories_limited", fake_hydrate)
    monkeypatch.setattr(search_module, "validate_memory_source_refs", fake_validate)

    class FakeCollection:
        async def update_many(self, *a, **k):
            return None

    class FakeBackend:
        _collection = FakeCollection()
        _logger = None
        _embedding_fn = None

    pool = [
        {"memory_id": "low-1", "text": "a", "score": 0.1},
        {"memory_id": "low-2", "text": "b", "score": 0.2},
        {"memory_id": "ok-1", "text": "c", "score": 0.35},
        {"memory_id": "ok-2", "text": "d", "score": 0.4},
        {"memory_id": "low-3", "text": "e", "score": 0.05},
        {"memory_id": "ok-3", "text": "f", "score": 0.45},
    ]
    monkeypatch.setattr(
        search_module, "rrf_merge", lambda text, vector, max_results: list(pool)
    )

    monkeypatch.setattr(search_module.settings, "NATIVE_MEMORY_RECALL_MIN_SCORE", 0.3)

    result = await recall_memories(
        FakeBackend(), "u1", "query", max_results=3, touch_access=False
    )

    ids = [m["memory_id"] for m in result["memories"]]
    assert ids == ["ok-3", "ok-2", "ok-1"], "低分候选应先过滤，达标者回填 top-N"
