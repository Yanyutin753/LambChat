"""
会话分享路由

允许用户分享会话，支持公开链接或需要登录访问。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.deps import get_current_user_optional, get_current_user_required
from src.infra.session.dual_writer import get_dual_writer
from src.infra.session.manager import SessionManager
from src.infra.share.storage import ShareStorage
from src.infra.user.storage import UserStorage
from src.kernel.schemas.share import (
    ShareCreate,
    SharedContentOwner,
    SharedContentResponse,
    SharedSessionListItem,
    SharedSessionResponse,
    ShareListResponse,
    ShareType,
    ShareVisibility,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = logging.getLogger(__name__)


def _check_permission(user: TokenPayload, permission: str) -> bool:
    """检查用户是否拥有指定权限"""
    return permission in user.permissions


def _require_share_permission(user: TokenPayload) -> None:
    """要求用户拥有分享权限"""
    if not _check_permission(user, Permission.SESSION_SHARE.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有分享会话的权限",
        )


@router.post("", response_model=SharedSessionResponse)
async def create_share(
    share_data: ShareCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建会话分享

    需要 session:share 权限。
    """
    _require_share_permission(user)

    # 验证会话所有权
    manager = SessionManager()
    session = await manager.get_session(share_data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.user_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能分享自己的会话",
        )

    # 验证 partial share 时提供了 run_ids
    if share_data.share_type == ShareType.PARTIAL and not share_data.run_ids:
        raise HTTPException(
            status_code=400,
            detail="部分分享需要指定 run_ids",
        )

    # 创建分享
    storage = ShareStorage()
    shared_session = await storage.create(share_data, owner_id=user.sub)

    return SharedSessionResponse(
        id=shared_session.id,
        share_id=shared_session.share_id,
        url=f"/shared/{shared_session.share_id}",
        session_id=shared_session.session_id,
        share_type=shared_session.share_type,
        visibility=shared_session.visibility,
        run_ids=shared_session.run_ids,
        created_at=shared_session.created_at,
    )


@router.get("", response_model=ShareListResponse)
async def list_shares(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出我创建的分享

    返回当前用户创建的所有分享记录。
    """
    storage = ShareStorage()
    shares, total = await storage.list_by_owner(user.sub, skip=skip, limit=limit)

    # 获取会话名称
    session_manager = SessionManager()
    result_shares = []
    for share in shares:
        session_name = None
        try:
            session = await session_manager.get_session(share.session_id)
            if session:
                session_name = session.name
        except Exception:
            pass

        result_shares.append(
            SharedSessionListItem(
                id=share.id,
                share_id=share.share_id,
                session_id=share.session_id,
                session_name=session_name,
                share_type=share.share_type,
                visibility=share.visibility,
                run_ids=share.run_ids,
                created_at=share.created_at,
            )
        )

    return ShareListResponse(shares=result_shares, total=total)


@router.get("/session/{session_id}", response_model=list[SharedSessionListItem])
async def list_session_shares(
    session_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出指定会话的所有分享

    只有会话所有者可以查看。
    """
    # 验证会话所有权
    manager = SessionManager()
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.user_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己会话的分享",
        )

    storage = ShareStorage()
    shares = await storage.list_by_session(session_id)

    # 添加会话名称
    result = []
    for share in shares:
        result.append(
            SharedSessionListItem(
                id=share.id,
                share_id=share.share_id,
                session_id=share.session_id,
                session_name=session.name,
                share_type=share.share_type,
                visibility=share.visibility,
                run_ids=share.run_ids,
                created_at=share.created_at,
            )
        )

    return result


@router.delete("/{share_id}")
async def delete_share(
    share_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除分享

    只有分享所有者可以删除。
    """
    storage = ShareStorage()

    # 获取分享记录验证所有权
    share = await storage.get_by_id(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")

    if share.owner_id != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己创建的分享",
        )

    success = await storage.delete(share_id, user.sub)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    return {"status": "deleted"}


# ========================================
# 公开访问路由（无需认证或可选认证）
# ========================================


@router.get("/public/{share_id}", response_model=SharedContentResponse)
async def get_shared_content(
    share_id: str,
    user: Optional[TokenPayload] = Depends(get_current_user_optional),
):
    """
    查看分享的会话内容

    根据 visibility 决定是否需要登录：
    - public: 任何人都可以查看
    - authenticated: 需要登录才能查看
    """
    storage = ShareStorage()
    share = await storage.get_by_share_id(share_id)

    if not share:
        raise HTTPException(status_code=404, detail="分享不存在或已过期")

    # 检查访问权限
    if share.visibility == ShareVisibility.AUTHENTICATED:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能查看此分享",
            )

    # 获取会话信息
    session_manager = SessionManager()
    session = await session_manager.get_session(share.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="原会话已不存在")

    # 获取会话事件
    dual_writer = get_dual_writer()

    # 如果是部分分享，只获取指定 run 的事件
    if share.share_type == ShareType.PARTIAL and share.run_ids:
        # 获取所有指定 run 的事件
        all_events = []
        for run_id in share.run_ids:
            events = await dual_writer.read_session_events(
                share.session_id,
                run_id=run_id,
                completed_only=True,
            )
            all_events.extend(events)
        # 按时间排序
        events = sorted(all_events, key=lambda e: e.get("timestamp", ""))
    else:
        # 全部分享，获取所有事件
        events = await dual_writer.read_session_events(
            share.session_id,
            completed_only=True,
        )

    # 获取分享者信息
    user_storage = UserStorage()
    owner = await user_storage.get_by_id(share.owner_id)
    owner_info = SharedContentOwner(
        username=owner.username if owner else "Unknown",
        avatar_url=owner.avatar_url if owner else None,
    )

    # 构建会话信息（只返回安全的字段）
    session_info = {
        "id": session.id,
        "name": session.name,
        "agent_id": session.agent_id,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }

    return SharedContentResponse(
        session=session_info,
        events=events,
        owner=owner_info,
        share_type=share.share_type,
        run_ids=share.run_ids,
    )
