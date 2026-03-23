# Skills 架构升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Skills 系统重构为「商城 + 用户 Skills」架构，管理员可上传管理商城 Skill，用户可浏览安装。

**Architecture:** 4 张 MongoDB 表（skill_marketplace, skill_marketplace_files, skill_files, skill_toggles），文件存储与元数据分离，沙箱写入无需注册。

**Tech Stack:** FastAPI, MongoDB (Motor), Redis, Pydantic

---

## 阶段概览

| 阶段 | 内容 | 涉及文件 |
|------|------|----------|
| 1 | 新建常量和类型定义 | constants.py, types.py |
| 2 | 新建 toggles.py, marketplace.py | toggles.py, marketplace.py |
| 3 | 重写 storage.py | storage.py |
| 4 | 新建 API routes | marketplace.py (user), admin/marketplace.py |
| 5 | 重写 skills.py | skills.py |
| 6 | 重写 skills_store.py | skills_store.py |
| 7 | 改写 loader/middleware/manager | loader.py, middleware.py, manager.py |
| 8 | 迁移脚本 | migration.py |

---

## Task 1: 常量和类型定义

**Files:**
- Modify: `src/infra/skill/constants.py`
- Create: `src/infra/skill/types.py`

---

- [ ] **Step 1: 修改 constants.py - 新增 collection 名称**

```python
# src/infra/skill/constants.py

# MongoDB collection names
SKILL_FILES_COLLECTION = "skill_files"              # 用户文件（保持不变）
SKILL_MARKETPLACE_COLLECTION = "skill_marketplace"  # 新增
SKILL_MARKETPLACE_FILES_COLLECTION = "skill_marketplace_files"  # 新增
SKILL_TOGGLES_COLLECTION = "skill_toggles"          # 新增

# Redis cache
SKILLS_CACHE_KEY_PREFIX = "user_skills:"
SKILLS_CACHE_TTL = 1800  # 30 minutes
```

- [ ] **Step 2: 创建 types.py - 类型定义**

```python
# src/infra/skill/types.py
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class InstalledFrom(str, Enum):
    """Skill 安装来源"""
    MARKETPLACE = "marketplace"
    MANUAL = "manual"


class MarketplaceSkill(BaseModel):
    """商城 Skill 元数据"""
    skill_name: str = Field(..., description="Skill 名称（唯一标识）")
    description: str = Field("", description="Skill 描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    version: str = Field("1.0.0", description="版本号")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None


class MarketplaceSkillCreate(BaseModel):
    """创建商城 Skill 请求"""
    skill_name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="Skill 描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    version: str = Field("1.0.0", description="版本号")


class MarketplaceSkillUpdate(BaseModel):
    """更新商城 Skill 请求"""
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    version: Optional[str] = None


class SkillToggle(BaseModel):
    """用户 Skill 开关"""
    skill_name: str
    user_id: str
    enabled: bool = True
    installed_from: InstalledFrom = InstalledFrom.MANUAL
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillFile(BaseModel):
    """Skill 文件"""
    skill_name: str
    user_id: str
    file_path: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserSkill(BaseModel):
    """用户 Skill 响应"""
    skill_name: str
    description: str = ""
    files: list[str] = Field(default_factory=list, description="文件路径列表")
    enabled: bool = True
    installed_from: Optional[str] = None
    file_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MarketplaceSkillResponse(BaseModel):
    """商城 Skill 响应"""
    skill_name: str
    description: str
    tags: list[str]
    version: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    file_count: int = 0  # 文件数量
```

---

## Task 2: toggles.py 和 marketplace.py

**Files:**
- Create: `src/infra/skill/toggles.py`
- Create: `src/infra/skill/marketplace.py`

---

### Task 2a: toggles.py - 用户开关管理

**Files:**
- Create: `src/infra/skill/toggles.py`

---

- [ ] **Step 1: 创建 toggles.py - 用户开关管理**

```python
# src/infra/skill/toggles.py
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from src.infra.logging import get_logger
from src.infra.skill.constants import SKILL_TOGGLES_COLLECTION
from src.infra.skill.types import InstalledFrom, SkillToggle
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)


class TogglesStorage:
    """用户 Skill 开关存储"""

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._collection: Optional["AsyncIOMotorCollection"] = None

    def _get_collection(self) -> "AsyncIOMotorCollection":
        if self._collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._collection = db[SKILL_TOGGLES_COLLECTION]
        return self._collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        collection = self._get_collection()
        await collection.create_index(
            [("skill_name", 1), ("user_id", 1)],
            unique=True,
            background=True,
        )

    async def get_toggle(
        self, skill_name: str, user_id: str
    ) -> Optional[SkillToggle]:
        """获取用户的某个 Skill 开关状态"""
        collection = self._get_collection()
        doc = await collection.find_one({
            "skill_name": skill_name,
            "user_id": user_id
        })
        if not doc:
            return None
        return SkillToggle(
            skill_name=doc["skill_name"],
            user_id=doc["user_id"],
            enabled=doc.get("enabled", True),
            installed_from=InstalledFrom(doc.get("installed_from", "manual")),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def list_user_toggles(self, user_id: str) -> list[SkillToggle]:
        """列出用户的所有开关"""
        collection = self._get_collection()
        toggles = []
        async for doc in collection.find({"user_id": user_id}):
            toggles.append(SkillToggle(
                skill_name=doc["skill_name"],
                user_id=doc["user_id"],
                enabled=doc.get("enabled", True),
                installed_from=InstalledFrom(doc.get("installed_from", "manual")),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
            ))
        return toggles

    async def list_enabled_skills(self, user_id: str) -> list[str]:
        """列出用户所有 enabled=True 的 skill_names"""
        collection = self._get_collection()
        names = []
        async for doc in collection.find({
            "user_id": user_id,
            "enabled": True
        }):
            names.append(doc["skill_name"])
        return names

    async def create_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
    ) -> SkillToggle:
        """创建开关记录"""
        collection = self._get_collection()
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "skill_name": skill_name,
            "user_id": user_id,
            "enabled": enabled,
            "installed_from": installed_from.value,
            "created_at": now,
            "updated_at": now,
        }
        await collection.insert_one(doc)
        return SkillToggle(
            skill_name=skill_name,
            user_id=user_id,
            enabled=enabled,
            installed_from=installed_from,
            created_at=now,
            updated_at=now,
        )

    async def upsert_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: Optional[InstalledFrom] = None,
    ) -> SkillToggle:
        """Upsert 开关记录（存在则更新，不存在则创建）"""
        collection = self._get_collection()
        now = datetime.now(timezone.utc).isoformat()

        existing = await collection.find_one({
            "skill_name": skill_name,
            "user_id": user_id
        })

        update_data = {
            "enabled": enabled,
            "updated_at": now,
        }
        if installed_from:
            update_data["installed_from"] = installed_from.value

        if existing:
            await collection.update_one(
                {"skill_name": skill_name, "user_id": user_id},
                {"$set": update_data}
            )
        else:
            update_data["skill_name"] = skill_name
            update_data["user_id"] = user_id
            update_data["installed_from"] = (installed_from or InstalledFrom.MANUAL).value
            update_data["created_at"] = now
            await collection.insert_one(update_data)

        return SkillToggle(
            skill_name=skill_name,
            user_id=user_id,
            enabled=enabled,
            installed_from=installed_from or InstalledFrom.MANUAL,
            created_at=existing.get("created_at") if existing else now,
            updated_at=now,
        )

    async def toggle_skill(self, skill_name: str, user_id: str) -> Optional[SkillToggle]:
        """切换开关状态"""
        existing = await self.get_toggle(skill_name, user_id)
        if not existing:
            return None
        new_enabled = not existing.enabled
        return await self.upsert_toggle(skill_name, user_id, enabled=new_enabled)

    async def delete_toggle(self, skill_name: str, user_id: str) -> bool:
        """删除开关记录"""
        collection = self._get_collection()
        result = await collection.delete_one({
            "skill_name": skill_name,
            "user_id": user_id
        })
        return result.deleted_count > 0

    async def delete_user_toggles(self, user_id: str, skill_name: str) -> int:
        """删除用户某个 Skill 的开关记录"""
        collection = self._get_collection()
        result = await collection.delete_many({
            "user_id": user_id,
            "skill_name": skill_name
        })
        return result.deleted_count

    async def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None
```

