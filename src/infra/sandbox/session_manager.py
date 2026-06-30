"""
User-Sandbox 绑定管理器

管理 User 与 Sandbox 的绑定关系，支持 Daytona、E2B 和 CubeSandbox 平台。
- 沙箱绑定关系存储在 MongoDB user_sandbox_bindings 集合中
- 每个用户对应一个沙箱，跨 session 共享
- 沙箱在空闲时自动 stop/archive (Daytona) 或超时销毁 (E2B)
- 使用 deepagents.CompositeBackend 组合 Sandbox 和 Skills Store

平台特定的生命周期逻辑分别放在 _daytona_helpers、_e2b_helpers、
_cubesandbox_helpers 模块中，通过 mixin 组合到本类。
"""

import asyncio
import re
import shlex
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from cubesandbox import Sandbox as CubeSandbox
    from daytona import Daytona
    from e2b import Sandbox as E2BSandbox

from deepagents.backends import CompositeBackend
from deepagents.backends.protocol import SandboxBackendProtocol

from src.infra.async_utils import run_blocking_io
from src.infra.backend.daytona import DaytonaBackend
from src.infra.backend.skills_store import create_skills_backend
from src.infra.logging import get_logger
from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings

from ._adapters import (
    _MAX_CACHE_ENTRIES,
    _MAX_LOCKS,
    _MAX_READY_WORK_DIRS,
    BINDING_COLLECTION,
    DEFAULT_DAYTONA_TIMEOUT,
    READY_STATES,
    RESUMABLE_STATES,
    TRANSITIONAL_STATES,
    UNAVAILABLE_STATES,
    CubeSandboxAdapter,
    E2BSandboxAdapter,
)
from ._cubesandbox_helpers import _CubeSandboxMixin
from ._daytona_helpers import _DaytonaMixin
from ._e2b_helpers import _E2BMixin

logger = get_logger(__name__)

# Re-export for backward compatibility (tests access sandbox_module.BINDING_COLLECTION)
__all__ = [
    "SessionSandboxManager",
    "close_session_sandbox_manager",
    "ensure_sandbox_mcp",
    "get_session_sandbox_manager",
]


