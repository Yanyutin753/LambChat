"""
角色路由
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import (
    get_current_user_required,
    invalidate_role_permissions_cache,
    require_permissions,
)
from src.infra.role.manager import RoleManager
from src.kernel.exceptions import ValidationError
from src.kernel.schemas.role import Role, RoleCreate, RoleUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("/", response_model=List[Role])
async def list_roles(
    skip: int = 0,
    limit: int = 100,
    _: TokenPayload = Depends(get_current_user_required),
):
    """列出角色（只需登录）"""
    manager = RoleManager()
    return await manager.list_roles(skip, limit)


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
        raise HTTPException(status_code=404, detail="角色不存在")
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
        raise HTTPException(status_code=404, detail="角色不存在")

    # 如果是系统角色，检查当前用户是否拥有该角色
    if target_role.is_system:
        from src.infra.user.manager import UserManager

        user_manager = UserManager()
        user = await user_manager.get_user(current_user.sub)
        if user and user.roles and target_role.name in user.roles:
            raise HTTPException(
                status_code=400,
                detail="不能修改自己所属角色的权限",
            )

    try:
        role = await manager.update_role(role_id, role_data)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    # 角色权限变更，失效该角色的缓存
    await invalidate_role_permissions_cache(target_role.name)
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
        raise HTTPException(status_code=404, detail="角色不存在")
    try:
        await manager.delete_role(role_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 删除角色，失效该角色的缓存
    await invalidate_role_permissions_cache(target_role.name)
    return {"status": "deleted"}
