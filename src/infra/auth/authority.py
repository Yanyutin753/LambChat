"""Fail closed on authority storage outages without rejecting valid credentials."""

from collections.abc import Iterator
from contextlib import contextmanager

from pymongo.errors import ConnectionFailure, ExecutionTimeout
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.kernel.errors import AppError, ErrorCode


@contextmanager
def authority_lookup() -> Iterator[None]:
    """Only wrap actual account/role/PAT storage calls, never token parsing."""
    try:
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
