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
    idle_timeout: float | None = None,
) -> AsyncIterator[T]:
    """Require the first event by a deadline, then bound inter-chunk gaps.

    ``timeout`` only guards the wait for the first event. ``idle_timeout``
    guards every subsequent chunk against an upstream stall（2026-09-05
    生产事故：中转流在首事件之后停滞，run 挂死 8 小时、trace 永远停在
    running）。任一值 <= 0 或 None 即禁用对应时限。
    """
    idle = idle_timeout if (idle_timeout is not None and idle_timeout > 0) else None
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
        while True:
            try:
                if idle is not None:
                    async with asyncio.timeout(idle):
                        item = await anext(iterator)
                else:
                    item = await anext(iterator)
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                raise TimeoutError(f"model stream stalled: no new chunk within {idle}s") from exc
            yield item
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
