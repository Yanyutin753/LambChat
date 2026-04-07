"""
Model 配置存储层

提供 Model 配置的数据库操作：
- 全局 Model 启用/禁用配置
- 角色可用的 Models 映射
"""

from datetime import datetime, timezone
from typing import Any, Optional

from src.kernel.config import settings

# MongoDB 集合名称
_COLL_MODEL_CONFIG = "model_config"
_COLL_ROLE_MODELS = "role_models"


class ModelConfigStorage:
    """
    Model 配置存储类

    使用 MongoDB 存储配置数据：
    - 全局 model 配置 (collection: model_config)
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
