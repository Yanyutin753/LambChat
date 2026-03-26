import asyncio
import os

os.environ["DEBUG"] = "false"

import pytest

from src.infra.sandbox.session_manager import SessionSandboxManager
from src.infra.tool import mcp_cache, mcp_global


@pytest.mark.asyncio
async def test_mcp_cache_cleanup_preserves_active_locks():
    user_id = "active-user"
    lock = asyncio.Lock()
    await lock.acquire()

    mcp_cache._tools_cache.clear()
    mcp_cache._cache_locks.clear()
    mcp_cache._cache_locks[user_id] = lock

    removed = mcp_cache._cleanup_expired_cache()

    assert removed == 0
    assert mcp_cache._cache_locks[user_id] is lock

    lock.release()
    mcp_cache._cleanup_expired_cache()
    assert user_id not in mcp_cache._cache_locks


@pytest.mark.asyncio
async def test_mcp_global_cleanup_preserves_active_orphan_locks():
    user_id = "active-user"
    lock = asyncio.Lock()
    await lock.acquire()

    mcp_global._global_entries.clear()
    mcp_global._local_locks.clear()
    mcp_global._local_locks[user_id] = lock

    removed = mcp_global._cleanup_orphan_locks()

    assert removed == 0
    assert mcp_global._local_locks[user_id] is lock

    lock.release()
    removed = mcp_global._cleanup_orphan_locks()
    assert removed == 1
    assert user_id not in mcp_global._local_locks


@pytest.mark.asyncio
async def test_session_sandbox_manager_preserves_active_locks_when_capacity_reached():
    manager = SessionSandboxManager()

    active_lock = asyncio.Lock()
    await active_lock.acquire()

    manager._locks.clear()
    manager._locks["active-user"] = active_lock
    manager._locks["idle-user"] = asyncio.Lock()

    from src.infra.sandbox import session_manager as session_manager_module

    previous_limit = session_manager_module._MAX_LOCKS
    session_manager_module._MAX_LOCKS = 2
    try:
        new_lock = manager._get_user_lock("new-user")
    finally:
        session_manager_module._MAX_LOCKS = previous_limit
        active_lock.release()

    assert "active-user" in manager._locks
    assert manager._locks["active-user"] is active_lock
    assert "new-user" in manager._locks
    assert manager._locks["new-user"] is new_lock
    assert "idle-user" not in manager._locks
