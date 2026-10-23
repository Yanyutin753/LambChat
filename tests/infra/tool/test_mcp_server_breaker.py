"""Per-server MCP load circuit breaker (issue #991).

状态机：closed → open（指数退避冷却）→ half-open（放行单个探测）→
成功闭合 / 失败重开加长。进程内共享：同一 server 名只算一份失败，
46 个用户的预热重建共享同一熔断状态。
"""

from __future__ import annotations

import time

import pytest

from src.infra.tool import mcp_server_breaker as breaker
from src.kernel.config import settings


@pytest.fixture(autouse=True)
def _fast_breaker(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(breaker, "_failure_threshold", lambda: 3)
    monkeypatch.setattr(breaker, "_cooldown_seconds", lambda: 0.05)
    monkeypatch.setattr(breaker, "_cooldown_max_seconds", lambda: 0.2)
    breaker.reset()
    yield
    breaker.reset()


def test_breaker_settings_defaults() -> None:
    assert settings.MCP_BREAKER_FAILURE_THRESHOLD == 3
    assert settings.MCP_BREAKER_COOLDOWN_SECONDS == 60
    assert settings.MCP_BREAKER_COOLDOWN_MAX_SECONDS == 1800


def test_failures_below_threshold_keep_circuit_closed() -> None:
    assert breaker.record_failure("sys:a", "err1") is None
    assert breaker.record_failure("sys:a", "err2") is None
    assert breaker.acquire_load_slot("sys:a") is None


def test_threshold_failures_open_circuit() -> None:
    breaker.record_failure("sys:a", "e1")
    breaker.record_failure("sys:a", "e2")
    event = breaker.record_failure("sys:a", "e3")

    assert event is not None
    assert event.kind == "opened"
    assert event.streak == 1
    assert event.error == "e3"

    reason = breaker.acquire_load_slot("sys:a")
    assert reason is not None
    assert "circuit" in reason


def test_cooldown_expiry_allows_single_half_open_probe() -> None:
    for i in range(3):
        breaker.record_failure("sys:a", f"e{i}")

    time.sleep(0.06)

    # 半开：恰好放行一个探测，第二个调用者被拒
    assert breaker.acquire_load_slot("sys:a") is None
    reason = breaker.acquire_load_slot("sys:a")
    assert reason is not None


def test_half_open_probe_success_closes_circuit() -> None:
    for i in range(3):
        breaker.record_failure("sys:a", f"e{i}")

    time.sleep(0.06)
    breaker.acquire_load_slot("sys:a")  # 占据探测名额
    event = breaker.record_success("sys:a")

    assert event is not None
    assert event.kind == "recovered"
    assert breaker.acquire_load_slot("sys:a") is None  # closed，放行


def test_half_open_probe_failure_reopens_with_longer_cooldown() -> None:
    for i in range(3):
        breaker.record_failure("sys:a", f"e{i}")

    time.sleep(0.06)
    breaker.acquire_load_slot("sys:a")
    event = breaker.record_failure("sys:a", "still-dead")

    assert event is not None
    assert event.kind == "reopened"
    assert event.streak == 2
    # 重开后仍在冷却，不放行
    assert breaker.acquire_load_slot("sys:a") is not None


def test_cooldown_backoff_is_capped() -> None:
    assert breaker._cooldown_for(streak=1) == 0.05
    assert breaker._cooldown_for(streak=2) == 0.1
    # 0.2 封顶：streak 再大也不超过 max
    assert breaker._cooldown_for(streak=10) == 0.2


def test_success_resets_closed_counter_with_recovery_event() -> None:
    breaker.record_failure("sys:a", "e1")
    breaker.record_failure("sys:a", "e2")
    assert breaker.record_success("sys:a").kind == "recovered"
    # 计数清零：需重新积累 3 次才触发
    breaker.record_failure("sys:a", "e1")
    breaker.record_failure("sys:a", "e2")
    assert breaker.record_failure("sys:a", "e3") is not None


def test_keys_are_isolated_by_scope() -> None:
    for i in range(3):
        breaker.record_failure("sys:a", "e")
    # user 作用域同名 server 不受系统源熔断影响
    assert breaker.acquire_load_slot("user:u1:a") is None


def test_snapshot_reports_state() -> None:
    for i in range(3):
        breaker.record_failure("sys:a", "e")
    snap = breaker.snapshot()
    assert snap["sys:a"]["status"] == "open"
    assert snap["sys:a"]["consecutive_failures"] == 3
