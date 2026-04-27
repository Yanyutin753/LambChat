from __future__ import annotations

import pytest

from src.infra.websocket_rate_limiter import WebSocketRateLimiter


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def ttl(self, key: str) -> int:
        return 42

    async def incr(self, key: str) -> int:
        next_value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(next_value)
        return next_value

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        return 1


@pytest.mark.asyncio
async def test_check_uses_fresh_redis_client_instead_of_constructor_cached_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_redis = _FakeRedis()
    current_redis = _FakeRedis({"ws:auth:fail:127.0.0.1": "7"})
    active_redis = initial_redis

    def _create_redis_client(*, isolated_pool: bool = False):
        assert isolated_pool is True
        return active_redis

    monkeypatch.setattr(
        "src.infra.websocket_rate_limiter.create_redis_client",
        _create_redis_client,
    )

    limiter = WebSocketRateLimiter(max_failures=5)
    active_redis = current_redis

    allowed, ttl = await limiter.check("127.0.0.1")

    assert allowed is False
    assert ttl == 42


@pytest.mark.asyncio
async def test_rate_limiter_uses_dedicated_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    isolated_pool_flags: list[bool] = []

    monkeypatch.setattr(
        "src.infra.websocket_rate_limiter.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )

    limiter = WebSocketRateLimiter(max_failures=5)

    allowed, ttl = await limiter.check("127.0.0.1")

    assert allowed is True
    assert ttl == 0
    assert isolated_pool_flags == [True]
