"""Persona preset storage."""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from src.kernel.config import settings


class PersonaPresetStorage:
    """MongoDB storage for persona presets."""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["persona_presets"]
        return self._collection

    _REQUIRED_DEFAULTS: dict[str, Any] = {
        "name": "Untitled",
        "description": "",
        "tags": [],
        "system_prompt": "You are a helpful assistant.",
        "skill_names": [],
        "visibility": "private",
        "status": "draft",
    }

    @classmethod
    def _to_model_dict(cls, doc: dict[str, Any]) -> dict[str, Any]:
        result = dict(doc)
        if "_id" in result:
            result["id"] = str(result.pop("_id"))
        for key, default in cls._REQUIRED_DEFAULTS.items():
            if result.get(key) is None:
                result[key] = default
        return result

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        doc = {
            **data,
            "created_at": data.get("created_at") or now,
            "updated_at": data.get("updated_at") or now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    async def insert_many(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.now()
        for doc in docs:
            doc.setdefault("created_at", now)
            doc.setdefault("updated_at", now)
        result = await self.collection.insert_many(docs)
        for doc, inserted_id in zip(docs, result.inserted_ids):
            doc["id"] = str(inserted_id)
        return docs

    async def get_by_id(self, preset_id: str) -> Optional[dict[str, Any]]:
        try:
            query_id = ObjectId(preset_id)
        except Exception:
            return None
        doc = await self.collection.find_one({"_id": query_id})
        return self._to_model_dict(doc) if doc else None

    async def list_visible(
        self,
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = self._build_visible_query(
            user_id=user_id,
            include_admin=include_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
        )
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        return [self._to_model_dict(doc) async for doc in cursor]

    async def count_visible(
        self,
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
    ) -> int:
        query = self._build_visible_query(
            user_id=user_id,
            include_admin=include_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
        )
        return await self.collection.count_documents(query)

    async def update(self, preset_id: str, update: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            query_id = ObjectId(preset_id)
        except Exception:
            return None
        update = {k: v for k, v in update.items() if v is not None}
        update["updated_at"] = datetime.now()
        if not update:
            return await self.get_by_id(preset_id)
        doc = await self.collection.find_one_and_update(
            {"_id": query_id},
            {"$set": update},
            return_document=True,
        )
        return self._to_model_dict(doc) if doc else None

    async def delete(self, preset_id: str) -> bool:
        try:
            query_id = ObjectId(preset_id)
        except Exception:
            return False
        result = await self.collection.delete_one({"_id": query_id})
        return result.deleted_count > 0

    async def increment_usage(self, preset_id: str) -> None:
        try:
            query_id = ObjectId(preset_id)
        except Exception:
            return
        await self.collection.update_one({"_id": query_id}, {"$inc": {"usage_count": 1}})

    @staticmethod
    def _build_visible_query(
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if not include_admin:
            query["$or"] = [
                {"scope": "user", "owner_user_id": user_id},
                {
                    "scope": "global",
                    "visibility": "public",
                    "status": "published",
                },
            ]
        if scope:
            query["scope"] = scope
        if status:
            query["status"] = status
        if tag:
            query["tags"] = tag
        if q:
            query["$and"] = query.get("$and", [])
            query["$and"].append(
                {
                    "$or": [
                        {"name": {"$regex": q, "$options": "i"}},
                        {"description": {"$regex": q, "$options": "i"}},
                    ]
                }
            )
        return query
