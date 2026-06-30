"""
Usage log routes.

提供 token 消耗追踪接口。
普通用户只能查看自己的用量，管理员可以查看所有用户的用量。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required
from src.api.routes.plugin_guard import plugin_route_guard
from src.infra.logging import get_logger
from src.infra.usage.storage import get_usage_storage
from src.kernel.schemas.usage import (
    UsageDashboardResponse,
    UsageLog,
    UsageLogListResponse,
    UsageStats,
)
from src.kernel.schemas.user import TokenPayload

USAGE_REPORTS_PLUGIN_ID = "usage_reports"

router = APIRouter(dependencies=[Depends(plugin_route_guard(USAGE_REPORTS_PLUGIN_ID))])
logger = get_logger(__name__)


def _is_admin(user: TokenPayload) -> bool:
    """检查用户是否有使用日志管理权限"""
    return "usage:admin" in user.permissions


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
    user_id: Optional[str] = Query(None, description="按用户ID过滤（仅管理员）"),
    period: Optional[str] = Query("all", description="周期: today, week, month, all"),
    user: TokenPayload = Depends(get_current_user_required),
) -> UsageStats:
    """
    获取聚合用量统计。
    """
    storage = get_usage_storage()

    effective_user_id: Optional[str] = user.sub
    if _is_admin(user):
        effective_user_id = user_id

    start_date = _compute_start_date(period or "all")

    _, _, stats = await storage.list_usage_logs(
        user_id=effective_user_id,
        start_date=start_date,
        skip=0,
        limit=1,  # 只需要 stats，不需要 items
    )
    return UsageStats(**stats)


@router.get("/dashboard", response_model=UsageDashboardResponse)
async def get_usage_dashboard(
    user_id: Optional[str] = Query(None, description="按用户ID过滤（仅管理员）"),
    period: Optional[str] = Query("week", description="周期: today, week, month, all"),
    model: Optional[str] = Query(None, description="按模型名称过滤"),
    search: Optional[str] = Query(None, description="搜索用户名（仅管理员）"),
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
        start_date=_compute_start_date(period or "week"),
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
