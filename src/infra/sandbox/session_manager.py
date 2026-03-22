"""
User-Sandbox 绑定管理器

管理 User 与 Sandbox 的绑定关系，支持 Daytona 和 E2B 平台。
- 沙箱绑定关系存储在 MongoDB user_sandbox_bindings 集合中
- 每个用户对应一个沙箱，跨 session 共享
- 沙箱在空闲时自动 stop/archive (Daytona) 或超时销毁 (E2B)
- 使用 deepagents.CompositeBackend 组合 Sandbox 和 Skills Store
"""

import asyncio
import threading
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from daytona import Daytona

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

# 每用户锁的最大数量（LRU 淘汰）
_MAX_LOCKS = 10_000


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

    def create_sandbox(self, user_id: str | None = None) -> tuple[object, str]:
        """创建沙箱，支持 lifecycle 配置和 metadata"""
        self._sync_from_settings()
        e2b_class = self._get_e2b_class()

        kwargs: dict = {
            "template": self._template,
            "timeout": self._timeout,
            "api_key": self._api_key or None,
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


class SessionSandboxManager:
    """管理 User 与 Sandbox 的绑定关系（每个用户一个沙箱，跨 session 共享）"""

    def __init__(self):
        self._daytona_client: Optional["Daytona"] = None
        self._e2b_adapter: Optional[E2BSandboxAdapter] = None
        self._collection: Any = None
        self._cache: dict[str, tuple[str, CompositeBackend, object | None]] = {}
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._locks_mutex = threading.Lock()

        platform = settings.SANDBOX_PLATFORM.lower()
        if platform == "e2b":
            self._e2b_adapter = E2BSandboxAdapter(
                api_key=settings.E2B_API_KEY,
                template=settings.E2B_TEMPLATE,
                timeout=settings.E2B_TIMEOUT,
                auto_pause=getattr(settings, "E2B_AUTO_PAUSE", True),
                auto_resume=getattr(settings, "E2B_AUTO_RESUME", True),
            )

    @property
    def _bindings(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[BINDING_COLLECTION]
            # 在后台异步创建索引（幂等，已存在则跳过）
            try:
                asyncio.create_task(self._ensure_index())
            except RuntimeError:
                # 没有 event loop 时（如测试），同步创建
                pass
        assert self._collection is not None
        return self._collection

    async def _ensure_index(self):
        """异步创建索引"""
        try:
            await self._collection.create_index(
                "user_id",
                unique=True,
                name="user_id_unique_idx",
                background=True,
            )
        except Exception as e:
            logger.warning(f"Failed to create index on {BINDING_COLLECTION}: {e}")

    def _get_daytona_client(self):
        """获取或创建 Daytona 客户端"""
        from daytona import Daytona, DaytonaConfig

        if self._daytona_client is None:
            config = DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                server_url=settings.DAYTONA_SERVER_URL,
            )
            self._daytona_client = Daytona(config)
        return self._daytona_client

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户级锁（线程安全，LRU 淘汰）"""
        with self._locks_mutex:
            if user_id in self._locks:
                # 移到末尾表示最近使用
                self._locks.move_to_end(user_id)
            else:
                # 超出上限时淘汰最久未使用的锁
                while len(self._locks) >= _MAX_LOCKS:
                    self._locks.popitem(last=False)
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
            raise ValueError(
                "user_id is required for sandbox binding. "
                "Anonymous users cannot use sandbox features."
            )

        if self._e2b_adapter:
            return await self._get_or_create_e2b(session_id, user_id)

        lock = self._get_user_lock(user_id)

        async with lock:
            # 1. 检查内存缓存
            if user_id in self._cache:
                sandbox_id, backend, _ = self._cache[user_id]
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
                        self._cache[user_id] = (sandbox_id, backend, None)
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
                        self._cache[user_id] = (sandbox_id, backend, None)
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
            raise ValueError(
                "user_id is required for sandbox binding. "
                "Anonymous users cannot use sandbox features."
            )

        if self._e2b_adapter:
            return await self._stop_e2b(user_id)

        lock = self._get_user_lock(user_id)

        async with lock:
            sandbox_id: str | None = None

            if user_id in self._cache:
                sandbox_id, _, _ = self._cache[user_id]
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
        from daytona import CreateSandboxFromSnapshotParams

        def _sync_create():
            client = self._get_daytona_client()
            params = CreateSandboxFromSnapshotParams(
                auto_delete_interval=settings.DAYTONA_AUTO_DELETE_INTERVAL,
                auto_stop_interval=settings.DAYTONA_AUTO_STOP_INTERVAL,
                auto_archive_interval=settings.DAYTONA_AUTO_ARCHIVE_INTERVAL,
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
        self._cache[user_id] = (sandbox_id, backend, None)

        logger.info(
            f"[SessionSandboxManager] Created sandbox {sandbox_id} for user {user_id} (session={session_id})"
        )

        return backend, work_dir

    def _delete_sandbox(self, sandbox_id: str) -> None:
        """删除沙箱（同步，用于 to_thread）"""

        client = self._get_daytona_client()
        sandbox = client.get(sandbox_id)
        sandbox.delete()

    # ── E2B platform methods ──────────────────────────────────────────

    async def _get_or_create_e2b(
        self, session_id: str, user_id: str
    ) -> tuple[CompositeBackend, str]:
        assert self._e2b_adapter is not None
        lock = self._get_user_lock(user_id)
        async with lock:
            if user_id in self._cache:
                sandbox_id, backend, provider_obj = self._cache[user_id]
                try:
                    if self._e2b_adapter.sandbox_is_running(provider_obj):
                        self._e2b_adapter.extend_timeout(provider_obj, settings.E2B_TIMEOUT)
                        await self._save_binding(user_id, sandbox_id, "running")
                        return backend, self._e2b_adapter.get_work_dir(provider_obj)
                except Exception as e:
                    logger.warning(f"[E2B] Cache hit but sandbox {sandbox_id} unhealthy: {e}")
                del self._cache[user_id]

            binding = await self._get_binding(user_id)
            metadata_sandbox_id = binding.get("sandbox_id") if binding else None
            if metadata_sandbox_id:
                # Sandbox.connect() 会自动恢复暂停的沙箱
                provider_obj = await asyncio.to_thread(
                    self._e2b_adapter.get_sandbox, metadata_sandbox_id
                )
                if provider_obj:
                    try:
                        self._e2b_adapter.extend_timeout(provider_obj, settings.E2B_TIMEOUT)
                        backend = self._build_composite_backend(provider_obj, user_id)
                        self._cache[user_id] = (metadata_sandbox_id, backend, provider_obj)
                        info = self._e2b_adapter.get_sandbox_info(provider_obj)
                        await self._save_binding(
                            user_id, metadata_sandbox_id, info.get("state", "running")
                        )
                        return backend, self._e2b_adapter.get_work_dir(provider_obj)
                    except Exception as e:
                        logger.warning(f"[E2B] Failed to reconnect {metadata_sandbox_id}: {e}")

            return await self._create_and_bind_e2b(session_id, user_id)

    async def _create_and_bind_e2b(
        self, session_id: str, user_id: str
    ) -> tuple[CompositeBackend, str]:
        assert self._e2b_adapter is not None
        adapter = self._e2b_adapter
        from src.infra.backend.e2b import E2BBackend

        def _sync_create():
            sandbox, work_dir = adapter.create_sandbox(user_id=user_id)
            e2b_backend = E2BBackend(sandbox=sandbox)
            skills_backend = create_skills_backend(user_id=user_id)
            composite = CompositeBackend(default=e2b_backend, routes={"/skills/": skills_backend})
            return composite, work_dir, adapter.get_sandbox_id(sandbox), sandbox

        backend, work_dir, sandbox_id, provider_obj = await asyncio.to_thread(_sync_create)
        try:
            await self._save_binding(user_id, sandbox_id, "running", is_new=True)
        except Exception as e:
            logger.error(f"[E2B] Created {sandbox_id} but failed to save binding: {e}")
            try:
                await asyncio.to_thread(self._e2b_adapter.stop_sandbox, provider_obj)
            except Exception:
                pass
            raise
        self._cache[user_id] = (sandbox_id, backend, provider_obj)
        logger.info(f"[E2B] Created sandbox {sandbox_id} for user {user_id} (session={session_id})")
        return backend, work_dir

    def _build_composite_backend(self, provider_obj: object, user_id: str) -> CompositeBackend:
        from src.infra.backend.e2b import E2BBackend

        return CompositeBackend(
            default=E2BBackend(sandbox=provider_obj),
            routes={"/skills/": create_skills_backend(user_id=user_id)},
        )

    async def _stop_e2b(self, user_id: str) -> bool:
        assert self._e2b_adapter is not None
        lock = self._get_user_lock(user_id)
        async with lock:
            if user_id in self._cache:
                sandbox_id, _, provider_obj = self._cache[user_id]
                try:
                    # stop_sandbox 优先 pause（保留数据），失败则 kill
                    await asyncio.to_thread(self._e2b_adapter.stop_sandbox, provider_obj)
                    self._cache.pop(user_id, None)
                    await self._save_binding(user_id, sandbox_id, "paused")
                    logger.info(f"[E2B] Paused sandbox {sandbox_id} for user {user_id}")
                    return True
                except Exception as e:
                    logger.error(f"[E2B] Failed to stop sandbox: {e}")
                    return False
            return False

    def clear_cache(self, user_id: str) -> None:
        """清除内存缓存（用于测试或强制刷新）"""
        self._cache.pop(user_id, None)

    async def close_all(self) -> None:
        """停止所有缓存中的沙箱并清理资源（应用关闭时调用）"""
        # 复制一份，避免迭代过程中修改
        entries = list(self._cache.items())
        for user_id, (sandbox_id, _backend, provider_obj) in entries:
            try:
                await self.stop(user_id)
            except Exception as e:
                logger.warning(
                    f"[SessionSandboxManager] Failed to stop sandbox {sandbox_id} "
                    f"for user {user_id} during shutdown: {e}"
                )
        self._cache.clear()
        with self._locks_mutex:
            self._locks.clear()
        logger.info("[SessionSandboxManager] All sandboxes stopped and resources cleaned up")


# Singleton
_session_sandbox_manager: Optional[SessionSandboxManager] = None


def get_session_sandbox_manager() -> SessionSandboxManager:
    """获取 SessionSandboxManager 单例"""
    global _session_sandbox_manager
    if _session_sandbox_manager is None:
        _session_sandbox_manager = SessionSandboxManager()
    return _session_sandbox_manager
