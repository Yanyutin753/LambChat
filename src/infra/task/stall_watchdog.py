"""Run-level stall watchdog for agent event streams (issue #293).

worker 存活但 agent stream 挂死（LLM 首包永不到达、工具 await 挂起等）时，
心跳持续刷新、孤儿接管判定永不触发，run/trace 停留在 running。本模块对
executor 事件流施加"每两个事件之间"的停滞 deadline：超时即抛
TaskStalledError，由 TaskExecutor 的通用错误路径迁移 error 终态。

与 ``src/infra/llm/streaming.py`` 的首事件超时互补：那只覆盖模型适配层的
首个流式事件，覆盖不了图内非流式调用与工具挂起。

progress_probe（2026-09-12/13 生产事故）：事件有两条入口——executor 循环
的 yield 与 presenter 直连路径（emit→save_event）。Search Agent 深跑时后者
持续产出而生成器可静默超过 deadline，watchdog 若只看 yield 会把满负荷运行
的健康 run 误杀。探针返回 presenter 最近一次 save_event 的单调时间戳，
deadline 到期时若探针窗口内仍有进展则重新武装，且绝不取消挂起的 anext
（取消会连带毁掉底层生成器）。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import TypeVar

from src.infra.task.exceptions import TaskStalledError

T = TypeVar("T")


def _probe_recent(progress_probe: Callable[[], float], timeout: float) -> bool:
    try:
        return (time.monotonic() - progress_probe()) < timeout
    except Exception:
        return False


async def aiter_with_stall_timeout(
    source: AsyncIterable[T],
    *,
    timeout: float | None,
    progress_probe: Callable[[], float] | None = None,
) -> AsyncIterator[T]:
    """Require stream progress by a recurring deadline between events.

    timeout 为 None 或 <=0 时直接透传（watchdog 关闭）。超时会取消对底层
    迭代器的等待并尝试 aclose 释放其资源；探针窗口内有外部进展时改为
    重新武装 deadline 而不判死。
    """
    if timeout is None or timeout <= 0:
        async for item in source:
            yield item
        return

    iterator = source.__aiter__()
    anext_task: asyncio.Task[T] | None = None
    try:
        while True:
            if anext_task is None:
                anext_task = asyncio.ensure_future(anext(iterator))
            done, _pending = await asyncio.wait({anext_task}, timeout=timeout)
            if anext_task not in done:
                if progress_probe is not None and _probe_recent(progress_probe, timeout):
                    continue  # 外部仍在推进：重新武装 deadline，不取消挂起的 anext
                raise TaskStalledError(f"agent stream stalled: no event within {timeout}s")
            try:
                item = anext_task.result()
            except StopAsyncIteration:
                return
            anext_task = None
            yield item
    finally:
        if anext_task is not None:
            anext_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await anext_task
        close = getattr(iterator, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass
