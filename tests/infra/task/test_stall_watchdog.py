"""Unit tests for the stall-watchdog async iterator wrapper (issue #293)."""

from __future__ import annotations

import asyncio

import pytest

from src.infra.task.stall_watchdog import TaskStalledError, aiter_with_stall_timeout


async def _gen(items: list, delay_before: float = 0.0, delay_each: float = 0.0):
    await asyncio.sleep(delay_before)
    for item in items:
        yield item
        await asyncio.sleep(delay_each)


@pytest.mark.asyncio
async def test_yields_all_items_when_stream_progresses() -> None:
    async def source():
        for i in range(3):
            await asyncio.sleep(0.01)
            yield i

    result = []
    async for item in aiter_with_stall_timeout(source(), timeout=1.0):
        result.append(item)
    assert result == [0, 1, 2]


@pytest.mark.asyncio
async def test_first_event_deadline_raises_task_stalled_error() -> None:
    with pytest.raises(TaskStalledError) as exc_info:
        async for _item in aiter_with_stall_timeout(_gen([1], delay_before=5), timeout=0.05):
            pass
    assert "0.05" in str(exc_info.value)


@pytest.mark.asyncio
async def test_idle_deadline_between_events_raises_task_stalled_error() -> None:
    async def source():
        yield "first"
        await asyncio.sleep(5)
        yield "second"

    seen: list = []
    with pytest.raises(TaskStalledError):
        async for item in aiter_with_stall_timeout(source(), timeout=0.05):
            seen.append(item)
    assert seen == ["first"]


@pytest.mark.asyncio
async def test_timeout_zero_or_none_disables_watchdog() -> None:
    for disabled in (0, None):
        result = []
        async for item in aiter_with_stall_timeout(_gen([1, 2], delay_each=0.05), timeout=disabled):
            result.append(item)
        assert result == [1, 2]


@pytest.mark.asyncio
async def test_timeout_closes_underlying_generator() -> None:
    closed = asyncio.Event()

    async def source():
        try:
            yield "first"
            await asyncio.sleep(5)
            yield "second"
        finally:
            closed.set()

    with pytest.raises(TaskStalledError):
        async for _item in aiter_with_stall_timeout(source(), timeout=0.05):
            pass

    assert closed.is_set()


@pytest.mark.asyncio
async def test_early_consumer_exit_closes_underlying_generator() -> None:
    closed = asyncio.Event()

    async def source():
        try:
            for i in range(10):
                yield i
        finally:
            closed.set()

    async for _item in aiter_with_stall_timeout(source(), timeout=1.0):
        break

    # 消费者提前退出后，generator 最终被 aclose 释放
    _, pending = await asyncio.wait([asyncio.create_task(closed.wait())], timeout=1)
    assert not pending
