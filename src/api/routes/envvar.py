"""
Environment Variable API router

提供用户环境变量的 CRUD 接口，环境变量加密存储，在沙箱创建时注入。
"""

import re

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.envvar.storage import EnvVarStorage
from src.infra.logging import get_logger
from src.kernel.schemas.envvar import (
    EnvVarBulkUpdateRequest,
    EnvVarBulkUpdateResponse,
    EnvVarCreate,
    EnvVarListResponse,
    EnvVarResponse,
    EnvVarUpdate,
)
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)

router = APIRouter()

# 环境变量 key 格式校验
_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def get_envvar_storage() -> EnvVarStorage:
    return EnvVarStorage()


def _validate_key(key: str) -> None:
    if not _ENV_KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=400,
            detail="Invalid key format. Must match: ^[A-Za-z_][A-Za-z0-9_]*$",
        )


# ==========================================
# Static routes (before dynamic {key} routes)
# ==========================================


@router.get("", response_model=EnvVarListResponse)
async def list_env_vars(
    user: TokenPayload = Depends(require_permissions("envvar:read")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """列出当前用户所有环境变量（value 掩码）"""
    variables = await storage.list_vars(user.sub)
    return EnvVarListResponse(variables=variables, count=len(variables))


@router.post("", response_model=EnvVarResponse, status_code=201)
async def create_env_var(
    data: EnvVarCreate,
    user: TokenPayload = Depends(require_permissions("envvar:write")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """创建环境变量"""
    try:
        result = await storage.set_var(user.sub, data.key, data.value)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/bulk", response_model=EnvVarBulkUpdateResponse)
async def bulk_update_env_vars(
    data: EnvVarBulkUpdateRequest,
    user: TokenPayload = Depends(require_permissions("envvar:write")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """批量设置环境变量"""
    # 校验所有 key 格式
    for key in data.variables:
        _validate_key(key)

    try:
        count = await storage.set_vars_bulk(user.sub, data.variables)
        return EnvVarBulkUpdateResponse(
            updated_count=count,
            message=f"Updated {count} environment variable(s)",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/all")
async def delete_all_env_vars(
    user: TokenPayload = Depends(require_permissions("envvar:delete")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """删除当前用户所有环境变量"""
    count = await storage.delete_all_vars(user.sub)
    return {"message": f"Deleted {count} environment variable(s)"}


# ==========================================
# Dynamic routes (with path parameters)
# ==========================================


@router.get("/{key}", response_model=EnvVarResponse)
async def get_env_var(
    key: str,
    user: TokenPayload = Depends(require_permissions("envvar:read")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """获取单个环境变量（明文）"""
    result = await storage.get_var(user.sub, key)
    if not result:
        raise HTTPException(status_code=404, detail=f"Environment variable '{key}' not found")
    return result


@router.put("/{key}", response_model=EnvVarResponse)
async def update_env_var(
    key: str,
    data: EnvVarUpdate,
    user: TokenPayload = Depends(require_permissions("envvar:write")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """更新环境变量"""
    _validate_key(key)
    try:
        result = await storage.set_var(user.sub, key, data.value)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{key}")
async def delete_env_var(
    key: str,
    user: TokenPayload = Depends(require_permissions("envvar:delete")),
    storage: EnvVarStorage = Depends(get_envvar_storage),
):
    """删除单个环境变量"""
    deleted = await storage.delete_var(user.sub, key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Environment variable '{key}' not found")
    return {"message": f"Environment variable '{key}' deleted"}
