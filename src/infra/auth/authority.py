"""Fail closed on authority storage outages without rejecting valid credentials."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pymongo.errors import ConnectionFailure, ExecutionTimeout
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.kernel.errors import AppError, ErrorCode

AUTHORITY_LOOKUP_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def authority_lookup() -> AsyncIterator[None]:
    """Only wrap actual account/role/PAT storage calls, never token parsing."""
    try:
        async with asyncio.timeout(AUTHORITY_LOOKUP_TIMEOUT_SECONDS):
            yield
    except AppError:
        raise
    except (
        ConnectionFailure,
        ExecutionTimeout,
        RedisConnectionError,
        RedisTimeoutError,
        TimeoutError,
        ConnectionError,
    ) as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE) from error
    except Exception as error:
        raise AppError(ErrorCode.INTERNAL_ERROR) from error
