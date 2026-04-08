"""
Model 配置路由

提供 Model 配置管理接口：
- 全局 Model 启用/禁用配置（含 per-model api_key/api_base）
- Provider 配置管理（api_key/api_base）
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
    ProviderConfig,
    ProviderConfigUpdate,
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
# Provider 配置接口
# ============================================


@router.get("/providers", response_model=list[ProviderConfig])
async def get_providers(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有 Provider 配置"""
    storage = get_model_config_storage()

    # 从 LLM_AVAILABLE_MODELS 中提取已知 providers
    available_models_raw = settings.LLM_AVAILABLE_MODELS or []
    known_providers: set[str] = set()
    for model in available_models_raw:
        model_id = model.get("value", "")
        if "/" in model_id:
            known_providers.add(model_id.split("/", 1)[0])

    # 获取已保存的 provider 配置
    saved_providers = await storage.get_providers()
    saved_map = {p["name"]: p for p in saved_providers}

    # 合并：已知 provider 没有保存配置时创建默认条目
    result = []
    # 先返回已保存的配置
    for p in saved_providers:
        result.append(
            ProviderConfig(
                name=p["name"],
                display_name=p.get("display_name", p["name"]),
                api_key=p.get("api_key"),
                api_base=p.get("api_base"),
                enabled=p.get("enabled", True),
            )
        )

    # 再添加新发现的 provider（未保存的）
    for name in sorted(known_providers):
        if name not in saved_map:
            result.append(
                ProviderConfig(
                    name=name,
                    display_name=name,
                    api_key=None,
                    api_base=None,
                    enabled=True,
                )
            )

    return result


@router.put("/providers", response_model=list[ProviderConfig])
async def update_providers(
    config_update: ProviderConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """更新 Provider 配置"""
    storage = get_model_config_storage()

    providers = [p.model_dump() for p in config_update.providers]
    await storage.set_providers(providers)

    # 清除本地 LLM 缓存 + 通知其他 worker
    from src.infra.llm.client import LLMClient
    from src.infra.model.pubsub import publish_model_config_change

    cleared = LLMClient.clear_cache_by_model()
    logger.info(f"Cleared {cleared} LLM cache entries after updating providers")
    await publish_model_config_change("update_providers")

    return config_update.providers


# ============================================
# 全局 Model 配置接口
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
                    api_key=saved.get("api_key"),
                    api_base=saved.get("api_base"),
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

    # 清除本地 LLM 缓存 + 通知其他 worker
    from src.infra.llm.client import LLMClient
    from src.infra.model.pubsub import publish_model_config_change

    cleared = LLMClient.clear_cache_by_model()
    logger.info(f"Cleared {cleared} LLM cache entries after updating global model config")
    await publish_model_config_change("update_global_models")

    return GlobalModelConfigResponse(
        models=config_update.models,
        available_models=[m.id for m in config_update.models if m.enabled],
    )


# ============================================
# 角色 Models 映射
# ============================================


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

    # 清除本地 LLM 缓存 + 通知其他 worker（角色变更影响可用模型列表）
    from src.infra.llm.client import LLMClient
    from src.infra.model.pubsub import publish_model_config_change

    cleared = LLMClient.clear_cache_by_model()
    logger.info(f"Cleared {cleared} LLM cache entries after updating role models")
    await publish_model_config_change("update_role_models")

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
