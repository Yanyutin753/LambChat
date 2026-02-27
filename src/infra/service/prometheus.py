"""
Prometheus 监控服务
"""

from typing import Optional

from src.infra.service.base import BaseService
from src.kernel.config import settings


class PrometheusService(BaseService):
    """
    Prometheus 监控服务

    提供指标收集和查询功能。
    """

    def __init__(self):
        self._url = settings.PROMETHEUS_URL
        self._enabled = settings.PROMETHEUS_ENABLED
        self._session = None

    async def initialize(self) -> None:
        """初始化 Prometheus 连接"""
        if not self._enabled:
            return

        import aiohttp

        self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        """关闭连接"""
        if self._session:
            await self._session.close()
            self._session = None

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._enabled or not self._session:
            return False

        try:
            async with self._session.get(f"{self._url}/-/healthy") as response:
                return response.status == 200
        except Exception:
            return False

    async def query(self, query: str) -> Optional[dict]:
        """执行 PromQL 查询"""
        if not self._enabled or not self._session:
            return None

        try:
            async with self._session.get(
                f"{self._url}/api/v1/query",
                params={"query": query},
            ) as response:
                return await response.json()
        except Exception:
            return None

    async def query_range(
        self,
        query: str,
        start: int,
        end: int,
        step: str = "15s",
    ) -> Optional[dict]:
        """执行范围查询"""
        if not self._enabled or not self._session:
            return None

        try:
            async with self._session.get(
                f"{self._url}/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "step": step,
                },
            ) as response:
                return await response.json()
        except Exception:
            return None
