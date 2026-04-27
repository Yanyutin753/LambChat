from __future__ import annotations

import pytest

from src.infra.session.event_merger import EventMerger


class _DedicatedRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[tuple, dict]] = []
        self.eval_calls: list[tuple[tuple, dict]] = []
        self.closed = False

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True

    async def eval(self, *args, **kwargs):
        self.eval_calls.append((args, kwargs))
        return 1

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_event_merger_uses_dedicated_redis_for_locking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dedicated = _DedicatedRedis()
    isolated_pool_flags: list[bool] = []

    monkeypatch.setattr(
        "src.infra.session.event_merger.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or dedicated,
    )

    merger = EventMerger(trace_storage=None)

    assert await merger._acquire_lock() is True
    assert dedicated.set_calls
    assert isolated_pool_flags == [True]

    await merger._release_lock()
    assert dedicated.eval_calls

    await merger.stop()
    assert dedicated.closed is True
