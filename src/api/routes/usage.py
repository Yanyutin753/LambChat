"""
Usage log routes.

提供 token 消耗追踪接口。
普通用户只能查看自己的用量，管理员可以查看所有用户的用量。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required, require_permissions
from src.infra.usage.notifications import broadcast_quota_changed as _broadcast_quota_changed
from src.infra.usage.storage import get_usage_storage
from src.kernel.schemas.usage import (
    UsageDashboardResponse,
    UsageLog,
    UsageLogListResponse,
    UsageStats,
)
from src.kernel.schemas.usage_quota import (
    QuotaResetRequest,
    ResetCardConsumeRequest,
    ScopedResetCardIssueRequest,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def _is_admin(user: TokenPayload) -> bool:
    """检查用户是否有使用日志管理权限"""
    return "usage:admin" in user.permissions


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/quota")
async def get_usage_quota(user: TokenPayload = Depends(get_current_user_required)) -> dict:
    """Own-account limits; administrative usage visibility never changes the payer."""
    return await _quota_snapshot(user.sub)


async def _quota_snapshot(user_id: str) -> dict:
    from src.infra.usage.quota import UsageQuota, user_budgets
    from src.infra.usage.reset import QuotaReset

    snapshot = await UsageQuota().snapshot(user_id, await user_budgets(user_id))
    snapshot["reset_credits"] = await QuotaReset().credits(user_id)
    return snapshot


async def _active_quota_target(user_id: str) -> None:
    from src.infra.user.storage import UserStorage
    from src.kernel.errors import AppError, ErrorCode

    target = await UserStorage().get_by_id(user_id)
    if target is None:
        raise AppError(ErrorCode.USER_NOT_FOUND)
    if not target.is_active:
        raise AppError(ErrorCode.FORBIDDEN)


@router.get("/users/{user_id}/quota")
async def get_user_usage_quota(
    user_id: str, user: TokenPayload = Depends(require_permissions("usage:admin"))
) -> dict:
    await _active_quota_target(user_id)
    return await _quota_snapshot(user_id)


@router.post("/users/{user_id}/quota/reset")
async def reset_user_usage_quota(
    user_id: str,
    body: QuotaResetRequest,
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.quota import user_budgets
    from src.infra.usage.reset import QuotaReset

    await _active_quota_target(user_id)
    result = await QuotaReset().reset(
        user_id, user.sub, body.window, str(body.idempotency_key), await user_budgets(user_id)
    )
    await _broadcast_quota_changed(user_id)
    return result


@router.post("/users/{user_id}/quota/reset-cards")
async def issue_usage_reset_card(
    user_id: str,
    body: ScopedResetCardIssueRequest,
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.reset import QuotaReset

    await _active_quota_target(user_id)
    result = await QuotaReset().issue_card(
        user_id, user.sub, str(body.idempotency_key), window=body.window
    )
    await _broadcast_quota_changed(user_id)
    return result


@router.post("/quota/reset-cards/consume")
async def consume_usage_reset_card(
    body: ResetCardConsumeRequest,
    user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    from src.infra.usage.quota import user_budgets
    from src.infra.usage.reset import QuotaReset

    result = await QuotaReset().consume(
        user.sub, str(body.idempotency_key), await user_budgets(user.sub), credit_id=body.credit_id
    )
    await _broadcast_quota_changed(user.sub)
    return result


@router.post("/quota/reset-card-batches")
async def create_reset_card_batch(
    body: QuotaResetRequest,
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.reset_batches import ResetCardBatches

    return await ResetCardBatches().create(user.sub, str(body.idempotency_key), body.window)


@router.get("/quota/reset-card-batches")
async def list_reset_card_batches(
    limit: int = Query(1, ge=1, le=20),
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.reset_batches import ResetCardBatches

    return await ResetCardBatches().latest(user.sub, limit)


@router.get("/quota/reset-card-batches/{batch_id}")
async def get_reset_card_batch(
    batch_id: str,
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.reset_batches import ResetCardBatches

    return await ResetCardBatches().get(batch_id, user.sub)


@router.post("/quota/reset-card-batches/{batch_id}/advance")
async def advance_reset_card_batch(
    batch_id: str,
    user: TokenPayload = Depends(require_permissions("usage:admin")),
) -> dict:
    from src.infra.usage.reset_batches import ResetCardBatches

    return await ResetCardBatches().advance(batch_id, user.sub)


@router.get("/logs", response_model=UsageLogListResponse)
async def list_usage_logs(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    user_id: Optional[str] = Query(None, description="按用户ID过滤（仅管理员）"),
    model: Optional[str] = Query(None, description="按模型名称过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 (ISO)"),
    end_date: Optional[str] = Query(None, description="结束日期 (ISO)"),
    search: Optional[str] = Query(None, description="搜索用户名"),
    user: TokenPayload = Depends(get_current_user_required),
) -> UsageLogListResponse:
    """
    获取使用日志列表。

    - 普通用户：只看自己的用量
    - 管理员：可看所有用户，可通过 user_id 过滤
    """
    storage = get_usage_storage()

    # 权限过滤：普通用户只能看自己的数据
    effective_user_id: Optional[str] = user.sub
    effective_search: Optional[str] = None

    if _is_admin(user):
        effective_user_id = user_id  # 管理员可传 None 表示全部
        effective_search = search
    # 非管理员的 user_id 和 search 参数被忽略

    items, total, stats = await storage.list_usage_logs(
        user_id=effective_user_id,
        model=model,
        start_date=start_date,
        end_date=end_date,
        search=effective_search,
        skip=skip,
        limit=limit,
    )
    return UsageLogListResponse(
        items=[UsageLog(**item) for item in items],
        total=total,
        stats=UsageStats(**stats),
    )


@router.get("/stats", response_model=UsageStats)
async def get_usage_stats(
    user_id: Optional[str] = Query(None, description="按用户ID过滤（仅管理员，缺省查自己）"),
    period: Optional[str] = Query("all", description="周期: today, week, month, all"),
    start_date: Optional[str] = Query(
        None, description="起始时间（ISO，含时区），优先于 period 推导"
    ),
    user: TokenPayload = Depends(get_current_user_required),
) -> UsageStats:
    """
    获取聚合用量统计（默认请求者本人；管理员可显式指定 user_id 查他人）。
    """
    storage = get_usage_storage()

    effective_user_id: Optional[str] = user.sub
    if _is_admin(user) and user_id:
        effective_user_id = user_id

    start = start_date or _compute_start_date(period or "all")

    stats = await storage.get_usage_stats_only(
        user_id=effective_user_id,
        start_date=start,
    )
    return UsageStats(**stats)


@router.get("/dashboard", response_model=UsageDashboardResponse)
async def get_usage_dashboard(
    user_id: Optional[str] = Query(None, description="按用户ID过滤（仅管理员）"),
    period: Optional[str] = Query("week", description="周期: today, week, month, all"),
    model: Optional[str] = Query(None, description="按模型名称过滤"),
    search: Optional[str] = Query(None, description="搜索用户名（仅管理员）"),
    start_date: Optional[str] = Query(
        None, description="起始时间（ISO，含时区），优先于 period 推导"
    ),
    user: TokenPayload = Depends(get_current_user_required),
) -> UsageDashboardResponse:
    """获取数字员工运营看板聚合数据。"""
    storage = get_usage_storage()

    effective_user_id: Optional[str] = user.sub
    effective_search: Optional[str] = None
    if _is_admin(user):
        effective_user_id = user_id
        effective_search = search

    data = await storage.get_usage_dashboard(
        user_id=effective_user_id,
        start_date=start_date or _compute_start_date(period or "week"),
        model=model,
        search=effective_search,
    )
    return UsageDashboardResponse(**data)


def _compute_start_date(period: str) -> Optional[str]:
    """将周期名称转换为 ISO 日期字符串"""
    now = _now_utc()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    elif period == "week":
        return (now - timedelta(days=7)).isoformat()
    elif period == "month":
        return (now - timedelta(days=30)).isoformat()
    return None  # "all"
