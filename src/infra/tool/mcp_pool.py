"""
MCP 服务器连接池

按服务器名称缓存 MCP 连接，多个用户共享相同的连接。
大幅减少重复连接的创建时间和资源消耗。
"""

import asyncio
import time
from typing import Any, Optional, Set

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.infra.logging import get_logger

logger = get_logger(__name__)

# 连接池：server_name -> PooledConnection
_connection_pool: dict[str, "PooledConnection"] = {}

# 连接池锁
_pool_lock = asyncio.Lock()

# 后台任务追踪集合
_background_tasks: Set[asyncio.Task] = set()

# 清理计数器
_cleanup_counter = 0

# 清理检查间隔
CLEANUP_CHECK_INTERVAL = 20

# 连接过期时间（秒），默认 30 分钟
CONNECTION_TTL = 1800


def _track_background_task(task: asyncio.Task) -> None:
    """追踪后台任务，完成后自动从集合中移除"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class PooledConnection:
    """池化的 MCP 连接"""

    def __init__(
        self,
        server_name: str,
        server_config: dict[str, Any],
        client: MultiServerMCPClient,
        tools: list[BaseTool],
    ):
        self.server_name = server_name
        self.server_config = server_config
        self.client = client
        self.tools = tools
        self.created_at = time.time()
        self.last_access = time.time()

    def is_expired(self, ttl: float = CONNECTION_TTL) -> bool:
        """检查连接是否过期"""
        return time.time() - self.created_at > ttl

    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()


def _compute_server_hash(server_config: dict[str, Any]) -> str:
    """计算服务器配置的哈希值"""
    import hashlib
    import json

    config_str = json.dumps(server_config, sort_keys=True, default=str)
    return hashlib.md5(config_str.encode()).hexdigest()


async def get_pooled_connection(
    server_name: str,
    server_config: dict[str, Any],
) -> tuple[Optional[MultiServerMCPClient], list[BaseTool]]:
    """
    获取池化的 MCP 连接（如果可用）

    Args:
        server_name: 服务器名称
        server_config: 服务器配置

    Returns:
        tuple: (client, tools) - 客户端和工具列表
    """
    # 定期清理过期连接
    await _maybe_cleanup()

    async with _pool_lock:
        # 检查连接池
        if server_name in _connection_pool:
            pooled = _connection_pool[server_name]

            # 检查配置是否匹配
            current_hash = _compute_server_hash(server_config)
            if (
                not pooled.is_expired()
                and _compute_server_hash(pooled.server_config) == current_hash
            ):
                pooled.touch()
                logger.debug(
                    f"[MCP Pool] Reusing connection for server '{server_name}', "
                    f"{len(pooled.tools)} tools"
                )
                return pooled.client, pooled.tools

        # 没有可用连接
        return None, []


async def add_pooled_connection(
    server_name: str,
    server_config: dict[str, Any],
    client: MultiServerMCPClient,
    tools: list[BaseTool],
) -> None:
    """
    添加连接到连接池

    Args:
        server_name: 服务器名称
        server_config: 服务器配置
        client: MCP 客户端
        tools: 工具列表
    """
    async with _pool_lock:
        # 如果已存在且未过期，不覆盖
        if server_name in _connection_pool:
            pooled = _connection_pool[server_name]
            if not pooled.is_expired():
                return

        _connection_pool[server_name] = PooledConnection(
            server_name=server_name,
            server_config=server_config,
            client=client,
            tools=tools,
        )
        logger.info(
            f"[MCP Pool] Added connection for server '{server_name}', "
            f"{len(tools)} tools, pool size: {len(_connection_pool)}"
        )


async def cleanup_expired_connections() -> int:
    """清理过期的连接，返回清理的数量"""
    async with _pool_lock:
        expired_servers = [name for name, conn in _connection_pool.items() if conn.is_expired()]

        for server_name in expired_servers:
            pooled = _connection_pool.pop(server_name, None)
            if pooled:
                try:
                    if hasattr(pooled.client, "close"):
                        task = asyncio.create_task(pooled.client.close())
                        _track_background_task(task)
                    elif hasattr(pooled.client, "__aexit__"):
                        task = asyncio.create_task(pooled.client.__aexit__(None, None, None))  # type: ignore[func-returns-value]
                        _track_background_task(task)
                except Exception as e:
                    logger.debug(f"[MCP Pool] Error cleaning up client for {server_name}: {e}")

        if expired_servers:
            logger.info(f"[MCP Pool] Cleaned up {len(expired_servers)} expired connections")

        return len(expired_servers)


async def _maybe_cleanup() -> None:
    """定期清理过期连接"""
    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter >= CLEANUP_CHECK_INTERVAL:
        _cleanup_counter = 0
        await cleanup_expired_connections()


async def get_pool_stats() -> dict[str, Any]:
    """获取连接池统计信息"""
    async with _pool_lock:
        servers_list: list[dict[str, Any]] = []

        for server_name, conn in _connection_pool.items():
            servers_list.append(
                {
                    "server_name": server_name,
                    "tools_count": len(conn.tools),
                    "age_seconds": int(time.time() - conn.created_at),
                    "is_expired": conn.is_expired(),
                }
            )

        stats: dict[str, Any] = {
            "total_connections": len(_connection_pool),
            "servers": servers_list,
        }

        return stats
