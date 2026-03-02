"""
PostgreSQL 存储实现

提供 LangGraph PostgresStore 的工厂函数。
"""

import logging
from typing import Any

from langgraph.store.postgres import PostgresStore
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# 全局连接池（所有 agent 共享）
_connection_pool: ConnectionPool[Connection[dict[str, Any]]] | None = None


def get_connection_pool() -> ConnectionPool[Connection[dict[str, Any]]]:
    """
    获取或创建全局连接池

    连接池在所有 agent 之间共享，支持高并发访问。

    Returns:
        ConnectionPool 实例
    """
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool[Connection[dict[str, Any]]](
            settings.postgres_url,
            min_size=settings.POSTGRES_POOL_MIN_SIZE,
            max_size=settings.POSTGRES_POOL_MAX_SIZE,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        logger.info(
            f"PostgreSQL connection pool created (min={settings.POSTGRES_POOL_MIN_SIZE}, max={settings.POSTGRES_POOL_MAX_SIZE})"
        )
    return _connection_pool


def create_postgres_store() -> PostgresStore:
    """
    创建新的 PostgresStore 实例

    每个 agent 应该调用此函数创建自己的 store 实例。
    所有 store 共享同一个连接池。

    Returns:
        PostgresStore 实例
    """
    pool = get_connection_pool()
    store = PostgresStore(conn=pool)
    store.setup()
    return store


def close_connection_pool() -> None:
    """
    关闭全局连接池

    应在应用关闭时调用以进行优雅关闭。
    """
    global _connection_pool
    if _connection_pool is not None:
        try:
            _connection_pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.warning(f"Error closing connection pool: {e}")
        finally:
            _connection_pool = None
