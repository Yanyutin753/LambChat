"""
Checkpoint 存储实现

提供 LangGraph checkpointer 的工厂函数，支持 MongoDB 持久化。
"""

import logging
from typing import Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# MongoDB Checkpointer 单例
_mongo_checkpointer: Optional[object] = None


def get_mongo_checkpointer(collection_name: str = "checkpoints"):
    """
    获取 MongoDB checkpointer 单例

    使用 pymongo 同步客户端创建 checkpointer，支持异步操作。

    Args:
        collection_name: MongoDB collection 名称，默认为 "checkpoints"

    Returns:
        MongoDBSaver 实例，如果创建失败则返回 None
    """
    global _mongo_checkpointer
    if _mongo_checkpointer is not None:
        return _mongo_checkpointer

    try:
        from urllib.parse import quote_plus

        from langgraph.checkpoint.mongodb import MongoDBSaver
        from pymongo import MongoClient

        # 构建 MongoDB 连接字符串
        base_url = settings.MONGODB_URL
        username = settings.MONGODB_USERNAME
        password = settings.MONGODB_PASSWORD
        auth_source = settings.MONGODB_AUTH_SOURCE

        if username and password:
            if base_url.startswith("mongodb://"):
                rest = base_url[len("mongodb://") :]
                encoded_user = quote_plus(username)
                encoded_pass = quote_plus(password)
                connection_string = (
                    f"mongodb://{encoded_user}:{encoded_pass}@{rest}?authSource={auth_source}"
                )
            elif base_url.startswith("mongodb+srv://"):
                rest = base_url[len("mongodb+srv://") :]
                encoded_user = quote_plus(username)
                encoded_pass = quote_plus(password)
                connection_string = (
                    f"mongodb+srv://{encoded_user}:{encoded_pass}@{rest}?authSource={auth_source}"
                )
            else:
                connection_string = base_url
        else:
            connection_string = base_url

        # 创建同步客户端（MongoDBSaver 需要）
        client: MongoClient = MongoClient(connection_string)

        # 创建 checkpointer
        _mongo_checkpointer = MongoDBSaver(
            client,
            db_name=settings.MONGODB_DB,
            checkpoint_collection_name=collection_name,
        )

        logger.info(f"MongoDB checkpointer created: {settings.MONGODB_DB}.{collection_name}")
        return _mongo_checkpointer

    except ImportError as e:
        logger.warning(f"MongoDB checkpointer not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to create MongoDB checkpointer: {e}")
        return None


def get_checkpointer():
    """
    获取 checkpointer 实例

    优先使用 MongoDB（持久化），如果不可用则返回 MemorySaver。

    Returns:
        Checkpointer 实例
    """
    # 优先尝试 MongoDB
    checkpointer = get_mongo_checkpointer()
    if checkpointer is not None:
        return checkpointer

    # 回退到 Memory
    from langgraph.checkpoint.memory import MemorySaver

    logger.warning("Using MemorySaver (data will be lost on restart)")
    return MemorySaver()
