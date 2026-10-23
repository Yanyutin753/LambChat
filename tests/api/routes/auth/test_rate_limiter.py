from __future__ import annotations

import pytest

from src.api.routes.auth import rate_limiter as rate_limiter_module
from src.api.routes.auth.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_close_rate_limiter_releases_existing_singleton_without_creating_one() -> None:
    rate_limiter_module._rate_limiter = None

    await rate_limiter_module.close_rate_limiter()

    assert rate_limiter_module._rate_limiter is None

    limiter = RateLimiter()
    rate_limiter_module._rate_limiter = limiter

    await rate_limiter_module.close_rate_limiter()

    assert rate_limiter_module._rate_limiter is None


async def test_email_limit_uses_an_atomic_expiring_counter(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    redis = SimpleNamespace(eval=AsyncMock(side_effect=[1, 5, 6]))
    monkeypatch.setattr(rate_limiter_module, "get_redis_client", lambda: redis)
    limiter = RateLimiter()
    assert await limiter.check_rate_limit("limit", 5, 3600) == (True, 4)
    assert await limiter.check_rate_limit("limit", 5, 3600) == (True, 0)
    assert await limiter.check_rate_limit("limit", 5, 3600) == (False, 0)
    assert redis.eval.call_args.args[1:] == (1, "limit", "3600")


async def test_email_limit_storage_failure_fails_closed(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.kernel.errors import AppError, ErrorCode

    monkeypatch.setattr(
        rate_limiter_module,
        "get_redis_client",
        lambda: SimpleNamespace(eval=AsyncMock(side_effect=ConnectionError())),
    )
    with pytest.raises(AppError) as failure:
        await RateLimiter().check_rate_limit("limit", 5, 3600)
    assert failure.value.error_code is ErrorCode.SERVICE_UNAVAILABLE
