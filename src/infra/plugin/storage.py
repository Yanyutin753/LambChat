"""插件中心存储层。"""

import re
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

from bson import ObjectId
from bson.errors import InvalidId

from src.infra.logging import get_logger
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.plugin.constants import (
    PLUGIN_COLLECTION,
    PLUGIN_FILES_COLLECTION,
    PLUGIN_INSTALLS_COLLECTION,
    PLUGIN_LIST_LIMIT,
    PLUGIN_TAG_LIST_LIMIT,
    PLUGIN_TAG_SCAN_LIMIT,
)
from src.infra.plugin.types import (
    PluginInstallRecord,
    PluginMcpServerPayload,
    PluginPersonaPayload,
    PluginResponse,
    PluginSkillPayload,
    PluginStatus,
)
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now, utc_now_iso
from src.kernel.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

logger = get_logger(__name__)

# 与用户名查询批大小对齐（marketplace.py）
_USERNAME_BATCH_SIZE = 25


class PluginStorage:
    """平台插件存储（元数据 / 负载文件 / 用户安装记录）。"""

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._plugins_collection: Optional["AsyncIOMotorCollection"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None
        self._installs_collection: Optional["AsyncIOMotorCollection"] = None
        self._users_collection: Optional["AsyncIOMotorCollection"] = None

    # ==========================================
    # 集合获取（测试可 monkeypatch）
    # ==========================================

    def _get_plugins_collection(self) -> "AsyncIOMotorCollection":
        if self._plugins_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._plugins_collection = db[PLUGIN_COLLECTION]
        return self._plugins_collection

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[PLUGIN_FILES_COLLECTION]
        return self._files_collection

    def _get_installs_collection(self) -> "AsyncIOMotorCollection":
        if self._installs_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._installs_collection = db[PLUGIN_INSTALLS_COLLECTION]
        return self._installs_collection

    def _get_users_collection(self) -> "AsyncIOMotorCollection":
        if self._users_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._users_collection = db["users"]
        return self._users_collection

    async def ensure_indexes(self) -> None:
        plugins = self._get_plugins_collection()
        await plugins.create_index("name", unique=True, background=True)
        await plugins.create_index("created_by", background=True)
        await plugins.create_index("status", background=True)

        files = self._get_files_collection()
        await files.create_index(
            [("plugin_name", 1), ("skill_name", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

        installs = self._get_installs_collection()
        await installs.create_index(
            [("user_id", 1), ("plugin_name", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 序列化
    # ==========================================

    @staticmethod
    def _mask_mcp_headers(mcp_servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        masked: list[dict[str, Any]] = []
        for server in mcp_servers:
            item = dict(server)
            headers = item.get("headers")
            if isinstance(headers, dict) and headers:
                item["headers"] = {key: "•••••" for key in headers}
            else:
                item["headers"] = None
            masked.append(item)
        return masked

    def _doc_to_response(
        self,
        doc: dict[str, Any],
        *,
        username_map: Optional[dict[str, str]] = None,
        viewer_id: Optional[str] = None,
        install_version: Optional[str] = None,
    ) -> PluginResponse:
        created_by = doc.get("created_by")
        return PluginResponse(
            name=doc["name"],
            display_name=doc.get("display_name", ""),
            description=doc.get("description", ""),
            version=doc.get("version") or "1.0.0",
            author_name=doc.get("author_name", ""),
            tags=doc.get("tags", []),
            skills=[PluginSkillPayload(**skill) for skill in doc.get("skills", [])],
            mcp_servers=[
                PluginMcpServerPayload(**server)
                for server in self._mask_mcp_headers(doc.get("mcp_servers", []))
            ],
            persona=(
                PluginPersonaPayload(**doc["persona"])
                if isinstance(doc.get("persona"), dict)
                else None
            ),
            status=PluginStatus(doc.get("status", PluginStatus.DRAFT.value)),
            created_by=created_by,
            created_by_username=(username_map or {}).get(created_by) if created_by else None,
            install_count=int(doc.get("install_count", 0)),
            is_owner=bool(viewer_id and created_by and created_by == viewer_id),
            installed=install_version is not None,
            installed_version=install_version,
            migrated_from=doc.get("migrated_from"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def _batch_get_usernames(self, user_ids: list[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        collection = self._get_users_collection()
        object_ids = []
        for user_id in user_ids:
            try:
                object_ids.append(ObjectId(user_id))
            except (InvalidId, TypeError):
                continue
        if not object_ids:
            return {}
        result: dict[str, str] = {}
        cursor = collection.find({"_id": {"$in": object_ids}}, {"_id": 1, "username": 1})
        async for doc in cursor:
            key = str(doc["_id"])
            result[key] = doc.get("username", key)
        return result

    # ==========================================
    # 元数据 CRUD
    # ==========================================

    async def plugin_name_exists(self, name: str) -> bool:
        return await self._get_plugins_collection().find_one({"name": name}) is not None

    async def get_plugin_doc(self, name: str) -> Optional[dict[str, Any]]:
        return await self._get_plugins_collection().find_one({"name": name})

    async def create_plugin(self, doc: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        doc.setdefault("version", "1.0.0")
        doc.setdefault("install_count", 0)
        doc["created_at"] = now
        doc["updated_at"] = now
        doc["mcp_servers"] = self._encrypt_mcp_headers(doc.get("mcp_servers", []))
        await self._get_plugins_collection().insert_one(doc)
        return doc

    async def update_plugin(self, name: str, update: dict[str, Any]) -> Optional[dict[str, Any]]:
        update = dict(update)
        update["updated_at"] = utc_now_iso()
        if "mcp_servers" in update:
            update["mcp_servers"] = self._encrypt_mcp_headers(update["mcp_servers"])
        await self._get_plugins_collection().update_one({"name": name}, {"$set": update})
        return await self.get_plugin_doc(name)

    async def set_plugin_status(self, name: str, status: PluginStatus) -> Optional[dict[str, Any]]:
        await self._get_plugins_collection().update_one(
            {"name": name},
            {"$set": {"status": status.value, "updated_at": utc_now_iso()}},
        )
        return await self.get_plugin_doc(name)

    async def delete_plugin(self, name: str) -> bool:
        result = await self._get_plugins_collection().delete_one({"name": name})
        if result.deleted_count > 0:
            await self._get_files_collection().delete_many({"plugin_name": name})
            await self._get_installs_collection().delete_many({"plugin_name": name})
            return True
        return False

    async def increment_install_count(self, name: str) -> None:
        await self._get_plugins_collection().update_one(
            {"name": name}, {"$inc": {"install_count": 1}}
        )

    async def list_plugins(
        self,
        *,
        tags: Optional[list[str]] = None,
        search: Optional[str] = None,
        include_inactive: bool = False,
        viewer_id: Optional[str] = None,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = PLUGIN_LIST_LIMIT,
    ) -> tuple[list[PluginResponse], int]:
        """列出插件（默认 active；投稿者/创建者可见自己的草稿与停用项）。"""
        collection = self._get_plugins_collection()
        query: dict[str, Any] = {}
        if not include_inactive:
            if viewer_id:
                query["$or"] = [
                    {"status": PluginStatus.ACTIVE.value},
                    {"created_by": viewer_id},
                ]
            else:
                query["status"] = PluginStatus.ACTIVE.value
        if tags:
            query["tags"] = {"$all": tags}
        if search:
            safe_search = re.escape(search)
            search_or = [
                {"name": {"$regex": safe_search, "$options": "i"}},
                {"display_name": {"$regex": safe_search, "$options": "i"}},
                {"description": {"$regex": safe_search, "$options": "i"}},
                {"tags": {"$elemMatch": {"$regex": safe_search, "$options": "i"}}},
            ]
            if "$or" in query:
                query["$and"] = [{"$or": query.pop("$or")}, {"$or": search_or}]
            else:
                query["$or"] = search_or

        total = await collection.count_documents(query)
        docs: list[dict[str, Any]] = []
        cursor = collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        async for doc in cursor:
            docs.append(doc)
        if not docs:
            return [], total

        username_map = await self._batch_get_usernames(
            [doc["created_by"] for doc in docs if doc.get("created_by")]
        )
        install_versions = (
            await self.get_install_versions(user_id, [doc["name"] for doc in docs])
            if user_id
            else {}
        )
        responses = [
            self._doc_to_response(
                doc,
                username_map=username_map,
                viewer_id=viewer_id,
                install_version=install_versions.get(doc["name"]),
            )
            for doc in docs
        ]
        return responses, total

    async def get_plugin_response(
        self,
        name: str,
        *,
        viewer_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[PluginResponse]:
        doc = await self.get_plugin_doc(name)
        if not doc:
            return None
        username_map = (
            await self._batch_get_usernames([doc["created_by"]]) if doc.get("created_by") else {}
        )
        install_version = None
        if user_id:
            install = await self.get_install(user_id, name)
            install_version = install.version if install else None
        return self._doc_to_response(
            doc,
            username_map=username_map,
            viewer_id=viewer_id,
            install_version=install_version,
        )

    async def list_tags(self) -> list[str]:
        collection = self._get_plugins_collection()
        tags: set[str] = set()
        cursor = (
            collection.find({"status": PluginStatus.ACTIVE.value}, {"tags": 1})
            .sort("updated_at", -1)
            .limit(PLUGIN_TAG_SCAN_LIMIT)
        )
        async for doc in cursor:
            for tag in doc.get("tags", []):
                tags.add(tag)
                if len(tags) >= PLUGIN_TAG_LIST_LIMIT:
                    return sorted(tags)
        return sorted(tags)

    @staticmethod
    def _encrypt_mcp_headers(mcp_servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        encrypted: list[dict[str, Any]] = []
        for server in mcp_servers:
            item = dict(server)
            headers = item.get("headers")
            if isinstance(headers, dict) and headers and not item.get("ref"):
                item["headers"] = encrypt_value(headers)
            encrypted.append(item)
        return encrypted

    def decrypt_mcp_headers(self, mcp_servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        decrypted: list[dict[str, Any]] = []
        for server in mcp_servers:
            item = dict(server)
            headers = item.get("headers")
            if isinstance(headers, dict) and "__encrypted__" in headers:
                item["headers"] = decrypt_value(headers)
            decrypted.append(item)
        return decrypted

    # ==========================================
    # 技能负载文件
    # ==========================================

    async def list_skill_file_paths(self, plugin_name: str, skill_name: str) -> list[str]:
        collection = self._get_files_collection()
        paths: list[str] = []
        cursor = collection.find(
            {"plugin_name": plugin_name, "skill_name": skill_name}, {"file_path": 1}
        )
        async for doc in cursor:
            paths.append(doc["file_path"])
        return sorted(paths)

    async def read_skill_file(
        self, plugin_name: str, skill_name: str, file_path: str
    ) -> Optional[str]:
        doc = await self._get_files_collection().find_one(
            {"plugin_name": plugin_name, "skill_name": skill_name, "file_path": file_path}
        )
        return doc.get("content") if doc else None

    async def iter_skill_file_batches(
        self, plugin_name: str, skill_name: str
    ) -> AsyncIterator[dict[str, str]]:
        collection = self._get_files_collection()
        cursor = collection.find({"plugin_name": plugin_name, "skill_name": skill_name}).batch_size(
            _USERNAME_BATCH_SIZE
        )
        batch: dict[str, str] = {}
        async for doc in cursor:
            batch[doc["file_path"]] = doc.get("content", "")
            if len(batch) >= _USERNAME_BATCH_SIZE:
                yield batch
                batch = {}
        if batch:
            yield batch

    async def write_skill_files(
        self, plugin_name: str, skill_name: str, files: dict[str, str]
    ) -> None:
        """整树替换插件的技能文件。"""
        if not files:
            return
        from pymongo import UpdateOne

        collection = self._get_files_collection()
        now = utc_now_iso()
        await collection.delete_many(
            {
                "plugin_name": plugin_name,
                "skill_name": skill_name,
                "file_path": {"$nin": list(files.keys())},
            }
        )
        operations = [
            UpdateOne(
                {"plugin_name": plugin_name, "skill_name": skill_name, "file_path": path},
                {
                    "$set": {"content": content, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            for path, content in files.items()
        ]
        if operations:
            await collection.bulk_write(operations, ordered=False)

    # ==========================================
    # 安装记录
    # ==========================================

    async def get_install(self, user_id: str, plugin_name: str) -> Optional[PluginInstallRecord]:
        doc = await self._get_installs_collection().find_one(
            {"user_id": user_id, "plugin_name": plugin_name}
        )
        if not doc:
            return None
        return PluginInstallRecord(
            plugin_name=doc["plugin_name"],
            version=doc.get("version", "1.0.0"),
            installed_at=doc.get("installed_at") or utc_now(),
        )

    async def get_install_versions(self, user_id: str, plugin_names: list[str]) -> dict[str, str]:
        if not plugin_names:
            return {}
        collection = self._get_installs_collection()
        result: dict[str, str] = {}
        cursor = collection.find({"user_id": user_id, "plugin_name": {"$in": plugin_names}})
        async for doc in cursor:
            result[doc["plugin_name"]] = doc.get("version", "1.0.0")
        return result

    async def upsert_install(self, user_id: str, plugin_name: str, version: str) -> None:
        collection = self._get_installs_collection()
        await collection.update_one(
            {"user_id": user_id, "plugin_name": plugin_name},
            {
                "$set": {"version": version, "installed_at": utc_now_iso()},
                "$setOnInsert": {"created_at": utc_now_iso()},
            },
            upsert=True,
        )

    async def delete_install(self, user_id: str, plugin_name: str) -> bool:
        result = await self._get_installs_collection().delete_one(
            {"user_id": user_id, "plugin_name": plugin_name}
        )
        return result.deleted_count > 0

    async def list_installs(self, user_id: str) -> list[PluginInstallRecord]:
        collection = self._get_installs_collection()
        records: list[PluginInstallRecord] = []
        cursor = collection.find({"user_id": user_id}).sort("installed_at", -1)
        async for doc in cursor:
            records.append(
                PluginInstallRecord(
                    plugin_name=doc["plugin_name"],
                    version=doc.get("version", "1.0.0"),
                    installed_at=doc.get("installed_at") or utc_now(),
                )
            )
        return records

    async def close(self) -> None:
        if self._client is not None:
            self._client = None
        self._plugins_collection = None
        self._files_collection = None
        self._installs_collection = None
        self._users_collection = None
