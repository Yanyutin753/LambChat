"""独立 arq worker 进程入口：启动面 / 信号退出 / embedded 开关绕过。

拆分动机（2026-09-09 生产断联复盘）：ARQ_EMBEDDED_WORKER=true 时 agent 任务
与 API 共享事件循环——重任务饿死 API（SSE/沙箱通道心跳停发），API 滚动发布
杀运行中任务。worker_main 是分进程部署的进程入口，本文件锁定它的启动面契约：
必须带上任务执行依赖的进程内服务（分布式取消监听、缓存一致性 pubsub），
且不带上 API 职责的服务（周期任务双跑会重复执行）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import worker_main


class _FakePubSub:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start_listener(self) -> None:
        self.started += 1

    async def stop_listener(self) -> None:
        self.stopped += 1


class _FakeTaskManager:
    def __init__(self) -> None:
        self.pubsub = _FakePubSub()

    async def start_pubsub_listener(self) -> None:
        self.pubsub.started += 1

    async def stop_pubsub_listener(self) -> None:
        self.pubsub.stopped += 1


class _FakeArqRuntime:
    def __init__(self) -> None:
        self.started_with: dict | None = None
        self.stopped = 0

    async def start(self, **kwargs) -> None:
        self.started_with = kwargs

    async def stop(self) -> None:
        self.stopped += 1


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch):
    """worker_main 全部协作者替换为可观测 fake；返回各 fake 供断言。"""
    task_manager = _FakeTaskManager()
    runtime = _FakeArqRuntime()
    pubsubs = {
        "settings": _FakePubSub(),
        "model_config": _FakePubSub(),
        "tool_cache": _FakePubSub(),
        "mcp_cache": _FakePubSub(),
        "pricing": _FakePubSub(),
        "memory": _FakePubSub(),
    }
    lag_monitor = SimpleNamespace(calls=0)

    async def fake_lag_monitor() -> None:
        lag_monitor.calls += 1

    monkeypatch.setattr(worker_main, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(worker_main, "get_arq_runtime", lambda: runtime)
    monkeypatch.setattr(worker_main, "start_event_loop_lag_monitor", fake_lag_monitor)
    monkeypatch.setattr(worker_main, "get_settings_pubsub", lambda: pubsubs["settings"])
    monkeypatch.setattr(worker_main, "get_model_config_pubsub", lambda: pubsubs["model_config"])
    monkeypatch.setattr(worker_main, "get_tool_cache_pubsub", lambda: pubsubs["tool_cache"])
    monkeypatch.setattr(worker_main, "get_mcp_cache_pubsub", lambda: pubsubs["mcp_cache"])
    monkeypatch.setattr(worker_main, "get_pricing_pubsub", lambda: pubsubs["pricing"])
    monkeypatch.setattr(worker_main, "get_memory_pubsub", lambda: pubsubs["memory"])

    startup_calls: list[str] = []
    shutdown_calls: list[str] = []

    async def fake_worker_startup(ctx: dict) -> None:
        startup_calls.append("worker_startup")

    async def fake_worker_shutdown(ctx: dict) -> None:
        shutdown_calls.append("worker_shutdown")

    async def fake_initialize_settings() -> None:
        return None

    def fake_validate(s) -> None:
        return None

    monkeypatch.setattr(worker_main, "initialize_settings", fake_initialize_settings)
    monkeypatch.setattr(worker_main, "validate_distributed_runtime_settings", fake_validate)
    monkeypatch.setattr(worker_main, "worker_startup", fake_worker_startup)
    monkeypatch.setattr(worker_main, "worker_shutdown", fake_worker_shutdown)

    return SimpleNamespace(
        task_manager=task_manager,
        runtime=runtime,
        pubsubs=pubsubs,
        lag_monitor=lag_monitor,
        startup_calls=startup_calls,
        shutdown_calls=shutdown_calls,
    )


async def test_amain_starts_required_services_with_forced_arq_runtime(wired, monkeypatch):
    """启动面契约：循环监控、取消监听、缓存一致性 pubsub、force 启动的 arq。"""
    monkeypatch.setattr(worker_main.settings, "ENABLE_MEMORY", True)

    async def release_stop(stop: asyncio.Event) -> None:
        await asyncio.sleep(0.01)
        stop.set()

    stop = asyncio.Event()
    done = asyncio.create_task(release_stop(stop))
    await worker_main._amain(stop)
    await done

    assert wired.lag_monitor.calls == 1
    assert wired.task_manager.pubsub.started == 1  # 分布式取消信号必须到达执行方
    for name in ("settings", "model_config", "tool_cache", "mcp_cache", "pricing", "memory"):
        assert wired.pubsubs[name].started == 1, name
    # force=True：绕过 ARQ_EMBEDDED_WORKER（该开关只约束 API 进程）
    assert wired.runtime.started_with == {"force": True}
    assert wired.startup_calls == ["worker_startup"]  # 分布式校验 + loop_bridge 登记


async def test_amain_loads_db_settings_before_any_service(wired, monkeypatch):
    """设置契约（2026-09-09 生产 P0）：worker 必须先 initialize_settings 再起服务。

    worker 只跑 pydantic 默认值时与 API 的 DB 生效值分叉：生产开了
    SESSION_EVENT_CHUNK_STORAGE_ENABLED，API 写 chunk、worker 走 legacy 内联，
    事件被 chunk 视图的 merge 覆写蒸发（刷新即丢历史）；SANDBOX_PLATFORM
    同理回落默认，本地 daemon 身份段（#499）不再注入。分布式校验随设置
    加载之后执行，对齐 API lifespan（main.py initialize_settings →
    validate_distributed_runtime_settings）。
    """
    order: list[str] = []

    async def fake_initialize_settings() -> None:
        order.append("initialize_settings")

    def fake_validate(s) -> None:
        order.append("validate")

    async def fake_lag_monitor() -> None:
        order.append("lag_monitor")

    monkeypatch.setattr(worker_main, "initialize_settings", fake_initialize_settings)
    monkeypatch.setattr(worker_main, "validate_distributed_runtime_settings", fake_validate)
    monkeypatch.setattr(worker_main, "start_event_loop_lag_monitor", fake_lag_monitor)

    async def release_stop(stop: asyncio.Event) -> None:
        await asyncio.sleep(0.01)
        stop.set()

    stop = asyncio.Event()
    done = asyncio.create_task(release_stop(stop))
    await worker_main._amain(stop)
    await done

    assert order[:2] == ["initialize_settings", "validate"]
    assert order.index("initialize_settings") < order.index("lag_monitor")
    assert wired.runtime.started_with == {"force": True}


async def test_amain_settings_init_failure_stops_startup(wired, monkeypatch):
    """设置加载失败必须快速失败（k8s CrashLoopBackOff 显性暴露），绝不带
    默认值继续起 worker 吞事件。"""

    async def failing_initialize() -> None:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(worker_main, "initialize_settings", failing_initialize)

    stop = asyncio.Event()
    with pytest.raises(RuntimeError):
        await worker_main._amain(stop)

    assert wired.runtime.started_with is None  # 未起 worker
    assert wired.startup_calls == []


async def test_amain_shutdown_stops_listeners_and_runtime_in_order(wired, monkeypatch):
    """退出面契约：先停 worker（等任务收尾），再停监听，最后 worker_shutdown。"""
    monkeypatch.setattr(worker_main.settings, "ENABLE_MEMORY", False)
    order: list[str] = []

    real_stop = wired.runtime.stop

    async def recording_runtime_stop() -> None:
        order.append("runtime_stop")
        await real_stop()

    wired.runtime.stop = recording_runtime_stop

    async def release_stop(stop: asyncio.Event) -> None:
        await asyncio.sleep(0.01)
        stop.set()

    stop = asyncio.Event()
    done = asyncio.create_task(release_stop(stop))
    await worker_main._amain(stop)
    await done

    assert order == ["runtime_stop"]
    assert wired.runtime.stopped == 1
    assert wired.task_manager.pubsub.stopped == 1
    assert wired.shutdown_calls == ["worker_shutdown"]  # 生命周期收尾（loop/恢复静默）


async def test_amain_skips_memory_pubsub_when_disabled(wired, monkeypatch):
    monkeypatch.setattr(worker_main.settings, "ENABLE_MEMORY", False)

    async def release_stop(stop: asyncio.Event) -> None:
        await asyncio.sleep(0.01)
        stop.set()

    stop = asyncio.Event()
    done = asyncio.create_task(release_stop(stop))
    await worker_main._amain(stop)
    await done

    assert wired.pubsubs["memory"].started == 0
    for name in ("settings", "model_config", "tool_cache", "mcp_cache", "pricing"):
        assert wired.pubsubs[name].started == 1, name


async def test_amain_stops_even_when_services_fail_to_start(wired, monkeypatch):
    """某个监听器启动失败也要走完退出面（不留半启动进程），异常原样上抛。"""
    monkeypatch.setattr(worker_main.settings, "ENABLE_MEMORY", False)

    async def broken_start() -> None:
        raise RuntimeError("redis down")

    wired.pubsubs["pricing"].start_listener = broken_start  # type: ignore[method-assign]

    stop = asyncio.Event()
    with pytest.raises(RuntimeError, match="redis down"):
        await worker_main._amain(stop)

    assert wired.runtime.stopped == 1  # 未启动过也要安全调用停止
    assert wired.task_manager.pubsub.stopped == 1


def test_signal_handler_sets_stop_event():
    """SIGTERM/SIGINT 的处理器只做一件事：置停止事件（退出面统一收尾）。"""
    stop = asyncio.Event()
    handler = worker_main._make_signal_handler(stop)
    assert not stop.is_set()
    handler()
    assert stop.is_set()
