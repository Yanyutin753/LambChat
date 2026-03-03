"""
Backend 工具函数

从 ToolRuntime 获取 Backend 的共享工具函数。
用于支持分布式环境下的安全 backend 访问。
"""

import logging
from typing import Any, Optional

from deepagents.backends.protocol import BackendProtocol

logger = logging.getLogger(__name__)


def get_backend_from_runtime(runtime: Any) -> Optional[BackendProtocol]:
    """从 ToolRuntime 获取 backend（分布式安全）

    Backend 通过 runtime.config["configurable"]["backend"] 传递
    注意：config 中存的是 backend_factory（函数），需要调用 factory(runtime) 获取实例
    """
    if runtime is None:
        return None

    try:
        # 方式1: 从 runtime.config["configurable"]["backend"] 获取（主要方式）
        if hasattr(runtime, "config") and runtime.config:
            config = runtime.config
            # 检查 configurable 字典
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                if isinstance(configurable, dict):
                    backend_or_factory = configurable.get("backend")
                    if backend_or_factory is not None:
                        # 如果是工厂函数，调用它获取 backend 实例
                        if callable(backend_or_factory):
                            logger.debug("Calling backend_factory to get backend instance")
                            return backend_or_factory(runtime)
                        else:
                            logger.debug(
                                "Got backend instance from runtime.config['configurable']['backend']"
                            )
                            return backend_or_factory
                # 也检查直接的 backend 键
                backend_or_factory = config.get("backend")
                if backend_or_factory is not None:
                    if callable(backend_or_factory):
                        logger.debug("Calling backend_factory from config['backend']")
                        return backend_or_factory(runtime)
                    else:
                        return backend_or_factory

        # 方式2: 从 runtime 的 attributes 中获取
        if hasattr(runtime, "attributes"):
            backend_or_factory = runtime.attributes.get("backend")
            if backend_or_factory is not None:
                if callable(backend_or_factory):
                    logger.debug("Calling backend_factory from attributes")
                    return backend_or_factory(runtime)
                else:
                    return backend_or_factory

        # 方式3: 从 configurable 属性获取
        if hasattr(runtime, "configurable"):
            configurable = runtime.configurable
            if isinstance(configurable, dict):
                backend_or_factory = configurable.get("backend")
                if backend_or_factory is not None:
                    if callable(backend_or_factory):
                        logger.debug("Calling backend_factory from configurable")
                        return backend_or_factory(runtime)
                    else:
                        return backend_or_factory

    except Exception as e:
        logger.warning(f"Failed to get backend from runtime: {e}")

    return None