---

### Task 2b: marketplace.py - 商城逻辑

**Files:**
- Create: `src/infra/skill/marketplace.py`

---

- [ ] **Step 1: 创建 marketplace.py - 商城逻辑**

```python
# src/infra/skill/marketplace.py
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, Any

import yaml

from src.infra.logging import get_logger
from src.infra.skill.constants import (
    SKILL_MARKETPLACE_COLLECTION,
    SKILL_MARKETPLACE_FILES_COLLECTION,
)
from src.infra.skill.types import (
    MarketplaceSkill,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
    MarketplaceSkillUpdate,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10MB


if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class MarketplaceStorage:
    """商城 Skill 存储"""

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._meta_collection: Optional["AsyncIOMotorCollection"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None

    def _get_meta_collection(self) -> "AsyncIOMotorCollection":
        if self._meta_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._meta_collection = db[SKILL_MARKETPLACE_COLLECTION]
        return self._meta_collection

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_MARKETPLACE_FILES_COLLECTION]
        return self._files_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        meta = self._get_meta_collection()
        await meta.create_index("skill_name", unique=True, background=True)

        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 元数据操作
    # ==========================================

    async def list_marketplace_skills(
        self, tags: Optional[list[str]] = None, search: Optional[str] = None
    ) -> list[MarketplaceSkillResponse]:
        """列出所有商城 Skills（可选按标签筛选/搜索）"""
        collection = self._get_meta_collection()

        query: dict[str, Any] = {}
        if tags:
            query["tags"] = {"$in": tags}
        if search:
            query["$or"] = [
                {"skill_name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]

        files_collection = self._get_files_collection()
        results = []
        async for doc in collection.find(query):
            # 统计文件数量
            file_count = await files_collection.count_documents({
                "skill_name": doc["skill_name"]
            })
            results.append(MarketplaceSkillResponse(
                skill_name=doc["skill_name"],
                description=doc.get("description", ""),
                tags=doc.get("tags", []),
                version=doc.get("version", "1.0.0"),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
                created_by=doc.get("created_by"),
                file_count=file_count,
            ))
        return results

    async def get_marketplace_skill(self, skill_name: str) -> Optional[MarketplaceSkill]:
        """获取商城 Skill 元数据"""
        collection = self._get_meta_collection()
        doc = await collection.find_one({"skill_name": skill_name})
        if not doc:
            return None
        return MarketplaceSkill(
            skill_name=doc["skill_name"],
            description=doc.get("description", ""),
            tags=doc.get("tags", []),
            version=doc.get("version", "1.0.0"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            created_by=doc.get("created_by"),
        )

    async def get_marketplace_skill_response(
        self, skill_name: str
    ) -> Optional[MarketplaceSkillResponse]:
        """获取商城 Skill 响应（含文件数量）"""
        skill = await self.get_marketplace_skill(skill_name)
        if not skill:
            return None
        files_collection = self._get_files_collection()
        file_count = await files_collection.count_documents({
            "skill_name": skill_name
        })
        return MarketplaceSkillResponse(
            skill_name=skill.skill_name,
            description=skill.description,
            tags=skill.tags,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=skill.created_by,
            file_count=file_count,
        )

    async def create_marketplace_skill(
        self, data: MarketplaceSkillCreate, admin_user_id: str
    ) -> MarketplaceSkill:
        """创建商城 Skill 元数据"""
        collection = self._get_meta_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 检查是否已存在
        existing = await collection.find_one({"skill_name": data.skill_name})
        if existing:
            raise ValueError(f"Marketplace skill '{data.skill_name}' already exists")

        doc = {
            "skill_name": data.skill_name,
            "description": data.description,
            "tags": data.tags,
            "version": data.version,
            "created_at": now,
            "updated_at": now,
            "created_by": admin_user_id,
        }
        await collection.insert_one(doc)
        return MarketplaceSkill(**doc)

    async def update_marketplace_skill(
        self, skill_name: str, data: MarketplaceSkillUpdate
    ) -> Optional[MarketplaceSkill]:
        """更新商城 Skill 元数据"""
        collection = self._get_meta_collection()

        existing = await collection.find_one({"skill_name": skill_name})
        if not existing:
            return None

        update_data: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if data.description is not None:
            update_data["description"] = data.description
        if data.tags is not None:
            update_data["tags"] = data.tags
        if data.version is not None:
            update_data["version"] = data.version

        await collection.update_one(
            {"skill_name": skill_name},
            {"$set": update_data}
        )

        updated = await collection.find_one({"skill_name": skill_name})
        return MarketplaceSkill(**updated) if updated else None

    async def delete_marketplace_skill(self, skill_name: str) -> bool:
        """删除商城 Skill 元数据和所有文件"""
        meta = self._get_meta_collection()
        files = self._get_files_collection()

        # 删除元数据
        meta_result = await meta.delete_one({"skill_name": skill_name})

        # 删除所有文件
        await files.delete_many({"skill_name": skill_name})

        return meta_result.deleted_count > 0

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_marketplace_files(
        self, skill_name: str
    ) -> dict[str, str]:
        """获取商城 Skill 所有文件"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        async for doc in collection.find({"skill_name": skill_name}):
            files[doc["file_path"]] = doc["content"]
        return files

    async def get_marketplace_file(
        self, skill_name: str, file_path: str
    ) -> Optional[str]:
        """获取商城 Skill 单个文件"""
        collection = self._get_files_collection()
        doc = await collection.find_one({
            "skill_name": skill_name,
            "file_path": file_path
        })
        return doc["content"] if doc else None

    async def set_marketplace_file(
        self, skill_name: str, file_path: str, content: str
    ) -> None:
        """设置商城 Skill 单个文件"""
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
        await collection.update_one(
            {"skill_name": skill_name, "file_path": file_path},
            {
                "$set": {
                    "content": content,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def sync_marketplace_files(
        self, skill_name: str, files: dict[str, str]
    ) -> None:
        """批量同步商城 Skill 文件"""
        if not files:
            return
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()

        from pymongo import DeleteOne, UpdateOne

        # 获取现有文件路径
        existing_paths = set()
        async for doc in collection.find(
            {"skill_name": skill_name}, {"file_path": 1}
        ):
            existing_paths.add(doc["file_path"])

        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        operations = []
        for path in removed_paths:
            operations.append(
                DeleteOne({"skill_name": skill_name, "file_path": path})
            )
        for file_path, content in files.items():
            operations.append(
                UpdateOne(
                    {"skill_name": skill_name, "file_path": file_path},
                    {
                        "$set": {"content": content, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            await collection.bulk_write(operations, ordered=True)

    async def list_marketplace_file_paths(self, skill_name: str) -> list[str]:
        """列出商城 Skill 所有文件路径"""
        collection = self._get_files_collection()
        paths = []
        async for doc in collection.find(
            {"skill_name": skill_name}, {"file_path": 1}
        ):
            paths.append(doc["file_path"])
        return paths

    # ==========================================
    # ZIP 上传
    # ==========================================

    async def upload_from_zip(
        self,
        skill_name: str,
        zip_content: bytes,
        admin_user_id: str,
    ) -> MarketplaceSkill:
        """从 ZIP 上传商城 Skill 文件"""
        if len(zip_content) > MAX_ZIP_SIZE:
            raise ValueError("ZIP file too large (max 10MB)")

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_content))
        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file")

        try:
            files = self._parse_zip(zf)

            # 确保 Skill 存在
            skill = await self.get_marketplace_skill(skill_name)
            if not skill:
                skill = await self.create_marketplace_skill(
                    MarketplaceSkillCreate(skill_name=skill_name),
                    admin_user_id,
                )

            # 同步文件
            await self.sync_marketplace_files(skill_name, files)

            return skill
        finally:
            zf.close()

    def _parse_zip(self, zf: zipfile.ZipFile) -> dict[str, str]:
        """解析 ZIP 文件"""
        all_files: dict[str, str] = {}

        names = zf.namelist()
        top_level = set()
        for n in names:
            parts = n.split("/")
            if parts[0]:
                top_level.add(parts[0])

        prefix = ""
        if len(top_level) == 1:
            top = list(top_level)[0]
            is_dir = any(n.startswith(top + "/") for n in names)
            if is_dir:
                prefix = top + "/"

        for name in names:
            if (
                name.endswith("/")
                or "__MACOSX" in name
                or name.endswith(".DS_Store")
                or name.endswith("Thumbs.db")
                or ".git/" in name
            ):
                continue
            if name.startswith(prefix):
                rel_path = name[len(prefix):]
            else:
                rel_path = name
            if not rel_path:
                continue

            try:
                raw = zf.read(name)
            except Exception:
                continue

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            all_files[rel_path] = text

        return all_files

    # ==========================================
    # 标签操作
    # ==========================================

    async def list_all_tags(self) -> list[str]:
        """获取所有不重复的标签"""
        collection = self._get_meta_collection()
        tags = set()
        async for doc in collection.find({}, {"tags": 1}):
            for tag in doc.get("tags", []):
                tags.add(tag)
        return sorted(list(tags))

    async def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._meta_collection = None
            self._files_collection = None
```

