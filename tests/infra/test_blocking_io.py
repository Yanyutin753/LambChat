from __future__ import annotations

import asyncio
import threading

import pytest

from src.infra.async_utils.blocking import run_blocking_io


def test_blocking_io_default_worker_count_is_bounded_for_api_process_memory() -> None:
    import src.infra.async_utils.blocking as blocking

    assert blocking._DEFAULT_MAX_WORKERS == 8


@pytest.mark.asyncio
async def test_run_blocking_io_runs_callable_away_from_event_loop_thread() -> None:
    loop_thread = threading.get_ident()

    def blocking_call(value: str, *, suffix: str) -> tuple[str, int]:
        return f"{value}{suffix}", threading.get_ident()

    result, worker_thread = await run_blocking_io(blocking_call, "ok", suffix="-done")

    assert result == "ok-done"
    assert worker_thread != loop_thread


@pytest.mark.asyncio
async def test_run_blocking_io_applies_timeout() -> None:
    def slow_call() -> None:
        import time

        time.sleep(0.2)

    with pytest.raises(asyncio.TimeoutError):
        await run_blocking_io(slow_call, timeout=0.01)


@pytest.mark.asyncio
async def test_run_blocking_io_keeps_slot_until_timed_out_call_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import src.infra.async_utils.blocking as blocking

    class _RecordingExecutor(ThreadPoolExecutor):
        def __init__(self) -> None:
            super().__init__(max_workers=1, thread_name_prefix="test-blocking-io")
            self.submitted_names: list[str] = []

        def submit(self, fn, /, *args, **kwargs):
            # 层层包装（车道标记→contextvars）：经显式标记属性解包真实目标
            target = getattr(fn, "__lambchat_target__", fn)
            self.submitted_names.append(
                getattr(getattr(target, "func", target), "__name__", "unknown")
            )
            return super().submit(fn, *args, **kwargs)

    executor = _RecordingExecutor()
    monkeypatch.setattr(blocking, "_BLOCKING_IO_EXECUTOR", executor)

    def slow_call() -> None:
        import time

        time.sleep(0.1)

    with pytest.raises(asyncio.TimeoutError):
        await blocking.run_blocking_io(slow_call, timeout=0.01)

    with pytest.raises(asyncio.TimeoutError):
        await blocking.run_blocking_io(lambda: "second", timeout=0.02)

    await asyncio.sleep(0.12)

    assert await blocking.run_blocking_io(lambda: "released", timeout=0.05) == "released"
    executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_run_blocking_io_applies_pending_submission_backpressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import src.infra.async_utils.blocking as blocking

    class _RecordingExecutor(ThreadPoolExecutor):
        def __init__(self) -> None:
            super().__init__(max_workers=1, thread_name_prefix="test-blocking-io")
            self.submitted_names: list[str] = []

        def submit(self, fn, /, *args, **kwargs):
            # 层层包装（车道标记→contextvars）：经显式标记属性解包真实目标
            target = getattr(fn, "__lambchat_target__", fn)
            self.submitted_names.append(
                getattr(getattr(target, "func", target), "__name__", "unknown")
            )
            return super().submit(fn, *args, **kwargs)

    executor = _RecordingExecutor()
    monkeypatch.setattr(blocking, "_BLOCKING_IO_EXECUTOR", executor)
    monkeypatch.setattr(blocking, "_MAX_PENDING_BLOCKING_IO", 1)
    monkeypatch.setattr(blocking, "_LOOP_LIMITERS", {})

    started = threading.Event()
    release = threading.Event()
    submitted: list[str] = []

    def slow_call() -> str:
        submitted.append("slow")
        started.set()
        release.wait(timeout=1)
        return "slow"

    def queued_call() -> str:
        submitted.append("queued")
        return "queued"

    def backpressured_call() -> str:
        submitted.append("backpressured")
        return "backpressured"

    slow_task = asyncio.create_task(blocking.run_blocking_io(slow_call))
    await asyncio.to_thread(started.wait, 1)

    queued_task = asyncio.create_task(blocking.run_blocking_io(queued_call))
    await asyncio.sleep(0.02)

    backpressured_task = asyncio.create_task(blocking.run_blocking_io(backpressured_call))
    await asyncio.sleep(0.02)

    try:
        assert executor.submitted_names == ["slow_call", "queued_call"]
        assert submitted == ["slow"]
        assert backpressured_task.done() is False

        release.set()
        assert await slow_task == "slow"
        assert await queued_task == "queued"
        assert await backpressured_task == "backpressured"
        assert executor.submitted_names == [
            "slow_call",
            "queued_call",
            "backpressured_call",
        ]
    finally:
        release.set()
        for task in (slow_task, queued_task, backpressured_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(slow_task, queued_task, backpressured_task, return_exceptions=True)
        executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_run_blocking_io_timeout_covers_pending_backpressure_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import src.infra.async_utils.blocking as blocking

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-blocking-io")
    monkeypatch.setattr(blocking, "_BLOCKING_IO_EXECUTOR", executor)
    monkeypatch.setattr(blocking, "_MAX_PENDING_BLOCKING_IO", 0)
    monkeypatch.setattr(blocking, "_LOOP_LIMITERS", {})

    started = threading.Event()
    release = threading.Event()
    submitted: list[str] = []

    def slow_call() -> str:
        submitted.append("slow")
        started.set()
        release.wait(timeout=1)
        return "slow"

    def should_not_submit() -> str:
        submitted.append("blocked")
        return "blocked"

    slow_task = asyncio.create_task(blocking.run_blocking_io(slow_call))
    await asyncio.to_thread(started.wait, 1)

    try:
        with pytest.raises(asyncio.TimeoutError):
            await blocking.run_blocking_io(should_not_submit, timeout=0.01)
        assert submitted == ["slow"]
    finally:
        release.set()
        assert await slow_task == "slow"
        executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_run_blocking_io_still_completes_after_settings_import() -> None:
    from src.kernel.config import settings

    assert settings is not None

    result = await run_blocking_io(lambda: "ok", timeout=1.0)

    assert result == "ok"


async def test_long_lane_executes_and_returns_value() -> None:
    from src.infra.async_utils.blocking import run_long_blocking_io

    assert await run_long_blocking_io(lambda a, b: a + b, 1, 2) == 3


async def test_long_lane_is_isolated_from_fast_lane_saturation() -> None:
    """快道线程全部占住时：秒级调用排队超时，长命令车道照常执行。"""

    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import run_long_blocking_io

    loop = asyncio.get_running_loop()
    limiter = blocking_mod._get_submission_limiter(loop)
    workers = max(1, int(getattr(blocking_mod._BLOCKING_IO_EXECUTOR, "_max_workers", 8)))
    release = threading.Event()

    def _hold() -> None:
        release.wait(5)

    futures = [blocking_mod._BLOCKING_IO_EXECUTOR.submit(_hold) for _ in range(workers)]
    for _ in range(workers):
        await limiter.acquire()

    try:
        with pytest.raises(asyncio.TimeoutError):
            await blocking_mod.run_blocking_io(lambda: "fast", timeout=0.05)
        assert await run_long_blocking_io(lambda: "long-lane-ok", timeout=5) == "long-lane-ok"
    finally:
        release.set()
        for future in futures:
            future.result()
        for _ in range(workers):
            limiter.release()


async def test_e2b_aexecute_routes_to_long_lane(monkeypatch) -> None:
    """沙箱命令派发走慢道：长命令不占快道线程。"""
    from types import SimpleNamespace

    import src.infra.backend.e2b as e2b_mod
    from src.infra.backend.e2b import E2BBackend

    routed: list[str] = []

    async def fake_long_run(func, *args, timeout=None, **kwargs):
        routed.append("long")
        return func(*args, **kwargs)

    monkeypatch.setattr(e2b_mod, "run_long_blocking_io", fake_long_run, raising=False)
    import src.infra.backend.e2b_async as e2b_async_mod

    monkeypatch.setattr(e2b_async_mod, "run_long_blocking_io", fake_long_run)

    sandbox = SimpleNamespace(
        sandbox_id="lane-test",
        commands=SimpleNamespace(
            run=lambda **kw: SimpleNamespace(stdout="ok\n", stderr="", exit_code=0)
        ),
        files=SimpleNamespace(),
    )
    sandbox.set_timeout = lambda t: None  # type: ignore[method-assign]
    backend = E2BBackend(sandbox=sandbox, timeout=300)
    backend.supports_async_sdk = False  # 线程路径（Cube 同款）验证慢道路由

    result = await backend.aexecute("echo hi")

    assert routed == ["long"]
    assert result.exit_code == 0


async def test_fast_lane_applies_default_timeout_to_wedged_calls() -> None:
    """快道默认超时：楔死的调用不能永久占用关键线程。"""
    import threading

    from src.infra.async_utils import blocking as blocking_mod

    release = threading.Event()

    def _wedged() -> str:
        release.wait(30)
        return "never"

    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                blocking_mod.run_blocking_io(
                    _wedged, timeout=blocking_mod._FAST_LANE_DEFAULT_TIMEOUT
                ),
                timeout=blocking_mod._FAST_LANE_DEFAULT_TIMEOUT + 5,
            )
    finally:
        release.set()


