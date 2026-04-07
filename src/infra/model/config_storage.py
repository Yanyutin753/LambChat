"""
Model 配置存储层

提供 Model 配置的数据库操作：
- Provider 分组配置（含 api_key 加密）
- 角色可用的 Models 映射
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.kernel.config import settings

# MongoDB 集合名称
_COLL_MODEL_CONFIG = "model_config"
_COLL_ROLE_MODELS = "role_models"

# Provider 配置文档类型标识
_TYPE_PROVIDERS = "providers"


class ModelConfigStorage:
    """
    Model 配置存储类

    使用 MongoDB 存储配置数据：
    - Provider 分组配置 (collection: model_config, type: "providers")
    - 角色-models 映射 (collection: role_models)
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

    async def get_provider_config(self) -> list[dict]:
        """获取 Provider 分组配置（api_key 已解密）。

        向后兼容：自动为老数据补齐新字段的默认值。
        """
        doc = await self._get_collection(_COLL_MODEL_CONFIG).find_one({"type": _TYPE_PROVIDERS})
        if not doc:
            return []
        providers = doc.get("providers", [])
        decrypted = self._decrypt_provider_config(providers)

        # Backward compat: fill in defaults for new fields if missing
        for p in decrypted:
            p.setdefault("temperature", 0.7)
            p.setdefault("max_tokens", 4096)
            p.setdefault("max_retries", 3)
            p.setdefault("retry_delay", 1.0)

        return decrypted

    async def set_provider_config(self, providers: list[dict]) -> list[dict]:
        """设置 Provider 分组配置（api_key 会加密存储）"""
        now = datetime.now(timezone.utc)
        encrypted_providers = self._encrypt_provider_config(providers)
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
        return providers  # 返回解密后的原始数据

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
                if m["value"] == model_value:
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
