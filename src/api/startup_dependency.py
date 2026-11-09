"""启动期依赖退避重试（#1212）。

宿主机重启后 a/b Pod 可能早于 Docker/Mongo 就绪：此前 lifespan 的首个
Mongo 步骤抛 ServerSelectionTimeoutError → 进程退出 → CrashLoopBackOff
2-3 分钟。这里在窗口内进程内指数退避等待依赖恢复，Pod 保持 NotReady
而非 CrashLoop；独立成模块同时遵守仓库 src/*.py ≤1000 行门禁。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)

_RETRY_WINDOW_SECONDS = 300.0
_RETRY_BASE_DELAY_SECONDS = 2.0
_RETRY_MAX_DELAY_SECONDS = 15.0


async def run_startup_step_with_retry(
    step_name: str,
    step: Callable[[], Awaitable[Any]],
    *,
    retry_window_seconds: float = _RETRY_WINDOW_SECONDS,
) -> Any:
    """运行一个启动步骤，依赖未就绪时退避重试。

    仅重试 pymongo 连接类异常（AutoReconnect/ConnectionFailure/
    ServerSelectionTimeoutError），配置/数据错误立即上抛保持原行为；
    窗口（默认 5 分钟）耗尽后按原行为退出，交给 k8s 重启兜底。
    """
    from pymongo.errors import AutoReconnect, ConnectionFailure, ServerSelectionTimeoutError

    deadline = time.monotonic() + retry_window_seconds
    delay = _RETRY_BASE_DELAY_SECONDS
    attempt = 1
    while True:
        try:
            return await step()
        except (AutoReconnect, ConnectionFailure, ServerSelectionTimeoutError) as exc:
            if time.monotonic() + delay >= deadline:
                raise
            logger.warning(
                "[Startup] %s waiting for dependencies (attempt %d: %s); retry in %.1fs",
                step_name,
                attempt,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            attempt += 1
            delay = min(delay * 2, _RETRY_MAX_DELAY_SECONDS)
