"""sandbox_heal：沙箱暂停/断连类错误的识别与唤醒重试。"""

from __future__ import annotations

import pytest

from src.infra.backend.sandbox_heal import SandboxHeal, is_retryable_sandbox_error


def test_timeout_errors_are_not_retryable() -> None:
    assert not is_retryable_sandbox_error(RuntimeError("Command timed out after 30 seconds"))
    assert not is_retryable_sandbox_error(TimeoutError())
    assert not is_retryable_sandbox_error(ValueError("bad path"))


def test_pause_and_connection_errors_are_retryable() -> None:
    assert is_retryable_sandbox_error(RuntimeError("Sandbox is paused"))
    assert is_retryable_sandbox_error(RuntimeError("connection refused"))
    assert is_retryable_sandbox_error(ConnectionError("connection reset by peer"))
    assert is_retryable_sandbox_error(RuntimeError("unexpected EOF in body"))


def test_run_success_never_wakes() -> None:
    wake_calls: list[int] = []
    heal = SandboxHeal(wake=lambda: wake_calls.append(1), sandbox_id="sbx")

    assert heal.run("op", lambda: "ok") == "ok"
    assert wake_calls == []
    assert heal.consecutive_failures == 0


def test_run_retries_once_after_wake_on_retryable_error() -> None:
    calls = {"n": 0}
    wake_calls: list[int] = []

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Sandbox is paused")
        return "healed"

    heal = SandboxHeal(wake=lambda: wake_calls.append(1), sandbox_id="sbx")

    assert heal.run("op", flaky) == "healed"
    assert wake_calls == [1]
    assert calls["n"] == 2
    assert heal.consecutive_failures == 0


def test_run_does_not_retry_non_retryable_errors() -> None:
    calls = {"n": 0}

    def boom() -> None:
        calls["n"] += 1
        raise ValueError("nope")

    heal = SandboxHeal(wake=lambda: None, sandbox_id="sbx")

    with pytest.raises(ValueError):
        heal.run("op", boom)
    assert calls["n"] == 1


def test_failed_retry_counts_consecutive_failures() -> None:
    def always_paused() -> None:
        raise RuntimeError("Sandbox is paused")

    heal = SandboxHeal(wake=lambda: None, sandbox_id="sbx")

    with pytest.raises(RuntimeError):
        heal.run("op", always_paused)
    assert heal.consecutive_failures == 1
    assert not heal.exhausted


def test_exhausted_after_three_consecutive_failures_then_resets() -> None:
    def always_paused() -> None:
        raise RuntimeError("Sandbox is paused")

    heal = SandboxHeal(wake=lambda: None, sandbox_id="sbx")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            heal.run("op", always_paused)
    assert heal.exhausted

    assert heal.run("op", lambda: "ok") == "ok"
    assert not heal.exhausted
    assert heal.consecutive_failures == 0


def test_wake_failure_still_retries_once() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Sandbox is paused")
        return "healed"

    def broken_wake() -> None:
        raise RuntimeError("wake failed")

    heal = SandboxHeal(wake=broken_wake, sandbox_id="sbx")

    assert heal.run("op", flaky) == "healed"
    assert calls["n"] == 2
