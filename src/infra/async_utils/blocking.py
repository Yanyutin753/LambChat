"""Controlled offloading for unavoidable synchronous IO.

Use this helper for third-party SDK calls and filesystem work that do not have
native async APIs. It keeps those calls off the FastAPI event loop and avoids
unbounded growth of the default executor.

两条车道（分池）：
- run_blocking_io：秒级快道（生命周期调用：续期/connect/pause/小文件等），
  小池保证低延迟；
- run_long_blocking_io：长持驻慢道（沙箱命令执行、批量文件传输），独立
  大池——长命令占满慢道时不拖累快道，其他沙箱的续租不会被饿死。
"""

from __future__ import annotations

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_DEFAULT_MAX_WORKERS = 8
_DEFAULT_LONG_MAX_WORKERS = 64
_DEFAULT_MAX_PENDING = 16
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
_LOOP_LIMITERS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_LOOP_LONG_LIMITERS: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


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


def _release_limiter(loop: asyncio.AbstractEventLoop, limiter: asyncio.Semaphore) -> None:
    if loop.is_closed():
        return
    loop.call_soon_threadsafe(limiter.release)


async def _run_on_executor(
    limiter_getter: Callable[[asyncio.AbstractEventLoop], asyncio.Semaphore],
    executor: ThreadPoolExecutor,
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    loop = asyncio.get_running_loop()
    limiter = limiter_getter(loop)
    start_time = loop.time()
    if timeout is not None:
        await asyncio.wait_for(limiter.acquire(), timeout=timeout)
    else:
        await limiter.acquire()

    call = functools.partial(func, *args, **kwargs)
    try:
        future = executor.submit(call)
    except Exception:
        limiter.release()
        raise
    future.add_done_callback(lambda _future: _release_limiter(loop, limiter))
    wrapped = asyncio.wrap_future(future)

    try:
        if timeout is not None:
            remaining_timeout = timeout - (loop.time() - start_time)
            if remaining_timeout <= 0:
                raise asyncio.TimeoutError
            return await asyncio.wait_for(wrapped, timeout=remaining_timeout)
        return await wrapped
    except asyncio.TimeoutError:
        future.cancel()
        raise


async def run_blocking_io(
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a synchronous IO callable without blocking the current event loop."""
    return await _run_on_executor(
        _get_submission_limiter,
        _BLOCKING_IO_EXECUTOR,
        func,
        *args,
        timeout=timeout,
        **kwargs,
    )


async def run_long_blocking_io(
    func: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """长持驻阻塞调用专用车道（沙箱命令、批量传输），与快道分池。"""
    return await _run_on_executor(
        _get_long_submission_limiter,
        _LONG_IO_EXECUTOR,
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
