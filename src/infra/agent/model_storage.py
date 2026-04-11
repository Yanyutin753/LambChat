"""
Model 配置存储层

提供 Model 配置的数据库操作：
- 模型的 CRUD
- 存储在 MongoDB
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import UpdateOne

from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.kernel.config import settings
from src.kernel.schemas.model import ModelConfig

# MongoDB 集合名称
_COLL_MODELS = "model_configs"


class ModelStorage:
    """
    Model 配置存储类

    使用 MongoDB 存储配置数据：
    - 模型配置 (collection: model_configs)
    """

    def __init__(self):
        self._collection: Optional[Any] = None
        self._migration_locks: dict[str, asyncio.Lock] = {}

    def _get_collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[_COLL_MODELS]
        return self._collection

    async def ensure_indexes(self):
        """创建必要的 MongoDB 索引"""
        await self._get_collection().create_index("id", unique=True)
        await self._get_collection().create_index("value")
        await self._get_collection().create_index("enabled")
        await self._get_collection().create_index("order")

    # ── 加密辅助 ──────────────────────────────────────────────────

    @staticmethod
    def _encrypt_api_key(key: str | None) -> dict | None:
        """加密 API Key（包装为 dict 后加密）"""
        if key is None:
            return None
        return encrypt_value({"v": key})

    @staticmethod
    def _decrypt_api_key(encrypted: Any) -> str | None:
        """解密 API Key"""
        if encrypted is None:
            return None
        result = decrypt_value(encrypted)
        if isinstance(result, dict):
            return result.get("v")
        # 向后兼容：如果值是明文字符串，直接返回
        return str(result) if result else None

    @staticmethod
    def _is_encrypted(value: Any) -> bool:
        """检查值是否已加密"""
        return isinstance(value, dict) and "__encrypted__" in value

    async def _decrypt_doc(self, doc: dict) -> dict:
        """解密文档中的 api_key，并在需要时执行 lazy migration"""
        if doc.get("api_key") is not None:
            if self._is_encrypted(doc["api_key"]):
                doc["api_key"] = self._decrypt_api_key(doc["api_key"])
            else:
                # 明文 key → 解密返回 + 异步回写加密版本（lazy migration）
                plain_key = doc["api_key"]
                doc["api_key"] = plain_key
                model_id = doc.get("id")
                if model_id:
                    lock = self._migration_locks.setdefault(model_id, asyncio.Lock())
                    if lock.locked():
                        # Another coroutine is already migrating this key, skip
                        return doc
                    async with lock:
                        # Re-check after acquiring lock (double-check pattern)
                        fresh_doc = await self._get_collection().find_one({"id": model_id})
                        if (
                            fresh_doc
                            and fresh_doc.get("api_key")
                            and not self._is_encrypted(fresh_doc["api_key"])
                        ):
                            try:
                                encrypted = self._encrypt_api_key(fresh_doc["api_key"])
                                await self._get_collection().update_one(
                                    {"id": model_id},
                                    {"$set": {"api_key": encrypted}},
                                )
                            except Exception as e:
                                from src.infra.logging import get_logger

                                get_logger(__name__).warning(
                                    f"Lazy migration failed for model {model_id}: {e}"
                                )
                            finally:
                                # Prune lock after migration completes
                                self._migration_locks.pop(model_id, None)
        return doc

    # ============================================
    # CRUD Operations
    # ============================================

    async def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
        """获取所有模型配置

        Args:
            include_disabled: 是否包含已禁用的模型

        Returns:
            模型配置列表，按 order 排序
        """
        query = {} if include_disabled else {"enabled": True}
        cursor = self._get_collection().find(query).sort("order", 1)
        models = []
        async for doc in cursor:
            doc.pop("_id", None)
            doc = await self._decrypt_doc(doc)
            models.append(ModelConfig(**doc))
        return models

    async def get(self, model_id: str) -> Optional[ModelConfig]:
        """根据 ID 获取模型配置

        Args:
            model_id: 模型 ID

        Returns:
            模型配置，不存在返回 None
        """
        doc = await self._get_collection().find_one({"id": model_id})
        if not doc:
            return None
        doc.pop("_id", None)
        doc = await self._decrypt_doc(doc)
        return ModelConfig(**doc)

    async def get_by_value(self, value: str) -> Optional[ModelConfig]:
        """根据 value (model identifier) 获取模型配置

        Args:
            value: 模型标识符

        Returns:
            模型配置，不存在返回 None
        """
        doc = await self._get_collection().find_one({"value": value})
        if not doc:
            return None
        doc.pop("_id", None)
        doc = await self._decrypt_doc(doc)
        return ModelConfig(**doc)

    async def create(self, model: ModelConfig) -> ModelConfig:
        """创建模型配置

        Args:
            model: 模型配置

        Returns:
            创建的模型配置
        """
        now = datetime.now(timezone.utc)
        model_dict = model.model_dump()

        # 如果没有提供 id，生成一个
        if not model_dict.get("id"):
            import uuid

            model_dict["id"] = str(uuid.uuid4())

        model_dict["created_at"] = now.isoformat()
        model_dict["updated_at"] = now.isoformat()

        # 加密 api_key
        if model_dict.get("api_key"):
            model_dict["api_key"] = self._encrypt_api_key(model_dict["api_key"])

        await self._get_collection().insert_one(model_dict)
        # 返回前解密 api_key
        model_dict = await self._decrypt_doc(model_dict)
        return ModelConfig(**model_dict)

    async def update(self, model_id: str, update: dict[str, Any]) -> Optional[ModelConfig]:
        """更新模型配置

        Args:
            model_id: 模型 ID
            update: 更新字段

        Returns:
            更新后的模型配置，不存在返回 None
        """
        update["updated_at"] = datetime.now(timezone.utc).isoformat()

        # 加密 api_key（如果更新中包含）
        if "api_key" in update and update["api_key"] is not None:
            update["api_key"] = self._encrypt_api_key(update["api_key"])

        result = await self._get_collection().find_one_and_update(
            {"id": model_id},
            {"$set": update},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        result = await self._decrypt_doc(result)
        return ModelConfig(**result)

    async def delete(self, model_id: str) -> bool:
        """删除模型配置

        Args:
            model_id: 模型 ID

        Returns:
            是否删除成功
        """
        result = await self._get_collection().delete_one({"id": model_id})
        return result.deleted_count > 0

    async def exists(self, value: str, *, field: str = "value") -> bool:
        """检查模型是否已存在

        Args:
            value: 要查找的值
            field: 查找字段，默认 "value"，可设为 "id"

        Returns:
            是否存在
        """
        doc = await self._get_collection().find_one({field: value})
        return doc is not None

    async def count(self, include_disabled: bool = False) -> dict[str, int]:
        """统计模型数量

        Args:
            include_disabled: 是否包含已禁用的模型

        Returns:
            {"total": int, "enabled": int}
        """
        pipeline = [
            {
                "$facet": {
                    "total": [{"$count": "count"}],
                    "enabled": [{"$match": {"enabled": True}}, {"$count": "count"}],
                }
            }
        ]
        result = await self._get_collection().aggregate(pipeline).to_list(length=1)
        if result:
            facet = result[0]
            total = facet["total"][0]["count"] if facet["total"] else 0
            enabled = facet["enabled"][0]["count"] if facet["enabled"] else 0
        else:
            total = 0
            enabled = 0
        return {"total": total, "enabled": enabled}

    async def toggle(self, model_id: str, enabled: bool) -> Optional[ModelConfig]:
        """启用/禁用模型

        Args:
            model_id: 模型 ID
            enabled: 是否启用

        Returns:
            更新后的模型配置
        """
        return await self.update(model_id, {"enabled": enabled})

    async def reorder(self, model_ids: list[str]) -> list[ModelConfig]:
        """批量更新模型顺序

        Args:
            model_ids: 模型 ID 列表（按新顺序排列）

        Returns:
            更新后的所有模型
        """
        now = datetime.now(timezone.utc).isoformat()
        operations = [
            UpdateOne(
                {"id": model_id},
                {"$set": {"order": order, "updated_at": now}},
            )
            for order, model_id in enumerate(model_ids)
        ]
        if operations:
            await self._get_collection().bulk_write(operations)
        return await self.list_models()

    async def upsert_by_value(self, model: ModelConfig) -> tuple[ModelConfig, bool]:
        """根据 value 插入或更新模型

        Args:
            model: 模型配置

        Returns:
            (模型配置, 是否为新创建)
        """
        existing = await self.get_by_value(model.value)
        if existing:
            update_data = model.model_dump(exclude={"id", "value", "created_at"})
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            # 加密 api_key
            if update_data.get("api_key"):
                update_data["api_key"] = self._encrypt_api_key(update_data["api_key"])

            updated = await self._get_collection().find_one_and_update(
                {"value": model.value},
                {"$set": update_data},
                return_document=True,
            )
            updated.pop("_id", None)
            updated = await self._decrypt_doc(updated)
            return ModelConfig(**updated), False
        else:
            created = await self.create(model)
            return created, True

    async def delete_all(self) -> int:
        """删除所有模型配置

        Returns:
            删除的数量
        """
        result = await self._get_collection().delete_many({})
        return result.deleted_count


# 全局单例
_model_storage: Optional[ModelStorage] = None


def get_model_storage() -> ModelStorage:
    """获取 Model 配置存储单例"""
    global _model_storage
    if _model_storage is None:
        _model_storage = ModelStorage()
    return _model_storage
