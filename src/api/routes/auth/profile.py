"""
User profile routes (password change, avatar, profile, username)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required
from src.infra.auth.password import verify_password
from src.infra.auth.turnstile import get_turnstile_service
from src.infra.user.manager import UserManager
from src.kernel.exceptions import ValidationError
from src.kernel.schemas.user import TokenPayload, User, UserUpdate

from .utils import _get_client_ip

router = APIRouter()
logger = logging.getLogger(__name__)


class PasswordChangeRequest(BaseModel):
    """Request schema for changing password"""

    old_password: str
    new_password: str


class AvatarUpdateRequest(BaseModel):
    """Request schema for updating avatar"""

    avatar_url: str


class UsernameUpdateRequest(BaseModel):
    """Request schema for updating username"""

    username: str = Field(..., min_length=3, max_length=50)


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    http_request: Request,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    修改当前用户密码

    需要提供旧密码和新密码。
    """
    # Turnstile 验证
    turnstile_service = get_turnstile_service()
    if turnstile_service.require_on_password_change:
        turnstile_token = http_request.headers.get("X-Turnstile-Token")
        client_ip = _get_client_ip(http_request)
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    user = await manager.get_user(current_user.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # Verify old password
    from src.infra.user.storage import UserStorage

    storage = UserStorage()
    db_user = await storage.get_by_id(current_user.sub)

    if not db_user or not verify_password(request.old_password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    # Update password
    await storage.update(current_user.sub, UserUpdate(password=request.new_password))

    return {"message": "密码修改成功"}


@router.post("/update-avatar")
async def update_avatar(
    request: AvatarUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新当前用户头像

    需要提供头像 URL（S3 上传后返回的 URL）。
    """
    manager = UserManager()
    user = await manager.get_user(current_user.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # Update avatar_url
    from src.infra.user.storage import UserStorage

    storage = UserStorage()
    updated_user = await storage.update(current_user.sub, UserUpdate(avatar_url=request.avatar_url))

    return updated_user


@router.get("/profile", response_model=User)
async def get_user_profile(
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取当前用户个人资料

    返回用户的完整信息，包括头像 URL 等。
    """
    manager = UserManager()
    user = await manager.get_user(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user


@router.post("/update-username")
async def update_username(
    request: UsernameUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新当前用户名

    用户名不能与现有用户名重复。
    """
    from src.infra.user.storage import UserStorage

    storage = UserStorage()
    try:
        updated_user = await storage.update(current_user.sub, UserUpdate(username=request.username))
        return updated_user
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
