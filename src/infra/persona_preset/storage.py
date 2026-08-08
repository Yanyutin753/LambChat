"""Persona preset storage."""

import re
from typing import Any, Optional

from bson import ObjectId

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

_SEARCH_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]+")
_SEARCH_HAS_LITERAL_RE = re.compile(r"[A-Za-z0-9_\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
PERSONA_PRESET_LIST_LIMIT = 200


def _build_persona_search_terms(text: str | None) -> list[str]:
    """Build role-search terms without broad single-character CJK matches."""
    if not text:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        clean = term.strip().lower()
        if not clean or clean in seen:
            return
        seen.add(clean)
        terms.append(re.escape(clean))

    stripped = text.strip()
    if _SEARCH_HAS_LITERAL_RE.search(stripped) and re.search(r"[^\w\s]", stripped):
        add(stripped)

    for match in _SEARCH_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token.isascii():
            add(token)
            continue

        add(token)
        if len(token) > 2:
            for index in range(len(token) - 1):
                add(token[index : index + 2])

    return terms[:32]


class PersonaPresetStorage:
    """MongoDB storage for persona presets."""

    def __init__(self):
        self._collection = None
        self._user_collection = None

    @property
    def collection(self):
        """Lazy MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["persona_presets"]
        return self._collection

    async def ensure_indexes(self) -> None:
        """Create indexes covering both branches of _build_visible_query $or."""
        from src.infra.logging import get_logger

        logger = get_logger(__name__)
        index_specs = [
            (
                [("scope", 1), ("owner_user_id", 1)],
                "persona_scope_owner_idx",
            ),
            (
                [("scope", 1), ("status", 1), ("visibility", 1)],
                "persona_scope_status_visibility_idx",
            ),
        ]
        for keys, name in index_specs:
            try:
                await self.collection.create_index(keys, name=name, background=True)
            except Exception as e:
                logger.error(f"Failed to create persona preset storage index {name}: {e}")
        logger.info("Persona preset storage index initialization finished")

    @property
    def user_collection(self):
        if self._user_collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._user_collection = db["users"]
        return self._user_collection

    _REQUIRED_DEFAULTS: dict[str, Any] = {
        "name": "Untitled",
        "description": "",
        "tags": [],
        "system_prompt": "You are a helpful assistant.",
        "starter_prompts": [],
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
        now = utc_now()
        doc = {
            **data,
            "created_at": data.get("created_at") or now,
            "updated_at": data.get("updated_at") or now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    async def insert_many(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = utc_now()
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

    # ── User preference helpers (stored in user metadata) ──

    MAX_PINNED = 10
    MAX_FAVORITES = 100

    @staticmethod
    def _bounded_unique_ids(values: Any, limit: int) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        if not isinstance(values, list):
            return result
        for value in values:
            clean = str(value).strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
            if len(result) >= limit:
                break
        return result

    async def _get_user_preset_preference(self, user_id: str) -> dict[str, list[str]]:
        doc = await self.user_collection.find_one(
            {"_id": ObjectId(user_id)},
            {"metadata.pinned_preset_ids": 1, "metadata.favorite_preset_ids": 1},
        )
        metadata = (doc or {}).get("metadata") or {}
        return {
            "pinned": self._bounded_unique_ids(
                metadata.get("pinned_preset_ids"),
                self.MAX_PINNED,
            ),
            "favorite": self._bounded_unique_ids(
                metadata.get("favorite_preset_ids"),
                self.MAX_FAVORITES,
            ),
        }

    async def _set_user_preset_preference(self, user_id: str, pref: dict[str, list[str]]) -> None:
        await self.user_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "metadata.pinned_preset_ids": pref["pinned"],
                    "metadata.favorite_preset_ids": pref["favorite"],
                    "updated_at": utc_now(),
                }
            },
        )

    async def update_user_preference(
        self,
        *,
        user_id: str,
        preset_id: str,
        update: dict[str, Any],
    ) -> dict[str, Any]:
        pref = await self._get_user_preset_preference(user_id)
        pinned: list[str] = list(pref["pinned"])
        favorite: list[str] = list(pref["favorite"])

        if update.get("is_pinned") is not None:
            if update["is_pinned"] and preset_id not in pinned:
                if len(pinned) >= self.MAX_PINNED:
                    return {
                        "is_favorite": preset_id in favorite,
                        "is_pinned": False,
                        "last_used_at": None,
                    }
                pinned.append(preset_id)
            elif not update["is_pinned"] and preset_id in pinned:
                pinned.remove(preset_id)

        if update.get("is_favorite") is not None:
            if update["is_favorite"] and preset_id not in favorite:
                if len(favorite) >= self.MAX_FAVORITES:
                    return {
                        "is_favorite": False,
                        "is_pinned": preset_id in pinned,
                        "last_used_at": None,
                    }
                favorite.append(preset_id)
            elif not update["is_favorite"] and preset_id in favorite:
                favorite.remove(preset_id)

        await self._set_user_preset_preference(user_id, {"pinned": pinned, "favorite": favorite})
        return {
            "is_favorite": preset_id in favorite,
            "is_pinned": preset_id in pinned,
            "last_used_at": None,
        }

    async def touch_user_preference(self, **_: Any) -> dict[str, Any]:
        return {"is_favorite": False, "is_pinned": False, "last_used_at": None}

    # ── List / Count ──

    async def list_visible(
        self,
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        favorite: bool | None = None,
        pinned: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        skip = max(int(skip or 0), 0)
        limit = min(max(int(limit or 1), 1), PERSONA_PRESET_LIST_LIMIT)
        query = self._build_visible_query(
            user_id=user_id,
            include_admin=include_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
        )

        pref: dict[str, list[str]] | None = None
        if favorite is not None or pinned is not None:
            pref = await self._get_user_preset_preference(user_id)
            target_ids: set[str] = set()
            if pinned:
                target_ids.update(pref["pinned"])
            if favorite:
                target_ids.update(pref["favorite"])
            if not target_ids:
                return []
            try:
                object_ids = [ObjectId(pid) for pid in target_ids]
            except Exception:
                return []
            query["_id"] = {"$in": object_ids}

        if pref is None:
            pref = await self._get_user_preset_preference(user_id)
        pinned_ids = pref["pinned"]
        favorite_ids = pref["favorite"]
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {
                "$addFields": {
                    "is_pinned": {"$in": [{"$toString": "$_id"}, pinned_ids]},
                    "is_favorite": {"$in": [{"$toString": "$_id"}, favorite_ids]},
                    "last_used_at": None,
                }
            },
            {
                "$sort": {
                    "is_pinned": -1,
                    "is_favorite": -1,
                    "updated_at": -1,
                    "created_at": -1,
                    "usage_count": -1,
                }
            },
            {"$skip": skip},
            {"$limit": limit},
        ]
        return [self._to_model_dict(doc) async for doc in self.collection.aggregate(pipeline)]

    async def count_visible(
        self,
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        favorite: bool | None = None,
        pinned: bool | None = None,
    ) -> int:
        query = self._build_visible_query(
            user_id=user_id,
            include_admin=include_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
        )

        if favorite is not None or pinned is not None:
            pref = await self._get_user_preset_preference(user_id)
            target_ids: set[str] = set()
            if pinned:
                target_ids.update(pref["pinned"])
            if favorite:
                target_ids.update(pref["favorite"])
            if not target_ids:
                return 0
            try:
                object_ids = [ObjectId(pid) for pid in target_ids]
            except Exception:
                return 0
            query["_id"] = {"$in": object_ids}

        return await self.collection.count_documents(query)

    async def update(self, preset_id: str, update: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            query_id = ObjectId(preset_id)
        except Exception:
            return None
        update = {k: v for k, v in update.items() if v is not None}
        update["updated_at"] = utc_now()
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

    # ── Internal helpers ──

    async def _apply_user_preferences(
        self,
        user_id: str,
        docs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not docs:
            return docs
        pref = await self._get_user_preset_preference(user_id)
        pinned_set = set(pref["pinned"])
        favorite_set = set(pref["favorite"])
        for doc in docs:
            doc["is_pinned"] = doc["id"] in pinned_set
            doc["is_favorite"] = doc["id"] in favorite_set
            doc["last_used_at"] = None
        return docs

    @staticmethod
    def _preference_sort_key(doc: dict[str, Any]) -> tuple:
        updated = doc.get("updated_at")
        created = doc.get("created_at")
        return (
            0 if doc.get("is_pinned") else 1,
            0 if doc.get("is_favorite") else 1,
            -(updated.timestamp() if updated else 0),
            -(created.timestamp() if created else 0),
            -int(doc.get("usage_count", 0) or 0),
        )

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
        if include_admin:
            query["$or"] = [
                {"scope": "user", "owner_user_id": user_id},
                {"scope": "global"},
            ]
        else:
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
            search_terms = _build_persona_search_terms(q)
            if not search_terms:
                query["$and"].append({"_id": {"$in": []}})
            else:
                query["$and"].append(
                    {
                        "$or": [
                            {
                                "$or": [
                                    {"name": {"$regex": term, "$options": "i"}},
                                    {"description": {"$regex": term, "$options": "i"}},
                                    {"tags": {"$elemMatch": {"$regex": term, "$options": "i"}}},
                                    {
                                        "skill_names": {
                                            "$elemMatch": {"$regex": term, "$options": "i"}
                                        }
                                    },
                                ]
                            }
                            for term in search_terms
                        ]
                    }
                )
        return query

    async def close(self) -> None:
        self._collection = None
        self._user_collection = None
