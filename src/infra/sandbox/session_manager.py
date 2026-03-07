"""
Session-Sandbox 绑定管理器

管理 Session 与 Daytona Sandbox 的绑定关系：
- 沙箱存储在 session.metadata 中
- 对话结束时 stop 而非 delete
- 下次对话时从 stopped/archived 状态恢复
"""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig

from src.infra.backend.daytona import DaytonaBackend
from src.infra.session.manager import SessionManager
from src.kernel.config import settings
from src.kernel.schemas.session import SessionUpdate

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

logger = logging.getLogger(__name__)

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


class SessionSandboxManager:
    """管理 Session 与 Sandbox 的绑定关系"""

    def __init__(self):
        self._session_manager = SessionManager()
        self._daytona_client: Optional[Daytona] = None
        # 内存缓存: session_id -> (sandbox_id, backend)
        self._cache: dict[str, tuple[str, "SandboxBackendProtocol"]] = {}

    def _get_daytona_client(self) -> Daytona:
        """获取或创建 Daytona 客户端"""
        if self._daytona_client is None:
            config = DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                server_url=settings.DAYTONA_SERVER_URL,
            )
            self._daytona_client = Daytona(config)
        return self._daytona_client

    async def get_or_create(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple["SandboxBackendProtocol", str]:
        """
        获取或创建沙箱

        流程：
        1. 检查内存缓存
        2. 检查 session.metadata 中的 sandbox_id
        3. 如果存在，查询 Daytona 状态
        4. Stopped/Archived → start() 恢复
        5. 不存在或恢复失败 → 创建新沙箱，覆盖绑定

        Returns:
            tuple[SandboxBackendProtocol, str]: (backend, work_dir)
        """
        # 1. 检查内存缓存
        if session_id in self._cache:
            sandbox_id, backend = self._cache[session_id]
            logger.debug(
                f"[SessionSandboxManager] Cache hit: session={session_id}, sandbox={sandbox_id}"
            )
            try:
                work_dir = await self._get_work_dir(sandbox_id)
                return backend, work_dir
            except Exception as e:
                logger.warning(
                    f"[SessionSandboxManager] Failed to get work_dir from cached sandbox {sandbox_id}: {e}. "
                    "Creating new sandbox."
                )
                # 清除缓存，创建新沙箱
                del self._cache[session_id]

        # 2. 从 session.metadata 获取 sandbox_id
        session = await self._session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        metadata_sandbox_id: str | None = (
            session.metadata.get("sandbox_id") if session.metadata else None
        )

        if metadata_sandbox_id:
            sandbox_id = metadata_sandbox_id
            # 3. 查询 Daytona 状态
            state = await self._get_sandbox_state(sandbox_id)
            logger.info(f"[SessionSandboxManager] Found sandbox {sandbox_id} with state={state}")

            # 3.1 如果处于中间状态，等待完成
            if state in TRANSITIONAL_STATES:
                state = await self._wait_for_final_state(sandbox_id, state)
                logger.info(
                    f"[SessionSandboxManager] Sandbox {sandbox_id} transitioned to state={state}"
                )

            if state in RESUMABLE_STATES:
                # 4. 尝试恢复
                try:
                    await self._start_sandbox(sandbox_id)
                    backend = await self._create_backend(sandbox_id)
                    self._cache[session_id] = (sandbox_id, backend)
                    await self._update_session_metadata(session_id, sandbox_id, "running")
                    logger.info(f"[SessionSandboxManager] Resumed sandbox {sandbox_id}")
                    work_dir = await self._get_work_dir(sandbox_id)
                    return backend, work_dir
                except Exception as e:
                    logger.warning(
                        f"[SessionSandboxManager] Failed to resume sandbox {sandbox_id}: {e}. "
                        "Creating new sandbox."
                    )
                    # 恢复失败，清除缓存，创建新沙箱
                    if session_id in self._cache:
                        del self._cache[session_id]

            elif state in READY_STATES:
                # 沙箱已在运行，直接使用
                try:
                    backend = await self._create_backend(sandbox_id)
                    self._cache[session_id] = (sandbox_id, backend)
                    work_dir = await self._get_work_dir(sandbox_id)
                    return backend, work_dir
                except Exception as e:
                    logger.warning(
                        f"[SessionSandboxManager] Failed to get work_dir from sandbox {sandbox_id}: {e}. "
                        "Creating new sandbox."
                    )
                    # 清除缓存，创建新沙箱
                    if session_id in self._cache:
                        del self._cache[session_id]

            elif state in UNAVAILABLE_STATES:
                logger.info(
                    f"[SessionSandboxManager] Sandbox {sandbox_id} is unavailable (state={state})"
                )
                # 沙箱不可用，创建新沙箱

        # 5. 创建新沙箱并绑定
        return await self._create_and_bind(session_id, user_id)

    async def stop(self, session_id: str) -> bool:
        """
        停止沙箱（对话结束时调用）

        Returns:
            是否成功停止
        """
        if session_id not in self._cache:
            # 尝试从 session.metadata 获取
            session = await self._session_manager.get_session(session_id)
            if not session or not session.metadata:
                return False
            sandbox_id = session.metadata.get("sandbox_id")
            if not sandbox_id:
                return False
        else:
            sandbox_id, _ = self._cache[session_id]

        def _sync_stop():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            sandbox.stop(timeout=30)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_sync_stop),
                timeout=DEFAULT_DAYTONA_TIMEOUT,
            )
            await self._update_session_metadata(session_id, sandbox_id, "stopped")
            logger.info(f"[SessionSandboxManager] Stopped sandbox {sandbox_id}")
            return True
        except asyncio.TimeoutError:
            logger.error(f"[SessionSandboxManager] Timeout stopping sandbox {sandbox_id}")
            return False
        except Exception as e:
            logger.error(f"[SessionSandboxManager] Failed to stop sandbox {sandbox_id}: {e}")
            return False

    async def _get_sandbox_state(self, sandbox_id: str) -> str:
        """查询沙箱状态: running / stopped / archived / destroyed"""

        def _sync_get_state():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            # state 是 SandboxState 枚举，提取枚举名称并转小写
            # 例如 SandboxState.STARTED -> "started"
            state = sandbox.state
            if state is not None and hasattr(state, "name"):
                return state.name.lower()
            elif state is not None and hasattr(state, "value"):
                return str(state.value).lower()
            return str(state).lower() if state else "unknown"

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_sync_get_state),
                timeout=DEFAULT_DAYTONA_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(f"[SessionSandboxManager] Timeout getting sandbox {sandbox_id} state")
            return "unknown"
        except Exception as e:
            # 如果沙箱不存在，返回 destroyed
            if "not found" in str(e).lower():
                return "destroyed"
            raise

    async def _wait_for_final_state(self, sandbox_id: str, initial_state: str) -> str:
        """
        等待沙箱从中间状态过渡到最终状态

        Args:
            sandbox_id: 沙箱 ID
            initial_state: 初始状态

        Returns:
            最终状态
        """
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
            # 超时后返回 unknown，触发创建新沙箱
            return "unknown"

        return state

    async def _start_sandbox(self, sandbox_id: str) -> None:
        """启动沙箱"""

        def _sync_start():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            sandbox.start(timeout=60)

        await asyncio.wait_for(
            asyncio.to_thread(_sync_start),
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _get_work_dir(self, sandbox_id: str) -> str:
        """获取沙箱工作目录

        Raises:
            Exception: 如果获取工作目录失败（沙箱不存在、认证失败等）
        """

        def _sync_get_work_dir():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            return sandbox.get_work_dir()

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_get_work_dir),
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _create_backend(self, sandbox_id: str) -> "SandboxBackendProtocol":
        """为已存在的沙箱创建 backend 包装"""

        def _sync_create_backend():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            return DaytonaBackend(sandbox=sandbox)

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_create_backend),
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _create_and_bind(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple["SandboxBackendProtocol", str]:
        """创建新沙箱并绑定到 session（替换旧的）

        Returns:
            tuple[SandboxBackendProtocol, str]: (backend, work_dir)
        """

        def _sync_create():
            client = self._get_daytona_client()
            params = CreateSandboxFromSnapshotParams(
                auto_delete_interval=settings.SANDBOX_AUTO_DELETE_INTERVAL,
                auto_stop_interval=settings.SANDBOX_AUTO_STOP_INTERVAL,
                auto_archive_interval=settings.SANDBOX_AUTO_ARCHIVE_INTERVAL,
                language="python",
                snapshot=settings.DAYTONA_IMAGE if settings.DAYTONA_IMAGE else None,
            )
            sandbox = client.create(params)
            return DaytonaBackend(sandbox=sandbox), sandbox.get_work_dir()

        backend, work_dir = await asyncio.wait_for(
            asyncio.to_thread(_sync_create),
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

        # 获取 sandbox_id
        sandbox_id = backend.id

        # 更新 session metadata（覆盖旧的 sandbox_id）
        await self._update_session_metadata(session_id, sandbox_id, "running", is_new=True)

        # 更新内存缓存
        self._cache[session_id] = (sandbox_id, backend)

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox_id} for session {session_id}"
        )

        return backend, work_dir

    async def _update_session_metadata(
        self,
        session_id: str,
        sandbox_id: str,
        state: str,
        is_new: bool = False,
    ) -> None:
        """更新 session metadata"""
        now = datetime.now().isoformat()
        metadata = {
            "sandbox_id": sandbox_id,
            "sandbox_state": state,
            "sandbox_last_used_at": now,
        }
        if is_new:
            metadata["sandbox_created_at"] = now

        await self._session_manager.update_session(
            session_id,
            SessionUpdate(metadata=metadata),
        )

    def clear_cache(self, session_id: str) -> None:
        """清除内存缓存（用于测试或强制刷新）"""
        self._cache.pop(session_id, None)
