from __future__ import annotations

import asyncio

import pytest

from src.infra.session.backfill import (
    ConversationHistoryBackfillWorker,
    SessionSearchBackfillWorker,
)


class _FakeRedis:
    def __init__(self, *, acquire=True) -> None:
        self.acquire = acquire
        self.set_calls: list[tuple[tuple, dict]] = []
        self.eval_calls: list[tuple[tuple, dict]] = []
        self.closed = False

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return self.acquire

    async def eval(self, *args, **kwargs):
        self.eval_calls.append((args, kwargs))
        return 1

    async def aclose(self) -> None:
        self.closed = True


class _FakeStorage:
    def __init__(self, batches: list[int]) -> None:
        self._batches = list(batches)
        self.calls: list[int] = []

    async def backfill_search_indexes(self, batch_size: int = 100) -> int:
        self.calls.append(batch_size)
        if not self._batches:
            return 0
        return self._batches.pop(0)


class _SlowStorage:
    def __init__(self) -> None:
        self.calls = 0

    async def backfill_search_indexes(self, batch_size: int = 100) -> int:
        del batch_size
        self.calls += 1
        await asyncio.sleep(0.03)
        return 1 if self.calls == 1 else 0


class _FakeHistoryService:
    def __init__(self, batches: list[int]) -> None:
        self._batches = list(batches)
        self.calls: list[int] = []

    async def backfill_indexes(self, batch_size: int = 100) -> int:
        self.calls.append(batch_size)
        return self._batches.pop(0) if self._batches else 0


@pytest.mark.asyncio
async def test_backfill_worker_uses_distributed_lock_and_processes_batches() -> None:
    redis_client = _FakeRedis(acquire=True)
    storage = _FakeStorage([3, 2, 0])
    worker = SessionSearchBackfillWorker(
        storage=storage,
        redis_client=redis_client,
        batch_size=7,
        batch_delay_seconds=0,
    )

    rebuilt = await worker.run_until_complete()

    assert rebuilt == 5
    assert storage.calls == [7, 7, 7]
    assert len(redis_client.set_calls) == 3
    assert len(redis_client.eval_calls) == 3

    await worker.close()
    assert redis_client.closed is True


@pytest.mark.asyncio
async def test_backfill_worker_skips_when_lock_is_held_elsewhere() -> None:
    redis_client = _FakeRedis(acquire=False)
    storage = _FakeStorage([5])
    worker = SessionSearchBackfillWorker(
        storage=storage,
        redis_client=redis_client,
        batch_size=9,
        batch_delay_seconds=0,
    )

    rebuilt = await worker.run_once()

    assert rebuilt == 0
    assert storage.calls == []
    assert len(redis_client.set_calls) == 1
    assert redis_client.eval_calls == []


@pytest.mark.asyncio
async def test_backfill_worker_renews_lock_while_batch_is_running() -> None:
    redis_client = _FakeRedis(acquire=True)
    storage = _SlowStorage()
    worker = SessionSearchBackfillWorker(
        storage=storage,
        redis_client=redis_client,
        batch_size=5,
        batch_delay_seconds=0,
        lock_ttl_seconds=1,
        renew_interval_seconds=0.01,
    )

    rebuilt = await worker.run_once()

    assert rebuilt == 1
    assert storage.calls == 1
    assert len(redis_client.set_calls) >= 1
    assert len(redis_client.eval_calls) >= 2


@pytest.mark.asyncio
async def test_conversation_backfill_uses_distinct_lock_and_runs_batches() -> None:
    redis_client = _FakeRedis(acquire=True)
    service = _FakeHistoryService([3, 1, 0])
    worker = ConversationHistoryBackfillWorker(
        service=service,
        redis_client=redis_client,
        batch_size=5,
        batch_delay_seconds=0,
    )

    rebuilt = await worker.run_until_complete()

    assert rebuilt == 4
    assert service.calls == [5, 5, 5]
    assert redis_client.set_calls[0][0][0] == "conversation:search_backfill:lock"
