"""
Model 配置路由

提供 Model 配置管理接口：
- LLM Provider CRUD（内置 + 自定义）
- 全局 Model 启用/禁用配置（含 per-model api_key/api_base）
- Provider 配置管理（api_key/api_base）
- 角色可用的 Models 映射
- 用户可用模型查询
"""

import time

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user_required, require_permissions
from src.infra.llm.providers.registry import ProviderRegistry
from src.infra.logging import get_logger
from src.infra.model.config_storage import get_model_config_storage
from src.infra.role.manager import get_role_manager
from src.infra.role.storage import RoleStorage
from src.kernel.config import settings
from src.kernel.schemas.model import (
    GlobalModelConfigResponse,
    LLMProvider,
    LLMProviderCreate,
    LLMProviderModel,
    LLMProvidersResponse,
    LLMProviderTestRequest,
    LLMProviderTestResponse,
    LLMProviderUpdate,
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


def _get_available_models() -> list[dict[str, str]]:
    """Return model metadata from legacy settings plus provider registry."""
    models_by_id: dict[str, dict[str, str]] = {}

    for model in settings.LLM_AVAILABLE_MODELS or []:
        model_id = model.get("value")
        if not model_id:
            continue
        models_by_id[model_id] = {
            "value": model_id,
            "label": model.get("label", model_id),
            "description": model.get("description", ""),
        }

    registry = ProviderRegistry.get_instance()
    for provider_name in registry.list_providers():
        provider = registry.get_provider(provider_name)
        if not provider:
            continue
        for model in provider.default_models:
            if model.model_id not in models_by_id:
                models_by_id[model.model_id] = {
                    "value": model.model_id,
                    "label": model.model_id,
                    "description": f"{provider.display_name} model",
                }

    return list(models_by_id.values())


# ============================================
# 辅助函数
# ============================================


async def _clear_cache_and_notify(reason: str) -> None:
    """清除本地 LLM 缓存并通知其他 worker。"""
    from src.infra.llm.client import LLMClient
    from src.infra.model.pubsub import publish_model_config_change

    cleared = LLMClient.clear_cache_by_model()
    logger.info(f"Cleared {cleared} LLM cache entries ({reason})")
    await publish_model_config_change(reason)


def _provider_doc_to_response(doc: dict, mask_api_key: bool = True) -> LLMProvider:
    """将 MongoDB document 转为 LLMProvider response，可选掩码 API key。"""
    api_key = doc.get("api_key")
    if mask_api_key and api_key:
        api_key = api_key[:8] + "..." if len(api_key) > 8 else "***"

    models = []
    for m in doc.get("models", []):
        m_key = m.get("api_key")
        if mask_api_key and m_key:
            m_key = m_key[:8] + "..." if len(m_key) > 8 else "***"
        models.append(
            LLMProviderModel(
                id=m.get("id", ""),
                name=m.get("name", ""),
                model_name=m.get("model_name", ""),
                description=m.get("description", ""),
                enabled=m.get("enabled", True),
                supports_thinking=m.get("supports_thinking", False),
                api_key=m_key,
                api_base=m.get("api_base"),
            )
        )

    return LLMProvider(
        name=doc["name"],
        display_name=doc.get("display_name", doc["name"]),
        provider_type=doc.get("provider_type", "openai_compatible"),
        enabled=doc.get("enabled", True),
        api_key=api_key,
        api_base=doc.get("api_base"),
        models=models,
        is_builtin=doc.get("is_builtin", False),
        builtin_provider_name=doc.get("builtin_provider_name"),
        color=doc.get("color", "#78716C"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


# ============================================
# LLM Provider CRUD（新接口）
# ============================================


@router.get("/llm-providers", response_model=LLMProvidersResponse)
async def list_llm_providers(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有 LLM Providers（内置 + 自定义）"""
    storage = get_model_config_storage()
    providers = await storage.get_llm_providers()

    result = [_provider_doc_to_response(p) for p in providers]
    available = [m.id for p in result for m in p.models if m.enabled and p.enabled]

    return LLMProvidersResponse(providers=result, available_models=available)


@router.post("/llm-providers", response_model=LLMProvider, status_code=201)
async def create_llm_provider(
    data: LLMProviderCreate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """创建自定义 LLM Provider"""
    storage = get_model_config_storage()

    # 检查名称冲突
    existing = await storage.get_llm_provider(data.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider '{data.name}' already exists")

    # 为 models 自动填充 id 和 model_name
    models = []
    for m in data.models:
        model_id = m.id or f"{data.name}/{m.model_name}"
        model_name = m.model_name or (m.id.split("/", 1)[-1] if "/" in m.id else m.id)
        models.append(
            {
                "id": model_id,
                "name": m.name or model_name,
                "model_name": model_name,
                "description": m.description,
                "enabled": m.enabled,
                "supports_thinking": m.supports_thinking,
                "api_key": m.api_key,
                "api_base": m.api_base,
            }
        )

    doc = {
        "name": data.name,
        "display_name": data.display_name,
        "provider_type": data.provider_type.value,
        "enabled": data.enabled,
        "api_key": data.api_key,
        "api_base": data.api_base,
        "models": models,
        "is_builtin": False,
        "builtin_provider_name": None,
        "color": data.color,
    }

    await storage.upsert_llm_provider(doc)
    await _clear_cache_and_notify("create_llm_provider")

    created = await storage.get_llm_provider(data.name)
    return _provider_doc_to_response(created)


@router.put("/llm-providers/{name}", response_model=LLMProvider)
async def update_llm_provider(
    name: str,
    data: LLMProviderUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """更新 LLM Provider 配置"""
    storage = get_model_config_storage()

    existing = await storage.get_llm_provider(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    # 构建更新 payload
    update = existing.copy()
    if data.display_name is not None:
        update["display_name"] = data.display_name
    if data.provider_type is not None:
        update["provider_type"] = data.provider_type.value
    if data.api_key is not None:
        update["api_key"] = data.api_key
    if data.api_base is not None:
        update["api_base"] = data.api_base
    if data.enabled is not None:
        update["enabled"] = data.enabled
    if data.color is not None:
        update["color"] = data.color
    if data.models is not None:
        models = []
        for m in data.models:
            model_id = m.id or f"{name}/{m.model_name}"
            model_name = m.model_name or (m.id.split("/", 1)[-1] if "/" in m.id else m.id)
            models.append(
                {
                    "id": model_id,
                    "name": m.name or model_name,
                    "model_name": model_name,
                    "description": m.description,
                    "enabled": m.enabled,
                    "supports_thinking": m.supports_thinking,
                    "api_key": m.api_key,
                    "api_base": m.api_base,
                }
            )
        update["models"] = models

    await storage.upsert_llm_provider(update)
    await _clear_cache_and_notify("update_llm_provider")

    updated = await storage.get_llm_provider(name)
    return _provider_doc_to_response(updated)


@router.delete("/llm-providers/{name}")
async def delete_llm_provider(
    name: str,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """删除自定义 LLM Provider（内置 provider 只能 disable，不能删除）"""
    storage = get_model_config_storage()

    existing = await storage.get_llm_provider(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    if existing.get("is_builtin", False):
        raise HTTPException(
            status_code=403,
            detail="Built-in providers cannot be deleted. Disable them instead.",
        )

    deleted = await storage.delete_llm_provider(name)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete provider")

    await _clear_cache_and_notify("delete_llm_provider")
    return {"deleted": True}


@router.post("/llm-providers/{name}/test", response_model=LLMProviderTestResponse)
async def test_llm_provider(
    name: str,
    body: LLMProviderTestRequest,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """测试 LLM Provider 连接"""
    storage = get_model_config_storage()

    provider = await storage.get_llm_provider(name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    # 确定 model name
    model_name = body.model_name
    if not model_name and provider.get("models"):
        first_enabled = next(
            (m for m in provider["models"] if m.get("enabled", True)),
            None,
        )
        if first_enabled:
            model_name = first_enabled.get("model_name") or first_enabled.get("id", "")

    if not model_name:
        return LLMProviderTestResponse(success=False, error="No model available to test")

    api_key = provider.get("api_key") or settings.LLM_API_KEY
    api_base = provider.get("api_base") or settings.LLM_API_BASE
    _ = provider.get("provider_type", "openai_compatible")  # used by LLMClient via model prefix

    try:
        from src.infra.llm.client import LLMClient

        start = time.monotonic()
        llm = LLMClient.get_model(
            model=f"{name}/{model_name}",
            api_key=api_key,
            api_base=api_base,
            temperature=0,
            max_tokens=1,
        )
        # 发一个最小请求验证连通性
        await llm.ainvoke("hi")
        latency = int((time.monotonic() - start) * 1000)
        return LLMProviderTestResponse(success=True, latency_ms=latency)
    except Exception as e:
        return LLMProviderTestResponse(success=False, error=str(e))


# ============================================
# Provider 配置接口（兼容旧接口）
# ============================================


@router.get("/providers", response_model=list[ProviderConfig])
async def get_providers(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有 Provider 配置（从 llm_providers collection 读取）"""
    storage = get_model_config_storage()
    llm_providers = await storage.get_llm_providers()

    # 从可用模型池中提取已知 providers
    available_models_raw = _get_available_models()
    known_providers: set[str] = set()
    for model in available_models_raw:
        model_id = model.get("value", "")
        provider = ProviderRegistry.get_instance().get_provider_for_model(model_id)
        if provider:
            known_providers.add(provider.config.name)

    saved_providers = await storage.get_providers()
    saved_map = {p["name"]: p for p in saved_providers}

    result = []
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
    """更新 Provider 配置（同时更新 llm_providers collection）"""
    storage = get_model_config_storage()

    providers = [p.model_dump() for p in config_update.providers]
    await storage.set_providers(providers)

    # 同步到 llm_providers collection
    for p in providers:
        existing = await storage.get_llm_provider(p["name"])
        if existing:
            existing["api_key"] = p.get("api_key")
            existing["api_base"] = p.get("api_base")
            existing["display_name"] = p.get("display_name", existing.get("display_name"))
            existing["enabled"] = p.get("enabled", True)
            await storage.upsert_llm_provider(existing)

    await _clear_cache_and_notify("update_providers")

    return config_update.providers


# ============================================
# 全局 Model 配置接口
# ============================================


@router.get("/global", response_model=GlobalModelConfigResponse)
async def get_global_model_config(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取全局 Model 配置（合并 llm_providers + LLM_AVAILABLE_MODELS）"""
    storage = get_model_config_storage()

    # 从兼容模型池获取模型列表（优先兼容旧配置，同时支持 registry）
    available_models_raw = _get_available_models()
    saved_configs = await storage.get_global_config()
    saved_configs_map = {c["id"]: c for c in saved_configs}

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

    # 验证 model IDs 是否在可用模型池中
    valid_ids = {m.get("value") for m in _get_available_models()}
    for model in config_update.models:
        if model.id not in valid_ids:
            from src.kernel.exceptions import ValidationError

            raise ValidationError(f"Model '{model.id}' 不在可用模型池中")

    models = [m.model_dump() for m in config_update.models]
    await storage.set_global_config(models)

    await _clear_cache_and_notify("update_global_models")

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

    await _clear_cache_and_notify("update_role_models")

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

    # 优先从 llm_providers 获取启用的模型
    enabled_ids = set(await storage.get_all_enabled_model_ids())

    # 如果没有全局配置，使用兼容模型池中的所有模型
    if not enabled_ids:
        enabled_ids = {m.get("value") for m in _get_available_models()}

    # 获取用户角色级别的限制
    allowed = set(enabled_ids)

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
            allowed = role_allowed & enabled_ids

    return UserAllowedModelsResponse(models=sorted(allowed))
