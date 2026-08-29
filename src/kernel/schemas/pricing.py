"""Pricing schemas: 汇率查询、同步状态、模型价格查询。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FxRatesResponse(BaseModel):
    """USD 基准汇率表（前端本地货币换算用）。"""

    base: str = "USD"
    rates: dict[str, float] = Field(default_factory=dict)
    synced_at: Optional[datetime] = None


class PricingSnapshotInfo(BaseModel):
    """models.dev 价格快照状态。"""

    entry_count: int = 0
    source_url: str = ""
    synced_at: Optional[datetime] = None


class PricingFxInfo(BaseModel):
    """汇率表状态。"""

    base: str = "USD"
    rate_count: int = 0
    synced_at: Optional[datetime] = None


class PricingStatusResponse(BaseModel):
    """同步状态（管理员）。"""

    prices: PricingSnapshotInfo = Field(default_factory=PricingSnapshotInfo)
    fx: PricingFxInfo = Field(default_factory=PricingFxInfo)


class PricingSyncResponse(PricingStatusResponse):
    """手动同步结果（管理员）。"""

    refreshed: bool = False
    error: Optional[str] = None


class PricingLookupResponse(BaseModel):
    """按模型标识查询解析后的单价（管理员，模型表单提示用）。"""

    found: bool = False
    source: str = ""
    rates: Optional[dict[str, Optional[float]]] = None
    matched_provider: str = ""
    matched_model_id: str = ""
