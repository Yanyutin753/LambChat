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
        vector=_vec(0.2), user_id="u1", context_values=["project_constraint"], limit=5
    )
    assert [h.memory_id for h in hits2] == ["b" * 32]


@pytest.mark.asyncio
async def test_search_filters_by_context_family_values():
    """context 家族（'project' → project/project_status/...）以具体值列表下推
    MatchAny；族外的 context 不可见。"""
    idx = _mk_index()
    await idx.upsert(
        memory_id="a" * 32,
        user_id="u1",
        vector=_vec(0.2),
        memory_type="project",
        context="project_status",
        updated_at=1,
    )
    await idx.upsert(
        memory_id="b" * 32,
        user_id="u1",
        vector=_vec(0.2),
        memory_type="project",
        context="project",
        updated_at=1,
    )
    await idx.upsert(
        memory_id="c" * 32,
        user_id="u1",
        vector=_vec(0.2),
        memory_type="project",
        context="user_identity",
        updated_at=1,
    )
    hits = await idx.search(
        vector=_vec(0.2),
        user_id="u1",
        context_values=["project", "project_status"],
        limit=5,
    )
    assert sorted(h.memory_id for h in hits) == sorted(["a" * 32, "b" * 32])


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


# ---------------------------------------------------------------------------
# 维度校验与自动回填（issue #278）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_collection_returns_created_flag():
    idx = _mk_index()
    assert await idx.ensure_collection() is True  # 首建
    assert await idx.ensure_collection() is False  # 已存在且维度一致


@pytest.mark.asyncio
async def test_dimension_mismatch_raises_without_deleting():
    idx = _mk_index()
    await idx.ensure_collection()
    idx._dims = DIMS // 2  # 模拟改了 EMBEDDING_DIMENSIONS
    with pytest.raises(RuntimeError, match="[Dd]imension"):
        await idx.ensure_collection()
    # 保守处理：不自动删库，原样保留待管理员处置
    info = await idx._client.get_collection("native_memories")
    assert info.config.params.vectors.size == DIMS


class _FakeRedis:
    """dict 后端的极简 redis 假件（set nx / get / delete / token-eval）。"""

    def __init__(self, initial: dict | None = None):
        self.store: dict = dict(initial or {})
        self.eval_calls: list = []

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    async def eval(self, _script, _numkeys, key, token):
        self.eval_calls.append((key, token))
        if self.store.get(key) == token:
            self.store.pop(key)


@pytest.mark.asyncio
async def test_run_backfill_once_skips_when_done_flag_set(monkeypatch):
    from src.infra.memory.client.native import vector_store as vs

    fake = _FakeRedis({vs._BACKFILL_DONE_KEY: "1"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    called = []
    monkeypatch.setattr(
        vs, "backfill_from_mongo", lambda coll, batch_size=100: called.append(coll) or _ok(0)
    )
    await vs._run_backfill_once(force=False)
    assert called == []


async def _ok(n):
    return {"upserted": n}


@pytest.mark.asyncio
async def test_run_backfill_once_runs_locks_and_marks_done(monkeypatch):
    from types import SimpleNamespace

    from src.infra.memory.client.native import vector_store as vs

    fake = _FakeRedis()
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    coll = object()
    calls = []

    async def fake_backfill(collection, batch_size=100):
        calls.append(collection)
        return {"upserted": 7}

    monkeypatch.setattr(vs, "backfill_from_mongo", fake_backfill)

    async def fake_backend():
        return SimpleNamespace(_collection=coll)

    monkeypatch.setattr("src.infra.memory.tools._get_backend", fake_backend)

    await vs._run_backfill_once(force=False)

    assert calls == [coll]
    assert fake.store.get(vs._BACKFILL_DONE_KEY) == "1"  # 完成标记
    assert vs._BACKFILL_LOCK_KEY not in fake.store  # 锁已释放


@pytest.mark.asyncio
async def test_run_backfill_once_force_overrides_done_flag(monkeypatch):
    from types import SimpleNamespace

    from src.infra.memory.client.native import vector_store as vs

    fake = _FakeRedis({vs._BACKFILL_DONE_KEY: "1"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    calls = []

    async def fake_backfill(collection, batch_size=100):
        calls.append(collection)
        return {"upserted": 1}

    monkeypatch.setattr(vs, "backfill_from_mongo", fake_backfill)

    async def fake_backend():
        return SimpleNamespace(_collection=object())

    monkeypatch.setattr("src.infra.memory.tools._get_backend", fake_backend)

    await vs._run_backfill_once(force=True)  # 首建/重建 → 忽略旧完成标记
    assert calls != []
    assert fake.store.get(vs._BACKFILL_DONE_KEY) == "1"


@pytest.mark.asyncio
async def test_run_backfill_once_skips_when_lock_held(monkeypatch):
    from src.infra.memory.client.native import vector_store as vs

    fake = _FakeRedis({vs._BACKFILL_LOCK_KEY: "other-replica"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    called = []
    monkeypatch.setattr(
        vs,
        "backfill_from_mongo",
        lambda coll, batch_size=100: called.append(coll) or _ok(0),
    )
    await vs._run_backfill_once(force=True)
    assert called == []
    assert fake.store.get(vs._BACKFILL_DONE_KEY) is None  # 未被误标完成


@pytest.mark.asyncio
async def test_run_backfill_once_redis_failure_is_silent(monkeypatch):
    from src.infra.memory.client.native import vector_store as vs

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", _boom)
    called = []
    monkeypatch.setattr(
        vs,
        "backfill_from_mongo",
        lambda coll, batch_size=100: called.append(coll) or _ok(0),
    )
    await vs._run_backfill_once(force=True)  # 不抛
    assert called == []


@pytest.mark.asyncio
async def test_get_vector_index_schedules_backfill_task_once(monkeypatch):
    import asyncio

    from src.infra.memory.client.native import vector_store as vs

    await vs.reset_vector_index()
    monkeypatch.setattr(vs, "vector_backend_enabled", lambda: True)
    monkeypatch.setattr(vs, "QdrantVectorIndex", _mk_index)
    forces: list[bool] = []

    async def fake_run(force: bool = False):
        forces.append(force)

    monkeypatch.setattr(vs, "_run_backfill_once", fake_run)
    try:
        idx = await vs.get_vector_index()
        assert idx is not None
        await asyncio.sleep(0.05)
        assert forces == [True]  # 首建 → force 回填

        idx2 = await vs.get_vector_index()
        assert idx2 is idx
        await asyncio.sleep(0.05)
        assert forces == [True]  # 单例复用，不重复调度
    finally:
        await vs.reset_vector_index()
