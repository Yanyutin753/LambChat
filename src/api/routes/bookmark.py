"""
消息书签路由

书签按 (user_id, session_id, message_id) 唯一，toggle 语义与 pin/favorite 一致。
toggle 端点挂在 /api/sessions/{id}/messages/{mid}/bookmark 下（与 fork/checkpoint
同构），列表端点挂在 /api/bookmarks 下，因此本路由整体注册在 /api 前缀。
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required
from src.api.routes.session import verify_session_ownership
from src.infra.bookmark.storage import BookmarkStorage
from src.infra.logging import get_logger
from src.infra.session.manager import SessionManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.bookmark import BookmarkToggleRequest
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)


@router.post("/sessions/{session_id}/messages/{message_id}/bookmark")
async def toggle_message_bookmark(
    session_id: str,
    message_id: str,
    payload: BookmarkToggleRequest | None = None,
    user: TokenPayload = Depends(get_current_user_required),
):
    """Toggle a bookmark anchored on a specific message."""
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise AppError(ErrorCode.SESSION_NOT_FOUND)
    verify_session_ownership(session, user)

    try:
        bookmarked, bookmark = await BookmarkStorage().toggle(
            user_id=user.sub,
            session_id=session_id,
            message_id=message_id,
            run_id=payload.run_id if payload else None,
            label=payload.label if payload else None,
        )
    except Exception as exc:
        logger.error(
            "Bookmark toggle 500: session=%s message=%s exc=%s",
            session_id,
            message_id,
            exc,
        )
        raise AppError(ErrorCode.BOOKMARK_UPDATE_FAILED) from exc

    return {
        "status": "updated",
        "bookmarked": bookmarked,
        "bookmark": bookmark,
    }


@router.get("/bookmarks/")
async def list_my_bookmarks(
    user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """获取当前用户的全部消息书签（联会话名，按创建时间倒序）"""
    items = await BookmarkStorage().list_for_user(user.sub)
    return {"items": items, "total": len(items)}
