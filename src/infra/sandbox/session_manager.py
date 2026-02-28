"""
Session-Sandbox 绑定管理器

管理 Session 与 Daytona Sandbox 的绑定关系：
- 沙箱存储在 session.metadata 中
- 对话结束时 stop 而非 delete
- 下次对话时从 stopped/archived 状态恢复
"""

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
    ) -> "SandboxBackendProtocol":
        """
        获取或创建沙箱

        流程：
        1. 检查内存缓存
        2. 检查 session.metadata 中的 sandbox_id
        3. 如果存在，查询 Daytona 状态
        4. Stopped/Archived → start() 恢复
        5. 不存在或恢复失败 → 创建新沙箱，覆盖绑定
        """
        # 1. 检查内存缓存
        if session_id in self._cache:
            sandbox_id, backend = self._cache[session_id]
            logger.debug(
                f"[SessionSandboxManager] Cache hit: session={session_id}, sandbox={sandbox_id}"
            )
            return backend

        # 2. 从 session.metadata 获取 sandbox_id
        session = await self._session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        sandbox_id = session.metadata.get("sandbox_id") if session.metadata else None

        if sandbox_id:
            # 3. 查询 Daytona 状态
            state = await self._get_sandbox_state(sandbox_id)
            logger.info(f"[SessionSandboxManager] Found sandbox {sandbox_id} with state={state}")

            if state in ("stopped", "archived"):
                # 4. 尝试恢复
                try:
                    await self._start_sandbox(sandbox_id)
                    backend = await self._create_backend(sandbox_id)
                    self._cache[session_id] = (sandbox_id, backend)
                    await self._update_session_metadata(session_id, sandbox_id, "running")
                    logger.info(f"[SessionSandboxManager] Resumed sandbox {sandbox_id}")
                    return backend
                except Exception as e:
                    logger.warning(
                        f"[SessionSandboxManager] Failed to resume sandbox {sandbox_id}: {e}"
                    )
                    # 恢复失败，创建新沙箱

            elif state == "running":
                # 沙箱已在运行，直接使用
                backend = await self._create_backend(sandbox_id)
                self._cache[session_id] = (sandbox_id, backend)
                return backend

            elif state == "destroyed":
                logger.info(f"[SessionSandboxManager] Sandbox {sandbox_id} was destroyed")
                # 沙箱已销毁，创建新沙箱

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

        try:
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            sandbox.stop(timeout=30)
            await self._update_session_metadata(session_id, sandbox_id, "stopped")
            logger.info(f"[SessionSandboxManager] Stopped sandbox {sandbox_id}")
            return True
        except Exception as e:
            logger.error(f"[SessionSandboxManager] Failed to stop sandbox {sandbox_id}: {e}")
            return False

    async def _get_sandbox_state(self, sandbox_id: str) -> str:
        """查询沙箱状态: running / stopped / archived / destroyed"""
        try:
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            # state 是 SandboxState 枚举，转换为小写字符串
            state = str(sandbox.state).lower()
            return state
        except Exception as e:
            # 如果沙箱不存在，返回 destroyed
            if "not found" in str(e).lower():
                return "destroyed"
            raise

    async def _start_sandbox(self, sandbox_id: str) -> None:
        """启动沙箱"""
        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        sandbox.start(timeout=60)

    async def _create_backend(self, sandbox_id: str) -> "SandboxBackendProtocol":
        """为已存在的沙箱创建 backend 包装"""
        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        return DaytonaBackend(sandbox=sandbox)

    async def _create_and_bind(
        self,
        session_id: str,
        user_id: str,
    ) -> "SandboxBackendProtocol":
        """创建新沙箱并绑定到 session（替换旧的）"""
        client = self._get_daytona_client()

        # 创建带 auto_stop_interval 的沙箱
        params = CreateSandboxFromSnapshotParams(
            auto_stop_interval=settings.SANDBOX_AUTO_STOP_INTERVAL,
            language="python",
        )
        sandbox = client.create(params)
        backend = DaytonaBackend(sandbox=sandbox)

        # 更新 session metadata（覆盖旧的 sandbox_id）
        await self._update_session_metadata(session_id, sandbox.id, "running", is_new=True)

        # 更新内存缓存
        self._cache[session_id] = (sandbox.id, backend)

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox.id} for session {session_id}"
        )

        return backend

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
