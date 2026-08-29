"""Run-level stall watchdog for agent event streams (issue #293).

worker 存活但 agent stream 挂死（LLM 首包永不到达、工具 await 挂起等）时，
心跳持续刷新、孤儿接管判定永不触发，run/trace 停留在 running。本模块对
executor 事件流施加"每两个事件之间"的停滞 deadline：超时即抛
TaskStalledError，由 TaskExecutor 的通用错误路径迁移 error 终态。

与 ``src/infra/llm/streaming.py`` 的首事件超时互补：那只覆盖模型适配层的
首个流式事件，覆盖不了图内非流式调用与工具挂起。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import TypeVar

from src.infra.task.exceptions import TaskStalledError

T = TypeVar("T")


async def aiter_with_stall_timeout(
    source: AsyncIterable[T],
    *,
    timeout: float | None,
) -> AsyncIterator[T]:
    """Require stream progress by a recurring deadline between events.

    timeout 为 None 或 <=0 时直接透传（watchdog 关闭）。超时会取消对底层
    迭代器的等待并尝试 aclose 释放其资源。
    """
    if timeout is None or timeout <= 0:
        async for item in source:
            yield item
        return

    iterator = source.__aiter__()
    try:
        while True:
            try:
                async with asyncio.timeout(timeout):
                    item = await anext(iterator)
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                raise TaskStalledError(f"agent stream stalled: no event within {timeout}s") from exc
            yield item
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass
