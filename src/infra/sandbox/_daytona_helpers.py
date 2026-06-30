"""Daytona-specific helper methods for SessionSandboxManager.

These are mixed into SessionSandboxManager via multiple inheritance.
All methods assume `self` provides the shared infra (cache, bindings, locks, etc.).
"""

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional

from deepagents.backends import CompositeBackend

from src.infra.async_utils import run_blocking_io as _run_blocking_io
from src.infra.backend.daytona import DaytonaBackend
from src.infra.backend.skills_store import create_skills_backend
from src.infra.logging import get_logger
from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp as _ensure_sandbox_mcp

from ._adapters import (
    DEFAULT_DAYTONA_TIMEOUT,
    STATE_POLL_INTERVAL,
    STATE_WAIT_TIMEOUT,
    TRANSITIONAL_STATES,
)

if TYPE_CHECKING:
    from daytona import Daytona

logger = get_logger(__name__)


def run_blocking_io(*args, **kwargs):
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "run_blocking_io", _run_blocking_io)(*args, **kwargs)


def ensure_sandbox_mcp(*args, **kwargs):
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "ensure_sandbox_mcp", _ensure_sandbox_mcp)(*args, **kwargs)


class _DaytonaMixin:
    """Daytona platform lifecycle methods for SessionSandboxManager."""

    if TYPE_CHECKING:
        _daytona_client: Optional["Daytona"]
        _cache: OrderedDict[str, tuple[str, CompositeBackend, object | None]]

        async def _save_binding(
            self,
            user_id: str,
            sandbox_id: str,
            state: str,
            is_new: bool = False,
        ) -> None: ...

        def _evict_if_needed(self) -> None: ...

        def _session_work_dir(self, base_work_dir: str, session_id: str) -> str: ...

        def _scope_daytona_backend(
            self,
            backend: CompositeBackend,
            user_id: str,
            work_dir: str,
        ) -> CompositeBackend: ...

        async def _ensure_work_dir(self, backend: CompositeBackend, work_dir: str) -> None: ...

    def _get_daytona_client(self) -> "Daytona":
        """获取或创建 Daytona 客户端"""
        from daytona import Daytona, DaytonaConfig

        from src.kernel.config import settings

        if self._daytona_client is None:
            config = DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                server_url=settings.DAYTONA_SERVER_URL,
            )
            self._daytona_client = Daytona(config)
        return self._daytona_client

    async def _get_sandbox_state(self, sandbox_id: str) -> str:
        """查询沙箱状态: running / stopped / archived / destroyed"""

        def _sync_get_state():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            state = sandbox.state
            if state is not None and hasattr(state, "name"):
                return state.name.lower()
            elif state is not None and hasattr(state, "value"):
                return str(state.value).lower()
            return str(state).lower() if state else "unknown"

        try:
            return await run_blocking_io(
                _sync_get_state,
                timeout=DEFAULT_DAYTONA_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(f"[SessionSandboxManager] Timeout getting sandbox {sandbox_id} state")
            return "unknown"
        except Exception as e:
            if "not found" in str(e).lower():
                return "destroyed"
            raise

    async def _wait_for_final_state(self, sandbox_id: str, initial_state: str) -> str:
        """等待沙箱从中间状态过渡到最终状态"""
        state = initial_state
        elapsed = 0.0

        while state in TRANSITIONAL_STATES and elapsed < STATE_WAIT_TIMEOUT:
            logger.debug(
                f"[SessionSandboxManager] Waiting for sandbox {sandbox_id} "
                f"state={state}, elapsed={elapsed:.1f}s"
            )
            await asyncio.sleep(STATE_POLL_INTERVAL)
            elapsed += STATE_POLL_INTERVAL
            state = await self._get_sandbox_state(sandbox_id)

        if state in TRANSITIONAL_STATES:
            logger.warning(
                f"[SessionSandboxManager] Timeout waiting for sandbox {sandbox_id} "
                f"to transition from {initial_state}, current state={state}"
            )
            return "unknown"

        return state

    async def _start_sandbox(self, sandbox_id: str) -> None:
        """启动沙箱"""

        def _sync_start():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            sandbox.start(timeout=60)

        await run_blocking_io(
            _sync_start,
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _get_work_dir(self, sandbox_id: str) -> str:
        """获取沙箱工作目录"""

        def _sync_get_work_dir():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            return sandbox.get_work_dir()

        return await run_blocking_io(
            _sync_get_work_dir,
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _create_backend(
        self,
        sandbox_id: str,
        user_id: str,
    ) -> CompositeBackend:
        """为已存在的沙箱创建 CompositeBackend"""

        def _sync_create_backend():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            daytona_backend = DaytonaBackend(sandbox=sandbox)
            skills_backend = create_skills_backend(user_id=user_id)
            return CompositeBackend(
                default=daytona_backend,
                routes={
                    "/skills/": skills_backend,
                },
            )

        return await run_blocking_io(
            _sync_create_backend,
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _create_and_bind(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[CompositeBackend, str]:
        """创建新沙箱并绑定到用户（替换旧的绑定）

        Args:
            session_id: 当前会话 ID（仅用于日志追踪）
            user_id: 用户 ID

        Returns:
            tuple[CompositeBackend, str]: (composite_backend, work_dir)
        """
        from daytona import CreateSandboxFromSnapshotParams

        from src.kernel.config import settings

        # 加载用户环境变量
        user_envs = await self._get_user_env_vars(user_id)

        def _sync_create():
            client = self._get_daytona_client()
            params = CreateSandboxFromSnapshotParams(
                auto_delete_interval=settings.DAYTONA_AUTO_DELETE_INTERVAL,
                auto_stop_interval=settings.DAYTONA_AUTO_STOP_INTERVAL,
                auto_archive_interval=settings.DAYTONA_AUTO_ARCHIVE_INTERVAL,
                language="python",
                snapshot=settings.DAYTONA_IMAGE if settings.DAYTONA_IMAGE else None,
                env_vars=user_envs if user_envs else None,
            )
            sandbox = client.create(params)
            daytona_backend = DaytonaBackend(sandbox=sandbox)
            skills_backend = create_skills_backend(user_id=user_id)
            composite_backend = CompositeBackend(
                default=daytona_backend,
                routes={
                    "/skills/": skills_backend,
                },
            )
            return composite_backend, sandbox.get_work_dir(), daytona_backend.id

        backend, work_dir, sandbox_id = await run_blocking_io(
            _sync_create,
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

        try:
            # 保存绑定到 MongoDB
            await self._save_binding(user_id, sandbox_id, "running", is_new=True)
        except Exception as e:
            logger.error(
                f"[SessionSandboxManager] Created sandbox {sandbox_id} but failed to save binding: {e}. "
                "Attempting to clean up orphan sandbox."
            )
            # 尝试清理孤儿沙箱
            try:
                await run_blocking_io(self._delete_sandbox, sandbox_id)
            except Exception as cleanup_err:
                logger.error(
                    f"[SessionSandboxManager] Failed to clean up orphan sandbox {sandbox_id}: {cleanup_err}"
                )
            raise

        # 更新内存缓存
        self._cache[user_id] = (sandbox_id, backend, None)
        self._evict_if_needed()

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox_id} for user {user_id} (session={session_id})"
        )

        scoped_work_dir = self._session_work_dir(work_dir, session_id)
        scoped_backend = self._scope_daytona_backend(backend, user_id, scoped_work_dir)
        await self._ensure_work_dir(scoped_backend, scoped_work_dir)
        await ensure_sandbox_mcp(scoped_backend, user_id)
        return scoped_backend, scoped_work_dir

    async def _get_user_env_vars(self, user_id: str) -> dict[str, str]:
        """加载用户的环境变量（解密后）"""
        try:
            from src.infra.envvar.storage import EnvVarStorage

            storage = EnvVarStorage()
            return await storage.get_decrypted_vars(user_id)
        except Exception as e:
            logger.warning(
                f"[SessionSandboxManager] Failed to load env vars for user {user_id}: {e}"
            )
            return {}

    def _delete_sandbox(self, sandbox_id: str) -> None:
        """删除沙箱（同步，用于 run_blocking_io）"""

        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        sandbox.delete()
