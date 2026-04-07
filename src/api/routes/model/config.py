"""
Model 配置路由

提供 Model 配置管理接口：
- Provider 分组配置（含 per-model 凭证）
- 角色可用的 Models 映射
- 用户可用模型查询
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required, require_permissions
from src.infra.model.config_storage import get_model_config_storage
from src.infra.role.manager import get_role_manager
from src.infra.role.storage import RoleStorage
from src.kernel.config import settings
from src.kernel.schemas.model import (
    GlobalModelConfigResponse,
    ModelConfig,
    ModelConfigLegacy,
    ModelConfigUpdate,
    ModelProviderConfig,
    ProviderModelConfigResponse,
    ProviderModelConfigUpdate,
    RoleModelAssignment,
    RoleModelAssignmentResponse,
    RoleModelAssignmentUpdate,
    UserAllowedModelsResponse,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()


def _models_compatible(model_a: str, model_b: str) -> bool:
    """Compatibility match between provider-prefixed and legacy model IDs."""
    if model_a == model_b:
        return True
    if "/" in model_a and "/" not in model_b:
        return model_a.endswith(f"/{model_b}")
    if "/" in model_b and "/" not in model_a:
        return model_b.endswith(f"/{model_a}")
    return False


def _legacy_to_provider_id(model_id: str, all_values: set[str]) -> str:
    """Resolve legacy model id to provider-prefixed value if possible."""
    if model_id in all_values:
        return model_id
    if "/" not in model_id:
        suffix = f"/{model_id}"
        for value in all_values:
            if value.endswith(suffix):
                return value
    return model_id


# ============================================
# Provider 配置接口
# ============================================


@router.get("/providers", response_model=ProviderModelConfigResponse)
async def get_provider_model_config(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有 Provider 分组配置（api_key 已解密）。"""
    storage = get_model_config_storage()

    providers_raw, metadata = await storage.get_provider_config_with_metadata()

    providers = [ModelProviderConfig(**p) for p in providers_raw]

    # 扁平化所有模型
    flat_models = []
    for p in providers:
        for m in p.models:
            flat_models.append(ModelConfig(**{**m.model_dump(), "provider": p.provider}))

    # 所有启用的模型 ID
    enabled_ids = []
    for p in providers:
        for m in p.models:
            if m.enabled:
                enabled_ids.append(m.value)

    return ProviderModelConfigResponse(
        providers=providers,
        flat_models=flat_models,
        available_models=enabled_ids,
        legacy_migration_applied=metadata["legacy_migration_applied"],
        legacy_inherited_providers=metadata["legacy_inherited_providers"],
    )


@router.put("/providers", response_model=ProviderModelConfigResponse)
async def update_provider_model_config(
    config_update: ProviderModelConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """更新 Provider 分组配置（api_key 会加密存储）"""
    from src.infra.llm.client import refresh_provider_config_cache

    storage = get_model_config_storage()

    providers_data = [p.model_dump() for p in config_update.providers]
    await storage.set_provider_config(providers_data)

    # 刷新 LLMClient 的 provider 缓存，使后续请求使用新配置
    refresh_provider_config_cache()

    # 重新加载（解密后的数据）
    providers_raw = await storage.get_provider_config()
    providers = [ModelProviderConfig(**p) for p in providers_raw]

    flat_models = []
    for p in providers:
        for m in p.models:
            flat_models.append(ModelConfig(**{**m.model_dump(), "provider": p.provider}))

    enabled_ids = await storage.get_enabled_model_ids()

    return ProviderModelConfigResponse(
        providers=providers,
        flat_models=flat_models,
        available_models=enabled_ids,
        legacy_migration_applied=False,
        legacy_inherited_providers=[],
    )


# ============================================
# Legacy Global Config (compatibility)
# ============================================


@router.get("/global", response_model=GlobalModelConfigResponse)
async def get_global_model_config(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """兼容旧版 API：获取全局模型配置。"""
    storage = get_model_config_storage()

    providers_raw = await storage.get_provider_config()
    providers = [ModelProviderConfig(**p) for p in providers_raw]
    legacy_models: list[ModelConfigLegacy] = []
    for p in providers:
        for m in p.models:
            legacy_models.append(
                ModelConfigLegacy(
                    id=m.value,
                    name=m.label,
                    description=m.description,
                    enabled=m.enabled,
                )
            )

    return GlobalModelConfigResponse(
        models=legacy_models,
        available_models=[m.id for m in legacy_models if m.enabled],
    )


@router.put("/global", response_model=GlobalModelConfigResponse)
async def update_global_model_config(
    config_update: ModelConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """兼容旧版 API：更新全局模型启用状态。"""
    from src.infra.llm.client import refresh_provider_config_cache

    storage = get_model_config_storage()
    providers_raw = await storage.get_provider_config()
    providers = [ModelProviderConfig(**p) for p in providers_raw]
    all_values = {m.value for p in providers for m in p.models}

    enabled_map: dict[str, bool] = {}
    for legacy_model in config_update.models:
        resolved = _legacy_to_provider_id(legacy_model.id, all_values)
        enabled_map[resolved] = legacy_model.enabled

    updated_providers: list[ModelProviderConfig] = []
    for provider in providers:
        updated_models = []
        for model in provider.models:
            updated_models.append(
                model.model_copy(update={"enabled": enabled_map.get(model.value, model.enabled)})
            )
        updated_providers.append(provider.model_copy(update={"models": updated_models}))

    await storage.set_provider_config([p.model_dump() for p in updated_providers])
    refresh_provider_config_cache()

    legacy_models: list[ModelConfigLegacy] = []
    for p in updated_providers:
        for m in p.models:
            legacy_models.append(
                ModelConfigLegacy(
                    id=m.value,
                    name=m.label,
                    description=m.description,
                    enabled=m.enabled,
                )
            )

    return GlobalModelConfigResponse(
        models=legacy_models,
        available_models=[m.id for m in legacy_models if m.enabled],
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

    # 获取全局启用的模型（优先 Provider 配置）
    enabled_ids = set(await storage.get_enabled_model_ids())
    if not enabled_ids:
        # Backward compat: fallback to legacy LLM_AVAILABLE_MODELS.
        enabled_ids = {m.get("value") for m in (settings.LLM_AVAILABLE_MODELS or []) if m.get("value")}

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
            allowed = {
                model_id
                for model_id in enabled_ids
                if any(_models_compatible(model_id, role_model) for role_model in role_allowed)
            }

    return UserAllowedModelsResponse(models=sorted(allowed))
