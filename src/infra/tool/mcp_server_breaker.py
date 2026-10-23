"""Per-server MCP tool-load circuit breaker (issue #991).

同一 MCP server 持续加载失败时跳过它的重连尝试，避免每个预热/缓存重建
周期都为必死上游白付一次加载超时。状态机：

    closed --(连续失败达到阈值)--> open --(冷却到期)--> half-open
    half-open --(探测成功)--> closed
    half-open --(探测失败)--> open（streak+1，冷却指数退避并封顶）

要点：
- 进程内共享：按 server 键（`sys:{name}` / `user:{user_id}:{name}`）计数，
  同一进程内所有用户的重建共享系统源熔断状态；k8s 多副本各自独立计数，
  行为一致只是各自跳闸。接口刻意保持无 await，未来可替换为 Redis 实现。
- 半开探测就是工具列表加载本身，不引入独立 ping 心跳（避免
  ping 失败无限重连一类问题）。
- 所有函数同步且无锁：仅在 asyncio 事件循环内调用，检查与修改之间
  无 await 点，天然原子。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# 进程内共享状态：key -> BreakerState
_states: dict[str, "BreakerState"] = {}

# closed 状态条目的清理阈值，防止已删除 server 的条目无限累积
_MAX_TRACKED_KEYS = 1000


@dataclass
class BreakerEvent:
    """状态迁移事件；仅迁移时产生，供状态回写钩子消费。"""

    key: str
    kind: str  # "opened" | "reopened" | "recovered"
    streak: int
    error: Optional[str] = None


@dataclass
class BreakerState:
    consecutive_failures: int = 0
    status: str = "closed"  # closed | open | half_open
    streak: int = 0  # 连续 open 轮数，决定退避长度
    retry_at: float = 0.0  # open 状态下允许进入 half-open 的时间
    probe_taken: bool = False  # half-open 探测名额是否已被占用


def _failure_threshold() -> int:
    default = 3
    try:
        value = int(getattr(settings, "MCP_BREAKER_FAILURE_THRESHOLD", default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _cooldown_seconds() -> float:
    default = 60.0
    try:
        value = float(getattr(settings, "MCP_BREAKER_COOLDOWN_SECONDS", default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _cooldown_max_seconds() -> float:
    default = 1800.0
    try:
        value = float(getattr(settings, "MCP_BREAKER_COOLDOWN_MAX_SECONDS", default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _cooldown_for(streak: int) -> float:
    base = _cooldown_seconds()
    return min(base * (2 ** max(0, streak - 1)), _cooldown_max_seconds())


def _evict_if_needed() -> None:
    if len(_states) <= _MAX_TRACKED_KEYS:
        return
    for key in [k for k, s in _states.items() if s.status == "closed"]:
        _states.pop(key, None)


def reset() -> None:
    """清空全部状态（测试用）。"""
    _states.clear()


def acquire_load_slot(key: str) -> Optional[str]:
    """尝试为一次工具加载取得名额。

    Returns:
        None: 允许加载（closed，或 half-open 探测名额归本次调用）
        str: 拒绝原因（circuit open / half-open 名额已占）
    """
    state = _states.get(key)
    if state is None:
        return None
    now = time.monotonic()
    if state.status == "open":
        if now < state.retry_at:
            remaining = int(state.retry_at - now)
            return f"circuit open, retry in ~{remaining}s (streak={state.streak})"
        # 冷却到期 → half-open，放行恰好一个探测
        state.status = "half_open"
        state.probe_taken = True
        return None
    if state.status == "half_open":
        if state.probe_taken:
            return "circuit half-open, probe already in flight"
        state.probe_taken = True
        return None
    return None  # closed


def record_failure(key: str, error: Optional[str] = None) -> Optional[BreakerEvent]:
    """记录一次加载失败；达到阈值跳闸或半开探测失败重开时返回迁移事件。"""
    state = _states.setdefault(key, BreakerState())
    now = time.monotonic()
    state.consecutive_failures += 1

    if state.status == "half_open":
        # 半开探测失败：重开并加长冷却
        state.streak += 1
        state.status = "open"
        state.retry_at = now + _cooldown_for(state.streak)
        state.probe_taken = False
        logger.info(
            "[MCP Breaker] Reopened '%s' after failed probe (streak=%s, next probe in %.0fs)",
            key,
            state.streak,
            _cooldown_for(state.streak),
        )
        return BreakerEvent(key=key, kind="reopened", streak=state.streak, error=error)

    if state.status == "closed" and state.consecutive_failures >= _failure_threshold():
        state.status = "open"
        state.streak = 1
        state.retry_at = now + _cooldown_for(1)
        _evict_if_needed()
        logger.info(
            "[MCP Breaker] Opened '%s' after %s consecutive failures; "
            "skipping loads until %.0fs cooldown elapses",
            key,
            state.consecutive_failures,
            _cooldown_for(1),
        )
        return BreakerEvent(key=key, kind="opened", streak=1, error=error)

    return None


def release_load_slot(key: str) -> None:
    state = _states.get(key)
    if state is not None and state.status == "half_open":
        state.probe_taken = False


def record_success(key: str) -> Optional[BreakerEvent]:
    """记录一次加载成功；从 open/half-open 恢复到 closed 时返回迁移事件。"""
    state = _states.get(key)
    if state is None:
        return None
    if state.status != "closed" or state.consecutive_failures:
        state.status = "closed"
        state.streak = 0
        state.consecutive_failures = 0
        state.retry_at = 0.0
        state.probe_taken = False
        logger.info("[MCP Breaker] Recovered '%s', circuit closed", key)
        return BreakerEvent(key=key, kind="recovered", streak=0, error=None)
    state.consecutive_failures = 0
    return None


def snapshot() -> dict[str, dict[str, object]]:
    """当前全部熔断状态（观测/测试用）。"""
    return {
        key: {
            "status": state.status,
            "consecutive_failures": state.consecutive_failures,
            "streak": state.streak,
            "retry_in": max(0.0, state.retry_at - time.monotonic()),
        }
        for key, state in _states.items()
    }