---

## Task 3: 重写 storage.py

**Files:**
- Modify: `src/infra/skill/storage.py`

---

- [ ] **Step 1: 重写 storage.py - 简化存储层**

```python
# src/infra/skill/storage.py
"""
Skill 存储层 - 简化架构

3 张核心表：
- skill_files: 用户文件存储
- skill_toggles: 用户开关
- skill_marketplace / skill_marketplace_files: 商城（见 marketplace.py）
"""

from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, Any

from src.infra.logging import get_logger
from src.infra.skill.constants import (
    SKILL_FILES_COLLECTION,
    SKILL_TOGGLES_COLLECTION,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.infra.skill.types import SkillToggle, InstalledFrom

logger = get_logger(__name__)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class SkillStorage:
    """
    用户 Skill 文件存储

    提供文件级别的 CRUD 操作，不管理元数据。
    """

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None
        self._toggles_collection: Optional["AsyncIOMotorCollection"] = None

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_FILES_COLLECTION]
        return self._files_collection

    def _get_toggles_collection(self) -> "AsyncIOMotorCollection":
        if self._toggles_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._toggles_collection = db[SKILL_TOGGLES_COLLECTION]
        return self._toggles_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("user_id", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

        toggles = self._get_toggles_collection()
        await toggles.create_index(
            [("skill_name", 1), ("user_id", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_skill_files(
        self, skill_name: str, user_id: str
    ) -> dict[str, str]:
        """获取用户某个 Skill 的所有文件"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id}
        ):
            files[doc["file_path"]] = doc["content"]
        return files

    async def get_skill_file(
        self, skill_name: str, file_path: str, user_id: str
    ) -> Optional[str]:
        """获取用户某个 Skill 的单个文件"""
        collection = self._get_files_collection()
        doc = await collection.find_one({
            "skill_name": skill_name,
            "user_id": user_id,
            "file_path": file_path,
        })
        return doc["content"] if doc else None

    async def set_skill_file(
        self, skill_name: str, file_path: str, content: str, user_id: str
    ) -> None:
        """原子 upsert 单个文件"""
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
            {
                "$set": {"content": content, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def delete_skill_file(
        self, skill_name: str, file_path: str, user_id: str
    ) -> None:
        """删除单个文件"""
        collection = self._get_files_collection()
        await collection.delete_one({
            "skill_name": skill_name,
            "user_id": user_id,
            "file_path": file_path,
        })

    async def sync_skill_files(
        self, skill_name: str, files: dict[str, str], user_id: str
    ) -> None:
        """批量同步文件（替换所有）"""
        if not files:
            return
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 获取现有文件路径
        existing_paths = set()
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id},
            {"file_path": 1}
        ):
            existing_paths.add(doc["file_path"])

        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        from pymongo import DeleteOne, UpdateOne

        operations = []
        for path in removed_paths:
            operations.append(
                DeleteOne({
                    "skill_name": skill_name,
                    "user_id": user_id,
                    "file_path": path,
                })
            )
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

    async def delete_skill_files(self, skill_name: str, user_id: str) -> None:
        """删除用户某个 Skill 的所有文件"""
        collection = self._get_files_collection()
        await collection.delete_many({
            "skill_name": skill_name,
            "user_id": user_id,
        })

    async def list_skill_file_paths(
        self, skill_name: str, user_id: str
    ) -> list[str]:
        """列出用户某个 Skill 的所有文件路径"""
        collection = self._get_files_collection()
        paths = []
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id},
            {"file_path": 1}
        ):
            paths.append(doc["file_path"])
        return paths

    async def list_user_skills(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户所有 Skill（带文件信息）"""
        collection = self._get_files_collection()

        # 获取用户所有 skill_name（去重）
        skill_names: set[str] = set()
        async for doc in collection.find(
            {"user_id": user_id}, {"skill_name": 1}
        ):
            skill_names.add(doc["skill_name"])

        # 获取开关状态
        toggles_collection = self._get_toggles_collection()
        toggles: dict[str, bool] = {}
        async for doc in toggles_collection.find({"user_id": user_id}):
            toggles[doc["skill_name"]] = doc.get("enabled", True)

        # 组装结果
        result = []
        for skill_name in sorted(skill_names):
            file_count = await collection.count_documents({
                "skill_name": skill_name,
                "user_id": user_id,
            })
            # 获取最早创建时间和最新更新时间
            created_at = None
            updated_at = None
            async for doc in collection.find(
                {"skill_name": skill_name, "user_id": user_id}
            ):
                if not created_at or doc.get("created_at", "") < created_at:
                    created_at = doc.get("created_at")
                if not updated_at or doc.get("updated_at", "") > updated_at:
                    updated_at = doc.get("updated_at")

            toggle = await toggles_collection.find_one({
                "skill_name": skill_name,
                "user_id": user_id,
            })

            result.append({
                "skill_name": skill_name,
                "enabled": toggles.get(skill_name, True),
                "file_count": file_count,
                "installed_from": toggle.get("installed_from") if toggle else None,
                "created_at": created_at,
                "updated_at": updated_at,
            })

        return result

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

        result: dict[tuple[str, str], dict[str, str]] = {}
        async for doc in collection.find({"$or": or_clauses}):
            key = (doc["skill_name"], doc["user_id"])
            if key not in result:
                result[key] = {}
            result[key][doc["file_path"]] = doc["content"]

        return result

    # ==========================================
    # 开关操作
    # ==========================================

    async def get_toggle(
        self, skill_name: str, user_id: str
    ) -> Optional[SkillToggle]:
        """获取用户某个 Skill 的开关状态"""
        collection = self._get_toggles_collection()
        doc = await collection.find_one({
            "skill_name": skill_name,
            "user_id": user_id,
        })
        if not doc:
            return None
        return SkillToggle(
            skill_name=doc["skill_name"],
            user_id=doc["user_id"],
            enabled=doc.get("enabled", True),
            installed_from=InstalledFrom(doc.get("installed_from", "manual")),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def upsert_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: Optional[InstalledFrom] = None,
    ) -> SkillToggle:
        """Upsert 开关记录"""
        collection = self._get_toggles_collection()
        now = datetime.now(timezone.utc).isoformat()

        existing = await collection.find_one({
            "skill_name": skill_name,
            "user_id": user_id,
        })

        update_data = {
            "enabled": enabled,
            "updated_at": now,
        }
        if installed_from:
            update_data["installed_from"] = installed_from.value

        if existing:
            await collection.update_one(
                {"skill_name": skill_name, "user_id": user_id},
                {"$set": update_data}
            )
        else:
            update_data.update({
                "skill_name": skill_name,
                "user_id": user_id,
                "installed_from": (installed_from or InstalledFrom.MANUAL).value,
                "created_at": now,
            })
            await collection.insert_one(update_data)

        return SkillToggle(
            skill_name=skill_name,
            user_id=user_id,
            enabled=enabled,
            installed_from=installed_from or InstalledFrom.MANUAL,
            created_at=existing.get("created_at") if existing else now,
            updated_at=now,
        )

    async def toggle_skill(self, skill_name: str, user_id: str) -> Optional[SkillToggle]:
        """切换开关状态"""
        toggle = await self.get_toggle(skill_name, user_id)
        if not toggle:
            return None
        return await self.upsert_toggle(
            skill_name, user_id, enabled=not toggle.enabled
        )

    async def delete_toggle(self, skill_name: str, user_id: str) -> bool:
        """删除开关记录"""
        collection = self._get_toggles_collection()
        result = await collection.delete_one({
            "skill_name": skill_name,
            "user_id": user_id,
        })
        return result.deleted_count > 0

    # ==========================================
    # 生效 Skills（供 DeepAgent 使用）
    # ==========================================

    async def get_effective_skills(self, user_id: str) -> dict[str, dict[str, Any]]:
        """
        获取用户生效的 Skills（已启用 + 有文件）

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
                import json
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis get failed: {e}")

        # 从 MongoDB 加载
        enabled_names = await self._get_enabled_skill_names(user_id)
        if not enabled_names:
            return {"skills": {}}

        # 批量获取文件
        skill_keys = [(name, user_id) for name in enabled_names]
        files_map = await self.batch_get_skill_files(skill_keys)

        result = {"skills": {}}
        for name in enabled_names:
            files = files_map.get((name, user_id), {})
            if files:  # 只包含有文件的 skill
                result["skills"][name] = {
                    "files": files,
                    "enabled": True,
                }

        # 缓存
        try:
            from src.infra.storage.redis import get_redis_client
            redis_client = get_redis_client()
            import json
            await redis_client.set(cache_key, json.dumps(result), ex=SKILLS_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis set failed: {e}")

        return result

    async def _get_enabled_skill_names(self, user_id: str) -> list[str]:
        """获取用户已启用的 skill_names"""
        collection = self._get_toggles_collection()
        names = []
        async for doc in collection.find({
            "user_id": user_id,
            "enabled": True
        }):
            names.append(doc["skill_name"])
        return names

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

    async def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._files_collection = None
            self._toggles_collection = None
```

