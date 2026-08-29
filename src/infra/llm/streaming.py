"""Streaming helpers shared by model-provider adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import TypeVar

T = TypeVar("T")


async def aiter_with_first_event_timeout(
    source: AsyncIterable[T],
    *,
    timeout: float | None,
) -> AsyncIterator[T]:
    """Require the first event by a deadline, then yield the stream without limits."""
    iterator = source.__aiter__()
    try:
        try:
            if timeout is None or timeout <= 0:
                first = await anext(iterator)
            else:
                async with asyncio.timeout(timeout):
                    first = await anext(iterator)
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            raise TimeoutError(f"model stream produced no first event within {timeout}s") from exc

        yield first
        async for item in iterator:
            yield item
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
