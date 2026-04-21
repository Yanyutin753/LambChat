"""
Model 配置路由

提供 Model 配置管理接口（CRUD）：
- 列出所有模型
- 获取单个模型
- 创建模型
- 更新模型
- 删除模型
- 批量导入模型
"""

from fastapi import APIRouter, Body, Depends

from src.api.deps import require_permissions
from src.infra.agent.model_storage import get_model_storage
from src.infra.logging import get_logger
from src.kernel.schemas.model import (
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelListResponse,
    ModelResponse,
    mask_api_key,
)
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission

router = APIRouter()
logger = get_logger(__name__)


# ============================================
# CRUD 接口
# ============================================


@router.get("/", response_model=ModelListResponse)
async def list_models(
    include_disabled: bool = False,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取所有模型配置（仅管理员）"""
    storage = get_model_storage()
    models = await storage.list_models(include_disabled=include_disabled)
    counts = await storage.count()

    return ModelListResponse(
        models=[mask_api_key(m) for m in models],
        count=counts["total"],
        enabled_count=counts["enabled"],
    )


@router.get("/available", response_model=ModelListResponse)
async def list_available_models(
    _: TokenPayload = Depends(require_permissions(Permission.AGENT_READ.value)),
):
    """获取所有可用的模型配置（任何已认证用户，仅返回启用的模型）"""
    logger.info("[Model] list_available_models called")
    storage = get_model_storage()
    models = await storage.list_models(include_disabled=False)
    counts = await storage.count()
    logger.info(f"[Model] Found {len(models)} models, counts={counts}")

    return ModelListResponse(
        models=[mask_api_key(m) for m in models],
        count=counts["total"],
        enabled_count=counts["enabled"],
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """获取单个模型配置"""
    storage = get_model_storage()
    model = await storage.get(model_id)

    if not model:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"Model '{model_id}' not found")

    return ModelResponse(model=mask_api_key(model))


@router.post("/", response_model=ModelResponse, status_code=201)
async def create_model(
    model_create: ModelConfigCreate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """创建新模型配置"""
    storage = get_model_storage()

    model = ModelConfig(**model_create.model_dump())
    try:
        created = await storage.create(model)
    except Exception as e:
        if "duplicate key" in str(e).lower():
            from src.kernel.exceptions import ValidationError

            raise ValidationError(f"Model with id '{model.id}' already exists")
        raise

    logger.info(f"[Model] Created model: {created.value} (id={created.id})")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return ModelResponse(model=mask_api_key(created), message="Model created successfully")


@router.get("/providers/list")
async def list_providers():
    """列出所有支持的 LLM 供应商（从 PROVIDER_REGISTRY 生成）。"""
    from src.infra.llm.client import PROVIDER_REGISTRY

    providers = []
    for slug, (protocol, prefixes) in PROVIDER_REGISTRY.items():
        providers.append(
            {
                "value": slug,
                "protocol": protocol,
                "prefixes": prefixes,
            }
        )
    return providers


@router.put("/reorder", response_model=ModelListResponse)
async def reorder_models(
    model_ids: list[str] = Body(..., description="Model IDs in new order"),
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """批量更新模型顺序"""
    storage = get_model_storage()

    models = await storage.reorder(model_ids)

    logger.info(f"[Model] Reordered {len(models)} models")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return ModelListResponse(
        models=[mask_api_key(m) for m in models],
        count=len(models),
        enabled_count=sum(1 for m in models if m.enabled),
    )


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    model_update: ModelConfigUpdate,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """更新模型配置"""
    storage = get_model_storage()

    # 检查模型是否存在
    existing = await storage.get(model_id)
    if not existing:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"Model '{model_id}' not found")

    # 执行更新
    update_data = {k: v for k, v in model_update.model_dump(exclude_none=True).items()}
    # Allow clearing api_key by sending empty string ""
    if "api_key" in update_data and update_data["api_key"] == "":
        update_data["api_key"] = None
    # 校验 fallback_model
    if "fallback_model" in update_data and update_data["fallback_model"] is not None:
        if update_data["fallback_model"] == model_id:
            from src.kernel.exceptions import ValidationError

            raise ValidationError("A model cannot be its own fallback")
        fallback_exists = await storage.get(update_data["fallback_model"])
        if not fallback_exists:
            from src.kernel.exceptions import ValidationError

            raise ValidationError(
                f"Fallback model '{update_data['fallback_model']}' does not exist"
            )
    updated = await storage.update(model_id, update_data)

    if not updated:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"Model '{model_id}' not found during update")

    logger.info(f"[Model] Updated model: {updated.value} (id={updated.id})")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return ModelResponse(model=mask_api_key(updated), message="Model updated successfully")


@router.delete("/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """删除模型配置"""
    storage = get_model_storage()

    # 检查模型是否存在
    existing = await storage.get(model_id)
    if not existing:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"Model '{model_id}' not found")

    model_value = existing.value
    await storage.delete(model_id)

    logger.info(f"[Model] Deleted model: {model_value} (id={model_id})")

    # 清理所有模型中被删模型作为 fallback_model 的孤儿引用
    from datetime import datetime, timezone

    collection = storage._get_collection()
    clear_result = await collection.update_many(
        {"fallback_model": model_id},
        {"$set": {"fallback_model": None, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if clear_result.modified_count:
        logger.info(
            f"[Model] Cleared orphaned fallback_model refs in {clear_result.modified_count} model(s)"
        )

    # 同步清理所有角色中关联的该模型（按 model_id 移除）
    from src.infra.agent.config_storage import get_agent_config_storage

    agent_storage = get_agent_config_storage()
    affected = await agent_storage.remove_model_from_all_roles(model_value)
    if affected:
        logger.info(f"[Model] Removed deleted model '{model_id}' from {affected} role(s)")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return None


@router.post("/{model_id}/toggle", response_model=ModelResponse)
async def toggle_model(
    model_id: str,
    enabled: bool,
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """启用/禁用模型"""
    storage = get_model_storage()

    model = await storage.toggle(model_id, enabled)
    if not model:
        from src.kernel.exceptions import NotFoundError

        raise NotFoundError(f"Model '{model_id}' not found")

    action = "enabled" if enabled else "disabled"
    logger.info(f"[Model] {action.capitalize()} model: {model.value} (id={model.id})")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return ModelResponse(model=mask_api_key(model), message=f"Model {action} successfully")


@router.post("/import", response_model=ModelListResponse)
async def import_models(
    models: list[ModelConfigCreate],
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """批量导入模型（upsert）"""
    storage = get_model_storage()

    config_models = [ModelConfig(**m.model_dump()) for m in models]
    imported = await storage.bulk_upsert_by_value(config_models)

    logger.info(f"[Model] Imported {len(imported)} models")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    counts = await storage.count()
    return ModelListResponse(
        models=[mask_api_key(m) for m in imported],
        count=counts["total"],
        enabled_count=counts["enabled"],
    )


@router.post("/batch-create", response_model=ModelListResponse, status_code=201)
async def batch_create_models(
    body: dict = Body(...),
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """批量创建模型（共享 api_base、api_key 等配置）

    Body:
        {
            "shared": { "api_base": "...", "api_key": "...", ... },
            "models": [{ "value": "...", "label": "..." }, ...]
        }
    """
    from src.kernel.schemas.model import ModelProfile

    shared = body.get("shared", {})
    models = body.get("models", [])

    if not models or not isinstance(models, list):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="models must be a non-empty list")

    # Validate provider if provided
    raw_provider = shared.get("provider")
    provider = None
    if raw_provider:
        if not isinstance(raw_provider, str) or not raw_provider.strip():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider '{raw_provider}'. Must be a non-empty string.",
            )
        provider = raw_provider.strip()

    storage = get_model_storage()

    # Build profile from shared config
    profile = None
    if shared.get("max_input_tokens"):
        profile = ModelProfile(max_input_tokens=int(shared["max_input_tokens"]))

    created_models = []
    try:
        for item in models:
            if not item.get("value") or not item.get("label"):
                continue
            model = ModelConfig(
                value=item["value"],
                label=item["label"],
                provider=provider,
                api_key=shared.get("api_key") or None,
                api_base=shared.get("api_base") or None,
                temperature=shared.get("temperature"),
                max_tokens=shared.get("max_tokens"),
                profile=profile,
                enabled=True,
            )
            created = await storage.create(model)
            created_models.append(created)
            logger.debug(f"[Model] Batch created model: {created.value}")
    finally:
        # Always invalidate cache, even on partial failure
        from src.infra.llm.models_service import invalidate_cache

        await invalidate_cache()

    logger.info(f"[Model] Batch created {len(created_models)} models")

    counts = await storage.count()
    return ModelListResponse(
        models=[mask_api_key(m) for m in created_models],
        count=counts["total"],
        enabled_count=counts["enabled"],
    )


@router.delete("/", status_code=204)
async def delete_all_models(
    _: TokenPayload = Depends(require_permissions(Permission.MODEL_ADMIN.value)),
):
    """删除所有模型配置（危险操作）"""
    storage = get_model_storage()

    count = await storage.delete_all()

    logger.warning(f"[Model] Deleted all {count} models")

    # 同步清空所有角色的模型关联（单次批量操作）
    from src.infra.agent.config_storage import get_agent_config_storage

    agent_storage = get_agent_config_storage()
    affected = await agent_storage.clear_all_role_models()
    if affected:
        logger.info(f"[Model] Cleared models in {affected} role(s)")

    # 使 models_service 缓存失效
    from src.infra.llm.models_service import invalidate_cache

    await invalidate_cache()

    return None
