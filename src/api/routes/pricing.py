"""Pricing routes.

- GET  /api/pricing/rates   汇率表（登录用户，前端本地货币换算）
- POST /api/pricing/sync    手动同步价格 + 汇率（管理员）
- GET  /api/pricing/status  同步状态（管理员）
- GET  /api/pricing/lookup  按模型标识查询单价（管理员，模型表单提示）
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required, require_permissions
from src.infra.logging import get_logger
from src.infra.pricing import service as pricing_service
from src.infra.pricing.storage import get_pricing_storage
from src.infra.pricing.sync import sync_pricing
from src.kernel.schemas.pricing import (
    FxRatesResponse,
    PricingBackfillResponse,
    PricingLookupResponse,
    PricingStatusResponse,
    PricingSyncResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = get_logger(__name__)


@router.get("/rates", response_model=FxRatesResponse)
async def get_fx_rates(
    user: TokenPayload = Depends(get_current_user_required),
) -> FxRatesResponse:
    """获取 USD 基准汇率表；从未同步时返回空表（前端回落 USD 展示）。"""
    doc = await pricing_service.get_fx_rates()
    if not doc:
        return FxRatesResponse()
    return FxRatesResponse(
        base=str(doc.get("base") or "USD"),
        rates=doc.get("rates") or {},
        synced_at=doc.get("synced_at"),
    )


@router.post("/sync", response_model=PricingSyncResponse)
async def sync_pricing_prices(
    user: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
) -> PricingSyncResponse:
    """手动同步 models.dev 价格与 USD 汇率（强制刷新）。"""
    status = await sync_pricing(force=True)
    pricing_service.reset_runtime_cache()
    return PricingSyncResponse(**status)


@router.get("/status", response_model=PricingStatusResponse)
async def get_pricing_status(
    user: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
) -> PricingStatusResponse:
    """查看价格/汇率快照状态。"""
    status = await get_pricing_storage().get_status()
    return PricingStatusResponse(**status)


@router.get("/lookup", response_model=PricingLookupResponse)
async def lookup_price(
    value: str = Query(..., description="模型标识，如 openai/gpt-4o"),
    provider: Optional[str] = Query(None, description="Provider 提示"),
    model_id: Optional[str] = Query(None, description="模型配置 ID（覆盖优先）"),
    user: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
) -> PricingLookupResponse:
    """查询某模型解析后的单价与来源。"""
    resolved = await pricing_service.resolve_price(
        value=value, provider=provider, model_config_id=model_id
    )
    if resolved is None:
        return PricingLookupResponse()
    return PricingLookupResponse(
        found=True,
        source=resolved.source,
        rates={
            "input": resolved.rates.input,
            "output": resolved.rates.output,
            "cache_read": resolved.rates.cache_read,
            "cache_write": resolved.rates.cache_write,
        },
        matched_provider=resolved.matched_provider,
        matched_model_id=resolved.matched_model_id,
    )


@router.post("/backfill-usage", response_model=PricingBackfillResponse)
async def backfill_usage_costs(
    dry_run: bool = Query(False, description="只统计不写入"),
    user: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
) -> PricingBackfillResponse:
    """用当前价格快照补算存量 usage_logs 的费用（幂等，可重复执行）。"""
    from fastapi import HTTPException

    from src.infra.pricing.backfill import backfill_usage_costs as run_backfill

    summary = await run_backfill(dry_run=dry_run)
    if summary.get("lock_contended"):
        raise HTTPException(status_code=409, detail="Another replica is running the backfill")
    return PricingBackfillResponse(**summary)
