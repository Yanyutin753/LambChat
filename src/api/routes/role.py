"""
角色路由
"""

from fastapi import APIRouter, Depends, Query

from src.api.deps import (
    get_current_user_required,
    require_permissions,
)
from src.infra.role.manager import RoleManager
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.role import Role, RoleCreate, RoleListResponse, RoleUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/", response_model=RoleListResponse)
async def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    q: str | None = None,
    _: TokenPayload = Depends(get_current_user_required),
):
    """列出角色（只需登录）"""
    manager = RoleManager()
    roles = await manager.list_roles(skip, limit, q)
    total = await manager.count_roles(q)
    return RoleListResponse(roles=roles, total=total, skip=skip, limit=limit)


@router.post("/", response_model=Role)
async def create_role(
    role_data: RoleCreate,
    _: None = Depends(require_permissions("role:manage")),
):
    """创建角色"""
    manager = RoleManager()
    return await manager.create_role(role_data)


@router.get("/{role_id}", response_model=Role)
async def get_role(
    role_id: str,
    _: None = Depends(require_permissions("role:manage")),
):
    """获取角色"""
    manager = RoleManager()
    role = await manager.get_role(role_id)
    if not role:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    return role


@router.put("/{role_id}", response_model=Role)
async def update_role(
    role_id: str,
    role_data: RoleUpdate,
    current_user: TokenPayload = Depends(get_current_user_required),
    _: None = Depends(require_permissions("role:manage")),
):
    """更新角色"""
    manager = RoleManager()

    # 获取目标角色
    target_role = await manager.get_role(role_id)
    if not target_role:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)

    # 如果是系统角色，检查当前用户是否拥有该角色
    if target_role.is_system:
        from src.infra.user.manager import UserManager

        user_manager = UserManager()
        user = await user_manager.get_user(current_user.sub)
        if user and user.roles and target_role.name in user.roles:
            raise AppError(ErrorCode.CANNOT_CHANGE_OWN_ROLE_PERMISSIONS)

    role = await manager.update_role(role_id, role_data)
    if not role:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    return role


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    _: None = Depends(require_permissions("role:manage")),
):
    """删除角色"""
    manager = RoleManager()
    # 先获取角色名用于缓存失效
    target_role = await manager.get_role(role_id)
    if not target_role:
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    await manager.delete_role(role_id)
    return {"status": "deleted"}
