"""Controlled offloading for unavoidable synchronous IO.

Use this helper for third-party SDK calls and filesystem work that do not have
native async APIs. It keeps those calls off the FastAPI event loop and avoids
unbounded growth of the default executor.

车道模型（分池 + 隔离，防互相饿死）：
- ``run_blocking_io``（快道，8 线程）：毫秒级关键路径——pubsub 控制消息、
  密钥加解密、websocket 广播小 json、沙箱生命周期探针。带默认超时，
  楔死调用不能永久占用关键线程。
- ``run_long_blocking_io``（慢道，64 线程）：吞吐型长持驻——S3 传输、
  文档解析、同步 SDK 兜底。可排队。
- ``run_long_blocking_io(..., urgent=True)``（形状子池，16 线程）：
  「大但延迟敏感」的当前 run 关键序列化——工具结果/子代理结果/上下文
  json、base64 解码。与慢道物理隔离，大传输排满也不卡当前对话。

所有车道共享饱和可观测性：等待超阈值告警（含车道名与排队深度），
``blocking_io_stats()`` 暴露 in_flight/pending/completed 供监控消费。
"""

from __future__ import annotations

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from src.infra.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)

_DEFAULT_MAX_WORKERS = 8
_DEFAULT_LONG_MAX_WORKERS = 64
_DEFAULT_SHAPE_MAX_WORKERS = 16
_DEFAULT_MAX_PENDING = 16
# 快道默认超时：毫秒级调用的兜底上限，防楔死调用永久占用关键线程。
_FAST_LANE_DEFAULT_TIMEOUT = 30.0
# 等待告警阈值（秒）：快道 0.5s / 慢道与形状子池 2s。
_FAST_WAIT_WARN_SECONDS = 0.5
_SLOW_WAIT_WARN_SECONDS = 2.0

_MAX_PENDING_BLOCKING_IO = max(
    0,
    int(os.getenv("BLOCKING_IO_MAX_PENDING", _DEFAULT_MAX_PENDING)),
)
_MAX_PENDING_LONG_IO = max(
    0,
    int(os.getenv("BLOCKING_IO_LONG_MAX_PENDING", _DEFAULT_MAX_PENDING)),
)
_BLOCKING_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("BLOCKING_IO_MAX_WORKERS", _DEFAULT_MAX_WORKERS)),
    thread_name_prefix="blocking-io",
)
_LONG_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("BLOCKING_IO_LONG_MAX_WORKERS", _DEFAULT_LONG_MAX_WORKERS)),
    thread_name_prefix="blocking-io-long",
)
_SHAPE_IO_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("BLOCKING_IO_SHAPE_MAX_WORKERS", _DEFAULT_SHAPE_MAX_WORKERS)),
    thread_name_prefix="blocking-io-shape",
)
_LOOP_LIMITERS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_LOOP_LONG_LIMITERS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_LOOP_SHAPE_LIMITERS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


class _LaneStats:
    """单车道计数（事件循环内更新，无需锁）。"""

    __slots__ = ("name", "in_flight", "completed", "wait_warns", "total_wait_seconds")

    def __init__(self, name: str) -> None:
        self.name = name
        self.in_flight = 0
        self.completed = 0
        self.wait_warns = 0
        self.total_wait_seconds = 0.0

    def snapshot(self) -> dict[str, float | int | str]:
        return {
            "name": self.name,
            "in_flight": self.in_flight,
            "completed": self.completed,
            "wait_warns": self.wait_warns,
            "avg_wait_seconds": round(self.total_wait_seconds / self.completed, 4)
            if self.completed
            else 0.0,
        }


_STATS: dict[str, _LaneStats] = {
    "fast": _LaneStats("fast"),
    "slow": _LaneStats("slow"),
    "shape": _LaneStats("shape"),
}


def blocking_io_stats() -> dict[str, dict[str, float | int | str]]:
    """车道统计快照（in_flight/completed/等待告警数/平均等待），供监控消费。"""
    return {lane: stats.snapshot() for lane, stats in _STATS.items()}


def _ensure_limiter(
    loop: asyncio.AbstractEventLoop,
    limiters: dict[asyncio.AbstractEventLoop, asyncio.Semaphore],
    executor: ThreadPoolExecutor,
    default_workers: int,
    max_pending: int,
) -> asyncio.Semaphore:
    limiter = limiters.get(loop)
    if limiter is not None:
        return limiter
    max_workers = max(1, int(getattr(executor, "_max_workers", default_workers)))
    limiter = asyncio.Semaphore(max_workers + max_pending)
    limiters[loop] = limiter
    return limiter


