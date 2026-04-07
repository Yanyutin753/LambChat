"""
Model 配置路由

提供 Model 配置管理接口：
- 全局 Model 启用/禁用配置
- 角色可用的 Models 映射
- 用户可用模型查询
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required, require_permissions
from src.infra.logging import get_logger
from src.infra.model.config_storage import get_model_config_storage
from src.infra.role.manager import get_role_manager
from src.infra.role.storage import RoleStorage
from src.kernel.config import settings
from src.kernel.schemas.model import (
    GlobalModelConfigResponse,
    ModelConfig,
    ModelConfigUpdate,
    RoleModelAssignment,
    RoleModelAssignmentResponse,
    RoleModelAssignmentUpdate,
    UserAllowedModelsResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = get_logger(__name__)


# ============================================
# 管理员接口
# ============================================


@router.get("/global", response_model=GlobalModelConfigResponse)
async def get_global_model_config(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取全局 Model 配置"""
    storage = get_model_config_storage()

    # 从 LLM_AVAILABLE_MODELS 获取模型池
    available_models_raw = settings.LLM_AVAILABLE_MODELS or []
    saved_configs = await storage.get_global_config()
    saved_configs_map = {c["id"]: c for c in saved_configs}

    # 合并：使用保存的配置，新发现的模型默认启用
    model_configs = []
    for model in available_models_raw:
        model_id = model.get("value", "")
        if model_id in saved_configs_map:
            saved = saved_configs_map[model_id]
            model_configs.append(
                ModelConfig(
                    id=saved["id"],
                    name=saved.get("name", model.get("label", model_id)),
                    description=saved.get("description", model.get("description", "")),
                    enabled=saved.get("enabled", True),
                )
            )
        else:
            model_configs.append(
                ModelConfig(
                    id=model_id,
                    name=model.get("label", model_id),
                    description=model.get("description", ""),
                    enabled=True,
                )
            )

    # 持久化新发现的模型
    await storage.set_global_config([m.model_dump() for m in model_configs])

    return GlobalModelConfigResponse(
        models=model_configs,
        available_models=[m.id for m in model_configs if m.enabled],
    )


@router.put("/global", response_model=GlobalModelConfigResponse)
async def update_global_model_config(
    config_update: ModelConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """更新全局 Model 配置"""
    storage = get_model_config_storage()

    # 验证 model IDs 是否在 LLM_AVAILABLE_MODELS 中
    valid_ids = {m.get("value") for m in (settings.LLM_AVAILABLE_MODELS or [])}
    for model in config_update.models:
        if model.id not in valid_ids:
            from src.kernel.exceptions import ValidationError

            raise ValidationError(f"Model '{model.id}' 不在 LLM_AVAILABLE_MODELS 中")

    models = [m.model_dump() for m in config_update.models]
    await storage.set_global_config(models)

    return GlobalModelConfigResponse(
        models=config_update.models,
        available_models=[m.id for m in config_update.models if m.enabled],
    )


@router.get("/roles/{role_id}", response_model=RoleModelAssignment)
async def get_role_models(
    role_id: str,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取角色的可用 Models"""
    storage = get_model_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    allowed_models = await storage.get_role_models(role_id) or []

    return RoleModelAssignment(
        role_id=role_id,
        role_name=role.name,
        allowed_models=allowed_models,
    )


@router.put("/roles/{role_id}", response_model=RoleModelAssignmentResponse)
async def update_role_models(
    role_id: str,
    assignment: RoleModelAssignmentUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """设置角色的可用 Models"""
    storage = get_model_config_storage()
    role_manager = get_role_manager()

    role = await role_manager.get_role(role_id)
    if not role:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"角色 '{role_id}' 不存在")

    await storage.set_role_models(role_id, role.name, assignment.allowed_models)

    return RoleModelAssignmentResponse(
        role_id=role_id,
        role_name=role.name,
        allowed_models=assignment.allowed_models,
    )


# ============================================
# 用户接口
# ============================================


@router.get("/user/allowed", response_model=UserAllowedModelsResponse)
async def get_user_allowed_models(
    user: TokenPayload = Depends(get_current_user_required),
):
    """获取当前用户可用的模型列表（基于全局配置 + 角色限制）"""
    storage = get_model_config_storage()

    # 获取全局启用的模型
    enabled_ids = set(await storage.get_enabled_model_ids())

    # 如果没有全局配置，使用 LLM_AVAILABLE_MODELS 中的所有模型
    if not enabled_ids:
        enabled_ids = {m.get("value") for m in (settings.LLM_AVAILABLE_MODELS or [])}

    # 获取用户角色级别的限制
    allowed = set(enabled_ids)  # 从全局启用的开始

    if user.roles:
        role_storage = RoleStorage()
        role_allowed = set()
        has_role_config = False
        for role in await role_storage.get_by_names(user.roles):
            role_models = await storage.get_role_models(role.id)
            if role_models is not None:
                has_role_config = True
                role_allowed.update(role_models)

        if has_role_config:
            # 角色允许 ∩ 全局启用
            allowed = role_allowed & enabled_ids

    return UserAllowedModelsResponse(models=sorted(allowed))
