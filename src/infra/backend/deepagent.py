"""
DeepAgent Backend 工厂模块

为 DeepAgent 创建不同模式的 Backend 工厂函数。

Skills 路径现在使用 SkillsStoreBackend，支持 LLM 直接读写 skills 到 MongoDB。
"""

from typing import Any, Callable, Optional

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.protocol import BackendProtocol

from src.infra.logging import get_logger

logger = get_logger(__name__)


def _create_routes(
    rt: Any,
    assistant_id: str,
    user_id: str,
) -> dict[str, BackendProtocol]:
    """创建通用的 backend 路由（skills + memories）"""
    from deepagents.backends.store import BackendContext

    from src.infra.backend.skills_store import create_skills_backend

    def memory_namespace_factory(ctx: BackendContext) -> tuple[str, ...]:  # type: ignore[arg-type]
        return (assistant_id, "memories")

    skills_backend = create_skills_backend(user_id=user_id, runtime=rt)

    return {
        "/skills/": skills_backend,
        "/memories/": StoreBackend(rt, namespace=memory_namespace_factory),  # type: ignore[arg-type]
    }


def create_memory_backend_factory(
    assistant_id: str,
    user_id: Optional[str] = None,
) -> Callable[[Any], CompositeBackend]:
    """创建基于内存的 Backend 工厂（不使用长期存储）"""

    def backend_factory(rt: Any) -> CompositeBackend:
        from src.infra.backend.skills_store import create_skills_backend

        skills_backend = create_skills_backend(user_id=user_id or "default", runtime=rt)

        return CompositeBackend(
            default=StateBackend(rt),
            routes={"/skills/": skills_backend},
        )

    return backend_factory


def create_persistent_backend_factory(
    assistant_id: str,
    user_id: Optional[str] = None,
) -> Callable[[Any], CompositeBackend]:
    """创建基于 Store 的 Backend 工厂（PostgreSQL / MongoDB 通用）。

    底层 Store 由 create_deep_agent 传入，此处只负责 namespace 路由。
    """

    def backend_factory(rt: Any) -> CompositeBackend:
        from deepagents.backends.store import BackendContext

        routes = _create_routes(rt, assistant_id, user_id or "default")

        def default_namespace_factory(ctx: BackendContext) -> tuple[str, ...]:  # type: ignore[arg-type]
            return (assistant_id, "filesystem")

        return CompositeBackend(
            default=StoreBackend(rt, namespace=default_namespace_factory),  # type: ignore[arg-type]
            routes=routes,
        )

    return backend_factory


def create_sandbox_backend_factory(
    sandbox_backend: Any,
    assistant_id: str,
    user_id: Optional[str] = None,
) -> Callable[[Any], CompositeBackend]:
    """创建基于沙箱的 Backend 工厂"""

    def backend_factory(rt: Any) -> CompositeBackend:
        routes = _create_routes(rt, assistant_id, user_id or "default")

        return CompositeBackend(
            default=sandbox_backend,
            routes=routes,
        )

    return backend_factory
