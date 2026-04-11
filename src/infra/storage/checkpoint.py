"""
Checkpoint 存储实现

提供 LangGraph checkpointer 的工厂函数，支持 MongoDB 持久化。

langgraph-checkpoint-mongodb 的 MongoDBSaver 是同步的，但其异步方法
（aput, aget_tuple 等）通过 run_in_executor 包装，不会阻塞事件循环。
这里复用 motor AsyncIOMotorClient 的底层同步客户端，避免创建第二个连接池。
"""

from typing import Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# MongoDB Checkpointer 单例
_mongo_checkpointer: Optional[object] = None


def get_mongo_checkpointer(collection_name: str = "checkpoints"):
    """
    获取 MongoDB checkpointer 单例

    复用 motor 的底层 pymongo.MongoClient（通过 delegate 属性），
    避免创建独立的同步连接池。shutdown 时由 close_mongo_client() 统一清理。

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

        # 复用 motor 的底层同步 MongoClient，避免连接池泄漏
        from src.infra.storage.mongodb import get_mongo_client

        motor_client = get_mongo_client()
        sync_client = motor_client.delegate

        _mongo_checkpointer = MongoDBSaver(
            sync_client,
            db_name=settings.MONGODB_DB,
            checkpoint_collection_name=collection_name,
        )

        logger.info(
            f"MongoDB checkpointer created: {settings.MONGODB_DB}.{collection_name} (reusing motor connection pool)"
        )
        return _mongo_checkpointer

    except ImportError as e:
        logger.warning(f"MongoDB checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create MongoDB checkpointer: {e}")
        return None


async def get_async_checkpointer():
    """
    获取 checkpointer 实例（兼容异步调用）

    优先使用 MongoDB（持久化），如果不可用则返回 MemorySaver。

    Returns:
        Checkpointer 实例
    """
    checkpointer = get_mongo_checkpointer()
    if checkpointer is not None:
        return checkpointer

    # MemorySaver fallback: 使用单例避免每次请求创建新实例
    from langgraph.checkpoint.memory import MemorySaver

    if not hasattr(get_async_checkpointer, "_memory_saver"):
        get_async_checkpointer._memory_saver = MemorySaver()  # type: ignore[attr-defined]
        logger.warning("Using MemorySaver singleton (data will be lost on restart)")
    return get_async_checkpointer._memory_saver  # type: ignore[attr-defined]
