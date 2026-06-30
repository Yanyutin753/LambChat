"""E2B-specific helper methods for SessionSandboxManager.

These are mixed into SessionSandboxManager via multiple inheritance.
All methods assume `self` provides the shared infra (cache, bindings, locks, etc.).
"""

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional, cast

from deepagents.backends import CompositeBackend

from src.infra.async_utils import run_blocking_io as _run_blocking_io
from src.infra.backend.skills_store import create_skills_backend
from src.infra.logging import get_logger
from src.infra.tool.sandbox_mcp_rebuild import ensure_sandbox_mcp as _ensure_sandbox_mcp

if TYPE_CHECKING:
    from e2b import Sandbox as E2BSandbox

    from ._adapters import E2BSandboxAdapter

logger = get_logger(__name__)


def run_blocking_io(*args, **kwargs):
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "run_blocking_io", _run_blocking_io)(*args, **kwargs)


def ensure_sandbox_mcp(*args, **kwargs):
    from src.infra.sandbox import session_manager

    return getattr(session_manager, "ensure_sandbox_mcp", _ensure_sandbox_mcp)(*args, **kwargs)


class _E2BMixin:
    """E2B platform lifecycle methods for SessionSandboxManager."""

    if TYPE_CHECKING:
        _e2b_adapter: Optional["E2BSandboxAdapter"]
        _cache: OrderedDict[str, tuple[str, CompositeBackend, object | None]]

        def _get_user_lock(self, user_id: str) -> asyncio.Lock: ...

        async def _get_binding(self, user_id: str) -> Any | None: ...

        async def _save_binding(
            self,
            user_id: str,
            sandbox_id: str,
            state: str,
            is_new: bool = False,
        ) -> None: ...

        def _evict_if_needed(self) -> None: ...

        def _session_work_dir(self, base_work_dir: str, session_id: str) -> str: ...

        def _scope_e2b_backend(
            self,
            provider_obj: object,
            user_id: str,
            work_dir: str,
        ) -> CompositeBackend: ...

        async def _ensure_work_dir(self, backend: CompositeBackend, work_dir: str) -> None: ...

        async def _get_user_env_vars(self, user_id: str) -> dict[str, str]: ...

    async def _get_or_create_e2b(
        self, session_id: str, user_id: str
    ) -> tuple[CompositeBackend, str]:
        assert self._e2b_adapter is not None
        from src.kernel.config import settings

        lock = self._get_user_lock(user_id)
        async with lock:
            if user_id in self._cache:
                self._cache.move_to_end(user_id)  # LRU: mark as recently used
                sandbox_id, _backend, provider_obj = self._cache[user_id]
                try:
                    is_running = await run_blocking_io(
                        self._e2b_adapter.sandbox_is_running,
                        provider_obj,
                    )
                    if is_running:
                        await run_blocking_io(
                            self._e2b_adapter.extend_timeout,
                            provider_obj,
                            settings.E2B_TIMEOUT,
                        )
                        await self._save_binding(user_id, sandbox_id, "running")
                        base_work_dir = await run_blocking_io(
                            self._e2b_adapter.get_work_dir,
                            provider_obj,
                        )
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_e2b_backend(provider_obj, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        await ensure_sandbox_mcp(scoped_backend, user_id)
                        return scoped_backend, work_dir
                except Exception as e:
                    logger.warning(f"[E2B] Cache hit but sandbox {sandbox_id} unhealthy: {e}")
                del self._cache[user_id]

            binding = await self._get_binding(user_id)
            metadata_sandbox_id = binding.get("sandbox_id") if binding else None
            if metadata_sandbox_id:
                # Sandbox.connect() 会自动恢复暂停的沙箱
                provider_obj = await run_blocking_io(
                    self._e2b_adapter.get_sandbox, metadata_sandbox_id
                )
                if provider_obj:
                    try:
                        await run_blocking_io(
                            self._e2b_adapter.extend_timeout,
                            provider_obj,
                            settings.E2B_TIMEOUT,
                        )
                        backend = self._build_composite_backend(provider_obj, user_id)
                        self._cache[user_id] = (metadata_sandbox_id, backend, provider_obj)
                        self._evict_if_needed()
                        info = await run_blocking_io(
                            self._e2b_adapter.get_sandbox_info,
                            provider_obj,
                        )
                        await self._save_binding(
                            user_id, metadata_sandbox_id, info.get("state", "running")
                        )
                        await ensure_sandbox_mcp(backend, user_id)
                        base_work_dir = await run_blocking_io(
                            self._e2b_adapter.get_work_dir,
                            provider_obj,
                        )
                        work_dir = self._session_work_dir(base_work_dir, session_id)
                        scoped_backend = self._scope_e2b_backend(provider_obj, user_id, work_dir)
                        await self._ensure_work_dir(scoped_backend, work_dir)
                        await ensure_sandbox_mcp(scoped_backend, user_id)
                        return scoped_backend, work_dir
                    except Exception as e:
                        logger.warning(f"[E2B] Failed to reconnect {metadata_sandbox_id}: {e}")

            return await self._create_and_bind_e2b(session_id, user_id)

    async def _create_and_bind_e2b(
        self, session_id: str, user_id: str
    ) -> tuple[CompositeBackend, str]:
        assert self._e2b_adapter is not None
        adapter = self._e2b_adapter
        from src.infra.backend.e2b import E2BBackend

        # 加载用户环境变量
        user_envs = await self._get_user_env_vars(user_id)

        def _sync_create():
            sandbox, work_dir = adapter.create_sandbox(
                user_id=user_id, envs=user_envs if user_envs else None
            )
            e2b_backend = E2BBackend(sandbox=cast("E2BSandbox", sandbox))
            skills_backend = create_skills_backend(user_id=user_id)
            composite = CompositeBackend(default=e2b_backend, routes={"/skills/": skills_backend})
            return composite, work_dir, adapter.get_sandbox_id(sandbox), sandbox

        backend, work_dir, sandbox_id, provider_obj = await run_blocking_io(_sync_create)
        try:
            await self._save_binding(user_id, sandbox_id, "running", is_new=True)
        except Exception as e:
            logger.error(f"[E2B] Created {sandbox_id} but failed to save binding: {e}")
            try:
                await run_blocking_io(self._e2b_adapter.stop_sandbox, provider_obj)
            except Exception:
                pass
            raise
        self._cache[user_id] = (sandbox_id, backend, provider_obj)
        self._evict_if_needed()
        logger.info(f"[E2B] Created sandbox {sandbox_id} for user {user_id} (session={session_id})")

        scoped_work_dir = self._session_work_dir(work_dir, session_id)
        scoped_backend = self._scope_e2b_backend(provider_obj, user_id, scoped_work_dir)
        await self._ensure_work_dir(scoped_backend, scoped_work_dir)
        await ensure_sandbox_mcp(scoped_backend, user_id)
        return scoped_backend, scoped_work_dir

    def _build_composite_backend(self, provider_obj: object, user_id: str) -> CompositeBackend:
        from src.infra.backend.e2b import E2BBackend

        return CompositeBackend(
            default=E2BBackend(sandbox=cast("E2BSandbox", provider_obj)),
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
                    await run_blocking_io(self._e2b_adapter.stop_sandbox, provider_obj)
                    self._cache.pop(user_id, None)
                    await self._save_binding(user_id, sandbox_id, "paused")
                    logger.info(f"[E2B] Paused sandbox {sandbox_id} for user {user_id}")
                    return True
                except Exception as e:
                    logger.error(f"[E2B] Failed to stop sandbox: {e}")
                    return False
            return False
