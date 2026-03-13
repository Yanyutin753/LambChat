"""
全局 MCP 管理器 - 分布式优化版（安全锁 + 内存管理 + Pub/Sub 缓存同步）

使用全局单例 + Redis 分布式锁（Lua 脚本），避免重复初始化。
使用 Redis Pub/Sub 实现跨实例缓存失效通知。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.tools import BaseTool

from src.infra.storage.redis import get_redis_client
from src.infra.tool.mcp_client import MCPClientManager

logger = logging.getLogger(__name__)

# 全局单例：user_id -> GlobalMCPEntry
_global_entries: dict[str, "GlobalMCPEntry"] = {}

# 本地异步锁（进程内）
_local_locks: dict[str, asyncio.Lock] = {}

# 分布式锁超时时间（秒）
DISTRIBUTED_LOCK_TTL = 30

# 全局缓存过期时间（秒），默认 30 分钟
GLOBAL_CACHE_TTL = 1800

# 最大缓存条目数（防止内存泄漏）
MAX_GLOBAL_ENTRIES = 500

# Redis 键前缀
LOCK_KEY_PREFIX = "mcp_init_lock:"
DONE_KEY_PREFIX = "mcp_init_done:"

# MCP 缓存失效 Pub/Sub 频道
MCP_CACHE_INVALIDATE_CHANNEL = "mcp:cache:invalidate"

# 当前实例的唯一标识（用于避免处理自己发送的消息）
_INSTANCE_ID = str(uuid.uuid4())[:8]

# Lua 脚本：安全释放锁
RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


@dataclass
class GlobalMCPEntry:
    """全局 MCP 缓存条目"""

    manager: MCPClientManager
    tools: list[BaseTool]
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)

    def is_expired(self, ttl: float = GLOBAL_CACHE_TTL) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.created_at > ttl

    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()


def _get_local_lock(user_id: str) -> asyncio.Lock:
    """获取本地异步锁"""
    return _local_locks.setdefault(user_id, asyncio.Lock())


async def acquire_distributed_lock(
    lock_key: str, ttl: int = DISTRIBUTED_LOCK_TTL
) -> tuple[bool, str]:
    """
    获取 Redis 分布式锁

    Args:
        lock_key: 锁的键
        ttl: 锁的超时时间（秒）

    Returns:
        (是否成功获取锁, 锁的唯一标识)
    """
    lock_value = str(uuid.uuid4())
    try:
        redis_client = get_redis_client()
        # 使用 SET NX EX 原子操作
        result = await redis_client.set(lock_key, lock_value, nx=True, ex=ttl)
        if result is not None:
            logger.debug(f"[Global MCP] Acquired lock: {lock_key}")
            return True, lock_value
        return False, ""
    except Exception as e:
        logger.warning(f"[Global MCP] Failed to acquire lock {lock_key}: {e}")
        return False, ""


async def release_distributed_lock(lock_key: str, lock_value: str) -> bool:
    """
    释放 Redis 分布式锁（只有持有者才能释放）

    使用 Lua 脚本确保原子性，防止误删其他实例的锁。

    Args:
        lock_key: 锁的键
        lock_value: 锁的唯一标识（获取锁时返回的）

    Returns:
        是否成功释放锁
    """
    try:
        redis_client = get_redis_client()
        # Redis eval 参数: (script, numkeys, *keys_and_args)
        # numkeys=1 表示有1个key
        raw_result = redis_client.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, lock_value)
        # eval 可能返回 Awaitable，需要 await
        result = int(await raw_result) if hasattr(raw_result, "__await__") else int(raw_result)  # type: ignore[misc]
        if result == 1:
            logger.debug(f"[Global MCP] Released lock: {lock_key}")
            return True
        else:
            logger.warning(f"[Global MCP] Lock not owned or already released: {lock_key}")
            return False
    except Exception as e:
        logger.warning(f"[Global MCP] Failed to release lock {lock_key}: {e}")
        return False


async def check_init_done(user_id: str) -> bool:
    """检查其他实例是否已完成初始化"""
    try:
        redis_client = get_redis_client()
        done_key = f"{DONE_KEY_PREFIX}{user_id}"
        result = await redis_client.exists(done_key)
        return result > 0
    except Exception as e:
        logger.warning(f"[Global MCP] Failed to check init done for {user_id}: {e}")
        return False


async def mark_init_done(user_id: str) -> None:
    """标记初始化完成"""
    try:
        redis_client = get_redis_client()
        done_key = f"{DONE_KEY_PREFIX}{user_id}"
        # 设置 30 秒过期，足够让其他实例看到
        await redis_client.set(done_key, "1", ex=30)
    except Exception as e:
        logger.warning(f"[Global MCP] Failed to mark init done for {user_id}: {e}")


def _cleanup_expired_entries() -> int:
    """清理过期的缓存条目，返回清理的数量"""
    expired_users = [user_id for user_id, entry in _global_entries.items() if entry.is_expired()]
    for user_id in expired_users:
        entry = _global_entries.pop(user_id, None)
        if entry:
            try:
                # 尝试关闭 manager
                asyncio.create_task(entry.manager.close())
            except Exception:
                pass
        _local_locks.pop(user_id, None)

    if expired_users:
        logger.info(f"[Global MCP] Cleaned up {len(expired_users)} expired entries")

    return len(expired_users)


def _cleanup_excess_entries() -> int:
    """清理超出的缓存条目（LRU），返回清理的数量"""
    if len(_global_entries) <= MAX_GLOBAL_ENTRIES:
        return 0

    # 按最后访问时间排序，删除最旧的
    sorted_entries = sorted(_global_entries.items(), key=lambda x: x[1].last_access)

    # 删除超出部分
    to_remove = len(_global_entries) - MAX_GLOBAL_ENTRIES
    for user_id, entry in sorted_entries[:to_remove]:
        _global_entries.pop(user_id, None)
        _local_locks.pop(user_id, None)
        try:
            asyncio.create_task(entry.manager.close())
        except Exception:
            pass

    logger.info(f"[Global MCP] Removed {to_remove} excess entries (LRU)")
    return to_remove


async def get_global_mcp_tools(user_id: str) -> tuple[list[BaseTool], Optional[MCPClientManager]]:
    """
    获取全局 MCP 工具（单例 + 缓存 + 分布式锁）

    1. 检查进程内全局单例
    2. 使用本地锁防止并发
    3. 使用 Redis 分布式锁防止跨实例并发
    4. 使用 Redis 标记检测其他实例是否已完成初始化

    Args:
        user_id: 用户 ID

    Returns:
        (tools, manager) - 工具列表和管理器
    """
    # 定期清理过期条目
    if len(_global_entries) > 0 and len(_global_entries) % 50 == 0:
        _cleanup_expired_entries()
        _cleanup_excess_entries()

    # 1. 快速路径：检查全局单例
    if user_id in _global_entries:
        entry = _global_entries[user_id]
        if entry.manager._initialized and not entry.is_expired():
            entry.touch()
            logger.info(f"[Global MCP] Hit singleton for user {user_id}, {len(entry.tools)} tools")
            return entry.tools, entry.manager

    # 2. 获取本地锁（防止同一进程内并发）
    local_lock = _get_local_lock(user_id)
    async with local_lock:
        # 3. 再次检查（double-check locking）
        if user_id in _global_entries:
            entry = _global_entries[user_id]
            if entry.manager._initialized and not entry.is_expired():
                entry.touch()
                return entry.tools, entry.manager

        # 4. 获取 Redis 分布式锁
        lock_key = f"{LOCK_KEY_PREFIX}{user_id}"
        lock_acquired, lock_value = await acquire_distributed_lock(lock_key)

        if not lock_acquired:
            # 其他实例正在初始化，等待其完成标记
            logger.info(f"[Global MCP] Waiting for other instance: {user_id}")

            # 等待完成标记（最多 30 秒）
            for attempt in range(30):
                await asyncio.sleep(1)

                # 检查本实例是否已有缓存（可能通过其他协程获取）
                if user_id in _global_entries:
                    entry = _global_entries[user_id]
                    if entry.manager._initialized:
                        entry.touch()
                        logger.info(
                            f"[Global MCP] Got cache after waiting {attempt + 1}s: {user_id}"
                        )
                        return entry.tools, entry.manager

                # 检查其他实例是否已完成
                if await check_init_done(user_id):
                    # 等待一小段时间让本地缓存更新（如果有的话）
                    await asyncio.sleep(0.5)
                    if user_id in _global_entries:
                        entry = _global_entries[user_id]
                        if entry.manager._initialized:
                            entry.touch()
                            logger.info(f"[Global MCP] Got cache after init done: {user_id}")
                            return entry.tools, entry.manager
                    # 其他实例完成但本地没有缓存，创建一个新的
                    break

            # 超时或未获取到缓存，尝试初始化（降级）
            logger.warning(f"[Global MCP] Timeout waiting, creating new: {user_id}")

        try:
            # 5. 再次检查（triple-check）
            if user_id in _global_entries:
                entry = _global_entries[user_id]
                if entry.manager._initialized and not entry.is_expired():
                    entry.touch()
                    return entry.tools, entry.manager

            # 6. 创建新的 MCPClientManager
            logger.info(f"[Global MCP] Creating manager for user {user_id}")
            manager = MCPClientManager(
                config_path=None,
                user_id=user_id,
                use_database=True,
            )
            await manager.initialize()
            tools = await manager.get_tools()

            # 7. 保存到全局单例
            _global_entries[user_id] = GlobalMCPEntry(
                manager=manager,
                tools=tools,
            )

            # 8. 标记初始化完成（通知其他实例）
            await mark_init_done(user_id)

            # 9. 检查是否超出最大条目数
            if len(_global_entries) > MAX_GLOBAL_ENTRIES:
                _cleanup_excess_entries()

            logger.info(f"[Global MCP] Created manager for user {user_id}, {len(tools)} tools")
            return tools, manager

        finally:
            # 10. 释放 Redis 锁（如果获取了）
            if lock_acquired and lock_value:
                await release_distributed_lock(lock_key, lock_value)


async def invalidate_global_cache(user_id: str) -> None:
    """
    使全局缓存失效

    Args:
        user_id: 用户 ID
    """
    # 清除进程内缓存
    if user_id in _global_entries:
        entry = _global_entries.pop(user_id)
        try:
            await entry.manager.close()
        except Exception as e:
            logger.warning(f"[Global MCP] Failed to close manager: {e}")
        logger.info(f"[Global MCP] Invalidated singleton for user {user_id}")

    # 清除本地锁
    if user_id in _local_locks:
        del _local_locks[user_id]

    # 清除 Redis 完成标记
    try:
        redis_client = get_redis_client()
        done_key = f"{DONE_KEY_PREFIX}{user_id}"
        await redis_client.delete(done_key)
    except Exception:
        pass


async def invalidate_all_global_cache() -> int:
    """
    使所有全局缓存失效

    Returns:
        被失效的缓存数量
    """
    count = len(_global_entries)

    # 关闭所有 manager
    for user_id, entry in list(_global_entries.items()):
        try:
            await entry.manager.close()
        except Exception:
            pass

    _global_entries.clear()
    _local_locks.clear()

    logger.info(f"[Global MCP] Invalidated all cache, {count} entries")
    return count


async def warmup_global_cache(user_ids: list[str]) -> None:
    """
    预热全局缓存（后台任务）

    Args:
        user_ids: 要预热的用户 ID 列表
    """
    logger.info(f"[Global MCP] Warming up cache for {len(user_ids)} users")

    async def _warmup_user(user_id: str):
        try:
            tools, _ = await get_global_mcp_tools(user_id)
            logger.info(f"[Global MCP] Warmed up {len(tools)} tools for user {user_id}")
        except Exception as e:
            logger.warning(f"[Global MCP] Warmup failed for user {user_id}: {e}")

    # 并行预热（限制并发数）
    semaphore = asyncio.Semaphore(5)  # 最多同时预热 5 个用户

    async def _warmup_with_limit(user_id: str):
        async with semaphore:
            await _warmup_user(user_id)

    await asyncio.gather(*[_warmup_with_limit(uid) for uid in user_ids])
    logger.info("[Global MCP] Warmup complete")


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    now = time.time()
    return {
        "total_users": len(_global_entries),
        "max_users": MAX_GLOBAL_ENTRIES,
        "ttl_seconds": GLOBAL_CACHE_TTL,
        "users": [
            {
                "user_id": user_id,
                "tools_count": len(entry.tools),
                "age_seconds": int(now - entry.created_at),
                "is_expired": entry.is_expired(),
                "last_access_seconds": int(now - entry.last_access),
            }
            for user_id, entry in _global_entries.items()
        ],
    }
