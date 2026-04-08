"""
Model 配置存储层

提供 Model 配置的数据库操作：
- 全局 Model 启用/禁用配置
- Provider 配置（api_key/api_base）
- 角色可用的 Models 映射
- LLM Provider 管理（内置 + 自定义）
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# MongoDB 集合名称
_COLL_MODEL_CONFIG = "model_config"
_COLL_ROLE_MODELS = "role_models"
_COLL_MODEL_PROVIDERS = "model_providers"
_COLL_LLM_PROVIDERS = "llm_providers"


class ModelConfigStorage:
    """
    Model 配置存储类

    使用 MongoDB 存储配置数据：
    - 全局 model 配置 (collection: model_config)
    - Provider 配置 (collection: model_providers)
    - 角色-models 映射 (collection: role_models)
    - LLM Provider 管理 (collection: llm_providers)
    """

    def __init__(self):
        self._collections: dict[str, Any] = {}

    def _get_collection(self, name: str):
        """延迟加载 MongoDB 集合"""
        if name not in self._collections:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collections[name] = db[name]
        return self._collections[name]

    async def ensure_indexes(self):
        """创建必要的 MongoDB 索引"""
        await self._get_collection(_COLL_MODEL_CONFIG).create_index("type", unique=True)
        await self._get_collection(_COLL_ROLE_MODELS).create_index("role_id", unique=True)
        await self._get_collection(_COLL_LLM_PROVIDERS).create_index("name", unique=True)

    # ============================================
    # 全局 Model 配置
    # ============================================

    async def get_global_config(self) -> list[dict]:
        """获取全局 Model 配置"""
        doc = await self._get_collection(_COLL_MODEL_CONFIG).find_one({"type": "global"})
        if not doc:
            return []
        return doc.get("models", [])

    async def set_global_config(self, models: list[dict]) -> list[dict]:
        """设置全局 Model 配置"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_MODEL_CONFIG).update_one(
            {"type": "global"},
            {
                "$set": {
                    "models": models,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return models

    async def get_enabled_model_ids(self) -> list[str]:
        """获取全局启用的 Model ID 列表"""
        models = await self.get_global_config()
        return [m["id"] for m in models if m.get("enabled", True)]

    # ============================================
    # Provider 配置
    # ============================================

    async def get_providers(self) -> list[dict]:
        """获取所有 Provider 配置"""
        doc = await self._get_collection(_COLL_MODEL_PROVIDERS).find_one({"type": "providers"})
        if not doc:
            return []
        return doc.get("providers", [])

    async def set_providers(self, providers: list[dict]) -> list[dict]:
        """设置所有 Provider 配置"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_MODEL_PROVIDERS).update_one(
            {"type": "providers"},
            {
                "$set": {
                    "providers": providers,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return providers

    async def get_provider_credentials(self, provider_name: str) -> dict:
        """获取指定 Provider 的 api_key/api_base。

        Returns:
            {"api_key": Optional[str], "api_base": Optional[str]}
            值为 None 表示未配置，应回退全局设置。
        """
        providers = await self.get_providers()
        for p in providers:
            if p.get("name") == provider_name and p.get("enabled", True):
                return {
                    "api_key": p.get("api_key"),
                    "api_base": p.get("api_base"),
                }
        return {"api_key": None, "api_base": None}

    # ============================================
    # 角色 Models 映射
    # ============================================

    async def get_role_models(self, role_id: str) -> Optional[list[str]]:
        """
        获取角色的可用 Models

        Returns:
            可用的 Model ID 列表，None 表示未配置
        """
        doc = await self._get_collection(_COLL_ROLE_MODELS).find_one({"role_id": role_id})
        if not doc:
            return None
        return doc.get("allowed_models") or None

    async def set_role_models(
        self, role_id: str, role_name: str, model_ids: list[str]
    ) -> list[str]:
        """设置角色的可用 Models"""
        now = datetime.now(timezone.utc)
        await self._get_collection(_COLL_ROLE_MODELS).update_one(
            {"role_id": role_id},
            {
                "$set": {
                    "role_name": role_name,
                    "allowed_models": model_ids,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return model_ids

    async def delete_role_models(self, role_id: str) -> bool:
        """删除角色的 Models 配置"""
        result = await self._get_collection(_COLL_ROLE_MODELS).delete_one({"role_id": role_id})
        return result.deleted_count > 0

    async def get_model_credentials(self, model_id: str) -> dict:
        """获取指定模型的 per-model api_key/api_base。

        Returns:
            {"api_key": Optional[str], "api_base": Optional[str]}
            值为 None 表示未配置 per-model 凭证，应回退全局设置。
        """
        models = await self.get_global_config()
        for m in models:
            if m.get("id") == model_id:
                return {
                    "api_key": m.get("api_key"),
                    "api_base": m.get("api_base"),
                }
        return {"api_key": None, "api_base": None}

    async def get_all_role_models(self) -> list[dict]:
        """获取所有角色的 Models 配置"""
        cursor = self._get_collection(_COLL_ROLE_MODELS).find()
        return [
            {
                "role_id": doc["role_id"],
                "role_name": doc.get("role_name", ""),
                "allowed_models": doc.get("allowed_models", []),
            }
            async for doc in cursor
        ]

    # ============================================
    # LLM Provider 管理（llm_providers collection）
    # ============================================

    async def get_llm_providers(self) -> list[dict]:
        """获取所有 LLM Providers（内置 + 自定义）"""
        cursor = self._get_collection(_COLL_LLM_PROVIDERS).find()
        return [doc async for doc in cursor]

    async def get_llm_provider(self, name: str) -> Optional[dict]:
        """获取指定名称的 LLM Provider"""
        return await self._get_collection(_COLL_LLM_PROVIDERS).find_one({"name": name})

    async def upsert_llm_provider(self, provider: dict) -> dict:
        """创建或更新 LLM Provider"""
        now = datetime.now(timezone.utc).isoformat()
        provider["updated_at"] = now
        await self._get_collection(_COLL_LLM_PROVIDERS).update_one(
            {"name": provider["name"]},
            {
                "$set": provider,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return provider

    async def delete_llm_provider(self, name: str) -> bool:
        """删除 LLM Provider。仅允许删除自定义 provider（is_builtin=False）。"""
        result = await self._get_collection(_COLL_LLM_PROVIDERS).delete_one(
            {"name": name, "is_builtin": False}
        )
        return result.deleted_count > 0

    async def get_all_enabled_models(self) -> list[dict]:
        """聚合所有启用 provider 的启用 models。"""
        providers = await self.get_llm_providers()
        models = []
        for p in providers:
            if not p.get("enabled", True):
                continue
            for m in p.get("models", []):
                if m.get("enabled", True):
                    models.append(
                        {
                            **m,
                            "_provider_name": p["name"],
                            "_provider_type": p.get("provider_type", "openai_compatible"),
                        }
                    )
        return models

    async def get_all_enabled_model_ids(self) -> list[str]:
        """获取所有启用 model ID 的扁平列表。"""
        models = await self.get_all_enabled_models()
        return [m["id"] for m in models]

    async def get_model_provider(self, model_id: str) -> Optional[dict]:
        """根据 model_id 找到其所属 provider document。"""
        provider_name = _extract_provider(model_id)
        if provider_name:
            return await self.get_llm_provider(provider_name)
        # 尝试遍历所有 provider 查找包含此 model_id 的
        providers = await self.get_llm_providers()
        for p in providers:
            for m in p.get("models", []):
                if m.get("id") == model_id:
                    return p
        return None

    async def seed_from_env(self) -> None:
        """首次启动时从 LLM_AVAILABLE_MODELS 环境变量填充 llm_providers collection。

        幂等操作：collection 非空时跳过。
        """
        count = await self._get_collection(_COLL_LLM_PROVIDERS).count_documents({})
        if count > 0:
            return

        available_models = settings.LLM_AVAILABLE_MODELS or []
        if not available_models:
            return

        # 按 provider 前缀分组
        provider_groups: dict[str, list] = {}
        for model in available_models:
            model_id = model.get("value", "")
            provider_name = model_id.split("/", 1)[0] if "/" in model_id else "openai"
            provider_groups.setdefault(provider_name, []).append(model)

        # 从 ProviderRegistry 获取元数据
        from src.infra.llm.providers.registry import ProviderRegistry

        registry = ProviderRegistry.get_instance()

        now = datetime.now(timezone.utc).isoformat()
        docs = []
        for provider_name, models in provider_groups.items():
            provider_type = "openai_compatible"
            display_name = provider_name
            color = "#78716C"

            reg_provider = registry.get_provider(provider_name)
            if reg_provider:
                cat = reg_provider.category
                if cat == "anthropic_compatible":
                    provider_type = "anthropic_compatible"
                elif cat == "google_compatible":
                    provider_type = "google_compatible"
                display_name = reg_provider.display_name or provider_name
                ui_meta = reg_provider.get_ui_meta()
                color = ui_meta.color or color

            doc = {
                "name": provider_name,
                "display_name": display_name,
                "provider_type": provider_type,
                "enabled": True,
                "api_key": None,
                "api_base": None,
                "models": [
                    {
                        "id": m.get("value", ""),
                        "name": m.get("label", m.get("value", "")),
                        "model_name": m.get("value", "").split("/", 1)[-1]
                        if "/" in m.get("value", "")
                        else m.get("value", ""),
                        "description": m.get("description", ""),
                        "enabled": True,
                        "supports_thinking": False,
                        "api_key": None,
                        "api_base": None,
                    }
                    for m in models
                ],
                "is_builtin": True,
                "builtin_provider_name": provider_name,
                "color": color,
                "created_at": now,
                "updated_at": now,
            }
            docs.append(doc)

        if docs:
            await self._get_collection(_COLL_LLM_PROVIDERS).insert_many(docs)
            logger.info(f"Seeded {len(docs)} LLM providers from LLM_AVAILABLE_MODELS")

    async def merge_legacy_credentials(self) -> None:
        """将旧 model_providers collection 的凭证合并到 llm_providers。"""
        old_providers = await self.get_providers()
        for old_p in old_providers:
            name = old_p.get("name")
            api_key = old_p.get("api_key")
            api_base = old_p.get("api_base")
            if not (api_key or api_base):
                continue
            await self._get_collection(_COLL_LLM_PROVIDERS).update_one(
                {"name": name},
                {
                    "$set": {
                        "api_key": api_key,
                        "api_base": api_base,
                    }
                },
            )
            logger.info(f"Merged legacy credentials for provider '{name}'")

    async def get_provider_type_map(self) -> dict[str, str]:
        """获取所有 provider 的 {name: provider_type} 映射，用于 LLMClient 缓存。"""
        providers = await self.get_llm_providers()
        return {
            p["name"]: p.get("provider_type", "openai_compatible")
            for p in providers
            if p.get("enabled", True)
        }


# 全局单例
_model_config_storage: Optional[ModelConfigStorage] = None


def get_model_config_storage() -> ModelConfigStorage:
    """获取 Model 配置存储单例"""
    global _model_config_storage
    if _model_config_storage is None:
        _model_config_storage = ModelConfigStorage()
    return _model_config_storage


def _extract_provider(model_id: str) -> str:
    """从 model ID 提取 provider 名称。"""
    if "/" in model_id:
        return model_id.split("/", 1)[0]
    return ""


async def resolve_model_credentials(model_id: str) -> tuple[Optional[str], Optional[str]]:
    """解析模型凭证：llm_providers → per-model config → provider config → 全局 fallback。

    Args:
        model_id: 模型 ID（如 "openai/gpt-4"）

    Returns:
        (api_key, api_base) — 按优先级查找，最后回退全局 LLM_API_KEY / LLM_API_BASE
    """
    try:
        storage = get_model_config_storage()

        # 0. 优先从 llm_providers collection 解析
        provider_doc = await storage.get_model_provider(model_id)
        if provider_doc and provider_doc.get("enabled", True):
            # 查找 per-model 覆盖
            for m in provider_doc.get("models", []):
                if m.get("id") == model_id:
                    model_api_key = m.get("api_key")
                    model_api_base = m.get("api_base")
                    provider_api_key = provider_doc.get("api_key")
                    provider_api_base = provider_doc.get("api_base")
                    api_key = model_api_key or provider_api_key or settings.LLM_API_KEY
                    api_base = model_api_base or provider_api_base or settings.LLM_API_BASE
                    return api_key, api_base
            # provider 找到但 model 没有精确匹配，用 provider 级凭证
            provider_api_key = provider_doc.get("api_key")
            provider_api_base = provider_doc.get("api_base")
            if provider_api_key or provider_api_base:
                return (
                    provider_api_key or settings.LLM_API_KEY,
                    provider_api_base or settings.LLM_API_BASE,
                )

        # 1. 检查 per-model 配置（旧 model_config collection）
        model_creds = await storage.get_model_credentials(model_id)
        model_api_key = model_creds.get("api_key")
        model_api_base = model_creds.get("api_base")

        # 2. 检查 provider 配置（旧 model_providers collection）
        provider_name = _extract_provider(model_id)
        provider_api_key: Optional[str] = None
        provider_api_base: Optional[str] = None
        if provider_name:
            provider_creds = await storage.get_provider_credentials(provider_name)
            provider_api_key = provider_creds.get("api_key")
            provider_api_base = provider_creds.get("api_base")

        # 3. 按优先级合并：model > provider > global
        api_key = model_api_key or provider_api_key or settings.LLM_API_KEY
        api_base = model_api_base or provider_api_base or settings.LLM_API_BASE
        return api_key, api_base
    except Exception as e:
        # DB 不可用时静默回退到全局配置，确保 chat 不中断
        logger.warning(
            "Failed to resolve model credentials for '%s', using global: %s", model_id, e
        )
        return settings.LLM_API_KEY, settings.LLM_API_BASE
