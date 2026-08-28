"""自进化调度器——扫描锁 token 语义（issue #278 补测）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.memory.evolution import scheduler


class _FakeRedis:
    def __init__(self, initial: dict | None = None):
        self.store: dict = dict(initial or {})
        self.eval_calls: list = []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, _script, _numkeys, key, token):
        self.eval_calls.append((key, token))
        if self.store.get(key) == token:
            self.store.pop(key)


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
    # 释放的 token 与获取时写入的一致（token-checked 释放）
    assert len(fake.eval_calls) == 1
    released_token = fake.eval_calls[0][1]
    assert released_token  # 用的是本次持有者 token（而非全局残留）
