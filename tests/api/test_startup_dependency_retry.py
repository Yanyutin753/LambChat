"""启动期依赖退避重试（#1212）。

宿主机重启后 a/b Pod 早于 Docker/Mongo 就绪：lifespan 首个 Mongo 步骤抛
ServerSelectionTimeoutError → 进程退出 → CrashLoopBackOff 2-3 分钟自愈。
退避重试只覆盖连接类异常；配置/数据错误仍立即失败。
"""

import asyncio

import pytest
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

from src.api.startup_dependency import run_startup_step_with_retry


async def test_returns_value_when_dependency_ready() -> None:
    calls: list[int] = []

    async def _step() -> str:
        calls.append(1)
        return "ok"

    assert await run_startup_step_with_retry("step", _step) == "ok"
    assert calls == [1]


async def test_retries_connection_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    failures = [AutoReconnect("down"), ServerSelectionTimeoutError("still down")]

    async def _step() -> str:
        if failures:
            raise failures.pop(0)
        return "ok"

    assert await run_startup_step_with_retry("step", _step) == "ok"
    assert sleeps == [2.0, 4.0]


async def test_non_retryable_error_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_sleep(delay: float) -> None:
        raise AssertionError("must not sleep")

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    async def _step() -> None:
        raise ValueError("Unverified storage environment change")

    with pytest.raises(ValueError):
        await run_startup_step_with_retry("step", _step)


async def test_gives_up_once_retry_window_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    async def _step() -> None:
        raise ServerSelectionTimeoutError("down")

    with pytest.raises(ServerSelectionTimeoutError):
        await run_startup_step_with_retry("step", _step, retry_window_seconds=0.0)
    assert sleeps == []
