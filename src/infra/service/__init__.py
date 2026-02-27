"""
第三方服务模块
"""

from src.infra.service.base import BaseService
from src.infra.service.milvus import MilvusService
from src.infra.service.prometheus import PrometheusService

__all__ = [
    "BaseService",
    "MilvusService",
    "PrometheusService",
]
