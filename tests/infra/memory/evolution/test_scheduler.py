"""自进化调度器——扫描锁 token 语义（issue #278 补测）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.memory.evolution import scheduler


class _FakeRedis:
    def __init__(self, initial: dict | None = None):
        self.store: dict = dict(initial or {})
        self.eval_calls: list = []
        self.expire_calls: list = []
        # eval 脚本行为开关：release 删 key，refresh 只续期
        self.eval_mode: str = "release"

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, _script, _numkeys, key, token, *_rest):
        self.eval_calls.append((key, token))
        if self.store.get(key) != token:
            return 0
        if self.eval_mode == "refresh":
            return 1
        self.store.pop(key)
        return 1

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))
        return key in self.store


@pytest.mark.asyncio
async def test_acquire_returns_token_stored_in_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    token = await scheduler._acquire_scan_lock()
    assert isinstance(token, str) and token
    assert fake.store[scheduler.EVOLUTION_SCAN_LOCK_KEY] == token


@pytest.mark.asyncio
async def test_acquire_returns_none_when_held(monkeypatch):
    fake = _FakeRedis({scheduler.EVOLUTION_SCAN_LOCK_KEY: "other"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    assert await scheduler._acquire_scan_lock() is None


@pytest.mark.asyncio
async def test_release_uses_given_token(monkeypatch):
    fake = _FakeRedis({scheduler.EVOLUTION_SCAN_LOCK_KEY: "tok-1"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    await scheduler._release_scan_lock("tok-1")
    assert fake.eval_calls == [(scheduler.EVOLUTION_SCAN_LOCK_KEY, "tok-1")]
    assert scheduler.EVOLUTION_SCAN_LOCK_KEY not in fake.store


@pytest.mark.asyncio
async def test_release_with_wrong_token_keeps_lock(monkeypatch):
    fake = _FakeRedis({scheduler.EVOLUTION_SCAN_LOCK_KEY: "tok-real"})
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    await scheduler._release_scan_lock("tok-stale")
    assert scheduler.EVOLUTION_SCAN_LOCK_KEY in fake.store  # 他人的锁不被误删


@pytest.mark.asyncio
async def test_release_empty_token_is_noop(monkeypatch):
    def _boom():
        raise AssertionError("eval must not be called for empty token")

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", _boom)
    await scheduler._release_scan_lock("")


@pytest.mark.asyncio
async def test_refresh_scan_lock_extends_ttl_for_owner(monkeypatch):
    fake = _FakeRedis({scheduler.EVOLUTION_SCAN_LOCK_KEY: "tok-1"})
    fake.eval_mode = "refresh"
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    assert await scheduler._refresh_scan_lock("tok-1") is True
    assert fake.eval_calls == [(scheduler.EVOLUTION_SCAN_LOCK_KEY, "tok-1")]
    # 续期不删锁
    assert fake.store.get(scheduler.EVOLUTION_SCAN_LOCK_KEY) == "tok-1"


@pytest.mark.asyncio
async def test_refresh_scan_lock_rejects_foreign_token(monkeypatch):
    fake = _FakeRedis({scheduler.EVOLUTION_SCAN_LOCK_KEY: "tok-real"})
    fake.eval_mode = "refresh"
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    assert await scheduler._refresh_scan_lock("tok-stale") is False
    assert fake.store.get(scheduler.EVOLUTION_SCAN_LOCK_KEY) == "tok-real"


@pytest.mark.asyncio
async def test_refresh_scan_lock_redis_error_fails_open(monkeypatch):
    class _BrokenRedis:
        async def eval(self, *_a, **_k):
            raise ConnectionError("redis down")

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: _BrokenRedis())
    # Redis 故障无法证伪所有权——延续当前扫描（fail-open），不误杀长任务
    assert await scheduler._refresh_scan_lock("tok-1") is True


@pytest.mark.asyncio
async def test_refresh_scan_lock_empty_token_is_noop(monkeypatch):
    def _boom():
        raise AssertionError("eval must not be called for empty token")

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", _boom)
    assert await scheduler._refresh_scan_lock("") is False


@pytest.mark.asyncio
async def test_run_scheduled_evolution_refreshes_lock_per_user(monkeypatch):
    fake = _FakeRedis()
    fake.eval_mode = "refresh"
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr(scheduler.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(scheduler.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)

    async def fake_collect(_cutoff):
        return ["u1", "u2"]

    monkeypatch.setattr(scheduler, "_collect_signal_user_ids", fake_collect)

    async def fake_backend():
        return SimpleNamespace()

    monkeypatch.setattr("src.infra.memory.tools._get_backend", fake_backend)

    async def fake_evolve(_backend, uid):
        return {"stored": 1}

    monkeypatch.setattr("src.infra.memory.evolution.reflector.evolve_user", fake_evolve)

    result = await scheduler.run_scheduled_evolution()
    assert result == {"users": 2, "users_evolved": 2, "stored": 2}
    # eval 序列：2 次逐用户续期 + 1 次最终释放；token 全部一致（本次持有者）
    assert len(fake.eval_calls) == 3
    tokens = {t for _, t in fake.eval_calls}
    assert len(tokens) == 1 and tokens.pop()  # 同一 token：续期与释放均为持有者


@pytest.mark.asyncio
async def test_run_scheduled_evolution_aborts_when_lock_lost(monkeypatch):
    fake = _FakeRedis()
    fake.eval_mode = "refresh_lost"  # eval 一律返回 0：锁已易主

    async def eval_override(_script, _numkeys, key, token, *_rest):
        fake.eval_calls.append((key, token))
        return 0

    fake.eval = eval_override  # type: ignore[method-assign]
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr(scheduler.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(scheduler.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)

    async def fake_collect(_cutoff):
        return ["u1", "u2"]

    monkeypatch.setattr(scheduler, "_collect_signal_user_ids", fake_collect)

    async def fake_backend():
        return SimpleNamespace()

    monkeypatch.setattr("src.infra.memory.tools._get_backend", fake_backend)

    evolved = []

    async def fake_evolve(_backend, uid):
        evolved.append(uid)
        return {"stored": 1}

    monkeypatch.setattr("src.infra.memory.evolution.reflector.evolve_user", fake_evolve)

    result = await scheduler.run_scheduled_evolution()
    # 锁确认易主后立即中止，不再处理后续用户（防双副本并发反思）
    assert evolved == []
    assert result["skipped"] == "scan_lock_lost"


@pytest.mark.asyncio
async def test_run_scheduled_evolution_releases_own_token(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr(scheduler.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(scheduler.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)

    async def fake_collect(_cutoff):
        return ["u1"]

    monkeypatch.setattr(scheduler, "_collect_signal_user_ids", fake_collect)

    async def fake_backend():
        return SimpleNamespace()

    monkeypatch.setattr("src.infra.memory.tools._get_backend", fake_backend)

    async def fake_evolve(_backend, uid):
        return {"stored": 1}

    monkeypatch.setattr("src.infra.memory.evolution.reflector.evolve_user", fake_evolve)

    result = await scheduler.run_scheduled_evolution()
    assert result == {"users": 1, "users_evolved": 1, "stored": 1}
    # eval 序列：1 次续期（单用户）+ 1 次释放；两者 token 一致且为本次持有者
    assert len(fake.eval_calls) == 2
    refresh_token = fake.eval_calls[0][1]
    release_token = fake.eval_calls[1][1]
    assert refresh_token == release_token and release_token


# ---------------------------------------------- _collect_signal_user_ids 扫描


class _FakeAsyncAggCursor:
    """模拟 await AsyncCollection.aggregate() 之后的异步命令游标。"""

    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class _FakeFeedbackCollection:
    """按 PyMongo AsyncMongoClient 语义模拟：aggregate() 是协程，await 后才拿到游标。"""

    def __init__(self, docs):
        self._docs = list(docs)
        self.aggregate_pipelines: list = []

    async def aggregate(self, pipeline):
        self.aggregate_pipelines.append(pipeline)
        return _FakeAsyncAggCursor(self._docs)


class _FakeTracesFindCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def limit(self, _n):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class _FakeTracesCollection:
    """find() 直接返回 AsyncCursor（可链 .limit()），无需 await——与 aggregate 语义不同。"""

    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, _query, _projection=None):
        return _FakeTracesFindCursor(self._docs)


@pytest.mark.asyncio
async def test_collect_signal_users_awaits_pymongo_style_aggregate(monkeypatch):
    """feedback 扫描必须 await aggregate() 再迭代，否则 TypeError 被吞、扫描恒为空。"""
    from datetime import datetime, timedelta, timezone

    feedback = _FakeFeedbackCollection([{"user_id": "u1"}, {"user_id": "u2"}])
    monkeypatch.setattr(
        "src.infra.memory.evolution.reflector._get_feedback_collection",
        lambda: feedback,
    )
    monkeypatch.setattr(
        "src.infra.memory.evolution.reflector._get_traces_collection",
        lambda: _FakeTracesCollection([]),
    )

    users = await scheduler._collect_signal_user_ids(
        datetime.now(timezone.utc) - timedelta(hours=24)
    )

    assert users == ["u1", "u2"]
    assert feedback.aggregate_pipelines, "aggregate pipeline should be executed"


@pytest.mark.asyncio
async def test_collect_signal_users_supplements_from_traces_deduped(monkeypatch):
    """feedback 用户不足时从 error traces 补充，按 seen 去重且不超上限。"""
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(
        "src.infra.memory.evolution.reflector._get_feedback_collection",
        lambda: _FakeFeedbackCollection([{"user_id": "u1"}]),
    )
    monkeypatch.setattr(
        "src.infra.memory.evolution.reflector._get_traces_collection",
        lambda: _FakeTracesCollection(
            [{"user_id": "u2"}, {"user_id": "u2"}, {"user_id": "u1"}, {"user_id": "u3"}]
        ),
    )

    users = await scheduler._collect_signal_user_ids(
        datetime.now(timezone.utc) - timedelta(hours=24)
    )

    assert users == ["u1", "u2", "u3"]
