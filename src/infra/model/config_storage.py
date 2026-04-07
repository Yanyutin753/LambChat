"""
Model 配置存储层

提供 Model 配置的数据库操作：
- Provider 分组配置（含 api_key 加密）
- 角色可用的 Models 映射
"""

from datetime import datetime, timezone
import os
from typing import Any, Optional

from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.kernel.config import settings

# MongoDB 集合名称
_COLL_MODEL_CONFIG = "model_config"
_COLL_ROLE_MODELS = "role_models"

# Provider 配置文档类型标识
_TYPE_PROVIDERS = "providers"
_TYPE_GLOBAL = "global"


class ModelConfigStorage:
    """
    Model 配置存储类

    使用 MongoDB 存储配置数据：
    - Provider 分组配置 (collection: model_config, type: "providers")
    - 角色-models 映射 (collection: role_models)
    """

    def __init__(self):
        self._collections: dict[str, Any] = {}
        self._legacy_setting_cache: dict[str, Any] = {}

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

    # ============================================
    # Provider 配置 (含加密 api_key)
    # ============================================

    def _encrypt_provider_config(self, providers: list[dict]) -> list[dict]:
        """对 provider 配置中的 api_key 进行加密"""
        result = []
        for p in providers:
            p_copy = p.copy()
            if p_copy.get("api_key"):
                p_copy["api_key"] = encrypt_value({"api_key": p_copy["api_key"]})
            else:
                p_copy["api_key"] = None
            # 递归加密 models 中的 api_key（如果有）
            if "models" in p_copy:
                p_copy["models"] = p_copy["models"]  # models 中无敏感字段
            result.append(p_copy)
        return result

    def _decrypt_provider_config(self, providers: list[dict]) -> list[dict]:
        """对 provider 配置中的 api_key 进行解密"""
        result = []
        for p in providers:
            p_copy = p.copy()
            if p_copy.get("api_key"):
                decrypted = decrypt_value(p_copy["api_key"])
                if decrypted and isinstance(decrypted, dict):
                    p_copy["api_key"] = decrypted.get("api_key")
                else:
                    p_copy["api_key"] = None
            result.append(p_copy)
        return result

    def _sanitize_provider_config_for_response(self, providers: list[dict]) -> list[dict]:
        """移除明文 api_key，仅返回是否已配置。"""
        result = []
        for p in providers:
            p_copy = p.copy()
            api_key = p_copy.get("api_key")
            p_copy["has_api_key"] = bool(api_key)
            p_copy["api_key"] = None
            p_copy["clear_api_key"] = False
            result.append(p_copy)
        return result

    async def _merge_provider_config_updates(self, providers: list[dict]) -> list[dict]:
        """Merge provider updates with stored encrypted credentials."""
        existing_doc = await self._get_collection(_COLL_MODEL_CONFIG).find_one({"type": _TYPE_PROVIDERS})
        existing_decrypted = self._decrypt_provider_config((existing_doc or {}).get("providers", []))
        existing_providers = {
            provider.get("provider"): provider
            for provider in existing_decrypted
            if provider.get("provider")
        }

        merged: list[dict] = []
        for provider in providers:
            provider_copy = provider.copy()
            provider_name = provider_copy.get("provider")
            existing = existing_providers.get(provider_name, {})

            clear_api_key = bool(provider_copy.pop("clear_api_key", False))
            provider_copy.pop("has_api_key", None)

            if clear_api_key:
                provider_copy["api_key"] = None
            elif provider_copy.get("api_key"):
                pass
            elif existing.get("api_key"):
                provider_copy["api_key"] = existing["api_key"]
            else:
                provider_copy["api_key"] = None

            merged.append(provider_copy)

        return merged

    async def _get_legacy_setting_value(self, key: str) -> Any:
        """Read legacy setting from DB-first settings service with env/settings fallback."""
        if key in self._legacy_setting_cache:
            return self._legacy_setting_cache[key]

        value = None
        try:
            from src.infra.settings.service import get_settings_service

            service = get_settings_service()
            if service:
                value = await service.get_raw(key)
        except Exception:
            value = None

        if value in (None, ""):
            value = os.environ.get(key)

        if value in (None, ""):
            value = getattr(settings, key, None)

        self._legacy_setting_cache[key] = value
        return value

    async def _build_provider_config_from_legacy_global(self, legacy_models: list[dict]) -> list[dict]:
        """Build provider config from legacy global model config for backward compatibility."""
        if not legacy_models:
            return []

        default_provider = getattr(settings, "LLM_PROVIDER_DEFAULT", "anthropic") or "anthropic"
        grouped_models: dict[str, list[dict]] = {}
        for m in legacy_models:
            raw_id = m.get("id") or m.get("value") or ""
            if not raw_id:
                continue
            provider_name = self._infer_provider_for_model(raw_id, default_provider)
            model_value = raw_id if "/" in raw_id else f"{provider_name}/{raw_id}"
            grouped_models.setdefault(provider_name, []).append(
                {
                    "value": model_value,
                    "label": m.get("name") or m.get("label") or raw_id,
                    "description": m.get("description", ""),
                    "enabled": m.get("enabled", True),
                }
            )

        if not grouped_models:
            return []

        legacy_primary_provider = self._get_legacy_primary_provider(
            default_provider, [m["value"] for models in grouped_models.values() for m in models]
        )
        providers = []
        for provider_name, models in grouped_models.items():
            provider_api_key, provider_base_url = await self._get_provider_credentials(
                provider_name, legacy_primary_provider
            )
            providers.append(
                {
                    "provider": provider_name,
                    "label": f"Legacy ({provider_name.title()})",
                    "base_url": provider_base_url,
                    "api_key": provider_api_key,
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "max_retries": 3,
                    "retry_delay": 1.0,
                    "models": models,
                }
            )
        return providers

    def _infer_provider_for_model(self, model_value: str, default_provider: str) -> str:
        """Infer provider for a model value, preserving old non-prefixed IDs."""
        if "/" in model_value:
            return model_value.split("/", 1)[0]

        from src.infra.llm.providers.registry import ProviderRegistry

        registry = ProviderRegistry.get_instance()
        provider = registry.get_provider_for_model(model_value)
        return provider.config.name if provider else default_provider

    @staticmethod
    def _models_compatible(model_a: str, model_b: str) -> bool:
        """Compatibility match between provider-prefixed and legacy model IDs."""
        if not model_a or not model_b:
            return False
        if model_a == model_b:
            return True
        if "/" in model_a and "/" not in model_b:
            return model_a.endswith(f"/{model_b}")
        if "/" in model_b and "/" not in model_a:
            return model_b.endswith(f"/{model_a}")
        return False

    def _get_legacy_primary_provider(
        self, default_provider: str, model_values: Optional[list[str]] = None
    ) -> str:
        """Determine which provider should inherit legacy global LLM_API_* settings."""
        if model_values:
            providers = {
                self._infer_provider_for_model(model_value, default_provider)
                for model_value in model_values
                if model_value
            }
            if len(providers) == 1:
                return next(iter(providers))

        configured_model = getattr(settings, "LLM_MODEL", "") or ""
        if configured_model:
            return self._infer_provider_for_model(configured_model, default_provider)

        return default_provider

    async def _get_provider_credentials(
        self, provider_name: str, legacy_primary_provider: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Resolve provider credentials with legacy global fallback for the legacy primary provider."""
        api_key = await self._get_legacy_setting_value(f"LLM_PROVIDER_{provider_name.upper()}_API_KEY")
        base_url = await self._get_legacy_setting_value(
            f"LLM_PROVIDER_{provider_name.upper()}_BASE_URL"
        )

        if provider_name == legacy_primary_provider:
            api_key = api_key or await self._get_legacy_setting_value("LLM_API_KEY")
            base_url = base_url or await self._get_legacy_setting_value("LLM_API_BASE")

        return api_key or None, base_url or None

    async def get_provider_config(self) -> list[dict]:
        providers, _ = await self.get_provider_config_with_metadata(include_secrets=False)
        return providers

    async def get_provider_config_raw(self) -> list[dict]:
        providers, _ = await self.get_provider_config_with_metadata(include_secrets=True)
        return providers

    async def get_provider_config_with_metadata(
        self, include_secrets: bool = False
    ) -> tuple[list[dict], dict[str, Any]]:
        """获取 Provider 分组配置。

        向后兼容：自动为老数据补齐新字段的默认值。
        """
        metadata = {
            "legacy_migration_applied": False,
            "legacy_inherited_providers": [],
        }
        doc = await self._get_collection(_COLL_MODEL_CONFIG).find_one({"type": _TYPE_PROVIDERS})
        if doc:
            providers = doc.get("providers", [])
            decrypted = self._decrypt_provider_config(providers)
        else:
            # Backward compat: migrate legacy `type=global` model config on read.
            legacy_doc = await self._get_collection(_COLL_MODEL_CONFIG).find_one({"type": _TYPE_GLOBAL})
            if not legacy_doc:
                return [], metadata
            decrypted = await self._build_provider_config_from_legacy_global(
                legacy_doc.get("models", [])
            )
            if decrypted:
                await self.set_provider_config(decrypted)
                metadata["legacy_migration_applied"] = True
                metadata["legacy_inherited_providers"] = [p["provider"] for p in decrypted]

        # Backward compat: fill in defaults for new fields if missing
        for p in decrypted:
            p.setdefault("temperature", 0.7)
            p.setdefault("max_tokens", 4096)
            p.setdefault("max_retries", 3)
            p.setdefault("retry_delay", 1.0)

        if include_secrets:
            return decrypted, metadata
        return self._sanitize_provider_config_for_response(decrypted), metadata

    async def set_provider_config(self, providers: list[dict]) -> list[dict]:
        """设置 Provider 分组配置（api_key 会加密存储）"""
        now = datetime.now(timezone.utc)
        merged_providers = await self._merge_provider_config_updates(providers)
        encrypted_providers = self._encrypt_provider_config(merged_providers)
        await self._get_collection(_COLL_MODEL_CONFIG).update_one(
            {"type": _TYPE_PROVIDERS},
            {
                "$set": {
                    "providers": encrypted_providers,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return self._sanitize_provider_config_for_response(merged_providers)

    async def get_all_model_values(self) -> list[str]:
        """获取所有模型的 value 列表（用于权限检查）"""
        providers = await self.get_provider_config()
        values = []
        for p in providers:
            for m in p.get("models", []):
                values.append(m["value"])
        return values

    async def get_enabled_model_ids(self) -> list[str]:
        """获取全局启用的 Model ID 列表"""
        providers = await self.get_provider_config()
        enabled = []
        for p in providers:
            for m in p.get("models", []):
                if m.get("enabled", True):
                    enabled.append(m["value"])
        return enabled

    async def get_provider_for_model(self, model_value: str) -> Optional[dict]:
        """根据 model value 查找其所属的 provider 配置"""
        providers = await self.get_provider_config()
        for p in providers:
            for m in p.get("models", []):
                if self._models_compatible(m.get("value", ""), model_value):
                    return p
        return None

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


# 全局单例
_model_config_storage: Optional[ModelConfigStorage] = None


def get_model_config_storage() -> ModelConfigStorage:
    """获取 Model 配置存储单例"""
    global _model_config_storage
    if _model_config_storage is None:
        _model_config_storage = ModelConfigStorage()
    return _model_config_storage