---

## Task 4: 用户 Skills API - skills.py

**Files:**
- Modify: `src/api/routes/skills.py`

---

- [ ] **Step 1: 重写 skills.py - 用户 Skills API**

```python
# src/api/routes/skills.py
"""
用户 Skills API

提供用户 Skills 的 CRUD 和 Toggle 操作。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.skill.storage import SkillStorage
from src.infra.skill.toggles import TogglesStorage
from src.infra.skill.types import UserSkill
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_storage() -> SkillStorage:
    return SkillStorage()


def get_toggles_storage() -> TogglesStorage:
    return TogglesStorage()


# ==========================================
# 用户 Skills API
# ==========================================


@router.get("/", response_model=list[UserSkill])
async def list_user_skills(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """列出用户安装的所有 Skills"""
    skills = await storage.list_user_skills(user.sub)
    return [
        UserSkill(
            skill_name=s["skill_name"],
            enabled=s["enabled"],
            file_count=s["file_count"],
            installed_from=s.get("installed_from"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
        )
        for s in skills
    ]


@router.get("/{name}", response_model=UserSkill)
async def get_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """获取用户某个 Skill 的详细信息"""
    skills = await storage.list_user_skills(user.sub)
    for s in skills:
        if s["skill_name"] == name:
            files = await storage.get_skill_files(name, user.sub)
            return UserSkill(
                skill_name=name,
                enabled=s["enabled"],
                files=list(files.keys()),
                file_count=s["file_count"],
                installed_from=s.get("installed_from"),
                created_at=s.get("created_at"),
                updated_at=s.get("updated_at"),
            )
    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


@router.get("/{name}/files/{path:path}")
async def get_skill_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    storage: SkillStorage = Depends(get_storage),
):
    """读取 Skill 的单个文件"""
    content = await storage.get_skill_file(name, path, user.sub)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content}


@router.put("/{name}/files/{path:path}")
async def update_skill_file(
    name: str,
    path: str,
    body: dict,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """更新 Skill 的单个文件"""
    content = body.get("content", "")
    await storage.set_skill_file(name, path, content, user.sub)

    # 确保开关记录存在（enabled=True）
    await storage.upsert_toggle(name, user.sub, enabled=True)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": "File updated"}


@router.delete("/{name}")
async def delete_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:delete")),
    storage: SkillStorage = Depends(get_storage),
):
    """删除（卸载）用户的 Skill"""
    # 删除所有文件
    await storage.delete_skill_files(name, user.sub)

    # 删除开关记录
    await storage.delete_toggle(name, user.sub)

    # 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {"message": f"Skill '{name}' deleted"}


@router.patch("/{name}/toggle")
async def toggle_user_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    storage: SkillStorage = Depends(get_storage),
):
    """切换 Skill 的启用状态"""
    toggle = await storage.toggle_skill(name, user.sub)
    if not toggle:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    await storage.invalidate_user_cache(user.sub)

    status = "enabled" if toggle.enabled else "disabled"
    return {"skill_name": name, "enabled": toggle.enabled, "message": f"Skill '{name}' is now {status}"}
```

