"""Streaming helpers shared by model-provider adapters."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import TypeVar

from src.infra.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


async def aiter_with_first_event_timeout(
    source: AsyncIterable[T],
    *,
    timeout: float | None,
    idle_timeout: float | None = None,
    gap_warn_timeout: float | None = None,
    gap_warn_context: str | None = None,
    gap_describe: Callable[[T], str] | None = None,
) -> AsyncIterator[T]:
    """Require the first event by a deadline, then bound inter-chunk gaps.

    ``timeout`` only guards the wait for the first event. ``idle_timeout``
    guards every subsequent chunk against an upstream stall（2026-09-05
    生产事故：中转流在首事件之后停滞，run 挂死 8 小时、trace 永远停在
    running）。任一值 <= 0 或 None 即禁用对应时限。

    ``gap_warn_timeout`` 是告警级的观测阈值，必须严格小于 idle_timeout：
    超过它但未触发 idle_timeout 的停滞仍会让流继续（2026-09-17 生产事故：
    中转停滞约 5.5s 后恢复，恢复点落在 token 中间，停滞期间生成的内容被
    中转丢弃，只能靠日志与 trace 的 text_id 对账），此处仅记录 warning，
    不改变任何行为。``gap_warn_context`` 传入模型名等定位信息，
    ``gap_describe`` 返回停滞恢复后首个 chunk 的可读标识（如 message.id）。
    """
    idle = idle_timeout if (idle_timeout is not None and idle_timeout > 0) else None
    warn_after = gap_warn_timeout if (gap_warn_timeout is not None and gap_warn_timeout > 0) else None
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
        last_arrival = time.monotonic()
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
            now = time.monotonic()
            gap = now - last_arrival
            last_arrival = now
            if warn_after is not None and gap > warn_after:
                describe = str(gap_describe(item) or "") if gap_describe is not None else ""
                logger.warning(
                    "LLM stream gap %.2fs exceeded warn threshold %.2fs "
                    "(model=%s, resumed_chunk=%s); content generated during the "
                    "stall may have been dropped by the upstream relay",
                    gap,
                    warn_after,
                    gap_warn_context or "unknown",
                    describe,
                )
            yield item
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
