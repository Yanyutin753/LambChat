"""
Model 配置存储层

提供 Model 配置的数据库操作：
- 模型的 CRUD
- 存储在 MongoDB
"""

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
        # value 不再唯一：同一模型可来自不同渠道（如直连 OpenAI、Azure、代理服务等）
        # 迁移：删除旧的唯一索引（如存在），然后创建非唯一索引
        existing = await self._get_collection().index_information()
        if "value_1" in existing and existing["value_1"].get("unique"):
            await self._get_collection().drop_index("value_1")
        if "value_1" not in existing or existing["value_1"].get("unique"):
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

    def _decrypt_doc(self, doc: dict) -> dict:
        """解密文档中的 api_key（纯读取，无副作用）。"""
        if doc.get("api_key") is not None:
            doc["api_key"] = self._decrypt_api_key(doc["api_key"])
        return doc

    # ── 批量迁移 ──────────────────────────────────────────────────

    async def migrate_plaintext_keys(self) -> int:
        """一次性批量加密所有明文 API Key。

        Returns:
            加密的文档数量
        """
        # 查找所有 api_key 不为空且未加密的文档
        cursor = self._get_collection().find({"api_key": {"$ne": None}})
        to_encrypt: list[tuple[str, str]] = []
        async for doc in cursor:
            key = doc.get("api_key")
            if key and not self._is_encrypted(key):
                to_encrypt.append((doc["id"], str(key)))

        if not to_encrypt:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        operations = [
            UpdateOne(
                {"id": model_id},
                {
                    "$set": {
                        "api_key": self._encrypt_api_key(key),
                        "updated_at": now,
                    }
                },
            )
            for model_id, key in to_encrypt
        ]
        result = await self._get_collection().bulk_write(operations)
        from src.infra.logging import get_logger

        get_logger(__name__).info(
            f"[ModelStorage] Migrated {result.modified_count} plaintext API keys to encrypted"
        )
        return result.modified_count

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
            doc = self._decrypt_doc(doc)
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
        doc = self._decrypt_doc(doc)
        return ModelConfig(**doc)

    async def get_by_value(self, value: str) -> Optional[ModelConfig]:
        """根据 value (model identifier) 获取模型配置

        优先返回 enabled 的模型。当同一 value 存在多条记录时
        （不同渠道/提供商），选择第一个启用的。

        Args:
            value: 模型标识符

        Returns:
            模型配置，不存在返回 None
        """
        # 优先查找 enabled 的
        doc = await self._get_collection().find_one(
            {"value": value, "enabled": True},
            sort=[("order", 1)],
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc = self._decrypt_doc(doc)
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
        model_dict = self._decrypt_doc(model_dict)
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
        result = self._decrypt_doc(result)
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

    async def exists(self, value: str) -> bool:
        """检查模型 value 是否已存在

        Args:
            value: 模型标识符

        Returns:
            是否存在
        """
        doc = await self._get_collection().find_one({"value": value})
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
            updated = self._decrypt_doc(updated)
            return ModelConfig(**updated), False
        else:
            created = await self.create(model)
            return created, True

    async def bulk_upsert_by_value(self, models: list[ModelConfig]) -> list[ModelConfig]:
        """批量根据 value 插入或更新模型（单次 bulk_write）

        Args:
            models: 模型配置列表

        Returns:
            创建/更新后的模型配置列表
        """
        now = datetime.now(timezone.utc).isoformat()
        import uuid

        operations = []
        for model in models:
            model_dict = model.model_dump()
            # 加密 api_key
            if model_dict.get("api_key"):
                model_dict["api_key"] = self._encrypt_api_key(model_dict["api_key"])

            # 生成 ID 如果没有
            if not model_dict.get("id"):
                model_dict["id"] = str(uuid.uuid4())

            update_fields = {
                k: v for k, v in model_dict.items() if k not in ("id", "value", "created_at")
            }
            update_fields["updated_at"] = now

            operations.append(
                UpdateOne(
                    {"value": model.value},
                    {
                        "$set": update_fields,
                        "$setOnInsert": {
                            "id": model_dict["id"],
                            "value": model.value,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            )

        if operations:
            await self._get_collection().bulk_write(operations)

        # 返回更新后的模型列表
        values = [m.value for m in models]
        result = []
        cursor = self._get_collection().find({"value": {"$in": values}})
        async for doc in cursor:
            doc.pop("_id", None)
            doc = self._decrypt_doc(doc)
            result.append(ModelConfig(**doc))
        return result

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
