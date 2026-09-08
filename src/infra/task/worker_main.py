"""独立 arq worker 进程入口：与 API 分进程部署（k8s worker Deployment）。

为什么拆分（2026-09-09 生产断联复盘）：``ARQ_EMBEDDED_WORKER=true`` 时 agent
任务与 API 共享事件循环——重任务的同步段会饿死 API（SSE/沙箱通道心跳停发），
且 API 滚动发布会杀掉运行中的任务。拆分后 API 进程只服务 HTTP/SSE，任务全部
由本进程消费；队列在 Redis，两拨进程天然协同，任一侧独立伸缩/发布互不牵连。

启动面（任务执行在独立进程里依赖的进程内服务，对齐 API lifespan 的最小集）：

- **initialize_settings（首要）**：从数据库加载生效设置（DB > env > 默认），
  再做分布式配置校验——与 API 进程看到同一份设置。缺了这一步 worker 只跑
  pydantic 默认值，与 API 的 DB 生效值分叉：生产开
  SESSION_EVENT_CHUNK_STORAGE_ENABLED 时 API 写 chunk、worker 走 legacy 内联，
  事件被 chunk 视图的 merge 覆写蒸发（2026-09-09 生产 P0，刷新即丢历史）；
  SANDBOX_PLATFORM 同理回落默认，本地 daemon 身份段（#499）不再注入；
- 事件循环滞后监控：观测「重任务饿死循环」的眼睛；
- task_manager pubsub 监听：分布式取消信号必须到达**执行方**，不启动则用户
  取消不了跑在本进程上的任务；
- 缓存一致性 pubsub（settings/模型配置/工具/MCP/定价/记忆）：热更新传播到
  本进程，否则 worker 里的模型配置等要等重启才刷新；
- arq runtime（``force=True`` 越过 ``ARQ_EMBEDDED_WORKER``——该开关只管 API
  进程）+ worker_startup（分布式配置校验、loop_bridge 登记——本地沙箱同步
  文件操作的协程桥接依赖它）。

**不**启动：内存周期 agent、定时任务 reconcile、websocket/channel 推送——
这些是 API 进程的职责，双跑会重复执行周期任务。

入口：``python -m src.infra.task.worker_main``（容器 command）；SIGTERM/SIGINT
置停止事件 → 先停 arq worker（收尾在途任务）→ 停监听 → worker_shutdown。
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import Any, Callable

# 协作者在模块级具名：测试按 monkeypatch worker_main.<name> 注入替身。
from src.infra.distributed_validation import validate_distributed_runtime_settings  # noqa: E402
from src.infra.llm.pubsub import get_model_config_pubsub  # noqa: E402
from src.infra.logging import get_logger
from src.infra.monitoring.event_loop import start_event_loop_lag_monitor
from src.infra.pricing.pubsub import get_pricing_pubsub  # noqa: E402
from src.infra.settings.pubsub import get_settings_pubsub  # noqa: E402
from src.infra.tool.cache_pubsub import get_tool_cache_pubsub  # noqa: E402
from src.infra.tool.mcp_global import get_mcp_cache_pubsub  # noqa: E402
from src.kernel.config import initialize_settings, settings

from .arq_runtime import get_arq_runtime
from .arq_worker import worker_shutdown, worker_startup
from .manager import get_task_manager

logger = get_logger(__name__)


def get_memory_pubsub() -> Any:
    """记忆 pubsub 惰性解析（ENABLE_MEMORY 才需要，模块级导入会拖重依赖）。"""
    from src.infra.memory.distributed import get_memory_pubsub as _get

    return _get()


# 已启动监听器引用：失败路径 shutdown 时逐一尽停
_started_listeners: list[tuple[str, Any]] = []


def _make_signal_handler(stop: asyncio.Event) -> Callable[[], None]:
    """SIGTERM/SIGINT → 置停止事件；退出收尾统一在 _amain 的 finally 完成。"""

    def _handle() -> None:
        logger.info("worker_main received stop signal")
        stop.set()

    return _handle


async def _start_cache_listeners() -> None:
    """缓存一致性 pubsub：settings/模型/工具/MCP/定价（+记忆开关）。"""
    listeners: list[tuple[str, Any]] = [
        ("settings", get_settings_pubsub()),
        ("model_config", get_model_config_pubsub()),
        ("tool_cache", get_tool_cache_pubsub()),
        ("mcp_cache", get_mcp_cache_pubsub()),
        ("pricing", get_pricing_pubsub()),
    ]
    if settings.ENABLE_MEMORY:
        listeners.append(("memory", get_memory_pubsub()))
    _started_listeners.extend(listeners)
    await asyncio.gather(*(pubsub.start_listener() for _, pubsub in listeners))


async def _stop_started_listeners() -> None:
    for name, pubsub in _started_listeners:
        stop = getattr(pubsub, "stop_listener", None)
        if stop is None:
            continue
        try:
            result = stop()
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001 - 单个监听器停止失败不阻断其余
            logger.warning("Failed to stop %s listener", name, exc_info=True)
    _started_listeners.clear()


async def _amain(stop: asyncio.Event) -> None:
    """worker 进程主协程：startup → 等 stop → shutdown（失败也要走完退出面）。"""
    task_manager = get_task_manager()
    runtime = get_arq_runtime()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        # 无信号实现的循环（如 Windows Proactor）抛 NotImplementedError，降级忽略
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _make_signal_handler(stop))

    logger.info("standalone arq worker starting (queue=%s)", settings.ARQ_QUEUE_NAME)
    try:
        # 设置加载必须先于一切服务启动（对齐 API lifespan）：worker 与 API
        # 看到同一份 DB > env > 默认的生效设置。失败快速退出（k8s
        # CrashLoopBackOff 显性暴露），绝不带默认值吞事件。
        await initialize_settings()
        logger.info("Settings initialized from database")
        validate_distributed_runtime_settings(settings)
        await start_event_loop_lag_monitor()
        await task_manager.start_pubsub_listener()
        await _start_cache_listeners()
        await worker_startup({})  # 分布式配置校验 + loop_bridge 登记
        await runtime.start(force=True)
        logger.info("standalone arq worker started")
        await stop.wait()
    finally:
        # 先停 worker（收尾在途任务），再停监听，最后生命周期标记
        try:
            await runtime.stop()
        except Exception:  # noqa: BLE101 - 退出路径尽力而为
            logger.warning("arq runtime stop failed", exc_info=True)
        try:
            await task_manager.stop_pubsub_listener()
        except Exception:  # noqa: BLE101
            logger.warning("task pubsub stop failed", exc_info=True)
        await _stop_started_listeners()
        try:
            await worker_shutdown({})  # loop_bridge 清理 + 恢复入口静默
        except Exception:  # noqa: BLE101
            logger.warning("worker_shutdown failed", exc_info=True)
        logger.info("standalone arq worker stopped")


def main() -> None:
    # API 进程由 lifespan 调 setup_logging；独立进程必须自己配，否则 INFO
    # 及以下日志无 handler 直接吞掉（首验实测：进程正常跑但日志全空）。
    from src.infra.logging import setup_logging

    setup_logging()
    asyncio.run(_amain(asyncio.Event()))


if __name__ == "__main__":
    main()