---

## Task 5: 用户商城 API - marketplace.py

**Files:**
- Create: `src/api/routes/marketplace.py`

---

- [ ] **Step 1: 创建 marketplace.py - 用户商城 API**

```python
# src/api/routes/marketplace.py
"""
用户商城 API

提供商城浏览和安装功能。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_permissions
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import MarketplaceSkillResponse, InstalledFrom
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


def get_storage() -> SkillStorage:
    return SkillStorage()


# ==========================================
# 用户商城 API
# ==========================================


@router.get("/", response_model=list[MarketplaceSkillResponse])
async def list_marketplace_skills(
    tags: Optional[str] = None,
    search: Optional[str] = None,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出所有商城 Skills（可选按标签筛选/搜索）"""
    tag_list = tags.split(",") if tags else None
    skills = await marketplace.list_marketplace_skills(
        tags=tag_list, search=search
    )
    return skills


@router.get("/tags")
async def list_tags(
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取所有标签"""
    tags = await marketplace.list_all_tags()
    return {"tags": tags}


@router.get("/{name}")
async def get_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """预览商城 Skill"""
    skill = await marketplace.get_marketplace_skill_response(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return skill


@router.get("/{name}/files/{path:path}")
async def get_marketplace_file(
    name: str,
    path: str,
    user: TokenPayload = Depends(require_permissions("skill:read")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """读取商城 Skill 的单个文件"""
    content = await marketplace.get_marketplace_file(name, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content}


@router.post("/{name}/install")
async def install_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """安装商城 Skill 到用户目录"""
    # 1. 检查商城 Skill 是否存在
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")

    # 2. 检查用户是否已安装
    existing_toggle = await storage.get_toggle(name, user.sub)
    if existing_toggle:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{name}' already installed"
        )

    # 3. 获取商城文件并复制到用户目录
    marketplace_files = await marketplace.get_marketplace_files(name)
    if marketplace_files:
        await storage.sync_skill_files(name, marketplace_files, user.sub)

    # 4. 创建开关记录
    await storage.upsert_toggle(
        name, user.sub,
        enabled=True,
        installed_from=InstalledFrom.MARKETPLACE,
    )

    # 5. 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{name}' installed successfully",
        "skill_name": name,
        "file_count": len(marketplace_files),
    }


@router.post("/{name}/update")
async def update_from_marketplace(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:write")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
    storage: SkillStorage = Depends(get_storage),
):
    """从商城更新用户的 Skill（覆盖）"""
    # 1. 检查商城 Skill 是否存在
    marketplace_skill = await marketplace.get_marketplace_skill(name)
    if not marketplace_skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")

    # 2. 检查用户是否安装过
    toggle = await storage.get_toggle(name, user.sub)
    if not toggle:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{name}' not installed. Install it first."
        )

    # 3. 获取商城文件并覆盖用户文件
    marketplace_files = await marketplace.get_marketplace_files(name)
    await storage.sync_skill_files(name, marketplace_files, user.sub)

    # 4. 失效缓存
    await storage.invalidate_user_cache(user.sub)

    return {
        "message": f"Skill '{name}' updated from marketplace",
        "skill_name": name,
        "file_count": len(marketplace_files),
    }
```

