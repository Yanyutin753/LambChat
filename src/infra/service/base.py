"""
服务基类
"""

from abc import ABC, abstractmethod


class BaseService(ABC):
    """
    服务基类

    所有第三方服务的抽象基类。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """初始化服务"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭服务连接"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
