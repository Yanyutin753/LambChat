import asyncio
import json

import pytest

from src.infra.task import cancellation as cancellation_module
from src.infra.task.cancellation import TaskCancellation


class _FakeRedis:
    async def set(self, *args, **kwargs):
        return True

    async def publish(self, *args, **kwargs):
        return 1


class _FakeTraceStorage:
    def __init__(self) -> None:
        self.complete_calls = []

    async def complete_trace(self, *args, **kwargs):
        self.complete_calls.append((args, kwargs))
        return True


@pytest.mark.asyncio
async def test_cancel_run_marks_trace_error_without_zero_usage_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_storage = _FakeTraceStorage()
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={})

    monkeypatch.setattr("src.infra.task.cancellation.get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(
        "src.infra.task.cancellation.get_trace_storage",
        lambda: trace_storage,
    )

    result = await cancellation.cancel_run(
        "run-1",
        user_id=None,
        run_info={"trace_id": "trace-1"},
    )

    assert result["success"] is True
    assert trace_storage.complete_calls == [
        (
            ("trace-1",),
            {
                "status": "error",
                "metadata": {"cancel_reason": "Task cancelled by user"},
                "ensure_token_usage": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_cancel_run_does_not_complete_trace_before_local_task_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_storage = _FakeTraceStorage()
    task_completed = asyncio.Event()

    async def _local_task() -> None:
        task_completed.set()

    task = asyncio.create_task(_local_task())
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={"run-1": task})

    monkeypatch.setattr(cancellation_module, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(cancellation_module, "get_trace_storage", lambda: trace_storage)

    result = await cancellation.cancel_run(
        "run-1",
        user_id="user-1",
        run_info={"session_id": "session-1", "trace_id": "trace-1"},
    )

    assert result["success"] is True
    assert task_completed.is_set()
    assert trace_storage.complete_calls == []


@pytest.mark.asyncio
async def test_cancel_run_flushes_existing_buffer_before_completing_trace_without_user_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    class _TraceStorage(_FakeTraceStorage):
        async def complete_trace(self, *args, **kwargs):
            call_order.append("complete_trace")
            return await super().complete_trace(*args, **kwargs)

    class _DualWriter:
        async def flush_mongo_buffer(self):
            call_order.append("flush_mongo_buffer")

    trace_storage = _TraceStorage()
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={})

    monkeypatch.setattr(cancellation_module, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(cancellation_module, "get_trace_storage", lambda: trace_storage)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _DualWriter(),
    )

    result = await cancellation.cancel_run(
        "run-1",
        user_id=None,
        run_info={"session_id": "session-1", "trace_id": "trace-1"},
    )

    assert result["success"] is True
    assert call_order == ["flush_mongo_buffer", "complete_trace"]


@pytest.mark.asyncio
async def test_cancel_run_offloads_cancel_publish_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    class _RecordingRedis:
        def __init__(self) -> None:
            self.published: list[tuple[str, str]] = []

        async def set(self, *args, **kwargs):
            return True

        async def publish(self, channel: str, payload: str):
            self.published.append((channel, payload))
            return 1

    redis = _RecordingRedis()
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={})

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(cancellation_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        cancellation_module, "run_blocking_io", _fake_run_blocking_io, raising=False
    )

    result = await cancellation.cancel_run("run-1", publish=True)

    assert result["success"] is True
    assert calls == [json.dumps]
    assert redis.published
    assert json.loads(redis.published[0][1])["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_cancel_run_waits_for_local_task_graceful_cancel_after_agent_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_storage = _FakeTraceStorage()
    agent_closed = asyncio.Event()
    task_cancelled = False

    async def _local_task() -> None:
        nonlocal task_cancelled
        try:
            await agent_closed.wait()
        except asyncio.CancelledError:
            task_cancelled = True
            raise

    task = asyncio.create_task(_local_task())
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={"run-1": task})

    class _FakeAgent:
        async def close(self, run_id: str) -> None:
            assert run_id == "run-1"
            agent_closed.set()

    class _FakeFactory:
        @staticmethod
        async def get(agent_id: str):
            assert agent_id == "search"
            return _FakeAgent()

    monkeypatch.setattr("src.infra.task.cancellation.get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(
        "src.infra.task.cancellation.get_trace_storage",
        lambda: trace_storage,
    )
    monkeypatch.setattr("src.agents.core.base.AgentFactory", _FakeFactory)

    result = await cancellation.cancel_run(
        "run-1",
        user_id=None,
        run_info={"trace_id": "trace-1", "agent_id": "search"},
    )

    assert result["success"] is True
    assert result["cancelled_locally"] is False
    assert task.done()
    assert task_cancelled is False


@pytest.mark.asyncio
async def test_cancel_run_cancels_local_task_when_agent_close_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_cancelled = False

    async def _local_task() -> None:
        nonlocal task_cancelled
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            task_cancelled = True
            raise

    task = asyncio.create_task(_local_task())
    cancellation = TaskCancellation(lock=asyncio.Lock(), tasks={"run-1": task})

    class _HangingAgent:
        async def close(self, run_id: str) -> None:
            assert run_id == "run-1"
            await asyncio.Event().wait()

    class _FakeFactory:
        @staticmethod
        async def get(agent_id: str):
            assert agent_id == "search"
            return _HangingAgent()

    monkeypatch.setattr("src.infra.task.cancellation.get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr("src.agents.core.base.AgentFactory", _FakeFactory)
    monkeypatch.setattr(cancellation_module, "_AGENT_CLOSE_CANCEL_TIMEOUT", 0.01)

    result = await cancellation.cancel_run(
        "run-1",
        user_id=None,
        run_info={"agent_id": "search"},
        publish=False,
    )

    assert result["success"] is True
    assert result["cancelled_locally"] is True
    assert task.done()
    assert task_cancelled is True