---

## Task 6: 管理员商城 API

**Files:**
- Create: `src/api/routes/admin/marketplace.py`

---

- [ ] **Step 1: 创建 admin/marketplace.py - 管理员商城 API**

```python
# src/api/routes/admin/marketplace.py
"""
管理员商城 API

提供商城 Skill 的管理功能（上传/编辑/删除）。
"""

import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.api.deps import require_permissions
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.types import MarketplaceSkillCreate, MarketplaceSkillResponse, MarketplaceSkillUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter(prefix="/admin/marketplace")


def get_marketplace_storage() -> MarketplaceStorage:
    return MarketplaceStorage()


def _is_admin(user: TokenPayload) -> bool:
    return "skill:admin" in (user.permissions or [])


# ==========================================
# 管理员商城 API
# ==========================================


@router.get("/", response_model=list[MarketplaceSkillResponse])
async def admin_list_marketplace_skills(
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """列出所有商城 Skills"""
    return await marketplace.list_marketplace_skills()


@router.post("/", response_model=MarketplaceSkillResponse, status_code=201)
async def admin_create_marketplace_skill(
    data: MarketplaceSkillCreate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """创建商城 Skill 元数据"""
    try:
        skill = await marketplace.create_marketplace_skill(data, user.sub)
        return MarketplaceSkillResponse(
            skill_name=skill.skill_name,
            description=skill.description,
            tags=skill.tags,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=skill.created_by,
            file_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}", response_model=MarketplaceSkillResponse)
async def admin_get_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """获取商城 Skill 详情"""
    skill = await marketplace.get_marketplace_skill_response(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return skill


@router.put("/{name}", response_model=MarketplaceSkillResponse)
async def admin_update_marketplace_skill(
    name: str,
    data: MarketplaceSkillUpdate,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """更新商城 Skill 元数据"""
    skill = await marketplace.update_marketplace_skill(name, data)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")

    response = await marketplace.get_marketplace_skill_response(name)
    return response


@router.delete("/{name}")
async def admin_delete_marketplace_skill(
    name: str,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """删除商城 Skill（元数据和文件）"""
    deleted = await marketplace.delete_marketplace_skill(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Marketplace skill '{name}' not found")
    return {"message": f"Marketplace skill '{name}' deleted"}


@router.post("/{name}/upload", response_model=MarketplaceSkillResponse)
async def admin_upload_skill_files(
    name: str,
    file: UploadFile,
    user: TokenPayload = Depends(require_permissions("skill:admin")),
    marketplace: MarketplaceStorage = Depends(get_marketplace_storage),
):
    """上传 Skill 文件（ZIP）"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    try:
        content = await file.read()
        await marketplace.upload_from_zip(name, content, user.sub)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response = await marketplace.get_marketplace_skill_response(name)
    return response
```

---

## Task 7: 重写 skills_store.py

**Files:**
- Modify: `src/infra/backend/skills_store.py`

---

- [ ] **Step 1: 重写 skills_store.py - 适配新架构**

需要修改的关键方法：

### 7.1 修改 `__init__` 和 `_get_storage`

```python
# 修改 __init__ 方法（保持原有签名）
# self._storage 改为 SkillStorage，不再需要 MarketplaceStorage

async def _get_storage(self) -> SkillStorage:
    """获取 SkillStorage 实例"""
    if self._storage is None:
        self._storage = SkillStorage()
    return self._storage
```

### 7.2 修改 `awrite` 方法（核心改动）

```python
async def awrite(self, file_path: str, content: str) -> WriteResult:
    """异步写入 skill 文件（无需注册）"""
    file_path = self._normalize_path(file_path)
    parsed = self._parse_skill_path(file_path)
    if not parsed:
        return WriteResult(error=f"Invalid skills path: {file_path}")

    skill_name, file_name = parsed
    storage = await self._get_storage()

    try:
        # 直接 upsert 文件（user_id = 当前用户）
        await storage.set_skill_file(skill_name, file_name, content, self._user_id)

        # 确保开关记录存在（enabled=True）
        await storage.upsert_toggle(skill_name, self._user_id, enabled=True)

        # 失效缓存
        await storage.invalidate_user_cache(self._user_id)

        # 发送变更事件
        if self._runtime:
            presenter = (
                self._runtime.config.get("configurable", {}).get("presenter")
                if hasattr(self._runtime, "config")
                else None
            )
            if presenter:
                await presenter.emit_skills_changed(
                    action="updated",
                    skill_name=skill_name,
                    files_count=1,
                )

        return WriteResult(path=file_path, files_update=None)

    except Exception as e:
        logger.error(f"Failed to write {file_path}: {e}", exc_info=True)
        return WriteResult(error=str(e))
```

