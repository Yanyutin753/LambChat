from __future__ import annotations

import asyncio

import pytest

from src.infra.llm.streaming import aiter_with_first_event_timeout, aiter_with_idle_timeout


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


async def test_idle_timeout_allows_gaps_under_the_budget() -> None:
    async def chunks():
        yield "first"
        await asyncio.sleep(0.01)
        yield "second"
        await asyncio.sleep(0.01)
        yield "third"

    result = [item async for item in aiter_with_idle_timeout(chunks(), timeout=0.05)]

    assert result == ["first", "second", "third"]


async def test_idle_timeout_fires_when_gap_exceeds_the_budget() -> None:
    async def chunks():
        yield "first"
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_idle_timeout(chunks(), timeout=0.01)

    assert await anext(stream) == "first"
    with pytest.raises(asyncio.TimeoutError, match="no event for 0.01s"):
        await anext(stream)


async def test_idle_timeout_applies_to_waiting_for_the_first_event_too() -> None:
    async def chunks():
        await asyncio.sleep(10)
        yield "never"

    stream = aiter_with_idle_timeout(chunks(), timeout=0.01)

    with pytest.raises(asyncio.TimeoutError, match="no event for 0.01s"):
        await anext(stream)


async def test_idle_timeout_closes_source_stream_on_timeout() -> None:
    closed = asyncio.Event()

    class Source:
        def __init__(self) -> None:
            self._gen = self._chunks()

        async def _chunks(self):
            try:
                yield "first"
                await asyncio.sleep(10)
                yield "never"
            finally:
                closed.set()

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self._gen.__anext__()

        async def aclose(self) -> None:
            await self._gen.aclose()

    stream = aiter_with_idle_timeout(Source(), timeout=0.01)

    assert await anext(stream) == "first"
    with pytest.raises(asyncio.TimeoutError):
        await anext(stream)
    assert closed.is_set()


async def test_idle_timeout_can_be_disabled() -> None:
    async def chunks():
        yield "first"
        await asyncio.sleep(0.02)
        yield "second"

    result = [item async for item in aiter_with_idle_timeout(chunks(), timeout=None)]
    assert result == ["first", "second"]
    assert [item async for item in aiter_with_idle_timeout(chunks(), timeout=0)] == [
        "first",
        "second",
    ]
