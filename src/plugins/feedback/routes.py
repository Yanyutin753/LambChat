"""Feedback plugin API routes.

The legacy import path ``src.api.routes.feedback`` is kept as a module alias,
but the route implementation is owned by this static plugin package.
"""

from functools import lru_cache
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_required, require_permissions
from src.api.routes.plugin_guard import plugin_route_guard
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

logger = get_logger(__name__)
FEEDBACK_PLUGIN_ID = "feedback"


router = APIRouter(dependencies=[Depends(plugin_route_guard(FEEDBACK_PLUGIN_ID))])


@lru_cache
def get_feedback_manager() -> FeedbackManager:
    """Return the cached Feedback manager used by the plugin routes."""
    return FeedbackManager()


async def close_feedback_manager() -> None:
    if get_feedback_manager.cache_info().currsize == 0:
        return
    try:
        await get_feedback_manager().close()
    finally:
        get_feedback_manager.cache_clear()


def validate_object_id(id_str: str) -> ObjectId:
    """Validate and convert a string ObjectId."""
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
    """Submit user feedback for one run."""
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
        logger.warning("Duplicate feedback for user %s: %s", user.sub, e)
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
    """List feedback records."""
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
    """Return feedback statistics."""
    return await manager.get_stats(session_id, run_id)


@router.get("/my/by-run/{session_id}/{run_id}", response_model=Optional[Feedback])
async def get_my_feedback_for_run(
    session_id: str,
    run_id: str,
    user: TokenPayload = Depends(get_current_user_required),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> Optional[Feedback]:
    """Return the current user's feedback for one run."""
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
    """Return all feedback for one run."""
    return await manager.get_feedback_by_run(session_id, run_id)


@router.get("/stats/{session_id}/{run_id}", response_model=FeedbackStats)
async def get_run_feedback_stats(
    session_id: str,
    run_id: str,
    _: None = Depends(require_permissions("feedback:read")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> FeedbackStats:
    """Return feedback statistics for one run."""
    return await manager.get_stats(session_id, run_id)


@router.delete("/{feedback_id}")
async def delete_feedback(
    feedback_id: str,
    _: None = Depends(require_permissions("feedback:admin")),
    manager: FeedbackManager = Depends(get_feedback_manager),
) -> dict:
    """Delete a feedback record."""
    validated_id = validate_object_id(feedback_id)

    success = await manager.delete_feedback(str(validated_id))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
        )
    return {"status": "deleted"}


__all__ = [
    "FeedbackManager",
    "close_feedback_manager",
    "delete_feedback",
    "get_feedback_by_run",
    "get_feedback_manager",
    "get_feedback_stats",
    "get_my_feedback_for_run",
    "get_run_feedback_stats",
    "list_feedback",
    "router",
    "submit_feedback",
    "validate_object_id",
]
