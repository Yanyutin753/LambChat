from __future__ import annotations

import inspect
from typing import Any
from urllib.parse import unquote, urlparse

from arq.connections import RedisSettings


def build_arq_redis_settings(settings: Any) -> RedisSettings:
    """Build arq Redis settings from LambChat's Redis configuration."""
    parsed = urlparse(settings.REDIS_URL)
    database = 0
    if parsed.path and parsed.path != "/":
        database = int(parsed.path.lstrip("/"))

    password = settings.REDIS_PASSWORD or (unquote(parsed.password) if parsed.password else None)
    username = unquote(parsed.username) if parsed.username else None

    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=database,
        username=username,
        password=password,
        ssl=parsed.scheme == "rediss",
    )


async def close_arq_pool(arq_pool: Any) -> None:
    """Close an initialized ARQ pool across sync and async client APIs."""
    if arq_pool is None:
        return

    close = getattr(arq_pool, "close", None)
    if close is not None:
        result = close()
        if inspect.isawaitable(result):
            await result
    wait_closed = getattr(arq_pool, "wait_closed", None)
    if wait_closed is not None:
        result = wait_closed()
        if inspect.isawaitable(result):
            await result
