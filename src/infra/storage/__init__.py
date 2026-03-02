"""
存储模块

提供存储服务的抽象和实现。
"""

from src.infra.storage.base import StorageBase
from src.infra.storage.mongodb import MongoDBStorage
from src.infra.storage.postgres import (
    close_connection_pool,
    create_postgres_store,
    get_connection_pool,
)
from src.infra.storage.redis import RedisStorage

__all__ = [
    "StorageBase",
    "MongoDBStorage",
    "RedisStorage",
    "get_connection_pool",
    "create_postgres_store",
    "close_connection_pool",
]
