from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.task import arq_payloads
from src.infra.task.arq_payloads import TaskArqPayloadStore


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return int(existed)


@pytest.mark.asyncio
async def test_task_arq_payload_store_round_trips_context() -> None:
    redis = _FakeRedis()
    store = TaskArqPayloadStore(redis=redis, ttl_seconds=60)
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "agent_id": "search",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "message": "hello",
        "agent_options": {"model": "test"},
    }

    await store.save("run-1", payload)
    loaded = await store.load("run-1")

    assert loaded == payload
    assert redis.expirations["task:arq:payload:run-1"] == 60
    assert json.loads(redis.values["task:arq:payload:run-1"]) == payload


@pytest.mark.asyncio
async def test_task_arq_payload_store_deletes_context() -> None:
    redis = _FakeRedis()
    store = TaskArqPayloadStore(redis=redis, ttl_seconds=60)

    await store.save("run-1", {"run_id": "run-1"})
    deleted = await store.delete("run-1")

    assert deleted is True
    assert await store.load("run-1") is None


@pytest.mark.parametrize("executor_key", ["conversation_schedule", "scheduled_agent_stream"])
async def test_scheduled_payload_survives_unbounded_queue_wait(executor_key):
    redis = _FakeRedis()
    store = TaskArqPayloadStore(redis=redis)
    await store.save("run-1", {"executor_key": executor_key})
    assert "task:arq:payload:run-1" not in redis.expirations


@pytest.mark.asyncio
async def test_task_arq_payload_store_rejects_oversized_payload_before_redis_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(arq_payloads, "TASK_ARQ_PAYLOAD_MAX_BYTES", 32, raising=False)
    redis = _FakeRedis()
    store = TaskArqPayloadStore(redis=redis, ttl_seconds=60)

    with pytest.raises(ValueError, match="task payload too large"):
        await store.save("run-1", {"message": "x" * 64})

    assert redis.values == {}


@pytest.mark.asyncio
async def test_task_arq_payload_store_offloads_payload_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _FakeRedis()
    store = TaskArqPayloadStore(redis=redis, ttl_seconds=60)

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(arq_payloads, "run_blocking_io", _fake_run_blocking_io, raising=False)

    await store.save("run-1", {"message": "x" * 20_000})

    assert calls == [json.dumps]
    assert redis.values["task:arq:payload:run-1"].startswith('{"message":')


@pytest.mark.asyncio
async def test_task_arq_payload_store_offloads_payload_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _FakeRedis()
    redis.values["task:arq:payload:run-1"] = '{"message": "' + ("x" * 20_000) + '"}'
    store = TaskArqPayloadStore(redis=redis, ttl_seconds=60)

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(arq_payloads, "run_blocking_io", _fake_run_blocking_io, raising=False)

    loaded = await store.load("run-1")

    assert calls == [json.loads]
    assert loaded == {"message": "x" * 20_000}
