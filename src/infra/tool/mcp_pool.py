"""
MCP 服务器连接池

按服务器名称缓存 MCP 连接，多个用户共享相同的连接。
大幅减少重复连接的创建时间和资源消耗。
"""

import asyncio
import inspect
import time
from typing import Any, Optional, Set

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.kernel.config import settings

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

# 连接过期时间（秒），默认 15 分钟
CONNECTION_TTL = 900
_DEFAULT_CONNECTION_TTL = CONNECTION_TTL

# 最大连接数，防止大量动态 MCP server name 让进程内连接池无限增长
MAX_CONNECTIONS = 100
_DEFAULT_MAX_CONNECTIONS = MAX_CONNECTIONS


def _track_background_task(task: asyncio.Task) -> None:
    """追踪后台任务，完成后自动从集合中移除"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _close_client(client: MultiServerMCPClient) -> None:
    try:
        if hasattr(client, "close"):
            result = client.close()
            if inspect.isawaitable(result):
                await result
        elif hasattr(client, "__aexit__"):
            result = client.__aexit__(None, None, None)  # type: ignore[func-returns-value]
            if inspect.isawaitable(result):
                await result
    except Exception as e:
        logger.debug(f"[MCP Pool] Error closing client: {e}")


def _get_connection_ttl() -> int:
    configured = getattr(settings, "MCP_POOL_TTL_SECONDS", None)
    if CONNECTION_TTL != _DEFAULT_CONNECTION_TTL and configured == _DEFAULT_CONNECTION_TTL:
        return max(int(CONNECTION_TTL), 1)
    return max(int(configured if configured is not None else CONNECTION_TTL), 1)


def _get_max_connections() -> int:
    configured = getattr(settings, "MCP_POOL_MAX_CONNECTIONS", None)
    if MAX_CONNECTIONS != _DEFAULT_MAX_CONNECTIONS and configured == _DEFAULT_MAX_CONNECTIONS:
        return max(int(MAX_CONNECTIONS), 1)
    return max(int(configured if configured is not None else MAX_CONNECTIONS), 1)


class PooledConnection:
    """池化的 MCP 连接"""

    def __init__(
        self,
        server_name: str,
        server_config: dict[str, Any],
        config_hash: str,
        client: MultiServerMCPClient,
        tools: list[BaseTool],
    ):
        self.server_name = server_name
        self.server_config = server_config
        self.config_hash = config_hash
        self.client = client
        self.tools = tools
        self.created_at = time.time()
        self.last_access = time.time()

    def is_expired(self, ttl: float | None = None) -> bool:
        """检查连接是否过期"""
        if ttl is None:
            ttl = _get_connection_ttl()
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
    current_hash = await run_long_blocking_io(_compute_server_hash, server_config)

    async with _pool_lock:
        # 检查连接池
        if server_name in _connection_pool:
            pooled = _connection_pool[server_name]

            # 检查配置是否匹配
            if not pooled.is_expired() and pooled.config_hash == current_hash:
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
    to_close: list[MultiServerMCPClient] = []
    reuse_existing = False
    config_hash = await run_long_blocking_io(_compute_server_hash, server_config)
    async with _pool_lock:
        # 如果已存在且未过期，不覆盖
        if server_name in _connection_pool:
            pooled = _connection_pool[server_name]
            if not pooled.is_expired():
                reuse_existing = True
                if pooled.client is not client:
                    to_close.append(client)
            else:
                to_close.append(pooled.client)

        if not reuse_existing:
            _connection_pool[server_name] = PooledConnection(
                server_name=server_name,
                server_config=server_config,
                config_hash=config_hash,
                client=client,
                tools=tools,
            )
            logger.info(
                f"[MCP Pool] Added connection for server '{server_name}', "
                f"{len(tools)} tools, pool size: {len(_connection_pool)}"
            )

            max_connections = _get_max_connections()
            if len(_connection_pool) > max_connections:
                sorted_entries = sorted(_connection_pool.items(), key=lambda x: x[1].last_access)
                for oldest_name, oldest in sorted_entries[
                    : len(_connection_pool) - max_connections
                ]:
                    if oldest_name == server_name and len(_connection_pool) <= max_connections:
                        continue
                    removed = _connection_pool.pop(oldest_name, None)
                    if removed:
                        to_close.append(removed.client)

    for stale_client in to_close:
        await _close_client(stale_client)


async def cleanup_expired_connections() -> int:
    """清理过期的连接，返回清理的数量"""
    async with _pool_lock:
        expired_servers = [name for name, conn in _connection_pool.items() if conn.is_expired()]

        for server_name in expired_servers:
            pooled = _connection_pool.pop(server_name, None)
            if pooled:
                try:
                    task = asyncio.create_task(_close_client(pooled.client))
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


async def close_all_connections() -> None:
    """Close every pooled MCP connection and clear process-local pool state."""
    async with _pool_lock:
        pooled_connections = list(_connection_pool.values())
        _connection_pool.clear()

    for pooled in pooled_connections:
        await _close_client(pooled.client)

    if _background_tasks:
        await asyncio.gather(*list(_background_tasks), return_exceptions=True)
