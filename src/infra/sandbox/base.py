"""
Sandbox 工厂和配置

统一管理 Runloop、Daytona、Modal 三个 Sandbox 平台。
直接使用 langchain-{platform} 库提供的实现。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.kernel.config import settings

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)


# =============================================================================
# 配置类
# =============================================================================


@dataclass
class SandboxConfig:
    """Sandbox 配置基类"""

    platform: str  # "runloop" | "daytona" | "modal"
    ttl_seconds: int = 3600


@dataclass
class RunloopConfig(SandboxConfig):
    """Runloop 配置"""

    platform: str = field(default="runloop", init=False)
    api_key: str = ""
    base_url: str = "https://api.runloop.ai"


@dataclass
class DaytonaConfig(SandboxConfig):
    """Daytona 配置"""

    platform: str = field(default="daytona", init=False)
    api_key: str = ""
    server_url: str = ""


@dataclass
class ModalConfig(SandboxConfig):
    """Modal 配置"""

    platform: str = field(default="modal", init=False)
    app_name: str = ""
    api_key: str = ""  # Modal 通常使用环境变量


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
    def create_runloop(
        cls,
        api_key: str,
        ttl_seconds: int = 3600,
    ) -> "SandboxBackendProtocol":
        """
        创建 Runloop Sandbox

        Args:
            api_key: Runloop API Key
            ttl_seconds: 生命周期（秒）

        Returns:
            RunloopSandbox 实例
        """
        try:
            from langchain_runloop import RunloopSandbox
            from runloop_api_client import RunloopSDK

            client = RunloopSDK(bearer_token=api_key)
            # Runloop API 使用 lifetime_minutes 参数
            lifetime_minutes = ttl_seconds // 60
            devbox = client.devbox.create(lifetime_minutes=lifetime_minutes)
            backend = RunloopSandbox(devbox=devbox)

            # 注册以便追踪和关闭
            sandbox_id = devbox.id
            cls._sandbox_registry[sandbox_id] = (backend, devbox)
            logger.info(f"Created Runloop sandbox: {sandbox_id}, TTL={lifetime_minutes}min")

            return backend
        except ImportError as e:
            raise ImportError(
                "Please install langchain-runloop: pip install langchain-runloop"
            ) from e

    @classmethod
    def create_daytona(
        cls,
        api_key: str,
        server_url: str = "",
        ttl_seconds: int = 3600,
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
    def create_modal(
        cls,
        app_name: str,
        ttl_seconds: int = 3600,
    ) -> "SandboxBackendProtocol":
        """
        创建 Modal Sandbox

        Args:
            app_name: Modal App 名称
            ttl_seconds: 生命周期（秒）- Modal 会自动处理

        Returns:
            ModalSandbox 实例
        """
        try:
            import modal
            from langchain_modal import ModalSandbox

            app = modal.App.lookup(app_name)
            # Modal sandbox 有内置的 timeout
            modal_sandbox = modal.Sandbox.create(
                app=app,
                timeout=ttl_seconds,  # Modal 使用 timeout 参数
            )
            backend = ModalSandbox(sandbox=modal_sandbox)

            # 注册以便追踪和关闭
            sandbox_id = modal_sandbox.object_id
            cls._sandbox_registry[sandbox_id] = (backend, modal_sandbox)
            logger.info(f"Created Modal sandbox: {sandbox_id}, timeout={ttl_seconds}s")

            return backend
        except ImportError as e:
            raise ImportError("Please install langchain-modal: pip install langchain-modal") from e

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

                if "runloop" in module_name:
                    # Runloop: devbox.shutdown()
                    provider_obj.shutdown()
                elif "daytona" in module_name:
                    # Daytona: sandbox.delete()
                    provider_obj.delete()
                elif "modal" in module_name:
                    # Modal: sandbox.terminate()
                    provider_obj.terminate()
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
        if config.platform == "runloop":
            if not isinstance(config, RunloopConfig):
                raise ValueError("Invalid config type for runloop platform")
            return cls.create_runloop(
                api_key=config.api_key,
                ttl_seconds=config.ttl_seconds,
            )
        elif config.platform == "daytona":
            if not isinstance(config, DaytonaConfig):
                raise ValueError("Invalid config type for daytona platform")
            return cls.create_daytona(
                api_key=config.api_key,
                server_url=config.server_url,
                ttl_seconds=config.ttl_seconds,
            )
        elif config.platform == "modal":
            if not isinstance(config, ModalConfig):
                raise ValueError("Invalid config type for modal platform")
            return cls.create_modal(
                app_name=config.app_name,
                ttl_seconds=config.ttl_seconds,
            )
        else:
            raise ValueError(f"Unknown sandbox platform: {config.platform}")


# =============================================================================
# 辅助函数
# =============================================================================


def get_sandbox_config_from_settings() -> SandboxConfig:
    """从配置创建 Sandbox 配置对象"""
    platform = settings.SANDBOX_PLATFORM.lower()

    if platform == "runloop":
        return RunloopConfig(
            api_key=getattr(settings, "RUNLOOP_API_KEY", ""),
            base_url=getattr(settings, "RUNLOOP_BASE_URL", "https://api.runloop.ai"),
            ttl_seconds=getattr(settings, "SANDBOX_TTL_SECONDS", 3600),
        )
    elif platform == "daytona":
        return DaytonaConfig(
            api_key=getattr(settings, "DAYTONA_API_KEY", ""),
            server_url=getattr(settings, "DAYTONA_SERVER_URL", ""),
            ttl_seconds=getattr(settings, "SANDBOX_TTL_SECONDS", 3600),
        )
    elif platform == "modal":
        return ModalConfig(
            app_name=getattr(settings, "MODAL_APP_NAME", ""),
            api_key=getattr(settings, "MODAL_API_KEY", ""),
            ttl_seconds=getattr(settings, "SANDBOX_TTL_SECONDS", 3600),
        )
    else:
        raise ValueError(f"Unsupported sandbox platform: {platform}")


def get_sandbox_from_settings() -> "SandboxBackendProtocol":
    """从配置创建 Sandbox 实例"""
    config = get_sandbox_config_from_settings()
    return SandboxFactory.create(config)
