from __future__ import annotations

import asyncio

import pytest

from src.infra.llm.streaming import aiter_with_first_event_timeout


async def test_stream_timeout_does_not_limit_total_duration() -> None:
    async def chunks():
        for value in range(4):
            await asyncio.sleep(0.01)
            yield value

    started = asyncio.get_running_loop().time()
    result = [item async for item in aiter_with_first_event_timeout(chunks(), timeout=0.025)]

    assert result == [0, 1, 2, 3]
    assert asyncio.get_running_loop().time() - started >= 0.04


async def test_stream_timeout_only_limits_wait_for_first_event() -> None:
    async def chunks():
        yield "started"
        await asyncio.sleep(0.02)
        yield "finished"

    stream = aiter_with_first_event_timeout(chunks(), timeout=0.01)

    assert await anext(stream) == "started"
    assert await anext(stream) == "finished"


async def test_stream_timeout_rejects_missing_first_event() -> None:
    async def chunks():
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_first_event_timeout(chunks(), timeout=0.01)

    with pytest.raises(asyncio.TimeoutError, match="first event.*0.01s"):
        await anext(stream)


async def test_stream_timeout_can_be_disabled() -> None:
    async def chunks():
        await asyncio.sleep(0.02)
        yield "ok"

    assert [item async for item in aiter_with_first_event_timeout(chunks(), timeout=None)] == ["ok"]
