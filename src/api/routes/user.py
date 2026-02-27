"""
用户路由
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from src.api.deps import get_current_user_required, require_permissions
from src.infra.user.manager import UserManager
from src.kernel.schemas.user import TokenPayload, User, UserCreate, UserUpdate

router = APIRouter()


@router.get("/", response_model=List[User])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    _: None = Depends(require_permissions("user:read")),
):
    """列出用户"""
    manager = UserManager()
    return await manager.list_users(skip, limit)


@router.post("/", response_model=User)
async def create_user(
    user_data: UserCreate,
    _: None = Depends(require_permissions("user:write")),
):
    """创建用户"""
    manager = UserManager()
    return await manager.register(user_data)


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    _: None = Depends(require_permissions("user:read")),
):
    """获取用户"""
    manager = UserManager()
    user = await manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """更新用户"""
    manager = UserManager()
    user = await manager.update_user(user_id, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 如果修改了当前用户的角色，返回响应头让前端强制重新登录
    response = Response()
    if user_id == current_user.sub and user_data.roles is not None:
        response.headers["X-Force-Relogin"] = "true"
        # FastAPI 需要特殊处理来同时返回数据和自定义响应头
        from fastapi.responses import JSONResponse

        return JSONResponse(
            content=user.model_dump(mode="json"),
            headers={"X-Force-Relogin": "true"},
        )

    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    _: None = Depends(require_permissions("user:delete")),
):
    """删除用户"""
    manager = UserManager()
    success = await manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "deleted"}
