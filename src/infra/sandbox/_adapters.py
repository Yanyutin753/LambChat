"""Sandbox platform adapters and shared constants.

Provides thin lifecycle adapters for E2B and CubeSandbox platforms,
plus state taxonomy constants used across the sandbox subsystem.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from src.infra.logging import get_logger

logger = get_logger(__name__)

# ── Daytona API / state constants ──────────────────────────────────

# Daytona API 操作的默认超时（秒）
DEFAULT_DAYTONA_TIMEOUT = 120

# 等待沙箱状态轮询间隔（秒）
STATE_POLL_INTERVAL = 3

# 等待中间状态完成的最大等待时间（秒）
STATE_WAIT_TIMEOUT = 180

# 需要等待的中间状态
TRANSITIONAL_STATES = {
    "creating",
    "restoring",
    "starting",
    "stopping",
    "building_snapshot",
    "pulling_snapshot",
    "pending_build",
    "archiving",
    "resizing",
}

# 可用的最终状态
READY_STATES = {"running", "started"}

# 需要恢复的暂停状态
RESUMABLE_STATES = {"stopped", "archived"}

# 不可用状态
UNAVAILABLE_STATES = {"destroyed", "destroying", "error", "build_failed", "unknown"}

# ── Binding / cache constants ──────────────────────────────────────

# MongoDB 集合名
BINDING_COLLECTION = "user_sandbox_bindings"

# 每用户锁的最大数量（LRU 淘汰）
_MAX_LOCKS = 10_000

# 内存缓存的最大条目数（LRU 淘汰，防止内存泄漏）
_MAX_CACHE_ENTRIES = 5_000

# 已经创建过的远端 session work_dir。只做进程内短路；进程重启后仍会重新 mkdir -p。
_MAX_READY_WORK_DIRS = 20_000


# ── Platform adapters ──────────────────────────────────────────────


class E2BSandboxAdapter:
    """E2B 沙箱生命周期适配器

    支持：
    - Auto-Pause + Auto-Resume：超时自动暂停，下次操作自动恢复
    - Metadata：创建沙箱时传入 user_id 用于可观测性
    - Pause/Resume：stop() 时暂停而非 kill，保留数据
    """

    def __init__(
        self,
        api_key: str,
        template: str,
        timeout: int,
        auto_pause: bool = True,
        auto_resume: bool = True,
    ):
        self._api_key = api_key
        self._template = template
        self._timeout = timeout
        self._auto_pause = auto_pause
        self._auto_resume = auto_resume

    def _sync_from_settings(self) -> None:
        """Sync config values from global settings (after DB update)."""
        from src.kernel.config.base import settings

        self._template = settings.E2B_TEMPLATE
        self._api_key = settings.E2B_API_KEY
        self._timeout = settings.E2B_TIMEOUT
        self._auto_pause = getattr(settings, "E2B_AUTO_PAUSE", True)
        self._auto_resume = getattr(settings, "E2B_AUTO_RESUME", True)

    def _get_e2b_class(self):
        from e2b import Sandbox as E2BSandbox

        return E2BSandbox

    def _get_e2b_opts(self) -> dict:
        opts: dict = {}
        api_url = os.environ.get("E2B_API_URL")
        if api_url:
            opts["api_url"] = api_url

        domain = os.environ.get("E2B_DOMAIN") or "e2b.app"
        opts["domain"] = domain
        opts["request_timeout"] = float(os.environ.get("E2B_REQUEST_TIMEOUT", "120"))
        return opts

    def create_sandbox(
        self, user_id: str | None = None, envs: dict[str, str] | None = None
    ) -> tuple[object, str]:
        """创建沙箱，支持 lifecycle 配置和 metadata"""
        self._sync_from_settings()
        e2b_class = self._get_e2b_class()

        kwargs: dict = {
            "template": self._template,
            "timeout": self._timeout,
            "api_key": self._api_key or None,
            **self._get_e2b_opts(),
        }

        # Auto-Pause + Auto-Resume lifecycle
        if self._auto_pause:
            kwargs["lifecycle"] = {
                "on_timeout": "pause",
                "auto_resume": self._auto_resume,
            }

        # Metadata 用于可观测性
        if user_id:
            kwargs["metadata"] = {"user_id": user_id}

        # 用户环境变量注入
        if envs:
            kwargs["envs"] = envs

        logger.info(
            "[E2B] Creating sandbox template=%s api_url=%s domain=%s timeout=%ss request_timeout=%ss",
            self._template,
            kwargs.get("api_url"),
            kwargs.get("domain"),
            self._timeout,
            kwargs.get("request_timeout"),
        )
        sandbox = e2b_class.create(**kwargs)
        return sandbox, "/home/user"

    def get_sandbox(self, sandbox_id: str) -> object | None:
        """连接到沙箱（自动恢复暂停状态）"""
        try:
            e2b_class = self._get_e2b_class()
            return e2b_class.connect(
                sandbox_id=sandbox_id,
                timeout=self._timeout,
                api_key=self._api_key or None,
                **self._get_e2b_opts(),
            )
        except Exception:
            return None

    def get_sandbox_id(self, sandbox) -> str:
        return sandbox.sandbox_id

    def get_work_dir(self, sandbox) -> str:
        return "/home/user"

    def pause_sandbox(self, sandbox) -> None:
        """暂停沙箱（保留文件系统和内存状态）"""
        try:
            sandbox.pause()
        except Exception as e:
            logger.warning(f"[E2B] Failed to pause sandbox: {e}")

    def stop_sandbox(self, sandbox) -> None:
        """停止沙箱 — 优先 pause（保留状态），失败则 kill"""
        try:
            sandbox.pause()
        except Exception:
            try:
                sandbox.kill()
            except Exception:
                pass

    def kill_sandbox(self, sandbox) -> None:
        """永久销毁沙箱（数据丢失）"""
        sandbox.kill()

    def sandbox_is_running(self, sandbox) -> bool:
        try:
            return sandbox.is_running()
        except Exception:
            return False

    def extend_timeout(self, sandbox, timeout: int) -> None:
        sandbox.set_timeout(timeout)

    def get_sandbox_info(self, sandbox) -> dict:
        """获取沙箱状态信息"""
        try:
            info = sandbox.get_info()
            return {
                "sandbox_id": info.sandbox_id,
                "state": info.state.name.lower()
                if hasattr(info.state, "name")
                else str(info.state),
            }
        except Exception:
            return {"sandbox_id": self.get_sandbox_id(sandbox), "state": "unknown"}


class CubeSandboxAdapter:
    """Native CubeSandbox lifecycle adapter."""

    def __init__(
        self,
        api_url: str,
        template: str,
        proxy_node_ip: str,
        proxy_port_http: int,
        sandbox_domain: str,
        timeout: int,
        request_timeout: float,
        auto_pause: bool = True,
        auto_resume: bool = True,
    ):
        self._api_url = api_url
        self._template = template
        self._proxy_node_ip = proxy_node_ip
        self._proxy_port_http = proxy_port_http
        self._sandbox_domain = sandbox_domain
        self._timeout = timeout
        self._request_timeout = request_timeout
        self._auto_pause = auto_pause
        self._auto_resume = auto_resume

    def _sync_from_settings(self) -> None:
        from src.kernel.config.base import settings

        self._api_url = settings.CUBE_API_URL
        self._template = settings.CUBE_TEMPLATE
        self._proxy_node_ip = settings.CUBE_PROXY_NODE_IP
        self._proxy_port_http = settings.CUBE_PROXY_PORT_HTTP
        self._sandbox_domain = settings.CUBE_SANDBOX_DOMAIN
        self._timeout = settings.CUBE_TIMEOUT
        self._request_timeout = settings.CUBE_REQUEST_TIMEOUT
        self._auto_pause = getattr(settings, "CUBE_AUTO_PAUSE", True)
        self._auto_resume = getattr(settings, "CUBE_AUTO_RESUME", True)

    def _get_config(self):
        from cubesandbox import Config

        return Config(
            api_url=self._api_url,
            template_id=self._template,
            proxy_node_ip=self._proxy_node_ip or None,
            proxy_port=self._proxy_port_http,
            sandbox_domain=self._sandbox_domain,
            timeout=self._timeout,
            request_timeout=self._request_timeout,
        )

    def _get_cube_class(self):
        from cubesandbox import Sandbox as CubeSandbox

        return CubeSandbox

    def create_sandbox(
        self, user_id: str | None = None, envs: dict[str, str] | None = None
    ) -> tuple[object, str]:
        self._sync_from_settings()
        cube_class = self._get_cube_class()
        lifecycle = None
        if self._auto_pause:
            lifecycle = {
                "on_timeout": "pause",
                "auto_resume": self._auto_resume,
            }
        metadata = {"user_id": user_id} if user_id else None
        logger.info(
            "[CubeSandbox] Creating sandbox template=%s api_url=%s timeout=%ss request_timeout=%ss",
            self._template,
            self._api_url,
            self._timeout,
            self._request_timeout,
        )
        sandbox = cube_class.create(
            template=self._template,
            timeout=self._timeout,
            env_vars=envs,
            metadata=metadata,
            lifecycle=lifecycle,
            config=self._get_config(),
        )
        return sandbox, "/home/user"

    def get_sandbox(self, sandbox_id: str) -> object | None:
        try:
            self._sync_from_settings()
            cube_class = self._get_cube_class()
            return cube_class.connect(sandbox_id, config=self._get_config())
        except Exception:
            return None

    def list_user_sandboxes(self, user_id: str) -> list[dict]:
        self._sync_from_settings()
        cube_class = self._get_cube_class()
        sandboxes = cube_class.list(config=self._get_config())
        result = []
        for item in sandboxes:
            metadata = item.get("metadata") or {}
            if metadata.get("user_id") != user_id:
                continue
            if str(item.get("state", "")).lower() not in READY_STATES:
                continue
            if self._template and item.get("templateID") != self._template:
                continue
            result.append(item)
        return sorted(result, key=lambda item: item.get("startedAt") or "", reverse=True)

    def get_sandbox_id(self, sandbox) -> str:
        return sandbox.sandbox_id

    def get_work_dir(self, sandbox) -> str:
        return "/home/user"

    def pause_sandbox(self, sandbox) -> None:
        try:
            sandbox.pause()
        except Exception as e:
            logger.warning(f"[CubeSandbox] Failed to pause sandbox: {e}")

    def stop_sandbox(self, sandbox) -> None:
        try:
            sandbox.pause()
        except Exception:
            try:
                sandbox.kill()
            except Exception:
                pass

    def kill_sandbox(self, sandbox) -> None:
        sandbox.kill()

    def sandbox_is_running(self, sandbox) -> bool:
        try:
            info = sandbox.get_info()
            return str(info.get("state", "")).lower() in READY_STATES
        except Exception:
            return False

    def extend_timeout(self, sandbox, timeout: int) -> None:
        # CubeSandbox's native SDK does not expose set_timeout; connect/create
        # carry the desired timeout. Keep this method for SessionSandboxManager
        # lifecycle symmetry.
        del sandbox, timeout

    def get_sandbox_info(self, sandbox) -> dict:
        try:
            info = sandbox.get_info()
            return {
                "sandbox_id": info.get("sandboxID", self.get_sandbox_id(sandbox)),
                "state": str(info.get("state", "unknown")).lower(),
            }
        except Exception:
            return {"sandbox_id": self.get_sandbox_id(sandbox), "state": "unknown"}
