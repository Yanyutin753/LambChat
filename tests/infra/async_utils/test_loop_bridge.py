"""loop_bridge：同步桥接统一投递到注册的主事件循环。

背景（生产事故 2026-09-06）：LocalSandboxBackend 的同步文件操作经
``_run_coro_sync`` 用 ``asyncio.run`` 临时建循环执行协程，而协程内部使用
进程级共享的 ``redis.asyncio`` 连接池——连接绑定首次使用它的循环，跨循环
复用直接 ``RuntimeError: got Future attached to a different loop``，且循环
关闭后残留的 pending Task 污染连接池，后续主循环上的 /api/sandbox/* 全部
500、daemon SSE 通道反复断连（read_file 报 daemon offline 的连锁根源）。

修复语义：注册主循环后，同步桥接一律 ``run_coroutine_threadsafe`` 投递到
该循环执行——全部 Redis 池使用收敛到同一个循环。
"""

import asyncio
import threading

import pytest

from src.infra.async_utils.loop_bridge import (
    clear_main_loop,
    get_main_loop,
    run_coro_sync,
    set_main_loop,
)


def test_get_main_loop_initially_none():
    clear_main_loop()
    assert get_main_loop() is None


def test_set_and_clear_main_loop():
    loop = asyncio.new_event_loop()
    try:
        set_main_loop(loop)
        assert get_main_loop() is loop
        clear_main_loop()
        assert get_main_loop() is None
    finally:
        loop.close()


def test_run_coro_sync_runs_on_registered_main_loop():
    """工作线程内同步桥接：协程在注册的主循环上执行（而非临时 asyncio.run 循环）。"""
    main_loop = asyncio.new_event_loop()
    set_main_loop(main_loop)
    try:
        thread = threading.Thread(target=main_loop.run_forever, daemon=True)
        thread.start()

        async def probe() -> object:
            return asyncio.get_running_loop()

        result: dict[str, object] = {}

        def run_sync() -> None:
            result["loop"] = run_coro_sync(probe())

        worker = threading.Thread(target=run_sync)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "sync bridge did not return"
        assert result["loop"] is main_loop
    finally:
        main_loop.call_soon_threadsafe(main_loop.stop)
        thread.join(timeout=10)
        clear_main_loop()
        main_loop.close()


def test_run_coro_sync_without_registered_loop_falls_back_to_asyncio_run():
    clear_main_loop()

    async def value() -> int:
        await asyncio.sleep(0)
        return 42

    assert run_coro_sync(value()) == 42


def test_run_coro_sync_inside_running_loop_still_rejected():
    """活动循环内同步调用必须报错（要求改用异步 API），语义与旧实现一致。"""

    async def value() -> int:
        return 1

    async def attempt() -> object:
        try:
            run_coro_sync(value())
        except RuntimeError as exc:
            return exc
        return None

    clear_main_loop()
    exc = asyncio.run(attempt())
    assert isinstance(exc, RuntimeError)
    assert "cannot run inside an active event loop" in str(exc)


def test_run_coro_sync_propagates_exception_from_main_loop():
    main_loop = asyncio.new_event_loop()
    set_main_loop(main_loop)
    try:
        thread = threading.Thread(target=main_loop.run_forever, daemon=True)
        thread.start()

        async def boom() -> None:
            raise ValueError("relay failure")

        with pytest.raises(ValueError, match="relay failure"):
            run_coro_sync(boom())
    finally:
        main_loop.call_soon_threadsafe(main_loop.stop)
        thread.join(timeout=10)
        clear_main_loop()
        main_loop.close()
