"""
存储基类

定义存储服务的抽象接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class StorageBase(ABC):
    """
    存储抽象基类

    定义所有存储实现必须遵循的接口。
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        获取数据

        Args:
            key: 键名

        Returns:
            数据或 None
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置数据

        Args:
            key: 键名
            value: 值
            ttl: 过期时间（秒）
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        删除数据

        Args:
            key: 键名

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在

        Args:
            key: 键名

        Returns:
            是否存在
        """
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> list[str]:
        """
        获取匹配的键列表

        Args:
            pattern: 匹配模式

        Returns:
            键列表
        """
        pass
