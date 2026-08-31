from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from src.infra.task import pubsub as task_pubsub_module
from src.infra.task.pubsub import TaskPubSub


@pytest.mark.asyncio
async def test_cancel_pubsub_offloads_message_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    handled: list[dict[str, Any]] = []

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    async def _on_message(data: dict[str, Any]) -> None:
        handled.append(data)

    monkeypatch.setattr(
        task_pubsub_module,
        "run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )

    pubsub = TaskPubSub(asyncio.Lock(), {})

    await pubsub._handle_cancel_message(
        {"data": json.dumps({"run_id": "run-1"})},
        _on_message,
    )

    assert calls == [json.loads]
    assert handled == [{"run_id": "run-1"}]


@pytest.mark.asyncio
async def test_cancel_pubsub_flushes_event_buffer_before_completing_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    class _TraceStorage:
        async def complete_trace(self, *args, **kwargs):
            del args, kwargs
            call_order.append("complete_trace")
            return True

    class _DualWriter:
        async def flush_mongo_buffer(self):
            call_order.append("flush_mongo_buffer")

    async def _on_message(data: dict[str, Any]) -> None:
        assert data["run_id"] == "run-1"
        call_order.append("on_message")

    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: _TraceStorage(),
    )
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _DualWriter(),
    )

    pubsub = TaskPubSub(asyncio.Lock(), {})

    await pubsub._handle_cancel_message(
        {
            "data": json.dumps(
                {
                    "run_id": "run-1",
                    "trace_id": "trace-1",
                }
            )
        },
        _on_message,
    )

    assert call_order == ["on_message", "flush_mongo_buffer", "complete_trace"]


@pytest.mark.asyncio
async def test_cancel_pubsub_sets_local_interrupt_flag_before_cancelling(monkeypatch):
    """跨副本取消：执行副本收到 pubsub 消息必须先设本地中断标志再取消任务。

    否则 executor 的取消路径会把用户取消误判为系统中断（无缝续跑分支），
    吞掉 user:cancel/error 终态事件（回归 R1-跨副本取消）。
    """
    from src.infra.task.cancellation import TaskCancellation, _interrupted_runs

    _interrupted_runs.pop("run-local-flag", None)

    cancelled_at: list[float | None] = [{"flag_age": None}]

    class _Task:
        def __init__(self):
            self._done = False

        def done(self):
            return self._done

        def cancel(self):
            age = TaskCancellation.check_interrupt_fast("run-local-flag")
            cancelled_at[0]["flag_age"] = age

    pubsub = TaskPubSub(asyncio.Lock(), {"run-local-flag": _Task()})

    await pubsub._handle_cancel_message({"data": json.dumps({"run_id": "run-local-flag"})})

    assert cancelled_at[0]["flag_age"] is True, "cancel() 前本地中断标志必须已设置"
    _interrupted_runs.pop("run-local-flag", None)
