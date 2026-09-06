"""同步→异步桥接的主循环登记处。

背景（生产事故 2026-09-06，会话 a5fd351a）：本地沙箱的同步文件操作经
``asyncio.run`` 临时建循环执行协程，协程内部使用进程级共享的
``redis.asyncio`` 连接池。redis 连接绑定首次使用它的事件循环，临时循环
复用主循环创建的连接直接 ``RuntimeError: got Future attached to a
different loop``；临时循环关闭后残留的 pending Task 持续污染池，主循环上
的 /api/sandbox/* 端点连锁 500、daemon SSE 通道反复断连。

修复：进程启动时（FastAPI lifespan / arq worker startup）登记主循环，
:func:`run_coro_sync` 一律 ``run_coroutine_threadsafe`` 投递到该循环——
全部 Redis 池使用收敛到同一个循环。未登记（脚本/测试）退回 ``asyncio.run``
维持旧行为。
"""

from __future__ import annotations

import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """登记进程主事件循环（lifespan / worker startup 调用）。"""
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    return _main_loop


def clear_main_loop() -> None:
    global _main_loop
    _main_loop = None


def run_coro_sync(coro: Coroutine[object, object, T]) -> T:
    """在同步上下文中运行协程：优先投递到已登记的主循环。

    - 当前线程已有运行中的循环：报错（要求改用异步 API），与旧行为一致；
    - 已登记主循环且仍在运行：``run_coroutine_threadsafe`` 投递执行——
      共享 Redis 池的全部使用都发生在该循环上，杜绝跨循环污染；
    - 未登记主循环（脚本/测试/未走 lifespan 的进程）：``asyncio.run`` 兜底。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        coro.close()
        raise RuntimeError(
            "LocalSandboxBackend.execute() cannot run inside an active event loop; use aexecute()."
        )
    loop = _main_loop
    if loop is not None and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)
