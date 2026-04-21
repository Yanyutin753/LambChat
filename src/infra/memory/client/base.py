"""
Memory Backend Base - Abstract interface & shared utilities.

All memory backends (Hindsight, memU, etc.) inherit from MemoryBackend.
A factory function creates the correct backend based on configuration.
"""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from src.infra.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Shared Concurrency Utilities
# ============================================================================

_loop_locals: dict[int, dict[str, Any]] = {}
_loop_locals_lock: Optional[asyncio.Lock] = None
_loop_locals_lock_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_loop_locals_lock() -> asyncio.Lock:
    """Get or create the loop-locals lock (lazy, multi-loop safe)."""
    global _loop_locals_lock, _loop_locals_lock_loop
    current_loop = asyncio.get_running_loop()
    if _loop_locals_lock is None or _loop_locals_lock_loop is not current_loop:
        _loop_locals_lock = asyncio.Lock()
        _loop_locals_lock_loop = current_loop
    return _loop_locals_lock


def _get_loop_id() -> int:
    """Get unique identifier for current event loop."""
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


async def _get_loop_local(name: str, factory: Callable[[], Any]) -> Any:
    """Get or create a loop-local resource (async-safe)."""
    loop_id = _get_loop_id()
    async with _get_loop_locals_lock():
        if loop_id not in _loop_locals:
            _loop_locals[loop_id] = {}
        if name not in _loop_locals[loop_id]:
            _loop_locals[loop_id][name] = factory()
        return _loop_locals[loop_id][name]


async def get_request_semaphore(namespace: str, max_concurrent: int = 64) -> asyncio.Semaphore:
    """Get or create a namespaced request semaphore for current event loop."""
    return await _get_loop_local(
        f"{namespace}_semaphore", lambda: asyncio.Semaphore(max_concurrent)
    )


async def get_client_lock(namespace: str) -> asyncio.Lock:
    """Get or create a namespaced client lock for current event loop."""
    return await _get_loop_local(f"{namespace}_client_lock", lambda: asyncio.Lock())


async def with_retry(
    func: Callable[[], Any],
    *,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
    retry_delay: float = 0.5,
    namespace: str = "Memory",
) -> Any:
    """Execute an async operation with retry logic and concurrency control."""
    last_error: BaseException | None = None
    for attempt in range(max_retries):
        try:
            async with semaphore:
                return await func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt) + random.uniform(0, 0.1)
                logger.warning(
                    f"[{namespace}] Retry {attempt + 1}/{max_retries} after error: {e}. "
                    f"Waiting {delay:.2f}s"
                )
                await asyncio.sleep(delay)

    if last_error is None:
        raise RuntimeError("Unexpected state: no error captured after retry loop")
    raise last_error


def clear_loop_locals(namespace: str) -> None:
    """Clear loop-local storage for a given namespace."""
    loop_id = _get_loop_id()
    if loop_id in _loop_locals:
        _loop_locals[loop_id].pop(f"{namespace}_semaphore", None)
        _loop_locals[loop_id].pop(f"{namespace}_client_lock", None)
        # Clean up empty loop entries to prevent memory accumulation
        if not _loop_locals[loop_id]:
            del _loop_locals[loop_id]


# ============================================================================
# Abstract Backend Interface
# ============================================================================


class MemoryBackend(ABC):
    """Abstract base class for memory backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g. 'hindsight', 'memu')."""
        ...

    @abstractmethod
    async def retain(
        self,
        user_id: str,
        content: str,
        context: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[list[str]] = None,
        existing_memory_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Store a memory."""
        ...

    @abstractmethod
    async def recall(
        self,
        user_id: str,
        query: str,
        max_results: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Recall memories matching the query."""
        ...

    @abstractmethod
    async def delete(
        self,
        user_id: str,
        memory_id: str,
    ) -> dict[str, Any]:
        """Delete a memory by ID."""
        ...

    async def close(self) -> None:
        """Release resources held by this backend. Default is a no-op."""
        pass


# ============================================================================
# Backend Factory
# ============================================================================


async def create_memory_backend() -> Optional[MemoryBackend]:
    """
    Create the active memory backend based on configuration.

    Returns None if memory is disabled via master switch.
    Only native (MongoDB-backed) backend is supported.
    """
    from src.kernel.config import settings

    if not settings.ENABLE_MEMORY:
        return None

    try:
        from src.infra.memory.client.native import NativeMemoryBackend

        backend = NativeMemoryBackend()
        await backend.initialize()
        if backend._collection is not None:
            return backend
    except Exception as e:
        logger.warning(f"[Memory] Failed to initialize native backend: {e}")

    return None


def is_memory_enabled() -> bool:
    """Check if memory feature is enabled (master switch)."""
    from src.kernel.config import settings

    return settings.ENABLE_MEMORY


def get_user_id_from_runtime(runtime: Any) -> Optional[str]:
    """Extract user_id from ToolRuntime context."""
    if not runtime:
        return None
    try:
        if hasattr(runtime, "config"):
            config = runtime.config
            if isinstance(config, dict):
                configurable = config.get("configurable", {})
                context = configurable.get("context")
                if context and hasattr(context, "user_id"):
                    return context.user_id
    except Exception:
        pass
    return None
