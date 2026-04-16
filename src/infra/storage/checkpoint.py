"""
Checkpoint 存储实现

提供 LangGraph checkpointer 的工厂函数，支持 MongoDB 和 PostgreSQL 持久化。

用户通过 CHECKPOINT_BACKEND 配置选择后端：
- "mongodb": 使用 MongoDBSaver（默认，受 16MB 文档大小限制）
- "postgres": 使用 AsyncPostgresSaver（无文档大小限制，需 ENABLE_POSTGRES_STORAGE=true）

两者都不可用时回退到 MemorySaver（内存存储，重启丢失）。
"""

from typing import Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# MongoDB Checkpointer 单例
_mongo_checkpointer: Optional[object] = None

# PostgreSQL Checkpointer 单例
_pg_checkpointer: Optional[object] = None
_pg_checkpointer_ctx: Optional[object] = None  # from_conn_string() 返回的 async context manager


def get_mongo_checkpointer(collection_name: str = "checkpoints"):
    """
    获取 MongoDB checkpointer 单例

    复用 motor 的底层同步 MongoClient，避免创建独立的同步连接池。

    Args:
        collection_name: MongoDB collection 名称，默认为 "checkpoints"

    Returns:
        MongoDBSaver 实例，如果创建失败则返回 None
    """
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        return _mongo_checkpointer

    try:
        from langgraph.checkpoint.mongodb import MongoDBSaver

        from src.infra.storage.mongodb import get_mongo_client

        motor_client = get_mongo_client()
        sync_client = motor_client.delegate

        cp = MongoDBSaver(
            sync_client,
            db_name=settings.MONGODB_DB,
            checkpoint_collection_name=collection_name,
        )

        logger.info(
            f"MongoDB checkpointer created: {settings.MONGODB_DB}.{collection_name} (reusing motor connection pool)"
        )
        _mongo_checkpointer = cp
        return _mongo_checkpointer

    except ImportError as e:
        logger.warning(f"MongoDB checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create MongoDB checkpointer: {e}")
        return None


def close_mongo_checkpointer():
    """释放 MongoDB checkpointer 单例引用，允许 GC 回收。"""
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        _mongo_checkpointer = None
        logger.info("MongoDB checkpointer reference released")


async def get_pg_checkpointer():
    """
    获取 PostgreSQL checkpointer 单例（异步）

    使用 AsyncPostgresSaver.from_conn_string()，无 16MB 文档大小限制。
    需要 ENABLE_POSTGRES_STORAGE=true 且 CHECKPOINT_BACKEND=postgres。

    Returns:
        AsyncPostgresSaver 实例，如果创建失败则返回 None
    """
    global _pg_checkpointer, _pg_checkpointer_ctx

    if _pg_checkpointer is not None:
        return _pg_checkpointer

    if not settings.ENABLE_POSTGRES_STORAGE:
        logger.warning("PostgreSQL checkpointer requested but ENABLE_POSTGRES_STORAGE is false")
        return None

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        ctx = AsyncPostgresSaver.from_conn_string(settings.postgres_url)
        try:
            cp = await ctx.__aenter__()
        except Exception:
            await ctx.__aexit__(None, None, None)
            raise

        logger.info("PostgreSQL checkpointer created (AsyncPostgresSaver via from_conn_string)")
        _pg_checkpointer_ctx = ctx
        _pg_checkpointer = cp
        return _pg_checkpointer

    except ImportError as e:
        logger.warning(f"PostgreSQL checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create PostgreSQL checkpointer: {e}")
        return None


async def close_pg_checkpointer():
    """
    关闭 PostgreSQL checkpointer（释放连接）

    应在应用关闭时调用。
    """
    global _pg_checkpointer, _pg_checkpointer_ctx
    if _pg_checkpointer is not None:
        try:
            await _pg_checkpointer_ctx.__aexit__(None, None, None)
            logger.info("PostgreSQL checkpointer closed")
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL checkpointer: {e}")
        finally:
            _pg_checkpointer = None
            _pg_checkpointer_ctx = None


async def get_async_checkpointer():
    """
    获取 checkpointer 实例（兼容异步调用）

    根据 CHECKPOINT_BACKEND 配置选择后端：
    - "postgres": 优先使用 PostgreSQL（无 16MB 限制）
    - "mongodb": 使用 MongoDB（默认）
    - 都不可用: 回退到 MemorySaver

    Returns:
        Checkpointer 实例
    """
    backend = getattr(settings, "CHECKPOINT_BACKEND", "mongodb")

    if backend == "postgres":
        checkpointer = await get_pg_checkpointer()
        if checkpointer is not None:
            return checkpointer
        logger.warning("PostgreSQL checkpointer unavailable, falling back")

    # MongoDB (default)
    checkpointer = get_mongo_checkpointer()
    if checkpointer is not None:
        return checkpointer

    # MemorySaver fallback
    from langgraph.checkpoint.memory import MemorySaver

    if not hasattr(get_async_checkpointer, "_memory_saver"):
        get_async_checkpointer._memory_saver = MemorySaver()  # type: ignore[attr-defined]
        logger.warning("Using MemorySaver singleton (data will be lost on restart)")
    return get_async_checkpointer._memory_saver  # type: ignore[attr-defined]
