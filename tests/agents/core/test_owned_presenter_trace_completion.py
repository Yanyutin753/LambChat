"""agent 自持 presenter 时 trace 终结的测试。

背景（2026-09-05 生产排查）：直连 ``/api/{agent_id}/stream`` 路径不传
presenter，``BaseGraphAgent._stream`` 内部创建的 presenter 在成功、报错、
客户端断开三种结束方式下都从不调用 ``complete``，trace 永远停在
status="running"（生产实例：run_20260905032659_eb9272e8 挂 running 8 小时）。
本文件锁定：agent 拥有 presenter 时必须在出口处终结 trace；外部传入的
presenter（TaskExecutor 路径）仍由 executor 负责，agent 不得代劳。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.core.base import complete_owned_presenter_trace

BASE_SOURCE = Path("src/agents/core/base.py").read_text()


class _FakePresenter:
    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []
        self.completed: list[str] = []
        self.complete_error: Exception | None = None

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        self.emitted.append(event)
        return event

    def error(
        self,
        message: str,
        error_type: str = "Error",
        details: dict | None = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "error",
            "data": {"error": message, "type": error_type, "code": code},
        }

    async def complete(self, status: str = "completed") -> None:
        if self.complete_error:
            raise self.complete_error
        self.completed.append(status)


@pytest.mark.asyncio
async def test_success_finalizes_trace_as_completed() -> None:
    presenter = _FakePresenter()

    await complete_owned_presenter_trace(presenter, terminal_error=None)

    assert presenter.completed == ["completed"]
    assert presenter.emitted == []


@pytest.mark.asyncio
async def test_terminal_error_emits_error_event_and_finalizes_as_error() -> None:
    presenter = _FakePresenter()

    await complete_owned_presenter_trace(presenter, terminal_error=RuntimeError("boom"))

    assert presenter.completed == ["error"]
    assert len(presenter.emitted) == 1
    data = presenter.emitted[0]["data"]
    assert data["type"] == "RuntimeError"
    assert "boom" in data["error"]


@pytest.mark.asyncio
async def test_cancellation_finalizes_as_error_with_cancelled_code() -> None:
    presenter = _FakePresenter()

    await complete_owned_presenter_trace(presenter, terminal_error=asyncio.CancelledError())

    assert presenter.completed == ["error"]
    assert presenter.emitted[0]["data"]["code"] == "task_cancelled"


@pytest.mark.asyncio
async def test_finalize_never_raises_even_if_presenter_complete_fails() -> None:
    presenter = _FakePresenter()
    presenter.complete_error = RuntimeError("mongo down")

    await complete_owned_presenter_trace(presenter, terminal_error=None)

    assert presenter.completed == []


@pytest.mark.asyncio
async def test_finalize_is_idempotent() -> None:
    presenter = _FakePresenter()

    await complete_owned_presenter_trace(presenter, terminal_error=None)
    await complete_owned_presenter_trace(presenter, terminal_error=None)

    assert presenter.completed == ["completed"]


def test_stream_wires_owned_presenter_finalization() -> None:
    # _stream 必须区分"自建 presenter"与"外部传入"，且在 finally 出口调用终结器
    assert "owns_presenter" in BASE_SOURCE
    assert "complete_owned_presenter_trace" in BASE_SOURCE


def test_executor_owned_presenters_are_not_finalized_by_agent() -> None:
    # 外部 presenter（TaskExecutor 路径）由 executor 负责终结；agent 侧
    # 终结器必须由 owns_presenter 分支守卫（源码结构校验，防接线遗漏）
    assert "if owns_presenter" in BASE_SOURCE or "if not owns_presenter" in BASE_SOURCE