async def test_urgent_ops_use_isolated_shape_pool() -> None:
    """urgent 慢道操作走独立形状子池：慢道被传输占满时照常执行。"""

    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import run_long_blocking_io

    workers = max(
        1,
        int(getattr(blocking_mod._LONG_IO_EXECUTOR, "_max_workers", 64)),
    )
    release = threading.Event()

    def _hold() -> str:
        release.wait(10)
        return "held"

    # 占满整个慢道
    holders = [asyncio.create_task(run_long_blocking_io(_hold)) for _ in range(workers)]
    await asyncio.sleep(0.3)

    try:
        # urgent 操作（工具结果序列化类）必须在形状子池立即完成
        result = await asyncio.wait_for(
            run_long_blocking_io(lambda a, b: a + b, 1, 2, urgent=True, timeout=5),
            timeout=5,
        )
        assert result == 3
    finally:
        release.set()
        await asyncio.gather(*holders, return_exceptions=True)


async def test_lane_stats_counters_update() -> None:
    """车道统计：in_flight/completed 计数随调用更新，可被监控消费。"""
    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import blocking_io_stats, run_long_blocking_io

    before = blocking_io_stats()
    await blocking_mod.run_blocking_io(lambda: "x")
    await run_long_blocking_io(lambda: "y")
    after = blocking_io_stats()

    assert after["fast"]["completed"] >= before["fast"]["completed"] + 1
    assert after["slow"]["completed"] >= before["slow"]["completed"] + 1
    assert after["fast"]["in_flight"] == 0
    assert after["slow"]["in_flight"] == 0


