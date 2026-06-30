from __future__ import annotations

import asyncio

import pytest

from src.infra.task.heartbeat import TaskHeartbeat


class _FakeRedisClient:
    def __init__(self) -> None:
        self.set_calls = 0
        self.deleted: list[str] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls += 1
        if self.set_calls >= 2:
            raise RuntimeError("heartbeat failed")
        return True

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        return 1


@pytest.mark.asyncio
async def test_heartbeat_stop_cancels_loop_and_cleans_task_after_write_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.task.heartbeat.get_redis_client",
        lambda: fake_redis,
    )

    class _NoopConcurrencyLimiter:
        async def refresh(self, user_id: str, run_id: str) -> None:
            return None

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _NoopConcurrencyLimiter(),
    )

    first_retry = asyncio.Event()

    async def _sleep(_: float) -> None:
        first_retry.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("src.infra.task.heartbeat.asyncio.sleep", _sleep)

    heartbeat = TaskHeartbeat()
    await heartbeat.start("run-1", user_id="user-1")

    await asyncio.wait_for(first_retry.wait(), timeout=1)
    await heartbeat.stop("run-1")

    assert "run-1" not in heartbeat._heartbeat_tasks
    assert fake_redis.deleted == ["task:heartbeat:run-1"]


@pytest.mark.asyncio
async def test_heartbeat_continues_after_transient_redis_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FlakyRedisClient:
        def __init__(self) -> None:
            self.set_calls = 0

        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            self.set_calls += 1
            if self.set_calls == 1:
                raise RuntimeError("temporary redis outage")
            return True

        async def delete(self, key: str) -> int:
            return 1

    fake_redis = _FlakyRedisClient()
    monkeypatch.setattr(
        "src.infra.task.heartbeat.get_redis_client",
        lambda: fake_redis,
    )

    sleeps = 0
    second_write = asyncio.Event()

    async def _sleep(_: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if fake_redis.set_calls >= 2:
            second_write.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("src.infra.task.heartbeat.asyncio.sleep", _sleep)

    heartbeat = TaskHeartbeat()
    await heartbeat.start("run-1", user_id=None)

    await asyncio.wait_for(second_write.wait(), timeout=1)
    await heartbeat.stop("run-1")

    assert fake_redis.set_calls >= 2
    assert sleeps >= 1


@pytest.mark.asyncio
async def test_heartbeat_stop_all_limits_parallel_redis_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    max_active = 0

    class _SlowDeleteRedisClient:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete(self, key: str) -> int:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            self.deleted.append(key)
            return 1

    fake_redis = _SlowDeleteRedisClient()
    monkeypatch.setattr(
        "src.infra.task.heartbeat.get_redis_client",
        lambda: fake_redis,
    )
    monkeypatch.setattr(
        "src.infra.task.startup_cleanup.settings.TASK_STARTUP_CLEANUP_CONCURRENCY", 2
    )

    heartbeat = TaskHeartbeat()
    loop = asyncio.get_running_loop()
    for index in range(5):
        done_task = loop.create_future()
        done_task.set_result(None)
        heartbeat._heartbeat_tasks[f"run-{index}"] = done_task  # type: ignore[assignment]

    await heartbeat.stop_all()

    assert max_active == 2
    assert heartbeat._heartbeat_tasks == {}
    assert sorted(fake_redis.deleted) == [
        "task:heartbeat:run-0",
        "task:heartbeat:run-1",
        "task:heartbeat:run-2",
        "task:heartbeat:run-3",
        "task:heartbeat:run-4",
    ]
