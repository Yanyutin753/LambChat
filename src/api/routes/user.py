"""User administration with separate profile, credential and grant authority."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_current_user_required, require_permissions
from src.infra.auth.delegation import (
    authority_mutation,
    authorize_role_assignment,
    ensure_usable_administrator,
    ensure_user_target,
    require_capability,
)
from src.infra.logging import get_logger
from src.infra.user.manager import UserManager
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import (
    AdminUserCreate,
    AdminUserUpdate,
    TokenPayload,
    User,
    UserCreate,
    UserListResponse,
    UserUpdate,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    _: None = Depends(require_permissions("user:read")),
):
    return await UserManager().list_users(skip, limit, search)


@router.post("/", response_model=User)
async def create_user(
    user_data: AdminUserCreate,
    current_user: TokenPayload = Depends(require_permissions("user:create")),
):
    async with authority_mutation(current_user) as actor:
        require_capability(actor, "user:create")
        if user_data.roles:
            await authorize_role_assignment(actor, user_data.roles)
        internal = UserCreate(**user_data.model_dump(), skip_verification=True)
        user = await UserManager().register(internal, assign_default_role=False)
        logger.info(
            "Account created actor=%s target=%s fields=%s",
            actor.sub,
            user.id,
            sorted(user_data.model_fields_set),
        )
        return user


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    _: None = Depends(require_permissions("user:read")),
):
    user = await UserManager().get_user(user_id)
    if not user:
        raise AppError(ErrorCode.USER_NOT_FOUND)
    return user


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    user_data: AdminUserUpdate,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    fields = user_data.model_fields_set
    async with authority_mutation(current_user) as actor:
        if fields & {"username", "email", "avatar_url"} or not fields:
            require_capability(actor, "user:write")
        if fields & {"password", "email"}:
            require_capability(actor, "user:reset_password")
        if "is_active" in fields:
            require_capability(actor, "user:status")
        if "roles" in fields:
            require_capability(actor, "user:assign_roles")
            if user_id == actor.sub:
                raise AppError(ErrorCode.CANNOT_CHANGE_OWN_ROLE_PERMISSIONS)
        if any(
            getattr(user_data, key) is None
            for key in fields & {"roles", "password", "is_active", "email", "username"}
        ):
            raise AppError(ErrorCode.BAD_REQUEST)

        manager = UserManager()
        target = await manager.get_user(user_id)
        if not target:
            raise AppError(ErrorCode.USER_NOT_FOUND)
        existing_roles = await ensure_user_target(actor, target)
        next_roles = existing_roles
        if user_data.roles is not None:
            next_roles = await authorize_role_assignment(actor, user_data.roles)
        had_admin = any("system:admin" in role.permissions for role in existing_roles)
        keeps_admin = any("system:admin" in role.permissions for role in next_roles)
        if had_admin and (
            user_data.is_active is False
            or not keeps_admin
            or (
                user_data.email is not None
                and user_data.email != target.email
                and settings.REQUIRE_EMAIL_VERIFICATION
            )
        ):
            await ensure_usable_administrator(excluded_user_id=user_id)
        user = await manager.update_user(
            user_id, UserUpdate(**user_data.model_dump(exclude_unset=True))
        )
        if not user:
            raise AppError(ErrorCode.USER_NOT_FOUND)
        logger.info(
            "Account updated actor=%s target=%s fields=%s", actor.sub, user_id, sorted(fields)
        )
        return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenPayload = Depends(require_permissions("user:delete")),
):
    async with authority_mutation(current_user) as actor:
        require_capability(actor, "user:delete")
        manager = UserManager()
        target = await manager.get_user(user_id)
        if not target:
            raise AppError(ErrorCode.USER_NOT_FOUND)
        roles = await ensure_user_target(actor, target)
        if any("system:admin" in role.permissions for role in roles):
            await ensure_usable_administrator(excluded_user_id=user_id)
        if not await manager.delete_user(user_id):
            raise AppError(ErrorCode.USER_NOT_FOUND)
        logger.info("Account deleted actor=%s target=%s", actor.sub, user_id)
        return {"status": "deleted"}
