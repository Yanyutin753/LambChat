"""
User-Sandbox 绑定管理器

管理 User 与 Daytona Sandbox 的绑定关系：
- 沙箱绑定关系存储在 MongoDB user_sandbox_bindings 集合中
- 每个用户对应一个沙箱，跨 session 共享
- 沙箱在空闲时由 Daytona 自动 stop/archive
- 下次对话时从 stopped/archived 状态恢复
- 使用 deepagents.CompositeBackend 组合 Sandbox 和 Skills Store
"""

import asyncio
import threading
from datetime import datetime
from typing import Optional

from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig
from deepagents.backends import CompositeBackend

from src.infra.backend.daytona import DaytonaBackend
from src.infra.backend.skills_store import create_skills_backend
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

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

# MongoDB 集合名
BINDING_COLLECTION = "user_sandbox_bindings"


class SessionSandboxManager:
    """管理 User 与 Sandbox 的绑定关系（每个用户一个沙箱，跨 session 共享）"""

    def __init__(self):
        self._daytona_client: Optional[Daytona] = None
        self._collection = None
        # 内存缓存: user_id -> (sandbox_id, backend)
        self._cache: dict[str, tuple[str, CompositeBackend]] = {}
        # 每用户锁，防止并发创建重复沙箱
        self._locks: dict[str, asyncio.Lock] = {}
        # 用于 _locks 字典的线程安全（asyncio.Lock 创建可能在非 event loop 线程触发）
        self._locks_mutex = threading.Lock()

    @property
    def _bindings(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[BINDING_COLLECTION]
        return self._collection

    def _get_daytona_client(self) -> Daytona:
        """获取或创建 Daytona 客户端"""
        if self._daytona_client is None:
            config = DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                server_url=settings.DAYTONA_SERVER_URL,
            )
            self._daytona_client = Daytona(config)
        return self._daytona_client

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户级锁（线程安全）"""
        with self._locks_mutex:
            if user_id not in self._locks:
                self._locks[user_id] = asyncio.Lock()
            return self._locks[user_id]

    async def _get_binding(self, user_id: str) -> Optional[dict]:
        """从 MongoDB 获取用户的沙箱绑定"""
        doc = await self._bindings.find_one({"user_id": user_id})
        return doc

    async def _save_binding(
        self,
        user_id: str,
        sandbox_id: str,
        state: str,
        is_new: bool = False,
    ) -> None:
        """保存/更新用户的沙箱绑定"""
        now = datetime.now().isoformat()
        update = {
            "$set": {
                "sandbox_id": sandbox_id,
                "sandbox_state": state,
                "sandbox_last_used_at": now,
            },
        }
        # 仅在首次创建时设置 sandbox_created_at
        if is_new:
            update["$set"]["sandbox_created_at"] = now
        else:
            update["$setOnInsert"] = {"sandbox_created_at": now}

        await self._bindings.update_one(
            {"user_id": user_id},
            update,
            upsert=True,
        )

    async def get_or_create(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[CompositeBackend, str]:
        """
        获取或创建沙箱

        返回 CompositeBackend，组合了 Sandbox 和 Skills Store。
        LLM 可以通过 /skills/ 路径读写用户技能。

        沙箱按用户维度绑定，同一用户的多个 session 共享同一个沙箱。

        流程：
        1. 检查内存缓存（user_id 维度）
        2. 检查 MongoDB 中的 user_sandbox_bindings
        3. 如果存在，查询 Daytona 状态
        4. Stopped/Archived → start() 恢复
        5. 不存在或恢复失败 → 创建新沙箱，覆盖绑定

        Args:
            session_id: 当前会话 ID（仅用于日志追踪，不影响沙箱绑定）
            user_id: 用户 ID（沙箱绑定的实际维度）

        Returns:
            tuple[CompositeBackend, str]: (composite_backend, work_dir)
        """
        if not user_id:
            raise ValueError("user_id must not be empty")

        lock = self._get_user_lock(user_id)

        async with lock:
            # 1. 检查内存缓存
            if user_id in self._cache:
                sandbox_id, backend = self._cache[user_id]
                logger.debug(
                    f"[SessionSandboxManager] Cache hit: user={user_id}, sandbox={sandbox_id}"
                )
                try:
                    work_dir = await self._get_work_dir(sandbox_id)
                    await self._save_binding(user_id, sandbox_id, "running")
                    return backend, work_dir
                except Exception as e:
                    logger.warning(
                        f"[SessionSandboxManager] Failed to get work_dir from cached sandbox {sandbox_id}: {e}. "
                        "Creating new sandbox."
                    )
                    del self._cache[user_id]

            # 2. 从 MongoDB 获取绑定
            binding = await self._get_binding(user_id)
            metadata_sandbox_id: str | None = binding.get("sandbox_id") if binding else None

            if metadata_sandbox_id:
                sandbox_id = metadata_sandbox_id
                # 3. 查询 Daytona 状态
                state = await self._get_sandbox_state(sandbox_id)
                logger.info(
                    f"[SessionSandboxManager] Found sandbox {sandbox_id} with state={state}"
                )

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
                        backend = await self._create_backend(sandbox_id, user_id=user_id)
                        self._cache[user_id] = (sandbox_id, backend)
                        await self._save_binding(user_id, sandbox_id, "running")
                        logger.info(f"[SessionSandboxManager] Resumed sandbox {sandbox_id}")
                        work_dir = await self._get_work_dir(sandbox_id)
                        return backend, work_dir
                    except Exception as e:
                        logger.warning(
                            f"[SessionSandboxManager] Failed to resume sandbox {sandbox_id}: {e}. "
                            "Creating new sandbox."
                        )
                        if user_id in self._cache:
                            del self._cache[user_id]

                elif state in READY_STATES:
                    try:
                        backend = await self._create_backend(sandbox_id, user_id=user_id)
                        self._cache[user_id] = (sandbox_id, backend)
                        await self._save_binding(user_id, sandbox_id, "running")
                        work_dir = await self._get_work_dir(sandbox_id)
                        return backend, work_dir
                    except Exception as e:
                        logger.warning(
                            f"[SessionSandboxManager] Failed to get work_dir from sandbox {sandbox_id}: {e}. "
                            "Creating new sandbox."
                        )
                        if user_id in self._cache:
                            del self._cache[user_id]

                elif state in UNAVAILABLE_STATES:
                    logger.info(
                        f"[SessionSandboxManager] Sandbox {sandbox_id} is unavailable (state={state})"
                    )

            # 5. 创建新沙箱并绑定
            return await self._create_and_bind(session_id, user_id)

    async def stop(self, user_id: str) -> bool:
        """
        停止用户的沙箱

        持有用户锁执行，防止与 get_or_create 竞态。

        Args:
            user_id: 用户 ID

        Returns:
            是否成功停止
        """
        if not user_id:
            raise ValueError("user_id must not be empty")

        lock = self._get_user_lock(user_id)

        async with lock:
            sandbox_id: str | None = None

            if user_id in self._cache:
                sandbox_id, _ = self._cache[user_id]
            else:
                binding = await self._get_binding(user_id)
                sandbox_id = binding.get("sandbox_id") if binding else None

            if not sandbox_id:
                return False

            def _sync_stop():
                client = self._get_daytona_client()
                sandbox = client.get(sandbox_id)
                sandbox.stop(timeout=30)

            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_sync_stop),
                    timeout=DEFAULT_DAYTONA_TIMEOUT,
                )
                # stop 成功后清除缓存，避免下次 get_or_create cache hit 后对 stopped 沙箱操作失败
                self._cache.pop(user_id, None)
                await self._save_binding(user_id, sandbox_id, "stopped")
                logger.info(
                    f"[SessionSandboxManager] Stopped sandbox {sandbox_id} for user {user_id}"
                )
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

        await asyncio.wait_for(
            asyncio.to_thread(_sync_start),
            timeout=DEFAULT_DAYTONA_TIMEOUT,
        )

    async def _get_work_dir(self, sandbox_id: str) -> str:
        """获取沙箱工作目录"""

        def _sync_get_work_dir():
            client = self._get_daytona_client()
            sandbox = client.get(sandbox_id)
            return sandbox.get_work_dir()

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_get_work_dir),
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

        return await asyncio.wait_for(
            asyncio.to_thread(_sync_create_backend),
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
            daytona_backend = DaytonaBackend(sandbox=sandbox)
            skills_backend = create_skills_backend(user_id=user_id)
            composite_backend = CompositeBackend(
                default=daytona_backend,
                routes={
                    "/skills/": skills_backend,
                },
            )
            return composite_backend, sandbox.get_work_dir(), daytona_backend.id

        backend, work_dir, sandbox_id = await asyncio.wait_for(
            asyncio.to_thread(_sync_create),
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
                await asyncio.to_thread(self._delete_sandbox, sandbox_id)
            except Exception as cleanup_err:
                logger.error(
                    f"[SessionSandboxManager] Failed to clean up orphan sandbox {sandbox_id}: {cleanup_err}"
                )
            raise

        # 更新内存缓存
        self._cache[user_id] = (sandbox_id, backend)

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox_id} for user {user_id} (session={session_id})"
        )

        return backend, work_dir

    def _delete_sandbox(self, sandbox_id: str) -> None:
        """删除沙箱（同步，用于 to_thread）"""
        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        sandbox.delete()

    def clear_cache(self, user_id: str) -> None:
        """清除内存缓存（用于测试或强制刷新）"""
        self._cache.pop(user_id, None)