### 7.3 修改 `als_info` 方法

```python
async def als_info(self, path: str) -> list[FileInfo]:
    """列出 skills 或文件"""
    path = self._normalize_path(path)
    storage = await self._get_storage()

    try:
        # 列出所有 skills
        if self._is_skills_root(path):
            effective = await storage.get_effective_skills(self._user_id)
            skills = effective.get("skills", {})

            entries = []
            for skill_name in skills.keys():
                entries.append(FileInfo(
                    path=f"/{skill_name}/",
                    is_dir=True,
                ))
            return entries

        # 解析路径
        parsed = self._parse_skill_path(path)
        if not parsed:
            if self._is_skill_dir(path):
                skill_name = self._get_skill_name_from_dir(path)
                if skill_name:
                    paths = await storage.list_skill_file_paths(skill_name, self._user_id)
                    return self._build_file_list_from_paths(skill_name, "", paths)
            return []

        skill_name, sub_path = parsed
        sub_path = sub_path.rstrip("/")

        # 检查文件是否存在
        content = await storage.get_skill_file(skill_name, sub_path, self._user_id)
        if content is not None:
            return [FileInfo(
                path=f"/{skill_name}/{sub_path}",
                is_dir=False,
                size=len(content),
            )]

        # 列出目录
        paths = await storage.list_skill_file_paths(skill_name, self._user_id)
        return self._build_file_list_from_paths(skill_name, sub_path, paths)

    except Exception as e:
        logger.error(f"Failed to list {path}: {e}")
        return []
```

### 7.4 删除 `awrite` 中的商城相关逻辑

原有代码中有：
- 检查 system skill → 创建用户副本
- 检查 system skill → 复制文件

这些逻辑在新架构中不需要了，因为：
- 所有文件都在 `skill_files` 表（用户）
- 商城文件在 `skill_marketplace_files` 表
- 安装时由 API 层处理复制

---

## Task 8: 改写 loader.py, middleware.py, manager.py

**Files:**
- Modify: `src/infra/skill/loader.py`
- Modify: `src/infra/skill/middleware.py`
- Modify: `src/infra/skill/manager.py`

---

- [ ] **Step 1: 改写 loader.py**

```python
# src/infra/skill/loader.py
"""
Skills 加载模块

从数据库加载用户技能文件，供 DeepAgent 使用。
"""

from typing import Any, List, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)


async def load_skill_files(user_id: Optional[str]) -> dict[str, Any]:
    """
    从数据库加载用户的技能文件和技能列表

    Returns:
        {
            "files": {file_path: file_data},
            "skills": [skill_dict],
        }
    """
    result = {
        "files": {},
        "skills": [],
    }

    if not settings.ENABLE_SKILLS:
        return result

    try:
        from deepagents.backends.utils import create_file_data
        from src.infra.skill.storage import SkillStorage

        storage = SkillStorage()
        effective = await storage.get_effective_skills(user_id)
        skills = effective.get("skills", {})

        if not skills:
            return result

        logger.info(f"Loading {len(skills)} skills for user: {user_id or 'default'}")

        for skill_name, skill_data in skills.items():
            files = skill_data.get("files", {})

            if files:
                for file_name, file_content in files.items():
                    file_path = f"/{skill_name}/{file_name}"
                    result["files"][file_path] = create_file_data(file_content)
            else:
                # 兼容：无 files 的情况
                pass

            result["skills"].append({
                "name": skill_name,
                "enabled": skill_data.get("enabled", True),
            })

        logger.info(f"Prepared {len(result['files'])} skill files for prompt")

    except Exception as e:
        logger.warning(f"Failed to load skills: {e}")

    return result
```

- [ ] **Step 2: 改写 manager.py**

```python
# src/infra/skill/manager.py
"""
Skill 管理器

门面类，封装 SkillStorage 操作。
"""

from typing import Optional

from src.infra.skill.storage import SkillStorage
from src.kernel.config import settings


class SkillManager:
    """Skill 管理器"""

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.storage = SkillStorage() if settings.ENABLE_SKILLS else None

    async def list_skills_async(self) -> list[dict]:
        """列出所有可用技能"""
        if not self.user_id or not self.storage:
            return []
        try:
            skills = await self.storage.list_user_skills(self.user_id)
            return [
                {
                    "name": s["skill_name"],
                    "enabled": s["enabled"],
                    "file_count": s["file_count"],
                }
                for s in skills
            ]
        except Exception:
            return []

    async def get_skill_async(self, skill_name: str) -> Optional[dict]:
        """获取指定技能"""
        if not self.user_id or not self.storage:
            return None
        try:
            files = await self.storage.get_skill_files(skill_name, self.user_id)
            toggle = await self.storage.get_toggle(skill_name, self.user_id)
            if not files:
                return None
            return {
                "name": skill_name,
                "files": files,
                "enabled": toggle.enabled if toggle else True,
            }
        except Exception:
            return None

    async def get_effective_skills(self) -> dict:
        """获取生效的技能"""
        if not self.user_id or not self.storage:
            return {}
        try:
            result = await self.storage.get_effective_skills(self.user_id)
            return result.get("skills", {})
        except Exception:
            return {}
```

- [ ] **Step 3: 改写 middleware.py**

主要修改：
- `inject_skills_to_sandbox`: 使用新的 `SkillManager`
- `inject_single_skill_to_sandbox`: 使用新的 `SkillManager`
- `load_all_skills_async`: 使用新的 `SkillManager`

```python
# src/infra/skill/middleware.py
# 修改所有 self._manager 调用为新的 SkillManager
# 保持原有接口不变，内部实现适配新架构
```

---

## Task 9: 迁移脚本

