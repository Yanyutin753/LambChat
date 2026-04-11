"""
Sandbox 工厂和配置

统一管理 Daytona、E2B 两个 Sandbox 平台。
直接使用 langchain-{platform} 库提供的实现。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.infra.logging import get_logger
from src.kernel.config import settings

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = get_logger(__name__)


# =============================================================================
# 配置类
# =============================================================================


@dataclass
class SandboxConfig:
    """Sandbox 配置基类"""

    platform: str  # "daytona" | "e2b"
    ttl_seconds: int = 1800


@dataclass
class DaytonaConfig(SandboxConfig):
    """Daytona 配置"""

    platform: str = field(default="daytona", init=False)
    api_key: str = ""
    server_url: str = ""


@dataclass
class E2BConfig(SandboxConfig):
    """E2B 配置"""

    platform: str = field(default="e2b", init=False)
    api_key: str = ""
    template: str = "base"
    timeout: int = 3600
    auto_pause: bool = True
    auto_resume: bool = True


# =============================================================================
# 工厂类
# =============================================================================


class SandboxFactory:
    """
    Sandbox 工厂类

    使用 langchain-{platform} 库提供的 Sandbox 实现。
    支持 TTL 自动清理和手动关闭。
    """

    # 追踪创建的 sandbox 和其底层 provider 对象（用于关闭）
    _sandbox_registry: dict[str, tuple["SandboxBackendProtocol", Any]] = {}
    # 追踪 run_id 到 sandbox_id 的映射（用于取消时关闭特定沙箱）
    _run_id_to_sandbox: dict[str, str] = {}

    @classmethod
    def create_daytona(
        cls,
        api_key: str,
        server_url: str = "",
        ttl_seconds: int = 1800,
    ) -> "SandboxBackendProtocol":
        """
        创建 Daytona Sandbox

        Args:
            api_key: Daytona API Key
            server_url: Daytona 服务器 URL
            ttl_seconds: 生命周期（秒）

        Returns:
            DaytonaSandbox 实例
        """
        try:
            from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig

            from src.infra.backend.daytona import DaytonaBackend

            # Daytona 客户端配置
            config = DaytonaConfig(
                api_key=api_key, server_url=server_url
            )  # Replace with your API key
            client = Daytona(config)

            # 创建带 TTL 的 sandbox
            params = CreateSandboxFromSnapshotParams(
                auto_delete_interval=ttl_seconds,  # 自动删除间隔
                language="python",
            )
            sandbox = client.create(params)
            backend = DaytonaBackend(sandbox=sandbox)

            # 注册以便追踪和关闭
            sandbox_id = sandbox.id
            cls._sandbox_registry[sandbox_id] = (backend, sandbox)
            logger.info(f"Created Daytona sandbox: {sandbox_id}, TTL={ttl_seconds}s")

            return backend
        except ImportError as e:
            raise ImportError("Please install daytona-sdk: pip install daytona-sdk") from e

    @classmethod
    def create_e2b(
        cls,
        api_key: str,
        template: str = "base",
        timeout: int = 3600,
        auto_pause: bool = True,
        auto_resume: bool = True,
    ) -> "SandboxBackendProtocol":
        """
        创建 E2B Sandbox

        Args:
            api_key: E2B API Key
            template: 沙箱模板名称 (default: "base")
            timeout: 沙箱超时时间（秒）
            auto_pause: 超时自动暂停（保留状态）
            auto_resume: 下次操作自动恢复暂停的沙箱

        Returns:
            E2BBackend 实例
        """
        try:
            from e2b import Sandbox as E2BSandbox

            from src.infra.backend.e2b import E2BBackend

            kwargs: dict = {
                "template": template,
                "timeout": timeout,
                "api_key": api_key or None,
            }
            if auto_pause:
                kwargs["lifecycle"] = {
                    "on_timeout": "pause",
                    "auto_resume": auto_resume,
                }

            sandbox = E2BSandbox.create(**kwargs)
            backend = E2BBackend(sandbox=sandbox, timeout=timeout)

            # 注册以便追踪和关闭
            sandbox_id = sandbox.sandbox_id
            cls._sandbox_registry[sandbox_id] = (backend, sandbox)
            logger.info(
                f"Created E2B sandbox: {sandbox_id}, template={template}, timeout={timeout}s"
            )

            return backend
        except ImportError as e:
            raise ImportError("Please install e2b: pip install e2b") from e

    @classmethod
    async def close_sandbox(
        cls,
        sandbox_id: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
    ) -> bool:
        """
        关闭指定的 sandbox

        Args:
            sandbox_id: Sandbox ID
            max_retries: 最大重试次数（默认 5 次）
            base_delay: 基础重试延迟（秒，默认 1 秒，使用指数退避）

        Returns:
            是否成功关闭
        """
        if sandbox_id not in cls._sandbox_registry:
            logger.warning(f"Sandbox {sandbox_id} not found in registry")
            return False

        # 不要在这里 pop，等成功关闭后再移除
        backend, provider_obj = cls._sandbox_registry[sandbox_id]

        last_error = None
        for attempt in range(max_retries):
            try:
                # 根据模块名判断类型并关闭
                module_name = type(provider_obj).__module__

                if "daytona" in module_name:
                    # Daytona: sandbox.delete()
                    provider_obj.delete()
                elif "e2b" in module_name:
                    # E2B: sandbox.kill()
                    provider_obj.kill()
                else:
                    logger.warning(f"Unknown provider type: {module_name}")

                # 成功关闭后才从 registry 移除
                cls._sandbox_registry.pop(sandbox_id, None)
                logger.info(f"Closed sandbox: {sandbox_id}")
                return True

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                # 检查是否是状态变更错误，如果是则使用指数退避重试
                is_state_change_error = (
                    "state change" in error_msg
                    or "state_transition" in error_msg
                    or "in progress" in error_msg
                )

                if is_state_change_error and attempt < max_retries - 1:
                    # 指数退避: 1s, 2s, 4s, 8s, 16s
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Sandbox {sandbox_id} state change in progress, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                # 其他错误直接记录并退出循环
                logger.error(f"Failed to close sandbox {sandbox_id}: {e}")
                break

        logger.error(
            f"Failed to close sandbox {sandbox_id} after {max_retries} attempts: {last_error}"
        )
        # 注意：失败时保留在 registry 中，以便后续可以重试
        return False

    @classmethod
    async def close_all(cls) -> int:
        """
        关闭所有追踪的 sandbox

        Returns:
            成功关闭的数量
        """
        sandbox_ids = list(cls._sandbox_registry.keys())
        closed_count = 0

        for sandbox_id in sandbox_ids:
            if await cls.close_sandbox(sandbox_id):
                closed_count += 1

        logger.info(f"Closed {closed_count}/{len(sandbox_ids)} sandboxes")
        return closed_count

    @classmethod
    def get_sandbox_id(cls, backend: "SandboxBackendProtocol") -> str | None:
        """
        获取 sandbox 的 ID

        Args:
            backend: Sandbox backend 实例

        Returns:
            Sandbox ID 或 None
        """
        for sandbox_id, (registered_backend, _) in cls._sandbox_registry.items():
            if registered_backend is backend:
                return sandbox_id
        return None

    @classmethod
    def set_run_id(cls, run_id: str, sandbox_id: str) -> None:
        """
        设置 run_id 到 sandbox_id 的映射

        Args:
            run_id: 运行 ID
            sandbox_id: 沙箱 ID
        """
        cls._run_id_to_sandbox[run_id] = sandbox_id

    @classmethod
    async def close_by_run_id(cls, run_id: str) -> bool:
        """
        通过 run_id 关闭对应的沙箱

        Args:
            run_id: 运行 ID

        Returns:
            是否成功关闭
        """
        sandbox_id = cls._run_id_to_sandbox.pop(run_id, None)
        if sandbox_id:
            return await cls.close_sandbox(sandbox_id)
        return False

    @classmethod
    def create(cls, config: SandboxConfig) -> "SandboxBackendProtocol":
        """
        根据配置创建 Sandbox

        Args:
            config: Sandbox 配置

        Returns:
            Sandbox 实例
        """
        if config.platform == "daytona":
            if not isinstance(config, DaytonaConfig):
                raise ValueError("Invalid config type for daytona platform")
            return cls.create_daytona(
                api_key=config.api_key,
                server_url=config.server_url,
                ttl_seconds=config.ttl_seconds,
            )
        elif config.platform == "e2b":
            if not isinstance(config, E2BConfig):
                raise ValueError("Invalid config type for e2b platform")
            return cls.create_e2b(
                api_key=config.api_key,
                template=config.template,
                timeout=config.timeout,
                auto_pause=config.auto_pause,
                auto_resume=config.auto_resume,
            )
        else:
            raise ValueError(f"Unknown sandbox platform: {config.platform}")


# =============================================================================
# 辅助函数
# =============================================================================


def get_sandbox_config_from_settings() -> SandboxConfig:
    """从配置创建 Sandbox 配置对象"""
    platform = settings.SANDBOX_PLATFORM.lower()

    if platform == "daytona":
        return DaytonaConfig(
            api_key=getattr(settings, "DAYTONA_API_KEY", ""),
            server_url=getattr(settings, "DAYTONA_SERVER_URL", ""),
            ttl_seconds=getattr(settings, "SANDBOX_TTL_SECONDS", 3600),
        )
    elif platform == "e2b":
        return E2BConfig(
            api_key=getattr(settings, "E2B_API_KEY", ""),
            template=getattr(settings, "E2B_TEMPLATE", "base"),
            timeout=getattr(settings, "E2B_TIMEOUT", 3600),
            auto_pause=getattr(settings, "E2B_AUTO_PAUSE", True),
            auto_resume=getattr(settings, "E2B_AUTO_RESUME", True),
        )
    else:
        raise ValueError(f"Unsupported sandbox platform: {platform}")


def get_sandbox_from_settings() -> "SandboxBackendProtocol":
    """从配置创建 Sandbox 实例"""
    config = get_sandbox_config_from_settings()
    return SandboxFactory.create(config)
