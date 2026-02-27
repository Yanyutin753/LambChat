"""
Milvus 向量数据库服务
"""

import logging
from typing import Optional

from src.infra.service.base import BaseService
from src.kernel.config import settings

logger = logging.getLogger(__name__)


class MilvusService(BaseService):
    """
    Milvus 向量数据库服务

    提供向量存储和检索功能。
    """

    def __init__(self):
        self._client = None
        self._connected = False

    async def initialize(self) -> None:
        """初始化 Milvus 连接"""
        if not settings.MILVUS_ENABLED:
            return

        try:
            from pymilvus import connections

            connections.connect(
                alias="default",
                host=settings.MILVUS_ADDRESS.split(":")[0],
                port=(
                    int(settings.MILVUS_ADDRESS.split(":")[1])
                    if ":" in settings.MILVUS_ADDRESS
                    else 19530
                ),
                user=settings.MILVUS_USERNAME,
                password=settings.MILVUS_PASSWORD,
                db_name=settings.MILVUS_DATABASE,
            )
            self._connected = True
        except ImportError:
            logger.warning("pymilvus not installed, Milvus service disabled")
        except Exception as e:
            logger.warning(f"Failed to connect to Milvus: {e}")

    async def close(self) -> None:
        """关闭 Milvus 连接"""
        if self._connected:
            try:
                from pymilvus import connections

                connections.disconnect("default")
            except Exception:
                pass
            self._connected = False

    async def health_check(self) -> bool:
        """健康检查"""
        return self._connected

    async def insert(
        self,
        collection_name: str,
        data: list,
    ) -> Optional[list]:
        """插入向量"""
        if not self._connected:
            return None
        # 实现插入逻辑
        return []

    async def search(
        self,
        collection_name: str,
        query_vector: list,
        top_k: int = 10,
    ) -> list:
        """搜索相似向量"""
        if not self._connected:
            return []
        # 实现搜索逻辑
        return []
