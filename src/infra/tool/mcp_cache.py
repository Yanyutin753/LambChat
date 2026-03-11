"""
MCP 工具缓存模块（混合缓存实现）

使用 Redis 存储配置哈希值检测变更，使用进程内内存缓存 BaseTool 对象和客户端连接

分布式支持：
- Redis 存储配置哈希， 用于跨实例检测配置变更
- 内存缓存 MCP 连接和工具对象（无法序列化）
- 配置变更时通过 Redis 通知所有实例失效缓存
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.infra.storage.redis import get_redis_client

logger = logging.getLogger(__name__)

# 缓存过期时间（秒），默认 30 分钟
CACHE_TTL = 1800

# 最大缓存条目数（防止内存泄漏）
MAX_CACHE_ENTRIES = 1000

# Redis 缓存键前缀
CONFIG_HASH_KEY_PREFIX = "mcp_config_hash:"

# 进程内缓存：user_id -> CachedMCPEntry
_tools_cache: dict[str, "CachedMCPEntry"] = {}

# 缓存锁，防止并发初始化
_cache_locks: dict[str, asyncio.Lock] = {}

# 全局清理锁，防止并发清理
_cleanup_lock = asyncio.Lock()


def _cleanup_expired_cache() -> int:
    """清理过期的缓存条目，返回清理的数量"""
    expired_users = [user_id for user_id, entry in _tools_cache.items() if entry.is_expired()]
    for user_id in expired_users:
        _tools_cache.pop(user_id, None)
        _cache_locks.pop(user_id, None)
    return len(expired_users)


def _cleanup_excess_cache() -> int:
    """清理超出的缓存条目（LRU），返回清理的数量"""
    if len(_tools_cache) <= MAX_CACHE_ENTRIES:
        return 0

    # 按最后访问时间排序，删除最旧的
    sorted_entries = sorted(_tools_cache.items(), key=lambda x: x[1].last_access)

    # 删除超出部分
    to_remove = len(_tools_cache) - MAX_CACHE_ENTRIES
    for user_id, _ in sorted_entries[:to_remove]:
        _tools_cache.pop(user_id, None)
        _cache_locks.pop(user_id, None)

    return to_remove


@dataclass
class CachedMCPEntry:
    """缓存的 MCP 工具条目（进程内）"""

    tools: list[BaseTool]
    client: MultiServerMCPClient
    config_hash: str
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)

    def is_expired(self, ttl: float = CACHE_TTL) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.created_at > ttl

    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()


def _get_cache_lock(user_id: str) -> asyncio.Lock:
    """获取指定用户的缓存锁（线程安全）

    使用 setdefault 确保原子性，防止竞态条件。
    同时定期清理过期和超出限制的缓存条目。
    """
    # 定期清理过期条目（简单触发机制）
    if len(_tools_cache) > 0 and len(_tools_cache) % 50 == 0:
        expired = _cleanup_expired_cache()
        if expired > 0:
            logger.debug(f"[MCP Cache] Auto-cleaned {expired} expired entries")

    # 检查是否超出最大条目数
    if len(_tools_cache) > MAX_CACHE_ENTRIES:
        removed = _cleanup_excess_cache()
        if removed > 0:
            logger.info(f"[MCP Cache] Removed {removed} excess cache entries (LRU)")

    # 使用 setdefault 确保原子性
    return _cache_locks.setdefault(user_id, asyncio.Lock())


def compute_config_hash(config: dict) -> str:
    """
    计算配置的哈希值，用于检测配置是否变更

    Args:
        config: MCP 配置字典，包含 mcpServers 等

    Returns:
        配置的 MD5 哈希值
    """
    # 提取 mcpServers 部分
    servers = config.get("mcpServers", {})

    # 排序键以确保一致性
    config_str = json.dumps(servers, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()


async def _get_stored_config_hash(user_id: str) -> Optional[str]:
    """从 Redis 获取存储的配置哈希"""
    try:
        redis_client = get_redis_client()
        key = f"{CONFIG_HASH_KEY_PREFIX}{user_id}"
        return await redis_client.get(key)
    except Exception as e:
        logger.warning(f"[MCP Cache] Redis get hash failed for user {user_id}: {e}")
        return None


async def _store_config_hash(user_id: str, config_hash: str) -> None:
    """存储配置哈希到 Redis"""
    try:
        redis_client = get_redis_client()
        key = f"{CONFIG_HASH_KEY_PREFIX}{user_id}"
        await redis_client.set(key, config_hash, ex=CACHE_TTL)
    except Exception as e:
        logger.warning(f"[MCP Cache] Redis set hash failed for user {user_id}: {e}")


async def get_cached_tools(
    user_id: str,
    config: dict,
    create_client_func,
) -> tuple[list[BaseTool], Optional[MultiServerMCPClient]]:
    """
    获取缓存的 MCP 工具（混合缓存策略）

    1. 计算当前配置的哈希值
    2. 从 Redis 获取存储的配置哈希
    3. 如果哈希匹配且进程内有缓存，直接返回
    4. 否则重新创建工具并更新缓存

    Args:
        user_id: 用户 ID
        config: MCP 配置字典
        create_client_func: 异步函数，用于创建新的 MCP 客户端和工具
            签名: async def create_client(config: dict) -> tuple[list[BaseTool], MultiServerMCPClient]

    Returns:
        tuple: (tools, client) - 工具列表和客户端
    """
    current_hash = compute_config_hash(config)
    lock = _get_cache_lock(user_id)

    async with lock:
        # 获取 Redis 中存储的配置哈希
        stored_hash = await _get_stored_config_hash(user_id)

        # 检查进程内缓存
        cached = _tools_cache.get(user_id)

        # 判断是否可以使用缓存
        if cached and not cached.is_expired():
            # 检查配置是否变更
            if stored_hash == current_hash and cached.config_hash == current_hash:
                # 配置未变更，检查工具列表是否有效
                if len(cached.tools) > 0:
                    # 有工具，使用缓存
                    cached.touch()
                    logger.info(
                        f"[MCP Cache] Hit for user {user_id}, {len(cached.tools)} tools "
                        f"(hash matched)"
                    )
                    return cached.tools, cached.client
                else:
                    # 缓存的工具列表为空，可能是之前创建失败，需要重新创建
                    logger.info(f"[MCP Cache] Empty tools cache for user {user_id}, will recreate")
            else:
                # 配置已变更，需要重新加载
                logger.info(
                    f"[MCP Cache] Config changed for user {user_id}, "
                    f"stored_hash={stored_hash[:8] if stored_hash else 'None'}, "
                    f"current_hash={current_hash[:8]}"
                )
        else:
            # 缓存过期或不存在
            logger.info(f"[MCP Cache] Miss for user {user_id} (no valid cache)")

        # 重新创建工具
        logger.info(f"[MCP Cache] Creating tools for user {user_id}")
        tools, client = await create_client_func(config)

        # 更新进程内缓存
        _tools_cache[user_id] = CachedMCPEntry(
            tools=tools,
            client=client,
            config_hash=current_hash,
        )

        # 更新 Redis 中的配置哈希
        await _store_config_hash(user_id, current_hash)

        logger.info(f"[MCP Cache] Cached {len(tools)} tools for user {user_id}")
        return tools, client


async def invalidate_user_cache(user_id: str) -> bool:
    """
    使指定用户的缓存失效

    同时清除 Redis 配置哈希和进程内缓存

    Args:
        user_id: 用户 ID

    Returns:
        bool: 是否成功删除缓存
    """
    # 清除 Redis 配置哈希
    try:
        redis_client = get_redis_client()
        key = f"{CONFIG_HASH_KEY_PREFIX}{user_id}"
        await redis_client.delete(key)
        logger.info(f"[MCP Cache] Invalidated Redis hash for user {user_id}")
    except Exception as e:
        logger.warning(f"[MCP Cache] Redis delete hash failed for user {user_id}: {e}")

    # 清除进程内缓存
    if user_id in _tools_cache:
        cached = _tools_cache.pop(user_id)
        logger.info(
            f"[MCP Cache] Invalidated memory cache for user {user_id}, {len(cached.tools)} tools"
        )
        return True

    logger.debug(f"[MCP Cache] No memory cache to invalidate for user {user_id}")
    return False


async def invalidate_all_cache() -> int:
    """
    使所有用户的缓存失效

    Returns:
        int: 被失效的缓存数量
    """
    # 清除 Redis 中所有配置哈希
    try:
        redis_client = get_redis_client()
        keys = await redis_client.keys(f"{CONFIG_HASH_KEY_PREFIX}*")
        if keys:
            for key in keys:
                await redis_client.delete(key)
            logger.info(f"[MCP Cache] Invalidated {len(keys)} Redis hash entries")
    except Exception as e:
        logger.warning(f"[MCP Cache] Redis keys/delete failed: {e}")

    # 清除所有进程内缓存
    count = len(_tools_cache)
    _tools_cache.clear()
    logger.info(f"[MCP Cache] Invalidated all memory cache, {count} entries")
    return count


async def get_cache_stats() -> dict[str, Any]:
    """
    获取缓存统计信息

    Returns:
        dict: 包含缓存统计的字典
    """
    now = time.time()
    stats: dict[str, Any] = {
        "memory_cache": {
            "total_entries": len(_tools_cache),
            "entries": [],
        },
        "redis_hash_keys": 0,
    }

    # 内存缓存统计
    for user_id, cached in _tools_cache.items():
        stats["memory_cache"]["entries"].append(
            {
                "user_id": user_id,
                "tools_count": len(cached.tools),
                "age_seconds": int(now - cached.created_at),
                "is_expired": cached.is_expired(),
                "config_hash": cached.config_hash[:8],
            }
        )

    # Redis 哈希键统计
    try:
        redis_client = get_redis_client()
        keys = await redis_client.keys(f"{CONFIG_HASH_KEY_PREFIX}*")
        stats["redis_hash_keys"] = len(keys)
    except Exception as e:
        stats["redis_hash_error"] = str(e)

    return stats
