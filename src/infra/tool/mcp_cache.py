"""
MCP 工具缓存模块

提供用户级别的 MCP 工具缓存，避免每次请求都重新获取工具列表。
当用户修改 MCP 配置时，缓存会自动失效。
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# 缓存过期时间（秒），默认 30 分钟
CACHE_TTL = 1800


@dataclass
class CachedMCPEntry:
    """缓存的 MCP 工具条目"""

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


# 模块级缓存：user_id -> CachedMCPEntry
_tools_cache: dict[str, CachedMCPEntry] = {}

# 缓存锁，防止并发初始化
_cache_locks: dict[str, asyncio.Lock] = {}


def _get_cache_lock(user_id: str) -> asyncio.Lock:
    """获取指定用户的缓存锁"""
    if user_id not in _cache_locks:
        _cache_locks[user_id] = asyncio.Lock()
    return _cache_locks[user_id]


def compute_config_hash(config: dict) -> str:
    """
    计算配置的哈希值，用于检测配置是否变更

    Args:
        config: MCP 配置字典，包含 mcpServers 等

    Returns:
        配置的 MD5 哈希值
    """
    import json

    # 提取 mcpServers 部分
    servers = config.get("mcpServers", {})

    # 排序键以确保一致性
    config_str = json.dumps(servers, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()


async def get_cached_tools(
    user_id: str,
    config: dict,
    create_client_func,
) -> tuple[list[BaseTool], Optional[MultiServerMCPClient]]:
    """
    获取缓存的 MCP 工具

    如果缓存存在且未过期且配置未变更，直接返回缓存的工具。
    否则，调用 create_client_func 创建新的客户端并缓存。

    Args:
        user_id: 用户 ID
        config: MCP 配置字典
        create_client_func: 异步函数，用于创建新的 MCP 客户端和工具
            签名: async def create_client(config: dict) -> tuple[list[BaseTool], MultiServerMCPClient]

    Returns:
        tuple: (tools, client) - 工具列表和客户端（可能为 None 如果使用缓存）
    """
    config_hash = compute_config_hash(config)
    lock = _get_cache_lock(user_id)

    async with lock:
        # 检查缓存
        cached = _tools_cache.get(user_id)

        if cached and not cached.is_expired() and cached.config_hash == config_hash:
            # 缓存命中
            # 但如果缓存的是空结果，不使用缓存（重新加载）
            if not cached.tools:
                logger.warning(
                    f"[MCP Cache] Hit but cached tools are empty for user {user_id}, invalidating and recreating"
                )
                # 删除空缓存
                del _tools_cache[user_id]
                # 继续执行下面的创建逻辑
            else:
                cached.touch()
                logger.info(f"[MCP Cache] Hit for user {user_id}, {len(cached.tools)} tools")
                return cached.tools, cached.client

        # 缓存未命中，需要创建新的
        logger.info(
            f"[MCP Cache] Miss for user {user_id} "
            f"(expired={cached.is_expired() if cached else 'N/A'}, "
            f"hash_changed={cached.config_hash != config_hash if cached else 'N/A'})"
        )

        tools, client = await create_client_func(config)

        # 只有获取到工具时才缓存，避免缓存失败的空结果
        if tools:
            _tools_cache[user_id] = CachedMCPEntry(
                tools=tools,
                client=client,
                config_hash=config_hash,
            )
            logger.info(f"[MCP Cache] Cached {len(tools)} tools for user {user_id}")
        else:
            logger.warning(f"[MCP Cache] Skipped caching empty tools for user {user_id}")

        return tools, client


def invalidate_user_cache(user_id: str) -> bool:
    """
    使指定用户的缓存失效

    当用户修改 MCP 配置时调用此函数。

    Args:
        user_id: 用户 ID

    Returns:
        bool: 是否存在并被失效的缓存
    """
    if user_id in _tools_cache:
        cached = _tools_cache.pop(user_id)
        logger.info(f"[MCP Cache] Invalidated cache for user {user_id}, {len(cached.tools)} tools")

        # 清理客户端连接
        if cached.client:
            try:
                # MultiServerMCPClient 没有显式的 close 方法
                # 但我们可以清理引用
                pass
            except Exception as e:
                logger.warning(f"[MCP Cache] Error cleaning up client: {e}")

        return True

    logger.debug(f"[MCP Cache] No cache to invalidate for user {user_id}")
    return False


def invalidate_all_cache() -> int:
    """
    使所有缓存失效

    用于系统级配置变更时。

    Returns:
        int: 被失效的缓存数量
    """
    count = len(_tools_cache)
    _tools_cache.clear()
    logger.info(f"[MCP Cache] Invalidated all cache, {count} entries")
    return count


def get_cache_stats() -> dict:
    """
    获取缓存统计信息

    Returns:
        dict: 包含缓存统计的字典
    """
    now = time.time()
    stats = {
        "total_entries": len(_tools_cache),
        "entries": [],
    }

    for user_id, cached in _tools_cache.items():
        stats["entries"].append(
            {
                "user_id": user_id,
                "tools_count": len(cached.tools),
                "age_seconds": int(now - cached.created_at),
                "is_expired": cached.is_expired(),
            }
        )

    return stats
