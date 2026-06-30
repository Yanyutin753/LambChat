import json
import re
from typing import TYPE_CHECKING, Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.skill.binary import (
    BINARY_REF_MARKER,
    SkillBinaryRef,
    build_binary_ref_content,
    build_storage_key,
    guess_mime_type,
    parse_binary_ref_async,
)
from src.infra.skill.constants import SKILL_FILES_COLLECTION
from src.infra.skill.storage_helpers import (
    SKILL_BATCH_FILE_LOOKUP_LIMIT,
    SKILL_EFFECTIVE_LOAD_LIMIT,
    SKILL_FILES_PER_SKILL_LIMIT,
    SKILL_MD_SCAN_LIMIT,
    SKILL_METADATA_LIST_LIMIT,
    normalize_skill_file_path,
    normalize_skill_files,
    normalize_skill_name_list,
)
from src.infra.skill.types import InstalledFrom, SkillMeta
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

logger = get_logger(__name__)


async def _parse_skill_md_offload(content: str) -> tuple[Optional[str], str, list[str]]:
    from src.infra.skill.parser import parse_skill_md

    return await run_blocking_io(parse_skill_md, content)


class SkillStorage:
    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None

    MAX_PINNED = 10
    MAX_FAVORITES = 100

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_FILES_COLLECTION]
        return self._files_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("user_id", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_skill_files(self, skill_name: str, user_id: str) -> dict[str, str]:
        """获取用户某个 Skill 的所有文件（排除 __meta__）"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        cursor = collection.find({"skill_name": skill_name, "user_id": user_id}).limit(
            SKILL_FILES_PER_SKILL_LIMIT + 1
        )
        async for doc in cursor:
            if doc["file_path"] != "__meta__":
                files[normalize_skill_file_path(doc["file_path"])] = doc["content"]
                if len(files) >= SKILL_FILES_PER_SKILL_LIMIT:
                    break
        return files

    async def get_skill_file(self, skill_name: str, file_path: str, user_id: str) -> Optional[str]:
        """获取用户某个 Skill 的单个文件"""
        collection = self._get_files_collection()
        file_path = normalize_skill_file_path(file_path)
        doc = await collection.find_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
                "file_path": file_path,
            }
        )
        if not doc and (file_path.endswith("/SKILL.md") or file_path == "SKILL.md"):
            legacy_path_pattern = re.escape(file_path[:-8]) + r"skill\.md"
            doc = await collection.find_one(
                {
                    "skill_name": skill_name,
                    "user_id": user_id,
                    "file_path": {"$regex": f"^{legacy_path_pattern}$", "$options": "i"},
                }
            )
        return doc["content"] if doc else None

    async def set_skill_file(
        self, skill_name: str, file_path: str, content: str, user_id: str
    ) -> None:
        """原子 upsert 单个文件（文本内容）"""
        collection = self._get_files_collection()
        file_path = normalize_skill_file_path(file_path)
        now = utc_now_iso()
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
            {
                "$set": {"content": content, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def set_skill_binary_file(
        self,
        skill_name: str,
        file_path: str,
        data: bytes,
        user_id: str,
        mime_type: Optional[str] = None,
    ) -> SkillBinaryRef:
        """上传二进制文件到 S3/本地存储，并在 MongoDB 存储引用。"""
        from src.infra.storage.s3.service import get_or_init_storage

        if not mime_type:
            mime_type = guess_mime_type(file_path)

        storage_key = build_storage_key(user_id, skill_name, file_path)
        storage_service = await get_or_init_storage()

        # 上传到 S3/本地存储
        await storage_service.upload_to_key(
            data=data,
            key=storage_key,
            content_type=mime_type,
            skip_size_limit=True,  # size already validated at API layer
        )

        # 构建引用并存入 MongoDB
        ref_content = build_binary_ref_content(storage_key, mime_type, len(data))
        await self.set_skill_file(skill_name, file_path, ref_content, user_id)

        return SkillBinaryRef(
            storage_key=storage_key,
            mime_type=mime_type,
            size=len(data),
        )

    async def update_skill_file_cas(
        self,
        skill_name: str,
        file_path: str,
        expected_content: str,
        new_content: str,
        user_id: str,
    ) -> bool:
        """
        Compare-and-swap: 仅当当前内容匹配 expected_content 时才更新。
        用于防止并发编辑丢失更新。

        Returns:
            True 如果更新成功，False 如果内容已被其他人修改
        """
        collection = self._get_files_collection()
        file_path = normalize_skill_file_path(file_path)
        now = utc_now_iso()
        result = await collection.update_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
                "file_path": file_path,
                "content": expected_content,
            },
            {
                "$set": {"content": new_content, "updated_at": now},
            },
        )
        return result.modified_count > 0

    async def delete_skill_file(self, skill_name: str, file_path: str, user_id: str) -> None:
        """删除单个文件（如果是二进制引用，同时删除 S3 对象）"""
        collection = self._get_files_collection()
        file_path = normalize_skill_file_path(file_path)
        doc = await collection.find_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
        )
        if doc:
            # 检查是否为二进制引用，如果是则删除 S3 对象
            binary_ref = await parse_binary_ref_async(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)
            await collection.delete_one(
                {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
            )

    async def _delete_s3_object(self, storage_key: str) -> None:
        """删除 S3/本地存储中的文件"""
        try:
            from src.infra.storage.s3.service import get_or_init_storage

            storage_service = await get_or_init_storage()
            await storage_service.delete_file(storage_key)
        except Exception as e:
            logger.warning(f"Failed to delete S3 object {storage_key}: {e}")

    async def sync_skill_files(self, skill_name: str, files: dict[str, str], user_id: str) -> None:
        """批量同步文件（替换所有，但保留 __meta__）。支持文本和二进制引用。"""
        files = normalize_skill_files(files)
        if not files:
            return
        if len(files) > SKILL_FILES_PER_SKILL_LIMIT:
            raise ValueError(f"Skill contains too many files (max {SKILL_FILES_PER_SKILL_LIMIT})")
        collection = self._get_files_collection()
        now = utc_now_iso()

        from pymongo import UpdateOne

        operations: list = []

        removed_query = {
            "skill_name": skill_name,
            "user_id": user_id,
            "file_path": {"$ne": "__meta__", "$nin": list(files.keys())},
        }

        # Only scan removed binary references for S3 cleanup; Mongo handles row deletion.
        s3_keys_to_delete: list[str] = []
        removed_binary_cursor = collection.find(
            {
                **removed_query,
                "content": {"$regex": BINARY_REF_MARKER},
            },
            {"content": 1},
        ).limit(SKILL_FILES_PER_SKILL_LIMIT)
        async for doc in removed_binary_cursor:
            binary_ref = await parse_binary_ref_async(doc.get("content", ""))
            if binary_ref:
                s3_keys_to_delete.append(binary_ref.storage_key)

        await collection.delete_many(removed_query)

        for file_path, content in files.items():
            operations.append(
                UpdateOne(
                    {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
                    {
                        "$set": {"content": content, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            await collection.bulk_write(operations, ordered=True)

        # 批量删除 S3 对象
        for s3_key in s3_keys_to_delete:
            await self._delete_s3_object(s3_key)

    async def upsert_skill_files_batch(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: str,
    ) -> int:
        """Upsert a bounded batch of text skill files without deleting other paths."""
        files = normalize_skill_files(files)
        if not files:
            return 0

        from pymongo import UpdateOne

        collection = self._get_files_collection()
        now = utc_now_iso()
        operations = [
            UpdateOne(
                {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
                {
                    "$set": {"content": content, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            for file_path, content in files.items()
        ]
        await collection.bulk_write(operations, ordered=True)
        return len(operations)

    async def delete_skill_files(self, skill_name: str, user_id: str) -> None:
        """删除用户某个 Skill 的所有文件（包括 S3 二进制清理）"""
        collection = self._get_files_collection()

        # 先收集所有二进制引用，清理 S3
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"content": 1},
        ):
            binary_ref = await parse_binary_ref_async(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)

        await collection.delete_many(
            {
                "skill_name": skill_name,
                "user_id": user_id,
            }
        )

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        """列出用户某个 Skill 的所有文件路径（排除 __meta__）"""
        collection = self._get_files_collection()
        paths = []
        cursor = collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"file_path": 1},
        ).limit(SKILL_FILES_PER_SKILL_LIMIT)
        async for doc in cursor:
            paths.append(normalize_skill_file_path(doc["file_path"]))
        return paths

    async def get_skill_file_stats(self, skill_name: str, user_id: str) -> dict[str, Any]:
        """获取单个 Skill 的文件统计信息（created_at/updated_at 来自文件聚合，排除 __meta__）"""
        collection = self._get_files_collection()
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "skill_name": skill_name,
                    "user_id": user_id,
                    "file_path": {"$ne": "__meta__"},
                }
            },
            {
                "$group": {
                    "_id": "$skill_name",
                    "file_count": {"$sum": 1},
                    "created_at": {"$min": "$created_at"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
        ]
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            return {
                "file_count": doc["file_count"],
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }
        return {"file_count": 0, "created_at": None, "updated_at": None}

    async def list_user_skills(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        disabled_skills: Optional[list[str]] = None,
        pinned_skill_names: Optional[list[str]] = None,
        favorite_skill_names: Optional[list[str]] = None,
        q: str | None = None,
        tags: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """列出用户所有 Skill（带文件信息）

        Args:
            user_id: 用户 ID
            skip: 分页跳过数量
            limit: 分页限制
            disabled_skills: 从用户 metadata 中获取的 disabled_skills 列表
        """
        if disabled_skills is None:
            disabled_skills = []
        if pinned_skill_names is None:
            pinned_skill_names = []
        if favorite_skill_names is None:
            favorite_skill_names = []
        disabled_skills = normalize_skill_name_list(disabled_skills)
        pinned_skill_names = normalize_skill_name_list(pinned_skill_names)
        favorite_skill_names = normalize_skill_name_list(favorite_skill_names)
        disabled_set = set(disabled_skills)
        pinned_set = set(pinned_skill_names)
        favorite_set = set(favorite_skill_names)
        has_preferences = bool(pinned_set or favorite_set)

        collection = self._get_files_collection()
        paged_skill_names: list[str] | None = None
        if q or tags:
            matching_skill_names = await self.list_matching_skill_names(user_id, q=q, tags=tags)
            paged_skill_names = (
                matching_skill_names
                if has_preferences
                else matching_skill_names[skip : skip + limit]
            )
            if not paged_skill_names:
                return []

        # 使用 aggregation 一次获取所有 skill 的统计信息 + 文件路径（排除 __meta__）
        match: dict[str, Any] = {"user_id": user_id, "file_path": {"$ne": "__meta__"}}
        if paged_skill_names is not None:
            match["skill_name"] = {"$in": paged_skill_names}

        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {
                "$group": {
                    "_id": "$skill_name",
                    "file_count": {"$sum": 1},
                    "file_paths": {"$push": "$file_path"},
                    "created_at": {"$min": "$created_at"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
        ]
        if has_preferences:
            pipeline.extend(
                [
                    {
                        "$addFields": {
                            "_is_pinned": {"$in": ["$_id", pinned_skill_names]},
                            "_is_favorite": {"$in": ["$_id", favorite_skill_names]},
                            "_updated_sort": {"$ifNull": ["$updated_at", "$created_at"]},
                            "_created_sort": {"$ifNull": ["$created_at", "$updated_at"]},
                        }
                    },
                    {
                        "$sort": {
                            "_is_pinned": -1,
                            "_is_favorite": -1,
                            "_updated_sort": -1,
                            "_created_sort": -1,
                            "_id": 1,
                        }
                    },
                    {"$skip": skip},
                    {"$limit": limit},
                ]
            )
        else:
            pipeline.append({"$sort": {"_id": 1}})
            if paged_skill_names is None:
                pipeline.extend([{"$skip": skip}, {"$limit": limit}])
        skill_stats: dict[str, dict] = {}
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            skill_stats[doc["_id"]] = {
                "file_count": doc["file_count"],
                "file_paths": doc.get("file_paths", []),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }

        # 批量获取所有 __meta__ 文档
        skill_names = list(skill_stats.keys())
        meta_map: dict[str, SkillMeta] = {}
        if skill_names:
            async for doc in collection.find(
                {"skill_name": {"$in": skill_names}, "user_id": user_id, "file_path": "__meta__"},
                {"skill_name": 1, "content": 1},
            ):
                try:
                    data = await run_blocking_io(json.loads, doc["content"])
                    meta_map[doc["skill_name"]] = SkillMeta(**data)
                except Exception:
                    pass

        # 组装结果
        result = []
        ordered_names = list(skill_stats.keys())
        if paged_skill_names is not None and not has_preferences:
            ordered_names = paged_skill_names
        for skill_name in ordered_names:
            if skill_name not in skill_stats:
                continue
            stats = skill_stats[skill_name]
            meta = meta_map.get(skill_name)
            enabled = skill_name not in disabled_set

            result.append(
                {
                    "skill_name": skill_name,
                    "enabled": enabled,
                    "file_count": stats["file_count"],
                    "file_paths": stats.get("file_paths", []),
                    "installed_from": meta.installed_from.value if meta else None,
                    "published_marketplace_name": meta.published_marketplace_name if meta else None,
                    "created_at": stats.get("created_at"),
                    "updated_at": stats.get("updated_at"),
                    "is_pinned": skill_name in pinned_set,
                    "is_favorite": skill_name in favorite_set,
                }
            )

        return result

    async def _get_user_skill_preference(self, user_id: str) -> dict[str, list[str]]:
        from src.infra.user.storage import UserStorage

        user_doc = await UserStorage().get_by_id(user_id)
        metadata = (user_doc.metadata if user_doc else None) or {}
        return {
            "pinned": normalize_skill_name_list(
                metadata.get("pinned_skill_names"),
                self.MAX_PINNED,
            ),
            "favorite": normalize_skill_name_list(
                metadata.get("favorite_skill_names"),
                self.MAX_FAVORITES,
            ),
        }

    async def update_user_preference(
        self,
        *,
        user_id: str,
        skill_name: str,
        update: dict[str, Any],
    ) -> dict[str, Any]:
        """Update the current user's favorite/pinned state for a skill."""
        from src.infra.user.storage import UserStorage

        pref = await self._get_user_skill_preference(user_id)
        pinned: list[str] = list(pref["pinned"])
        favorite: list[str] = list(pref["favorite"])

        if update.get("is_pinned") is not None:
            if update["is_pinned"] and skill_name not in pinned:
                if len(pinned) >= self.MAX_PINNED:
                    return {
                        "is_favorite": skill_name in favorite,
                        "is_pinned": False,
                    }
                pinned.append(skill_name)
            elif not update["is_pinned"] and skill_name in pinned:
                pinned.remove(skill_name)

        if update.get("is_favorite") is not None:
            if update["is_favorite"] and skill_name not in favorite:
                if len(favorite) >= self.MAX_FAVORITES:
                    return {
                        "is_favorite": False,
                        "is_pinned": skill_name in pinned,
                    }
                favorite.append(skill_name)
            elif not update["is_favorite"] and skill_name in favorite:
                favorite.remove(skill_name)

        await UserStorage().update_metadata(
            user_id,
            {
                "pinned_skill_names": pinned,
                "favorite_skill_names": favorite,
            },
        )
        return {
            "is_favorite": skill_name in favorite,
            "is_pinned": skill_name in pinned,
        }

    async def remove_user_skill_preference(self, user_id: str, skill_names: list[str]) -> None:
        """Remove deleted skill names from the current user's preference lists."""
        from src.infra.user.storage import UserStorage

        remove_names = set(skill_names)
        if not remove_names:
            return

        pref = await self._get_user_skill_preference(user_id)
        pinned = [name for name in pref["pinned"] if name not in remove_names]
        favorite = [name for name in pref["favorite"] if name not in remove_names]
        if pinned == pref["pinned"] and favorite == pref["favorite"]:
            return
        await UserStorage().update_metadata(
            user_id,
            {
                "pinned_skill_names": pinned,
                "favorite_skill_names": favorite,
            },
        )

    async def count_user_skills(
        self,
        user_id: str,
        q: str | None = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Count user skills matching an optional name search."""
        if q or tags:
            return len(await self.list_matching_skill_names(user_id, q=q, tags=tags))
        collection = self._get_files_collection()
        match: dict[str, Any] = {"user_id": user_id, "file_path": {"$ne": "__meta__"}}
        if q:
            match["skill_name"] = {"$regex": q, "$options": "i"}
        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {"$group": {"_id": "$skill_name"}},
            {"$count": "total"},
        ]
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            return int(doc.get("total", 0))
        return 0

    async def count_disabled_user_skills(
        self,
        user_id: str,
        disabled_skills: list[str],
        q: str | None = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Count disabled skills that exist in the current list filters."""
        disabled_skills = normalize_skill_name_list(disabled_skills)
        disabled_set = set(disabled_skills)
        if not disabled_set:
            return 0

        if q or tags:
            matching_names = await self.list_matching_skill_names(user_id, q=q, tags=tags)
            return len(disabled_set.intersection(matching_names))

        collection = self._get_files_collection()
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "user_id": user_id,
                    "file_path": {"$ne": "__meta__"},
                    "skill_name": {"$in": list(disabled_set)},
                }
            },
            {"$group": {"_id": "$skill_name"}},
            {"$count": "total"},
        ]
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            return int(doc.get("total", 0))
        return 0

    async def list_user_skill_tags(self, user_id: str) -> list[str]:
        """List all tags used by a user's skills."""
        _, tags = await self._list_matching_skill_names_and_tags(user_id)
        return tags

    async def list_matching_skill_names(
        self,
        user_id: str,
        q: str | None = None,
        tags: Optional[list[str]] = None,
    ) -> list[str]:
        """List skill names matching search text and all selected tags."""
        names, _ = await self._list_matching_skill_names_and_tags(user_id, q=q, tags=tags)
        return names

    async def _list_matching_skill_names_and_tags(
        self,
        user_id: str,
        q: str | None = None,
        tags: Optional[list[str]] = None,
    ) -> tuple[list[str], list[str]]:
        collection = self._get_files_collection()
        q_lower = q.lower() if q else None
        selected_tags = set(tags or [])
        matching_names: list[str] = []
        available_tags: set[str] = set()

        cursor = collection.find(
            {"user_id": user_id, "file_path": "SKILL.md"},
            {"skill_name": 1, "content": 1},
        ).limit(SKILL_MD_SCAN_LIMIT)
        async for doc in cursor:
            skill_name = doc["skill_name"]
            _, description, parsed_tags = await _parse_skill_md_offload(doc.get("content", ""))
            tag_set = set(parsed_tags)
            available_tags.update(tag_set)

            if q_lower and (
                q_lower not in skill_name.lower()
                and q_lower not in (description or "").lower()
                and not any(q_lower in tag.lower() for tag in parsed_tags)
            ):
                continue
            if selected_tags and not selected_tags.issubset(tag_set):
                continue
            matching_names.append(skill_name)

        return sorted(matching_names), sorted(available_tags)

    async def batch_get_skill_md_contents(
        self, skill_names: list[str], user_id: str
    ) -> dict[str, str]:
        """批量获取多个 skill 的 SKILL.md 内容"""
        skill_names = normalize_skill_name_list(skill_names, SKILL_METADATA_LIST_LIMIT)
        if not skill_names:
            return {}
        collection = self._get_files_collection()
        docs = {}
        async for doc in collection.find(
            {"skill_name": {"$in": skill_names}, "user_id": user_id, "file_path": "SKILL.md"},
            {"skill_name": 1, "content": 1},
        ):
            docs[doc["skill_name"]] = doc.get("content", "")
        return docs

    async def batch_get_skill_files(
        self, skill_keys: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, str]]:
        """批量获取多个 Skill 的文件"""
        if not skill_keys:
            return {}

        collection = self._get_files_collection()

        # 去重
        seen: set[tuple[str, str]] = set()
        or_clauses = []
        for skill_name, user_id in skill_keys:
            key = (skill_name, user_id)
            if key not in seen:
                seen.add(key)
                or_clauses.append({"skill_name": skill_name, "user_id": user_id})
                if len(or_clauses) >= SKILL_BATCH_FILE_LOOKUP_LIMIT:
                    break

        result: dict[tuple[str, str], dict[str, str]] = {}
        for clause in or_clauses:
            key = (clause["skill_name"], clause["user_id"])
            result[key] = {}
            cursor = collection.find(
                {
                    **clause,
                    "file_path": {"$ne": "__meta__"},
                }
            ).limit(SKILL_FILES_PER_SKILL_LIMIT)
            async for doc in cursor:
                result[key][normalize_skill_file_path(doc["file_path"])] = doc["content"]

        return result

    # ==========================================
    # Skill 元数据操作（存储在 __meta__ 文档中）
    # ==========================================

    async def get_skill_meta(self, skill_name: str, user_id: str) -> Optional[SkillMeta]:
        """获取 skill 元数据（从 __meta__ 文档）"""
        collection = self._get_files_collection()
        doc = await collection.find_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"}
        )
        if not doc:
            return None
        try:
            data = await run_blocking_io(json.loads, doc["content"])
            return SkillMeta(**data)
        except Exception:
            return None

    async def set_skill_meta(
        self,
        skill_name: str,
        user_id: str,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
        published_marketplace_name: Optional[str] = None,
    ) -> None:
        """设置 skill 元数据（存储为 __meta__ 文档）"""
        collection = self._get_files_collection()
        now = utc_now_iso()
        meta = SkillMeta(
            installed_from=installed_from,
            published_marketplace_name=published_marketplace_name,
            created_at=now,
            updated_at=now,
        )
        content = await run_blocking_io(json.dumps, meta.model_dump())
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"},
            {
                "$set": {"content": content, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def delete_skill_meta(self, skill_name: str, user_id: str) -> None:
        """删除 skill __meta__ 文档"""
        collection = self._get_files_collection()
        await collection.delete_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"}
        )

    async def delete_skill_and_meta(self, skill_name: str, user_id: str) -> None:
        """删除 Skill 所有文件（包括 __meta__ 和 S3 二进制文件）"""
        collection = self._get_files_collection()

        # 先收集所有二进制引用，清理 S3
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"content": 1},
        ):
            binary_ref = await parse_binary_ref_async(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)

        await collection.delete_many({"skill_name": skill_name, "user_id": user_id})

    # ==========================================
    # 生效 Skills（供 DeepAgent 使用）
    # ==========================================

    async def get_effective_skills(
        self, user_id: str, disabled_skills: Optional[list[str]] = None
    ) -> dict[str, dict[str, Any]]:
        """
        获取用户生效的 Skills（已启用 + 有文件）

        Args:
            user_id: 用户 ID
            disabled_skills: 从用户 metadata 中获取的 disabled_skills 列表

        Returns:
            {
                "skills": {
                    "skill_name": {
                        "files": {file_path: content},
                        "enabled": True,
                    }
                }
            }
        """
        from src.infra.skill.constants import SKILLS_CACHE_KEY_PREFIX, SKILLS_CACHE_TTL

        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"

        # 尝试从 Redis 缓存获取
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            cached = await redis_client.get(cache_key)
            if cached:
                return await run_blocking_io(json.loads, cached)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis get failed: {e}")

        if disabled_skills is None:
            disabled_skills = await self._get_user_disabled_skills(user_id)
        disabled_skills = normalize_skill_name_list(disabled_skills)

        enabled_names = await self.get_all_user_skill_names(
            user_id,
            exclude_skill_names=disabled_skills,
            limit=SKILL_EFFECTIVE_LOAD_LIMIT,
        )

        if not enabled_names:
            return {"skills": {}}

        # 批量获取文件
        skill_keys = [(name, user_id) for name in enabled_names]
        files_map = await self.batch_get_skill_files(skill_keys)

        result: dict[str, Any] = {"skills": {}}
        for name in enabled_names:
            files = files_map.get((name, user_id), {})
            if files:  # 只包含有文件的 skill
                # 从 SKILL.md frontmatter 解析 description
                description = ""
                if "SKILL.md" in files:
                    try:
                        _, parsed_desc, _ = await _parse_skill_md_offload(files["SKILL.md"])
                        if parsed_desc:
                            description = parsed_desc
                    except Exception:
                        pass

                result["skills"][name] = {
                    "name": name,
                    "description": description or f"Skill: {name}",
                    "files": files,
                    "enabled": True,
                }

        # 缓存
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()

            serialized = await run_blocking_io(json.dumps, result)
            await redis_client.set(cache_key, serialized, ex=SKILLS_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis set failed: {e}")

        return result

    async def _get_user_disabled_skills(self, user_id: str) -> list[str]:
        """Load disabled skills from user metadata for cache-safe default behavior."""
        try:
            from src.infra.user.storage import UserStorage

            user_storage = UserStorage()
            user_doc = await user_storage.get_by_id(user_id)
            if user_doc and user_doc.metadata:
                return normalize_skill_name_list(user_doc.metadata.get("disabled_skills", []))
        except Exception as e:
            logger.warning(f"Failed to load disabled_skills for user {user_id}: {e}")
        return []

    async def get_all_user_skill_names(
        self,
        user_id: str,
        exclude_skill_names: Optional[list[str]] = None,
        limit: Optional[int] = None,
    ) -> list[str]:
        """获取用户所有 skill 名称（无论 enabled/disabled，排除 __meta__）"""
        collection = self._get_files_collection()
        match: dict[str, Any] = {"user_id": user_id, "file_path": {"$ne": "__meta__"}}
        excluded = normalize_skill_name_list(exclude_skill_names or [])
        if excluded:
            match["skill_name"] = {"$nin": excluded}
        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {"$group": {"_id": "$skill_name"}},
        ]
        effective_limit = SKILL_EFFECTIVE_LOAD_LIMIT if limit is None else limit
        bounded_limit = max(0, min(int(effective_limit), SKILL_EFFECTIVE_LOAD_LIMIT))
        pipeline.extend([{"$sort": {"_id": 1}}, {"$limit": bounded_limit}])
        return [doc["_id"] async for doc in collection.aggregate(pipeline)]

    async def invalidate_user_cache(self, user_id: str) -> None:
        """失效用户缓存"""
        from src.infra.skill.constants import SKILLS_CACHE_KEY_PREFIX

        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            await redis_client.delete(cache_key)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis delete failed: {e}")

    async def create_user_skill(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: str,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
        enabled: bool = True,
        binary_files: Optional[dict[str, bytes]] = None,
    ) -> None:
        """
        Create a complete user skill: sync files + upload binaries + create __meta__ + invalidate cache.

        This is the single entry point for all skill creation paths:
        - MarketplacePanel direct create (installed_from=MARKETPLACE)
        - SkillsPanel manual create (installed_from=MANUAL)
        - GitHub import (installed_from=MANUAL)
        - ZIP upload (installed_from=MANUAL)

        Args:
            files: 文本文件 {file_path: text_content}
            binary_files: 二进制文件 {file_path: binary_data}，上传到 S3/local
            user_id: 用户 ID
            skill_name: Skill 名称
            installed_from: 安装来源
            enabled: 是否启用

        Note: The `enabled` parameter is kept for API compatibility but the actual
        enabled/disabled state is managed in user.metadata.disabled_skills.
        """
        if not files and not binary_files:
            raise ValueError("Skill must have at least one file")

        files = normalize_skill_files(files)
        await self.sync_skill_files(skill_name, files, user_id)

        # 上传二进制文件
        if binary_files:
            for file_path, data in binary_files.items():
                await self.set_skill_binary_file(skill_name, file_path, data, user_id)

        await self.set_skill_meta(skill_name, user_id, installed_from=installed_from)
        await self.invalidate_user_cache(user_id)

    async def close(self):
        """关闭连接（仅清理本地引用，不关闭全局 MongoDB 客户端）"""
        self._client = None
        self._files_collection = None