**Files:**
- Create: `src/scripts/migrate_skills_to_marketplace.py`

---

- [ ] **Step 1: 创建迁移脚本**

```python
#!/usr/bin/env python3
"""
迁移脚本：将 system_skills 迁移到 skill_marketplace

用法：
    python -m src.scripts.migrate_skills_to_marketplace
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings


async def migrate():
    client = get_mongo_client()
    db = client[settings.MONGODB_DB]

    old_system = db["system_skills"]
    old_user = db["user_skills"]
    old_files = db["skill_files"]
    old_prefs = db["user_skill_preferences"]

    new_marketplace = db["skill_marketplace"]
    new_marketplace_files = db["skill_marketplace_files"]
    new_toggles = db["skill_toggles"]

    # 创建索引
    await new_marketplace.create_index("skill_name", unique=True, background=True)
    await new_marketplace_files.create_index(
        [("skill_name", 1), ("file_path", 1)], unique=True, background=True
    )
    await new_toggles.create_index(
        [("skill_name", 1), ("user_id", 1)], unique=True, background=True
    )
    print("Created indexes")

    migrated_count = 0

    # 迁移 system_skills -> skill_marketplace
    async for doc in old_system.find({}):
        skill_name = doc["name"]

        # 导入元数据
        await new_marketplace.update_one(
            {"skill_name": skill_name},
            {
                "$set": {
                    "description": doc.get("description", ""),
                    "tags": [],
                    "version": doc.get("version", "1.0.0"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "created_by": doc.get("updated_by", "system"),
                },
                "$setOnInsert": {
                    "skill_name": skill_name,
                },
            },
            upsert=True,
        )

        # 复制文件到 skill_marketplace_files
        async for file_doc in old_files.find({
            "skill_name": skill_name,
            "user_id": "system"
        }):
            await new_marketplace_files.update_one(
                {"skill_name": skill_name, "file_path": file_doc["file_path"]},
                {
                    "$set": {
                        "content": file_doc["content"],
                        "updated_at": file_doc.get("updated_at"),
                    },
                    "$setOnInsert": {
                        "created_at": file_doc.get("created_at"),
                    },
                },
                upsert=True,
            )

        migrated_count += 1
        print(f"Migrated marketplace skill: {skill_name}")

    print(f"\nMigrated {migrated_count} marketplace skills")

    # 迁移 user_skills -> skill_toggles
    migrated_users = set()
    async for doc in old_user.find({}):
        user_id = doc["user_id"]
        skill_name = doc["name"]
        enabled = doc.get("enabled", True)

        await new_toggles.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "installed_from": "manual",
                    "updated_at": doc.get("updated_at"),
                },
                "$setOnInsert": {
                    "created_at": doc.get("created_at"),
                },
            },
            upsert=True,
        )
        migrated_users.add(user_id)

    print(f"Migrated skills for {len(migrated_users)} users")

    # 迁移 user_skill_preferences -> skill_toggles
    async for doc in old_prefs.find({}):
        user_id = doc["user_id"]
        skill_name = doc["skill_name"]
        enabled = doc.get("enabled", True)

        await new_toggles.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "installed_from": "marketplace",
                    "updated_at": doc.get("updated_at"),
                },
                "$setOnInsert": {
                    "created_at": doc.get("created_at"),
                },
            },
            upsert=True,
        )

    print("Migrated user preferences")

    print("\nMigration complete!")
    print("Old collections can now be dropped:")
    print("  - system_skills")
    print("  - user_skills")
    print("  - user_skill_preferences")
    print("  - skill_files (user_id='system' records only)")


if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## Task 10: 更新 API 路由注册

**Files:**
- Modify: `src/api/main.py` 或路由注册文件

---

- [ ] **Step 1: 注册新路由**

在 API 路由注册处添加：

```python
# 用户商城 API
from src.api.routes.marketplace import router as marketplace_router
api_router.include_router(marketplace_router, prefix="/marketplace", tags=["marketplace"])

# 管理员商城 API
from src.api.routes.admin.marketplace import router as admin_marketplace_router
api_router.include_router(admin_marketplace_router, prefix="/api", tags=["admin:marketplace"])
```

---

## Task 11: 删除旧文件和更新 __init__.py

**Files:**
- Delete: `src/infra/skill/converters.py`
- Delete: `src/infra/skill/preferences.py`
- Delete: `src/infra/skill/import_export.py`
- Delete: `src/infra/skill/builtin.py`
- Modify: `src/infra/skill/__init__.py`

---

- [ ] **Step 1: 更新 __init__.py**

```python
# src/infra/skill/__init__.py
"""
Skills 管理模块
"""

from src.infra.skill.loader import load_skill_files
from src.infra.skill.manager import SkillManager
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.middleware import SkillsMiddleware
from src.infra.skill.storage import SkillStorage
from src.infra.skill.toggles import TogglesStorage

__all__ = [
    "SkillManager",
    "SkillsMiddleware",
    "SkillStorage",
    "MarketplaceStorage",
    "TogglesStorage",
    "load_skill_files",
]
```

---

## Task 12: 更新 schemas

**Files:**
- Modify: `src/kernel/schemas/skill.py`

---

- [ ] **Step 1: 简化 skill.py**

保留向后兼容的类型，删除不再需要的复杂 schema：

```python
# src/kernel/schemas/skill.py
"""
Skill schemas - 简化版（保留向后兼容）
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# 保留向后兼容
class SkillSource(str, Enum):
    BUILTIN = "builtin"
    GITHUB = "github"
    MANUAL = "manual"


# 保留基本响应类型（供 API 兼容使用）
class SkillResponse(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
```

---

## 验收标准

每个 Task 完成后应验证：
1. 代码无语法错误
2. MongoDB 索引创建成功
3. API 路由正确注册
4. 迁移脚本能正确运行
5. DeepAgent 能正常加载 skills

---

## 注意事项

1. **Task 顺序很重要**：按顺序执行，不要跳阶段
2. **迁移前备份**：运行迁移脚本前先备份数据库
3. **API 兼容**：保留原有 `/api/skills/` 路由的用户体验
4. **缓存失效**：所有写入操作后都要失效 Redis 缓存
