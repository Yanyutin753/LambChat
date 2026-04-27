from __future__ import annotations

import pytest

from src.infra.storage import redis as redis_storage


class _FakePool:
    closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeConnectionPoolFactory:
    @staticmethod
    def from_url(*args, **kwargs):
        return _FakePool()


class _FakeAsyncRedisModule:
    ConnectionPool = _FakeConnectionPoolFactory


class _FakeRedisWithClosablePool:
    def __init__(self, *, connection_pool) -> None:
        self.connection_pool = connection_pool

    async def aclose(self) -> None:
        return None


class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(message)


class _FakeRedisClient:
    def __init__(self, *, connection_pool, **kwargs) -> None:
        self.connection_pool = connection_pool


def test_get_redis_client_returns_distinct_clients_sharing_one_pool(
    monkeypatch,
) -> None:
    pool = _FakePool()
    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = lambda *args, **kwargs: pool

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    client_a = redis_storage.get_redis_client()
    client_b = redis_storage.get_redis_client()

    assert client_a is not client_b
    assert client_a.connection_pool is pool
    assert client_b.connection_pool is pool


def test_create_redis_client_can_use_an_isolated_pool(monkeypatch) -> None:
    pools: list[_FakePool] = []

    def _from_url(*args, **kwargs):
        pool = _FakePool()
        pools.append(pool)
        return pool

    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = _from_url

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    shared_client = redis_storage.create_redis_client()
    isolated_client = redis_storage.create_redis_client(isolated_pool=True)

    assert shared_client.connection_pool is redis_storage.get_redis_connection_pool()
    assert isolated_client.connection_pool is not shared_client.connection_pool
    assert isolated_client.connection_pool is pools[-1]


def test_create_redis_client_can_override_socket_timeout(monkeypatch) -> None:
    captured_kwargs: list[dict] = []

    def _from_url(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return _FakePool()

    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = _from_url

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisClient)
    redis_storage.get_redis_connection_pool.cache_clear()

    redis_storage.create_redis_client(isolated_pool=True, socket_timeout=None)

    assert captured_kwargs[-1]["socket_timeout"] is None


@pytest.mark.asyncio
async def test_close_redis_client_closes_shared_connection_pool(monkeypatch) -> None:
    pool = _FakePool()
    fake_module = _FakeAsyncRedisModule()
    fake_module.ConnectionPool.from_url = lambda *args, **kwargs: pool
    fake_logger = _FakeLogger()

    monkeypatch.setattr(redis_storage, "redis", fake_module)
    monkeypatch.setattr(redis_storage, "Redis", _FakeRedisWithClosablePool)
    monkeypatch.setattr(redis_storage, "logger", fake_logger)
    redis_storage.get_redis_connection_pool.cache_clear()

    await redis_storage.close_redis_client()

    assert pool.closed is True
    assert redis_storage.get_redis_connection_pool.cache_info().currsize == 0
