"""
用户反馈路由

提供用户反馈的 API 端点。
每个用户对每个 run 只能提交一次反馈。
"""

from functools import lru_cache
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required, require_permissions
from src.infra.feedback.manager import FeedbackManager
from src.infra.logging import get_logger
from src.kernel.schemas.feedback import (
    Feedback,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackStats,
    RatingValue,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)


@lru_cache
def get_feedback_manager() -> FeedbackManager:
    """获取反馈管理器依赖（单例）"""
    return FeedbackManager()


def validate_object_id(id_str: str) -> ObjectId:
    """验证并转换字符串为 ObjectId"""
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid feedback ID format",
        )


@router.post("/", response_model=Feedback)
async def submit_feedback(
    feedback_data: FeedbackCreate,
    user: TokenPayload = Depends(get_current_user_required),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> Feedback:
    """
    提交用户反馈

    需要 feedback:write 权限
    每个用户对每个 run 只能提交一次反馈
    """
    if "feedback:write" not in user.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缺少权限: feedback:write",
        )

    try:
        feedback = await manager.submit_feedback(
            user_id=user.sub,
            username=user.username,
            data=feedback_data,
        )
        return feedback
    except ValueError as e:
        logger.warning(f"Duplicate feedback for user {user.sub}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/", response_model=FeedbackListResponse)
async def list_feedback(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(50, ge=1, le=100, description="限制数量"),
    rating: Optional[RatingValue] = Query(None, description="评分过滤：up 或 down"),
    user_id: Optional[str] = Query(None, description="用户ID过滤"),
    session_id: Optional[str] = Query(None, description="会话ID过滤"),
    _: None = Depends(require_permissions("feedback:read")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> FeedbackListResponse:
    """
    获取反馈列表

    需要 feedback:read 权限
    """
    return await manager.list_feedback(
        skip=skip,
        limit=limit,
        rating=rating,
        user_id=user_id,
        session_id=session_id,
    )


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(
    session_id: Optional[str] = Query(None, description="会话ID过滤"),
    run_id: Optional[str] = Query(None, description="运行ID过滤"),
    _: None = Depends(require_permissions("feedback:read")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> FeedbackStats:
    """
    获取反馈统计信息

    需要 feedback:read 权限
    """
    return await manager.get_stats(session_id, run_id)


@router.get("/my/by-run/{session_id}/{run_id}", response_model=Optional[Feedback])
async def get_my_feedback_for_run(
    session_id: str,
    run_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> Optional[Feedback]:
    """
    获取当前用户对某个 run 的反馈

    需要 feedback:write 权限（表示用户可以查看自己的反馈）
    """
    if "feedback:write" not in user.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缺少权限: feedback:write",
        )
    return await manager.get_user_feedback_for_run(user.sub, session_id, run_id)


@router.get("/by-run/{session_id}/{run_id}", response_model=list[Feedback])
async def get_feedback_by_run(
    session_id: str,
    run_id: str,
    _: None = Depends(require_permissions("feedback:read")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> list[Feedback]:
    """
    获取某个 run 的所有反馈

    需要 feedback:read 权限
    """
    return await manager.get_feedback_by_run(session_id, run_id)


@router.get("/stats/{session_id}/{run_id}", response_model=FeedbackStats)
async def get_run_feedback_stats(
    session_id: str,
    run_id: str,
    _: None = Depends(require_permissions("feedback:read")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> FeedbackStats:
    """
    获取某个 run 的反馈统计

    需要 feedback:read 权限
    """
    return await manager.get_stats(session_id, run_id)


@router.delete("/{feedback_id}")
async def delete_feedback(
    feedback_id: str,
    _: None = Depends(require_permissions("feedback:admin")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> dict:
    """
    删除反馈

    需要 feedback:admin 权限
    """
    validated_id = validate_object_id(feedback_id)

    success = await manager.delete_feedback(str(validated_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
        )
    return {"status": "deleted"}
