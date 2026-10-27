"""CubeSandbox-specific helper methods for SessionSandboxManager.

These are mixed into SessionSandboxManager via multiple inheritance.
All methods assume `self` provides the shared infra (cache, bindings, locks, etc.).
"""

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional, cast

from deepagents.backends import CompositeBackend

from src.infra.async_utils import run_blocking_io as _run_blocking_io
from src.infra.async_utils import run_long_blocking_io as _run_long_blocking_io
from src.infra.backend.resource_authority import AuthorizedCompositeBackend
from src.infra.backend.skills_store import create_skills_backend
from src.infra.envvar.sync import sync_sandbox_env_vars
from src.infra.logging import get_logger

if TYPE_CHECKING:
    from cubesandbox import Sandbox as CubeSandbox

    from ._adapters import CubeSandboxAdapter

logger = get_logger(__name__)


def run_blocking_io(*args, **kwargs):
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "run_blocking_io", _run_blocking_io)(*args, **kwargs)


def run_long_blocking_io(*args, **kwargs):
    """慢道间接层（沙箱 create/connect/stop 等秒级调用），测试可拦截。"""
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "run_long_blocking_io", _run_long_blocking_io)(*args, **kwargs)


class _CubeSandboxMixin:
    """CubeSandbox platform lifecycle methods for SessionSandboxManager."""

    if TYPE_CHECKING:
        _cube_adapter: Optional["CubeSandboxAdapter"]
        _cache: OrderedDict[str, tuple[str, CompositeBackend, object | None]]

        def _get_user_lock(self, user_id: str) -> asyncio.Lock: ...

        async def _get_binding(self, user_id: str) -> Any | None: ...

        async def _save_binding(
            self,
            user_id: str,
            sandbox_id: str,
            state: str,
            is_new: bool = False,
            previous_sandbox_id: str | None = None,
        ) -> None: ...

        def _evict_if_needed(self) -> None: ...

        def _session_work_dir(self, base_work_dir: str, session_id: str) -> str: ...

        def _scope_cube_backend(
            self,
            provider_obj: object,
            user_id: str,
            work_dir: str,
        ) -> CompositeBackend: ...

        async def _ensure_work_dir(self, backend: CompositeBackend, work_dir: str) -> None: ...

        async def _verify_cloud_storage(
            self, backend: CompositeBackend, storage: dict | None
        ) -> None: ...

        async def _prepare_cloud_storage(self, user_id: str) -> dict | None: ...

        async def _cloud_work_dir(
            self, user_id: str, fallback: str, backend: CompositeBackend
        ) -> str: ...

        async def _get_user_env_vars(self, user_id: str) -> dict[str, str]: ...

    async def _get_or_create_cubesandbox(
        self, session_id: str, user_id: str, *, create: bool = True
    ) -> tuple[CompositeBackend, str]:
        assert self._cube_adapter is not None
        from src.infra.sandbox.session_manager import SandboxPeekError
        from src.kernel.config import settings

        lock = self._get_user_lock(user_id)
        async with lock:
            unusable_sandbox_ids: set[str] = set()
            if user_id in self._cache:
                self._cache.move_to_end(user_id)
                sandbox_id, _backend, provider_obj = self._cache[user_id]
                try:
                    is_running = await run_blocking_io(
                        self._cube_adapter.sandbox_is_running,
                        provider_obj,
                    )
                    if is_running:
                        await run_blocking_io(
                            self._cube_adapter.extend_timeout,
                            provider_obj,
                            settings.CUBE_TIMEOUT,
                        )
                        await self._save_binding(user_id, sandbox_id, "running")
                        base_work_dir = await run_blocking_io(
                            self._cube_adapter.get_work_dir,
                            provider_obj,
                        )
                        base_work_dir = await self._cloud_work_dir(
                            user_id, base_work_dir, self._cache[user_id][1]
                        )
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_cube_backend(provider_obj, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        await sync_sandbox_env_vars(scoped_backend, user_id)
                        self._schedule_duplicate_cubesandbox_cleanup(
                            user_id, keep_sandbox_id=sandbox_id
                        )
                        return scoped_backend, work_dir
                except Exception as e:
                    logger.warning(
                        f"[CubeSandbox] Cache hit but sandbox {sandbox_id} unhealthy: {e}"
                    )
                    unusable_sandbox_ids.add(sandbox_id)
                del self._cache[user_id]

            binding = await self._get_binding(user_id) or {}
            metadata_sandbox_id = binding.get("sandbox_id") if binding else None
            if metadata_sandbox_id:
                provider_obj = await run_long_blocking_io(
                    self._cube_adapter.get_sandbox, metadata_sandbox_id
                )
                if provider_obj:
                    try:
                        await run_blocking_io(
                            self._cube_adapter.extend_timeout,
                            provider_obj,
                            settings.CUBE_TIMEOUT,
                        )
                        backend = self._build_cube_composite_backend(provider_obj, user_id)
                        self._cache[user_id] = (metadata_sandbox_id, backend, provider_obj)
                        self._evict_if_needed()
                        info = await run_long_blocking_io(
                            self._cube_adapter.get_sandbox_info,
                            provider_obj,
                        )
                        await self._save_binding(
                            user_id, metadata_sandbox_id, info.get("state", "running")
                        )
                        base_work_dir = await run_blocking_io(
                            self._cube_adapter.get_work_dir,
                            provider_obj,
                        )
                        base_work_dir = await self._cloud_work_dir(
                            user_id, base_work_dir, self._cache[user_id][1]
                        )
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_cube_backend(provider_obj, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        await sync_sandbox_env_vars(scoped_backend, user_id)
                        self._schedule_duplicate_cubesandbox_cleanup(
                            user_id, keep_sandbox_id=metadata_sandbox_id
                        )
                        return scoped_backend, work_dir
                    except Exception:
                        self._cache.pop(user_id, None)
                        raise
                storage = (binding.get("cloud_storage") or {}).get("cubesandbox")
                if create and storage and binding.get("sandbox_work_dir") == storage["mount_path"]:
                    return await self._create_and_bind_cubesandbox(
                        session_id, user_id, previous_sandbox_id=metadata_sandbox_id
                    )
                raise SandboxPeekError("recycled")

            storage = ((binding or {}).get("cloud_storage") or {}).get("cubesandbox")
            existing = (
                None
                if storage
                else await self._find_existing_cubesandbox_for_user(
                    session_id,
                    user_id,
                    exclude_ids=unusable_sandbox_ids,
                )
            )
            if existing is not None:
                # 复用同用户的其他沙箱，数据保留，不算重建
                return existing

            # 浏览路径（create=False）只连不建（与 E2B 同语义）
            if not create:
                from src.infra.sandbox.session_manager import SandboxPeekError

                raise SandboxPeekError("not_created")
            return await self._create_and_bind_cubesandbox(session_id, user_id)

    async def _find_existing_cubesandbox_for_user(
        self,
        session_id: str,
        user_id: str,
        *,
        exclude_ids: set[str] | None = None,
    ) -> tuple[CompositeBackend, str] | None:
        assert self._cube_adapter is not None
        exclude_ids = exclude_ids or set()
        candidates = await run_blocking_io(self._cube_adapter.list_user_sandboxes, user_id)
        if len(candidates) > 1:
            raise RuntimeError("Multiple existing workspaces require explicit recovery")

        for info in candidates:
            # list() 返回 CubeAPI 原始 JSON（camelCase 键）
            sandbox_id = info.get("sandboxID")
            if not sandbox_id or sandbox_id in exclude_ids:
                continue
            provider_obj = await run_long_blocking_io(self._cube_adapter.get_sandbox, sandbox_id)
            if not provider_obj:
                continue
            try:
                await run_blocking_io(
                    self._cube_adapter.extend_timeout,
                    provider_obj,
                    self._get_cube_timeout(),
                )
                backend = self._build_cube_composite_backend(provider_obj, user_id)
                self._cache[user_id] = (sandbox_id, backend, provider_obj)
                self._evict_if_needed()
                await self._save_binding(user_id, sandbox_id, "running")
                base_work_dir = await run_blocking_io(
                    self._cube_adapter.get_work_dir,
                    provider_obj,
                )
                work_dir = self._session_work_dir(base_work_dir, session_id)
                scoped_backend = self._scope_cube_backend(provider_obj, user_id, work_dir)
                await self._ensure_work_dir(scoped_backend, work_dir)
                await sync_sandbox_env_vars(scoped_backend, user_id)
                await self._cleanup_duplicate_cubesandboxes(user_id, keep_sandbox_id=sandbox_id)
                logger.info(
                    f"[CubeSandbox] Reused existing sandbox {sandbox_id} for user {user_id} "
                    f"(session={session_id})"
                )
                return scoped_backend, work_dir
            except Exception as e:
                logger.warning(f"[CubeSandbox] Existing sandbox {sandbox_id} unusable: {e}")
                self._cache.pop(user_id, None)
                exclude_ids.add(sandbox_id)
        if candidates:
            from src.infra.sandbox.session_manager import SandboxPeekError

            raise SandboxPeekError("recycled")
        return None

    async def _cleanup_duplicate_cubesandboxes(
        self,
        user_id: str,
        *,
        keep_sandbox_id: str,
    ) -> None:
        assert self._cube_adapter is not None
        try:
            candidates = await run_blocking_io(self._cube_adapter.list_user_sandboxes, user_id)
        except Exception as e:
            logger.warning(f"[CubeSandbox] Failed to list duplicates for {user_id}: {e}")
            return

        for info in candidates:
            sandbox_id = info.get("sandboxID")
            if not sandbox_id or sandbox_id == keep_sandbox_id:
                continue
            # Same owner does not prove that another sandbox's files were copied.
            logger.warning(
                "[CubeSandbox] Retaining workspace sandbox %s for user %s", sandbox_id, user_id
            )

    def _schedule_duplicate_cubesandbox_cleanup(
        self,
        user_id: str,
        *,
        keep_sandbox_id: str,
    ) -> None:
        try:
            task = asyncio.create_task(
                self._cleanup_duplicate_cubesandboxes(user_id, keep_sandbox_id=keep_sandbox_id)
            )
        except RuntimeError:
            return

        def _log_cleanup_failure(done_task: asyncio.Task[None]) -> None:
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception as e:
                logger.warning(f"[CubeSandbox] Background duplicate cleanup failed: {e}")

        task.add_done_callback(_log_cleanup_failure)

    async def _create_and_bind_cubesandbox(
        self,
        session_id: str,
        user_id: str,
        *,
        previous_sandbox_id: str | None = None,
    ) -> tuple[CompositeBackend, str]:
        assert self._cube_adapter is not None
        adapter = self._cube_adapter
        from src.infra.backend.cubesandbox import CubeSandboxBackend

        user_envs = await self._get_user_env_vars(user_id)
        storage = await self._prepare_cloud_storage(user_id)

        def _sync_create():
            sandbox, work_dir = adapter.create_sandbox(
                user_id=user_id,
                envs=user_envs if user_envs else None,
                storage=storage,
            )
            cube_backend = CubeSandboxBackend(sandbox=cast("CubeSandbox", sandbox))
            skills_backend = create_skills_backend(user_id=user_id)
            composite = AuthorizedCompositeBackend(
                user_id=user_id, default=cube_backend, routes={"/skills/": skills_backend}
            )
            return composite, work_dir, adapter.get_sandbox_id(sandbox), sandbox

        backend, work_dir, sandbox_id, provider_obj = await run_long_blocking_io(_sync_create)
        try:
            await self._verify_cloud_storage(backend, storage)
            scoped_work_dir = self._session_work_dir(work_dir, session_id)
            scoped_backend = self._scope_cube_backend(provider_obj, user_id, scoped_work_dir)
            await self._ensure_work_dir(scoped_backend, scoped_work_dir)
            await sync_sandbox_env_vars(scoped_backend, user_id)
            await self._save_binding(
                user_id,
                sandbox_id,
                "running",
                is_new=True,
                previous_sandbox_id=previous_sandbox_id,
            )
        except Exception as e:
            logger.error(f"[CubeSandbox] Created {sandbox_id} but failed to save binding: {e}")
            try:
                await run_long_blocking_io(self._cube_adapter.stop_sandbox, provider_obj)
            except Exception:
                pass
            raise
        self._cache[user_id] = (sandbox_id, backend, provider_obj)
        self._evict_if_needed()
        logger.info(
            f"[CubeSandbox] Created sandbox {sandbox_id} for user {user_id} (session={session_id})"
        )
        await self._cleanup_duplicate_cubesandboxes(user_id, keep_sandbox_id=sandbox_id)

        return scoped_backend, scoped_work_dir

    def _build_cube_composite_backend(self, provider_obj: object, user_id: str) -> CompositeBackend:
        from src.infra.backend.cubesandbox import CubeSandboxBackend

        return AuthorizedCompositeBackend(
            user_id=user_id,
            default=CubeSandboxBackend(sandbox=cast("CubeSandbox", provider_obj)),
            routes={"/skills/": create_skills_backend(user_id=user_id)},
        )

    async def _stop_cubesandbox(self, user_id: str) -> bool:
        assert self._cube_adapter is not None
        lock = self._get_user_lock(user_id)
        async with lock:
            # 本进程缓存优先；跨 pod 场景（对话在别的 pod 跑）回退按 binding
            # 重连沙箱再暂停，空闲自动暂停才能在任意 pod 生效。
            sandbox_id: str | None = None
            provider_obj: object | None = None
            if user_id in self._cache:
                sandbox_id, _, provider_obj = self._cache[user_id]
            else:
                binding = await self._get_binding(user_id) or {}
                sandbox_id = binding.get("sandbox_id") if binding else None
                if sandbox_id:
                    provider_obj = await run_long_blocking_io(
                        self._cube_adapter.get_sandbox, sandbox_id
                    )
            if not sandbox_id or provider_obj is None:
                return False
            try:
                await run_long_blocking_io(self._cube_adapter.stop_sandbox, provider_obj)
                self._cache.pop(user_id, None)
                await self._save_binding(user_id, sandbox_id, "paused")
                logger.info(f"[CubeSandbox] Paused sandbox {sandbox_id} for user {user_id}")
                return True
            except Exception as e:
                logger.error(f"[CubeSandbox] Failed to stop sandbox: {e}")
                return False

    def _get_cube_timeout(self) -> int:
        """Read CUBE_TIMEOUT from settings (lazy import)."""
        from src.kernel.config import settings

        return settings.CUBE_TIMEOUT
