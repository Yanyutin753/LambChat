"""Assistant storage layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pymongo import ReturnDocument

from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

from .types import AssistantCreate, AssistantRecord, AssistantScope, AssistantUpdate


class AssistantStorage:
    """MongoDB-backed assistant storage."""

    COLLECTION = "assistants"

    def __init__(self) -> None:
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.COLLECTION]
        return self._collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("assistant_id", unique=True)
        await self.collection.create_index([("scope", 1), ("is_active", 1), ("updated_at", -1)])
        await self.collection.create_index([("created_by", 1), ("updated_at", -1)])
        await self.collection.create_index("tags")
        await self.collection.create_index("cloned_from_assistant_id")

    async def list_public_assistants(self) -> list[AssistantRecord]:
        cursor = self.collection.find({"scope": AssistantScope.PUBLIC.value, "is_active": True})
        docs = await cursor.sort("updated_at", -1).to_list(length=200)
        return [AssistantRecord.model_validate(self._normalize_doc(doc)) for doc in docs]

    async def list_user_assistants(self, user_id: str) -> list[AssistantRecord]:
        cursor = self.collection.find(
            {"scope": AssistantScope.PRIVATE.value, "created_by": user_id}
        )
        docs = await cursor.sort("updated_at", -1).to_list(length=200)
        return [AssistantRecord.model_validate(self._normalize_doc(doc)) for doc in docs]

    async def get_assistant_by_assistant_id(self, assistant_id: str) -> AssistantRecord | None:
        doc = await self.collection.find_one({"assistant_id": assistant_id})
        if doc is None:
            return None
        return AssistantRecord.model_validate(self._normalize_doc(doc))

    async def create_assistant(self, data: AssistantCreate, user_id: str) -> AssistantRecord:
        now = datetime.now(timezone.utc)
        doc = {
            "assistant_id": f"asst_{uuid4().hex[:12]}",
            "name": data.name,
            "description": data.description,
            "system_prompt": data.system_prompt,
            "scope": data.scope.value if isinstance(data.scope, AssistantScope) else data.scope,
            "created_by": user_id,
            "is_active": True,
            "tags": data.tags,
            "avatar_url": data.avatar_url,
            "cloned_from_assistant_id": None,
            "version": data.version,
            "bound_skill_names": data.bound_skill_names,
            "default_model": data.default_model,
            "default_agent_options": data.default_agent_options,
            "default_disabled_tools": data.default_disabled_tools,
            "default_disabled_skills": data.default_disabled_skills,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        return AssistantRecord.model_validate(self._normalize_doc(doc))

    async def update_assistant(
        self, assistant_id: str, data: AssistantUpdate
    ) -> AssistantRecord | None:
        update_doc = {
            key: value
            for key, value in data.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if not update_doc:
            return await self.get_assistant_by_assistant_id(assistant_id)

        update_doc["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.find_one_and_update(
            {"assistant_id": assistant_id},
            {"$set": update_doc},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        return AssistantRecord.model_validate(self._normalize_doc(result))

    async def delete_assistant(self, assistant_id: str) -> bool:
        result = await self.collection.delete_one({"assistant_id": assistant_id})
        return result.deleted_count > 0

    async def clone_assistant(self, assistant_id: str, user_id: str) -> AssistantRecord:
        source = await self.get_assistant_by_assistant_id(assistant_id)
        if source is None:
            raise ValueError(f"Assistant '{assistant_id}' not found")

        now = datetime.now(timezone.utc)
        doc = {
            "assistant_id": f"asst_{uuid4().hex[:12]}",
            "name": source.name,
            "description": source.description,
            "system_prompt": source.system_prompt,
            "scope": AssistantScope.PRIVATE.value,
            "created_by": user_id,
            "is_active": True,
            "tags": list(source.tags),
            "avatar_url": source.avatar_url,
            "cloned_from_assistant_id": source.assistant_id,
            "version": source.version,
            "bound_skill_names": list(source.bound_skill_names),
            "default_model": source.default_model,
            "default_agent_options": dict(source.default_agent_options),
            "default_disabled_tools": list(source.default_disabled_tools),
            "default_disabled_skills": list(source.default_disabled_skills),
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        return AssistantRecord.model_validate(self._normalize_doc(doc))

    @staticmethod
    def _normalize_doc(doc: dict) -> dict:
        normalized = dict(doc)
        normalized.pop("_id", None)
        return normalized


_assistant_storage: Optional[AssistantStorage] = None


def get_assistant_storage() -> AssistantStorage:
    global _assistant_storage
    if _assistant_storage is None:
        _assistant_storage = AssistantStorage()
    return _assistant_storage
