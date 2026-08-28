"""Qdrant 向量索引层测试（A：专用向量库路线）。

Qdrant 用 qdrant-client 的 :memory: 嵌入式模式——零外部依赖，CI 友好。
"""

from __future__ import annotations

import pytest

from src.infra.memory.client.native.vector_store import QdrantVectorIndex

DIMS = 8


def _vec(seed: float) -> list[float]:
    import math

    return [math.sin(seed + i) for i in range(DIMS)]


def _mk_index() -> QdrantVectorIndex:
    return QdrantVectorIndex(location=":memory:", dims=DIMS)


@pytest.mark.asyncio
async def test_collection_created_with_cosine_and_dims():
    idx = _mk_index()
    await idx.ensure_collection()
    cols = {c.name: c for c in (await idx._client.get_collections()).collections}
    assert "native_memories" in cols
    info = await idx._client.get_collection("native_memories")
    assert str(info.config.params.vectors.distance).lower().startswith("cosine")
    assert info.config.params.vectors.size == DIMS


@pytest.mark.asyncio
async def test_upsert_search_roundtrip_with_user_isolation():
    idx = _mk_index()
    await idx.upsert(
        memory_id="11111111111111111111111111111111",
        user_id="u1",
        vector=_vec(0.1),
        memory_type="user",
        context="user_identity",
        updated_at=100,
    )
    await idx.upsert(
        memory_id="22222222222222222222222222222222",
        user_id="u2",
        vector=_vec(0.1),
        memory_type="user",
        context=None,
        updated_at=100,
    )
    hits = await idx.search(vector=_vec(0.1), user_id="u1", limit=5)
    assert [h.memory_id for h in hits] == ["1" * 32]
    # 隔离：u2 的点不可见
    hits_u2 = await idx.search(vector=_vec(0.1), user_id="u2", limit=5)
    assert [h.memory_id for h in hits_u2] == ["22222222222222222222222222222222"]


@pytest.mark.asyncio
async def test_search_filters_by_type_and_context():
    idx = _mk_index()
    await idx.upsert(
        memory_id="a" * 32,
        user_id="u1",
        vector=_vec(0.2),
        memory_type="user",
        context="user_identity",
        updated_at=1,
    )
    await idx.upsert(
        memory_id="b" * 32,
        user_id="u1",
        vector=_vec(0.2),
        memory_type="project",
        context="project_constraint",
        updated_at=1,
    )
    hits = await idx.search(vector=_vec(0.2), user_id="u1", memory_types=["project"], limit=5)
    assert [h.memory_id for h in hits] == ["b" * 32]
    hits2 = await idx.search(
        vector=_vec(0.2), user_id="u1", context_filter="project_constraint", limit=5
    )
    assert [h.memory_id for h in hits2] == ["b" * 32]


@pytest.mark.asyncio
async def test_delete_removes_point():
    idx = _mk_index()
    await idx.upsert(
        memory_id="c" * 32,
        user_id="u1",
        vector=_vec(0.3),
        memory_type="user",
        context=None,
        updated_at=1,
    )
    ok = await idx.delete(memory_id="c" * 32, user_id="u1")
    assert ok is True
    hits = await idx.search(vector=_vec(0.3), user_id="u1", limit=5)
    assert hits == []


@pytest.mark.asyncio
async def test_error_returns_none_for_graceful_fallback():
    idx = _mk_index()
    await idx._client.close()
    assert await idx.search(vector=_vec(0.1), user_id="u1", limit=3) is None
    assert (
        await idx.upsert(
            memory_id="d" * 32,
            user_id="u1",
            vector=_vec(0.1),
            memory_type="user",
            context=None,
            updated_at=1,
        )
        is False
    )
    assert await idx.delete(memory_id="d" * 32, user_id="u1") is False


@pytest.mark.asyncio
async def test_get_vector_index_returns_none_when_unreachable(monkeypatch):
    """Qdrant 不可达 → 单例初始化失败返回 None → 调用方走既有降级链路。"""
    import src.infra.memory.client.native.vector_store as vs

    async def _teardown():
        await vs.reset_vector_index()

    monkeypatch.setattr(vs.settings, "NATIVE_MEMORY_VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(vs.settings, "NATIVE_MEMORY_QDRANT_URL", "http://127.0.0.1:59999")
    await vs.reset_vector_index()
    try:
        assert await vs.get_vector_index() is None
        assert await vs.index_search(vector=[0.1] * 4, user_id="u1", limit=3) is None
    finally:
        await _teardown()