async def test_all_lanes_propagate_contextvars() -> None:
    """contextvars 必须传播进卸载线程（anyio to_thread 同款行为）。

    被卸载函数读 TraceContext/请求上下文时不能静默拿到空值。
    """
    import contextvars

    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import run_long_blocking_io

    var = contextvars.ContextVar("lane_probe")

    def _read() -> str:
        return var.get("MISSING")

    var.set("from-loop")
    fast_result = await blocking_mod.run_blocking_io(_read)
    slow_result = await run_long_blocking_io(_read)
    shape_result = await run_long_blocking_io(_read, urgent=True)

    assert fast_result == "from-loop"
    assert slow_result == "from-loop"
    assert shape_result == "from-loop"


def test_loop_limiter_registrations_do_not_leak_closed_loops() -> None:
    """车道限流器注册表用弱引用：已关闭的事件循环不被强引用滞留。

    测试与内嵌场景常有大量短命 loop，强引用会让 loop+semaphore 永不
    回收（anyio 用 ContextVar 挂载规避，我们用 WeakKeyDictionary）。
    """
    import gc
    import weakref

    from src.infra.async_utils import blocking as blocking_mod

    async def _touch() -> None:
        await blocking_mod.run_blocking_io(lambda: 1)
        await blocking_mod.run_long_blocking_io(lambda: 2)

    loops: list[weakref.ref] = []

    async def _touch_and_capture() -> None:
        await blocking_mod.run_blocking_io(lambda: 1)
        await blocking_mod.run_long_blocking_io(lambda: 2)
        loops.append(weakref.ref(asyncio.get_running_loop()))

    for _ in range(10):
        asyncio.run(_touch_and_capture())
    del _touch
    gc.collect()
    assert not any(ref() is not None for ref in loops), (
        "用过车道的 loop 关闭后必须可回收（注册表不得强引用）"
    )


async def test_same_lane_reentrancy_executes_inline_with_warning(monkeypatch, caplog) -> None:
    """同车道重入自死锁防护（asgiref deadlock_context 同思路）。

    被卸载代码经 loop_bridge/asyncio.run 回调同车道时，若仍走提交
    路径，车道线程池被外层占满即自死锁。重入必须直接内联执行并告警。
    """
    import logging

    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import run_long_blocking_io

    submitted: list[str] = []
    original_submit = blocking_mod._LONG_IO_EXECUTOR.submit

    def _recording_submit(fn, /, *args, **kwargs):
        submitted.append("slow")
        return original_submit(fn, *args, **kwargs)

    monkeypatch.setattr(blocking_mod._LONG_IO_EXECUTOR, "submit", _recording_submit)

    # 模拟：当前线程已在慢道内（外层调用占住车道线程后经嵌套 loop 回调）
    blocking_mod._lane_thread_local.current_lane = "slow"
    try:
        with caplog.at_level(logging.WARNING, logger="src.infra.async_utils.blocking"):
            result = await run_long_blocking_io(lambda: "inline-ok")
    finally:
        blocking_mod._lane_thread_local.current_lane = None

    assert result == "inline-ok"
    assert submitted == []  # 未提交线程池——内联执行
    assert any("re-entrant" in r.message.lower() or "重入" in r.message for r in caplog.records)


async def test_cross_lane_reentrancy_still_submits() -> None:
    """跨车道调用不受重入防护影响（快道内调慢道是合法的）。"""
    from src.infra.async_utils import blocking as blocking_mod
    from src.infra.async_utils.blocking import run_long_blocking_io

    submitted: list[str] = []
    original_submit = blocking_mod._LONG_IO_EXECUTOR.submit

    def _recording_submit(fn, /, *args, **kwargs):
        submitted.append("slow")
        return original_submit(fn, *args, **kwargs)

    monkeypatch_local = blocking_mod._lane_thread_local
    monkeypatch_local.current_lane = "fast"
    monkeypatch_exec = blocking_mod._LONG_IO_EXECUTOR
    orig = monkeypatch_exec.submit
    monkeypatch_exec.submit = _recording_submit
    try:
        result = await run_long_blocking_io(lambda: "submitted-ok")
    finally:
        monkeypatch_exec.submit = orig
        monkeypatch_local.current_lane = None

    assert result == "submitted-ok"
    assert submitted == ["slow"]
