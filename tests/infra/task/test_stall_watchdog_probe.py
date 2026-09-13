"""stall watchdog 原语：generator 静默时的外部进展探针。

生产事故（2026-09-12/13，ginko 两次深跑被杀）：Search Agent 深跑时
message:chunk / 子代理事件走 presenter.emit 直连路径，executor 生成器
可静默超过 1 小时；watchdog 只看生成器 yield，把满负荷运行的健康 run
按「3600s 无事件」误杀。本组测试锁定新契约：探针观察到外部进展时
重新武装 deadline，且等待期间不得取消挂起的 anext（否则生成器被毁）。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.infra.task.exceptions import TaskStalledError
from src.infra.task.stall_watchdog import aiter_with_stall_timeout


async def _slow_gen(delay: float, items: int):
    for i in range(items):
        await asyncio.sleep(delay)
        yield {"event": "message:chunk", "data": {"content": str(i)}}


async def _collect(async_iter):
    return [item async for item in async_iter]


async def test_probe_fresh_external_progress_prevents_stall() -> None:
    """生成器静默超过 deadline，但探针持续上报进展 → 不误杀，事件照常流出。"""
    probe_clock = {"last": time.monotonic()}

    async def _probe_updater(stop: asyncio.Event) -> None:
        while not stop.is_set():
            await asyncio.sleep(0.02)
            probe_clock["last"] = time.monotonic()

    stop = asyncio.Event()
    updater = asyncio.create_task(_probe_updater(stop))
    try:
        # 生成器每 0.12s 才出一个事件，远超 0.05s deadline；全靠探针续命
        items = await asyncio.wait_for(
            _collect(
                aiter_with_stall_timeout(
                    _slow_gen(0.12, 2),
                    timeout=0.05,
                    progress_probe=lambda: probe_clock["last"],
                )
            ),
            timeout=5,
        )
        assert len(items) == 2
    finally:
        stop.set()
        await updater


async def test_probe_stale_still_raises_stall_error() -> None:
    """生成器静默且探针时间戳过期（外部也没有进展）→ 照常判死。"""

    def _stale_probe() -> float:
        return time.monotonic() - 999.0

    with pytest.raises(TaskStalledError):
        async for _ in aiter_with_stall_timeout(
            _slow_gen(10, 1), timeout=0.05, progress_probe=_stale_probe
        ):
            pass


async def test_no_probe_keeps_original_gap_semantics() -> None:
    """不传探针 → 保持原行为：事件间隔超时即判死。"""
    with pytest.raises(TaskStalledError):
        async for _ in aiter_with_stall_timeout(_slow_gen(10, 1), timeout=0.05):
            pass


async def test_zero_timeout_passthrough_with_probe() -> None:
    """timeout<=0 时直通，探针存在也不生效。"""

    def _any_probe() -> float:
        return time.monotonic()

    items = await _collect(
        aiter_with_stall_timeout(_slow_gen(0.0, 3), timeout=0, progress_probe=_any_probe)
    )
    assert len(items) == 3


async def test_generator_exhaustion_ends_cleanly_with_probe() -> None:
    """生成器自然耗尽（StopAsyncIteration）在探针模式下正常收尾。"""

    def _fresh_probe() -> float:
        return time.monotonic()

    items = await _collect(
        aiter_with_stall_timeout(_slow_gen(0.01, 2), timeout=1.0, progress_probe=_fresh_probe)
    )
    assert len(items) == 2
