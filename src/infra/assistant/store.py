"""Tenant-scoped assistant storage; revisions fence concurrent configuration edits."""

from typing import Any
from uuid import uuid4

from bson import ObjectId
from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now
from src.kernel.schemas.assistant import Assistant, AssistantCreate, AssistantUpdate


def _assistant(document: dict[str, Any]) -> Assistant:
    return Assistant.model_validate(
        {"id": document["_id"], **{k: v for k, v in document.items() if k != "_id"}}
    )


class AssistantStore:
    def __init__(self, collection=None):
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            self._collection = get_mongo_client()[settings.MONGODB_DB]["assistants"]
        return self._collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index([("user_id", 1), ("updated_at", -1), ("_id", -1)])
        await self.collection.create_index("session_id", unique=True)

    async def create(self, user_id: str, data: AssistantCreate, *, identity=None) -> Assistant:
        now = utc_now()
        document = {
            **data.model_dump(by_alias=True),
            "_id": identity or uuid4().hex,
            "user_id": user_id,
            "session_id": str(ObjectId()),
            "revision": 1,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        if identity:
            from pymongo.errors import DuplicateKeyError

            try:
                document = await self.collection.find_one_and_update(
                    {"_id": identity, "user_id": user_id},
                    {"$setOnInsert": document},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
            except DuplicateKeyError:
                document = await self.collection.find_one({"_id": identity, "user_id": user_id})
            if document is None:
                raise ValueError("Assistant identity conflict")
        else:
            await self.collection.insert_one(document)
        return _assistant(document)

    async def get(self, user_id: str, assistant_id: str) -> Assistant | None:
        document = await self.collection.find_one({"_id": assistant_id, "user_id": user_id})
        return _assistant(document) if document else None

    async def for_session(self, user_id: str, session_id: str) -> Assistant | None:
        document = await self.collection.find_one({"session_id": session_id, "user_id": user_id})
        return _assistant(document) if document else None

    async def list(
        self, user_id: str, *, skip: int = 0, limit: int = 50, archived: bool = False
    ) -> list[Assistant]:
        if skip < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid assistant page")
        query = {"user_id": user_id, "status": "archived" if archived else {"$ne": "archived"}}
        documents = (
            await self.collection.find(query)
            .sort([("updated_at", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        return [_assistant(document) for document in documents]

    async def count(self, user_id: str, *, archived: bool = False) -> int:
        return await self.collection.count_documents(
            {"user_id": user_id, "status": "archived" if archived else {"$ne": "archived"}}
        )

    async def update(
        self, user_id: str, assistant_id: str, data: AssistantUpdate
    ) -> Assistant | None:
        document = await self.collection.find_one_and_update(
            {"_id": assistant_id, "user_id": user_id, "revision": data.revision},
            {
                "$set": {
                    **data.model_dump(
                        exclude={"revision"}
                        | ({"description", "avatar", "starter_prompts"} - data.model_fields_set),
                        by_alias=True,
                    ),
                    "updated_at": utc_now(),
                },
                "$inc": {"revision": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return _assistant(document) if document else None