def _get_submission_limiter(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    """快道（秒级调用）提交限流器。"""
    return _ensure_limiter(
        loop,
        _LOOP_LIMITERS,
        _BLOCKING_IO_EXECUTOR,
        _DEFAULT_MAX_WORKERS,
        _MAX_PENDING_BLOCKING_IO,
    )


def _get_long_submission_limiter(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    """慢道（长持驻调用）提交限流器。"""
    return _ensure_limiter(
        loop,
        _LOOP_LONG_LIMITERS,
        _LONG_IO_EXECUTOR,
        _DEFAULT_LONG_MAX_WORKERS,
        _MAX_PENDING_LONG_IO,
    )


def _get_shape_submission_limiter(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    """形状子池（大但延迟敏感的当前 run 关键序列化）提交限流器。"""
    return _ensure_limiter(
        loop,
        _LOOP_SHAPE_LIMITERS,
        _SHAPE_IO_EXECUTOR,
        _DEFAULT_SHAPE_MAX_WORKERS,
        _MAX_PENDING_LONG_IO,
    )


def _release_limiter(loop: asyncio.AbstractEventLoop, limiter: asyncio.Semaphore) -> None:
    if loop.is_closed():
        return
    loop.call_soon_threadsafe(limiter.release)


async def _run_on_executor(
    lane: str,
    limiter_getter: Callable[[asyncio.AbstractEventLoop], asyncio.Semaphore],
    executor: ThreadPoolExecutor,
    wait_warn_seconds: float,
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    loop = asyncio.get_running_loop()
    limiter = limiter_getter(loop)
    stats = _STATS[lane]
    start_time = loop.time()
    if timeout is not None:
        await asyncio.wait_for(limiter.acquire(), timeout=timeout)
    else:
        await limiter.acquire()
    waited = loop.time() - start_time
    stats.total_wait_seconds += waited
    if waited > wait_warn_seconds:
        stats.wait_warns += 1
        logger.warning(
            "blocking-io lane=%s saturated: waited %.2fs before submission "
            "(in_flight=%d, completed=%d); check lane stats for the hog",
            lane,
            waited,
            stats.in_flight,
            stats.completed,
        )
    stats.in_flight += 1

    call = functools.partial(func, *args, **kwargs)
    try:
        future = executor.submit(call)
    except Exception:
        stats.in_flight -= 1
        limiter.release()
        raise
    future.add_done_callback(lambda _future: _release_limiter(loop, limiter))
    wrapped = asyncio.wrap_future(future)

    try:
        if timeout is not None:
            remaining_timeout = timeout - (loop.time() - start_time)
            if remaining_timeout <= 0:
                raise asyncio.TimeoutError
            result = await asyncio.wait_for(wrapped, timeout=remaining_timeout)
        else:
            result = await wrapped
        stats.completed += 1
        return result
    except asyncio.TimeoutError:
        future.cancel()
        raise
    finally:
        stats.in_flight -= 1


async def run_blocking_io(
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a synchronous IO callable without blocking the current event loop.

    快道带默认超时（``BLOCKING_IO_FAST_DEFAULT_TIMEOUT``，默认 30s）：
    楔死的调用不能永久占用关键线程；确需更长的短调用显式传 timeout。
    """
    effective_timeout = (
        timeout
        if timeout is not None
        else float(os.getenv("BLOCKING_IO_FAST_DEFAULT_TIMEOUT", _FAST_LANE_DEFAULT_TIMEOUT))
    )
    return await _run_on_executor(
        "fast",
        _get_submission_limiter,
        _BLOCKING_IO_EXECUTOR,
        _FAST_WAIT_WARN_SECONDS,
        func,
        *args,
        timeout=effective_timeout,
        **kwargs,
    )


async def run_long_blocking_io(
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    urgent: bool = False,
    **kwargs: Any,
) -> T:
    """长持驻阻塞调用专用车道（沙箱命令、批量传输），与快道分池。

    Args:
        urgent: 「大但延迟敏感」的当前 run 关键操作（工具结果/子代理
            结果/上下文序列化、base64 解码）。走独立形状子池，与慢道
            大传输物理隔离——传输排满也不卡当前对话。
    """
    if urgent:
        return await _run_on_executor(
            "shape",
            _get_shape_submission_limiter,
            _SHAPE_IO_EXECUTOR,
            _SLOW_WAIT_WARN_SECONDS,
            func,
            *args,
            timeout=timeout,
            **kwargs,
        )
    return await _run_on_executor(
        "slow",
        _get_long_submission_limiter,
        _LONG_IO_EXECUTOR,
        _SLOW_WAIT_WARN_SECONDS,
        func,
        *args,
        timeout=timeout,
        **kwargs,
    )


def shutdown_blocking_io_executor() -> None:
    """Release worker threads during process shutdown.

    Do not wait here: shutdown runs on the application stop path and must not
    hang behind a third-party SDK or filesystem call that failed to return.
    """
    _BLOCKING_IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    _LONG_IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
    _SHAPE_IO_EXECUTOR.shutdown(wait=False, cancel_futures=True)
