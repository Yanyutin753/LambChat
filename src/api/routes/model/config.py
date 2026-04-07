"""
Model 配置路由

提供 Model 配置管理接口：
- Provider 分组配置（含 per-model 凭证）
- 角色可用的 Models 映射
- 用户可用模型查询
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_required, require_permissions
from src.infra.logging import get_logger
from src.infra.model.config_storage import get_model_config_storage
from src.infra.role.manager import get_role_manager
from src.infra.role.storage import RoleStorage
from src.kernel.schemas.model import (
    ModelConfig,
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
logger = get_logger(__name__)


# ============================================
# Provider 配置接口
# ============================================


def _build_default_provider_config() -> list[dict]:
    """从 Provider Registry 构建默认 Provider 配置。

    使用 Provider Registry 中第一个可用的 provider 作为默认配置，
    配合环境变量中的 API Key 实现开箱即用。
    """
    from src.infra.llm.providers.registry import ProviderRegistry

    registry = ProviderRegistry.get_instance()
    default_provider_name = getattr(
        __import__("src.kernel.config", fromlist=["settings"]).settings,
        "LLM_PROVIDER_DEFAULT",
        "anthropic",
    )

    # Use registry to get provider info
    provider_instance = registry.get_provider(default_provider_name)
    if not provider_instance:
        # Fallback to anthropic
        default_provider_name = "anthropic"
        provider_instance = registry.get_provider(default_provider_name)

    # Get first model from provider's default models
    first_model = provider_instance.default_models[0] if provider_instance.default_models else None
    model_value = (
        f"{default_provider_name}/{first_model.model_id}"
        if first_model
        else f"{default_provider_name}/default"
    )
    model_name = first_model.model_id if first_model else "default"

    # Get api_key from env if set directly
    import os

    api_key = os.environ.get(f"LLM_PROVIDER_{default_provider_name.upper()}_API_KEY", "")
    base_url = os.environ.get(f"LLM_PROVIDER_{default_provider_name.upper()}_BASE_URL", "")

    return [
        {
            "provider": default_provider_name,
            "label": f"Default ({default_provider_name.title()})",
            "base_url": base_url or None,
            "api_key": api_key or None,
            "models": [
                {
                    "value": model_value,
                    "label": model_name,
                    "description": f"Default model: {model_value}",
                    "enabled": True,
                }
            ],
        }
    ]


@router.get("/providers", response_model=ProviderModelConfigResponse)
async def get_provider_model_config(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有 Provider 分组配置（api_key 已解密）。

    如果 MongoDB 中没有配置，自动使用全局 LLM_MODEL/LLM_API_KEY/LLM_API_BASE
    生成一个默认 Provider，确保开箱即用。
    """
    storage = get_model_config_storage()

    providers_raw = await storage.get_provider_config()

    # 数据库为空时，使用全局设置生成默认配置（不持久化到数据库）
    if not providers_raw:
        logger.info("No provider config found, using default from global settings")
        providers_raw = _build_default_provider_config()

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
            flat_models.append(m)

    enabled_ids = await storage.get_enabled_model_ids()

    return ProviderModelConfigResponse(
        providers=providers,
        flat_models=flat_models,
        available_models=enabled_ids,
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

    # 获取全局启用的模型（仅从 Provider 配置中获取）
    enabled_ids = set(await storage.get_enabled_model_ids())

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
