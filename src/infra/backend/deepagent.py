"""
DeepAgent Backend 工厂模块

为 DeepAgent 创建不同模式的 Backend 工厂函数。
"""

from typing import Any, Callable

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend


def create_memory_backend_factory(
    assistant_id: str,
) -> Callable[[Any], CompositeBackend]:
    """
    创建基于内存的 Backend 工厂函数（非沙箱模式，不使用长期存储）

    Args:
        assistant_id: 助手 ID，用于命名空间隔离

    Returns:
        Backend 工厂函数
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        return CompositeBackend(
            default=StateBackend(rt),  # 默认使用内存状态后端
            routes={
                "/skills/": StateBackend(rt),
            },
        )

    return backend_factory


def create_postgres_backend_factory(
    assistant_id: str,
) -> Callable[[Any], CompositeBackend]:
    """
    创建基于 PostgreSQL 的 Backend 工厂函数（非沙箱模式）

    Args:
        assistant_id: 助手 ID，用于命名空间隔离

    Returns:
        Backend 工厂函数
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        from deepagents.backends.store import BackendContext

        def memory_namespace_factory(ctx: BackendContext) -> tuple[str, ...]:
            """Memory 使用 PostgresStore 持久化，按 assistant_id 隔离"""
            return (assistant_id, "memories")

        def default_namespace_factory(ctx: BackendContext) -> tuple[str, ...]:
            """默认文件系统按 assistant_id 隔离"""
            return (assistant_id, "filesystem")

        return CompositeBackend(
            default=StoreBackend(rt, namespace=default_namespace_factory),
            routes={
                "/skills/": StateBackend(rt),
                "/memories/": StoreBackend(rt, namespace=memory_namespace_factory),
            },
        )

    return backend_factory


def create_sandbox_backend_factory(
    sandbox_backend: Any,
    assistant_id: str,
) -> Callable[[Any], CompositeBackend]:
    """
    创建基于沙箱的 Backend 工厂函数

    Args:
        sandbox_backend: 沙箱后端实例（从 SessionSandboxManager 获取）
        assistant_id: 助手 ID，用于命名空间隔离

    Returns:
        Backend 工厂函数
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        from deepagents.backends.store import BackendContext

        def memory_namespace_factory(ctx: BackendContext) -> tuple[str, ...]:
            """Memory 使用沙箱持久化，按 assistant_id 隔离"""
            return (assistant_id, "memories")

        return CompositeBackend(
            default=sandbox_backend,  # 沙箱模式使用沙箱 backend 作为默认
            routes={
                "/skills/": StateBackend(rt),
                "/memories/": StoreBackend(rt, namespace=memory_namespace_factory),
            },
        )

    return backend_factory
