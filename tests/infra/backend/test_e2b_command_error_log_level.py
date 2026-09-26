"""E2B 正常语义日志降噪：命令非零退出与 keepalive 失败不进错误监控。

命令 exit≠0 是沙箱执行的正常结果（模型写码-跑-修循环，2026-09-20 巡检
结论：此类 ERROR 污染错误监控）；keepalive set_timeout 失败（沙箱已回收
或暂停）属生命周期正常事件。真实基础设施故障仍保持 ERROR。
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.backend.e2b import E2BBackend


def _ok(stdout: str = "ok\n") -> Any:
    return SimpleNamespace(stdout=stdout, stderr="", exit_code=0)


class _OneShotCommands:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome

    def run(self, **kwargs: Any) -> Any:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _FakeSandbox:
    """最小沙箱替身：commands.run 可抛异常，set_timeout 可失败。"""

    def __init__(self, outcome: Any, set_timeout_error: Exception | None = None) -> None:
        self.sandbox_id = "e2b-loglevel"
        self.commands = _OneShotCommands(outcome)
        self._set_timeout_error = set_timeout_error
        self.set_timeout_calls: list[int] = []

    def set_timeout(self, timeout: int) -> None:
        self.set_timeout_calls.append(timeout)
        if self._set_timeout_error is not None:
            raise self._set_timeout_error


def _exit_exception(exit_code: int = 1) -> Exception:
    from e2b.sandbox.commands.command_handle import CommandExitException

    return CommandExitException(
        stderr="boom",
        stdout="partial",
        exit_code=exit_code,
        error=f"Command exited with code {exit_code}",
    )


def test_nonzero_command_exit_logs_info_not_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """agent 代码 exit 1 是正常语义：记 INFO，不得再刷 ERROR。"""
    backend = E2BBackend(sandbox=_FakeSandbox(outcome=_exit_exception(1)), timeout=600)

    with caplog.at_level(logging.INFO, logger="src.infra.backend.e2b"):
        resp = backend.execute("python bad.py")

    assert resp.exit_code == -1  # 响应契约不变
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert any(
        r.levelno == logging.INFO and "exit" in r.getMessage().lower() for r in caplog.records
    )


def test_infra_command_failure_still_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """真实基础设施故障（非命令退出）保持 ERROR。"""
    backend = E2BBackend(
        sandbox=_FakeSandbox(outcome=RuntimeError("connection refused")), timeout=600
    )

    with caplog.at_level(logging.INFO, logger="src.infra.backend.e2b"):
        backend.execute("ls")

    assert any(
        r.levelno == logging.ERROR and "Command failed" in r.getMessage() for r in caplog.records
    )


def test_sync_keepalive_failure_logs_info_not_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = E2BBackend(
        sandbox=_FakeSandbox(
            outcome=_ok(), set_timeout_error=RuntimeError("Sandbox sbx-1 not found")
        ),
        timeout=600,
    )
    backend._last_timeout_extend = -1e9  # 强制越过续期间隔

    with caplog.at_level(logging.INFO, logger="src.infra.backend.e2b"):
        resp = backend.execute("ls")

    assert resp.exit_code == 0
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert any("keepalive" in r.getMessage().lower() for r in caplog.records)


async def test_async_keepalive_failure_logs_info_not_warning(
    monkeypatch: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = E2BBackend(sandbox=_FakeSandbox(outcome=_ok()), timeout=600)
    backend._last_timeout_extend = -1e9

    class _AsyncSandboxStub:
        async def set_timeout(self, timeout: int) -> None:
            raise RuntimeError("Sandbox sbx-1 not found")

    async def fake_async_sandbox(self: Any) -> Any:
        return _AsyncSandboxStub()

    monkeypatch.setattr(E2BBackend, "_async_sandbox", fake_async_sandbox)

    with caplog.at_level(logging.INFO, logger="src.infra.backend.e2b_async"):
        await backend._amaybe_extend_timeout()

    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert any("keepalive" in r.getMessage().lower() for r in caplog.records)