class SessionSandboxManager(_DaytonaMixin, _E2BMixin, _CubeSandboxMixin):
    """管理 User 与 Sandbox 的绑定关系（每个用户一个沙箱，跨 session 共享）"""

    _index_task: asyncio.Task[None] | None = None
    _index_ensured = False

    def __init__(self):
        self._daytona_client: Optional["Daytona"] = None
        self._e2b_adapter: Optional[E2BSandboxAdapter] = None
        self._cube_adapter: Optional[CubeSandboxAdapter] = None
        self._collection: Any = None
        self._cache: OrderedDict[str, tuple[str, CompositeBackend, object | None]] = OrderedDict()
        self._ready_work_dirs: OrderedDict[str, None] = OrderedDict()
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
        elif platform == "cubesandbox":
            self._cube_adapter = CubeSandboxAdapter(
                api_url=settings.CUBE_API_URL,
                template=settings.CUBE_TEMPLATE,
                proxy_node_ip=settings.CUBE_PROXY_NODE_IP,
                proxy_port_http=settings.CUBE_PROXY_PORT_HTTP,
                sandbox_domain=settings.CUBE_SANDBOX_DOMAIN,
                timeout=settings.CUBE_TIMEOUT,
                request_timeout=settings.CUBE_REQUEST_TIMEOUT,
                auto_pause=getattr(settings, "CUBE_AUTO_PAUSE", True),
                auto_resume=getattr(settings, "CUBE_AUTO_RESUME", True),
            )

    # ── Infrastructure / state plumbing ─────────────────────────────

    @property
    def _bindings(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[BINDING_COLLECTION]
            self._schedule_index()
        assert self._collection is not None
        return self._collection

    def _schedule_index(self) -> None:
        cls = type(self)
        if cls._index_ensured:
            return
        task = cls._index_task
        if task is not None and not task.done():
            return
        try:
            task = asyncio.create_task(self._ensure_index())
        except RuntimeError:
            return
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        cls._index_task = task
        cls._index_ensured = True

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

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户级锁（线程安全，LRU 淘汰）"""
        with self._locks_mutex:
            if user_id in self._locks:
                # 移到末尾表示最近使用
                self._locks.move_to_end(user_id)
            else:
                # 超出上限时淘汰最久未使用的锁
                while len(self._locks) >= _MAX_LOCKS:
                    evicted = False
                    for existing_user_id, existing_lock in list(self._locks.items()):
                        if existing_lock.locked():
                            continue
                        self._locks.pop(existing_user_id, None)
                        evicted = True
                        break
                    # 如果所有锁都在使用中，宁可临时超出上限也不要破坏互斥语义
                    if not evicted:
                        break
                self._locks[user_id] = asyncio.Lock()
            return self._locks[user_id]

    def _binding_platform(self) -> str:
        """Return the active sandbox platform used to scope persisted bindings."""
        return settings.SANDBOX_PLATFORM.lower()

    async def _get_binding(self, user_id: str) -> Optional[dict]:
        """从 MongoDB 获取当前平台的用户沙箱绑定"""
        doc = await self._bindings.find_one({"user_id": user_id})
        if not doc:
            return None

        platform = self._binding_platform()
        platform_binding = (doc.get("sandboxes") or {}).get(platform)
        if platform_binding:
            scoped_doc = dict(doc)
            scoped_doc.update(platform_binding)
            scoped_doc["sandbox_platform"] = platform
            return scoped_doc

        # Backward compatibility for records written before platform-scoped
        # bindings existed. Once saved again, the platform slot is populated.
        legacy_platform = doc.get("sandbox_platform")
        if legacy_platform is None or legacy_platform == platform:
            return doc
        return None

    def _evict_if_needed(self) -> None:
        """淘汰最久未使用的缓存条目（LRU），防止内存泄漏。

        仅移除内存引用，不停止沙箱（平台有自己的 auto-stop/auto-archive 生命周期）。
        下次访问会从 MongoDB binding 重新创建。
        """
        while len(self._cache) > _MAX_CACHE_ENTRIES:
            evicted_user_id, (sandbox_id, _, _) = self._cache.popitem(last=False)
            logger.info(
                f"[SessionSandboxManager] Evicted LRU cache entry: "
                f"user={evicted_user_id}, sandbox={sandbox_id}"
            )

    # ── Work-directory management ───────────────────────────────────

    def _session_work_dir(self, base_work_dir: str, session_id: str) -> str:
        """Return a stable, shell-safe workspace directory for a session."""
        safe_session_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip(".-")
        if not safe_session_id:
            safe_session_id = "session"
        return f"{base_work_dir.rstrip('/')}/sessions/{safe_session_id[:80]}"

    async def _ensure_work_dir(self, backend: CompositeBackend, work_dir: str) -> None:
        sandbox_backend = cast(SandboxBackendProtocol, backend.default)
        sandbox_id = str(getattr(sandbox_backend, "id", "unknown"))
        cache_key = f"{sandbox_id}:{work_dir}"
        if cache_key in self._ready_work_dirs:
            self._ready_work_dirs.move_to_end(cache_key)
            return

        result = await sandbox_backend.aexecute(f"mkdir -p {shlex.quote(work_dir)}")
        if getattr(result, "exit_code", 0) != 0:
            raise RuntimeError(f"Failed to create session work_dir {work_dir}: {result.output}")
        self._ready_work_dirs[cache_key] = None
        while len(self._ready_work_dirs) > _MAX_READY_WORK_DIRS:
            self._ready_work_dirs.popitem(last=False)

    # ── Backend scoping ──────────────────────────────────────────────

    def _scope_daytona_backend(
        self,
        backend: CompositeBackend,
        user_id: str,
        work_dir: str,
    ) -> CompositeBackend:
        default = backend.default
        if not isinstance(default, DaytonaBackend):
            return backend
        daytona_backend = DaytonaBackend(
            sandbox=default._sandbox,
            timeout=default._timeout,
            env_vars=default.env_vars,
            work_dir=work_dir,
        )
        return CompositeBackend(
            default=daytona_backend,
            routes={"/skills/": create_skills_backend(user_id=user_id)},
        )

    def _scope_e2b_backend(
        self,
        provider_obj: object,
        user_id: str,
        work_dir: str,
    ) -> CompositeBackend:
        from src.infra.backend.e2b import E2BBackend

        return CompositeBackend(
            default=E2BBackend(sandbox=cast("E2BSandbox", provider_obj), work_dir=work_dir),
            routes={"/skills/": create_skills_backend(user_id=user_id)},
        )

    def _scope_cube_backend(
        self,
        provider_obj: object,
        user_id: str,
        work_dir: str,
    ) -> CompositeBackend:
        from src.infra.backend.cubesandbox import CubeSandboxBackend

        return CompositeBackend(
            default=CubeSandboxBackend(
                sandbox=cast("CubeSandbox", provider_obj),
                work_dir=work_dir,
            ),
            routes={"/skills/": create_skills_backend(user_id=user_id)},
        )

    # ── Binding persistence ─────────────────────────────────────────

    async def _save_binding(
        self,
        user_id: str,
        sandbox_id: str,
        state: str,
        is_new: bool = False,
    ) -> None:
        """保存/更新用户的沙箱绑定"""
        now = utc_now_iso()
        platform = self._binding_platform()
        update = {
            "$set": {
                "sandbox_platform": platform,
                "sandbox_id": sandbox_id,
                "sandbox_state": state,
                "sandbox_last_used_at": now,
                f"sandboxes.{platform}.sandbox_id": sandbox_id,
                f"sandboxes.{platform}.sandbox_state": state,
                f"sandboxes.{platform}.sandbox_last_used_at": now,
                f"sandboxes.{platform}.sandbox_platform": platform,
            },
        }
        # 仅在首次创建时设置 sandbox_created_at
        if is_new:
            update["$set"]["sandbox_created_at"] = now
            update["$set"][f"sandboxes.{platform}.sandbox_created_at"] = now
        else:
            update["$setOnInsert"] = {
                "sandbox_created_at": now,
                f"sandboxes.{platform}.sandbox_created_at": now,
            }

        await self._bindings.update_one(
            {"user_id": user_id},
            update,
            upsert=True,
        )

    # ── Public API ──────────────────────────────────────────────────

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
        if self._cube_adapter:
            return await self._get_or_create_cubesandbox(session_id, user_id)

        lock = self._get_user_lock(user_id)

        async with lock:
            # 1. 检查内存缓存
            if user_id in self._cache:
                self._cache.move_to_end(user_id)  # LRU: mark as recently used
                sandbox_id, backend, _ = self._cache[user_id]
                logger.debug(
                    f"[SessionSandboxManager] Cache hit: user={user_id}, sandbox={sandbox_id}"
                )
                try:
                    base_work_dir = await self._get_work_dir(sandbox_id)
                    work_dir = self._session_work_dir(base_work_dir, session_id)
                    scoped_backend = self._scope_daytona_backend(backend, user_id, work_dir)
                    await self._ensure_work_dir(scoped_backend, work_dir)
                    await self._save_binding(user_id, sandbox_id, "running")
                    from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp

                    await ensure_sandbox_mcp(scoped_backend, user_id)
                    return scoped_backend, work_dir
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
                        self._evict_if_needed()
                        await self._save_binding(user_id, sandbox_id, "running")
                        base_work_dir = await self._get_work_dir(sandbox_id)
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_daytona_backend(backend, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp

                        await ensure_sandbox_mcp(scoped_backend, user_id)
                        return scoped_backend, work_dir
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
                        self._evict_if_needed()
                        await self._save_binding(user_id, sandbox_id, "running")
                        base_work_dir = await self._get_work_dir(sandbox_id)
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_daytona_backend(backend, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp

                        await ensure_sandbox_mcp(scoped_backend, user_id)
                        return scoped_backend, work_dir
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
        if self._cube_adapter:
            return await self._stop_cubesandbox(user_id)

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
                await run_blocking_io(
                    _sync_stop,
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

    # ── Cache management ────────────────────────────────────────────

    def clear_cache(self, user_id: str) -> None:
        """清除内存缓存（用于测试或强制刷新）"""
        self._cache.pop(user_id, None)

    def get_cached_backend(self, user_id: str):
        """Return the currently cached backend for a user, if one exists."""
        entry = self._cache.get(user_id)
        if entry is None:
            return None
        return entry[1]

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
        task = type(self)._index_task
        type(self)._index_task = None
        type(self)._index_ensured = False
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._collection = None
        logger.info("[SessionSandboxManager] All sandboxes stopped and resources cleaned up")


# Singleton
_session_sandbox_manager: Optional[SessionSandboxManager] = None


def get_session_sandbox_manager() -> SessionSandboxManager:
    """获取 SessionSandboxManager 单例"""
    global _session_sandbox_manager
    if _session_sandbox_manager is None:
        _session_sandbox_manager = SessionSandboxManager()
    return _session_sandbox_manager


async def close_session_sandbox_manager() -> None:
    global _session_sandbox_manager
    manager = _session_sandbox_manager
    _session_sandbox_manager = None
    if manager is not None:
        await manager.close_all()
