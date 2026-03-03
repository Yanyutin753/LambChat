"""
Skill storage using MongoDB with PostgreSQL file storage via agent_files

Supports both system-level and user-level skill configurations.
Skills are stored as metadata in MongoDB, file content in agent_files table with user_id.
Follows the same pattern as MCP storage for consistency.
"""

import copy
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.infra.storage.mongodb import get_mongo_client
from src.infra.storage.redis import get_redis_client
from src.kernel.config import settings
from src.kernel.schemas.skill import (
    GitHubInstallRequest,
    SkillCreate,
    SkillExportResponse,
    SkillImportRequest,
    SkillImportResponse,
    SkillResponse,
    SkillSource,
    SkillUpdate,
    SystemSkill,
    UserSkill,
)

logger = logging.getLogger(__name__)

# Redis 缓存 TTL（秒），默认 30 分钟
SKILLS_CACHE_TTL = 1800
MCP_TOOLS_METADATA_CACHE_TTL = 1800

# Redis 缓存键前缀
SKILLS_CACHE_KEY_PREFIX = "user_skills:"
MCP_TOOLS_METADATA_KEY_PREFIX = "mcp_tools_metadata:"


if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class SkillStorage:
    """
    Skill storage

    Supports system-level (admin managed) and user-level configurations.
    User preferences allow users to override enabled state of system skills.
    """

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._system_collection: Optional["AsyncIOMotorCollection"] = None
        self._user_collection: Optional["AsyncIOMotorCollection"] = None
        self._preferences_collection: Optional["AsyncIOMotorCollection"] = None

    # ==========================================
    # Redis Cache
    # ==========================================

    async def _invalidate_user_skills_cache(self, user_id: str) -> None:
        """Invalidate skills Redis cache for a specific user"""
        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"
        try:
            redis_client = get_redis_client()
            result = await redis_client.delete(cache_key)
            if result > 0:
                logger.info(f"[Skills Cache] Invalidated Redis cache for user {user_id}")
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis delete failed for user {user_id}: {e}")

    async def _invalidate_all_skills_cache(self) -> None:
        """Invalidate all skills Redis cache (system config changed)"""
        try:
            redis_client = get_redis_client()
            keys = await redis_client.keys(f"{SKILLS_CACHE_KEY_PREFIX}*")
            if keys:
                deleted = 0
                for key in keys:
                    if await redis_client.delete(key) > 0:
                        deleted += 1
                logger.info(f"[Skills Cache] Invalidated {deleted} Redis cache entries")
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis keys/delete failed: {e}")

    def _get_system_collection(self) -> "AsyncIOMotorCollection":
        """Get system skills collection lazily"""
        if self._system_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._system_collection = db["system_skills"]
        return self._system_collection

    def _get_user_collection(self) -> "AsyncIOMotorCollection":
        """Get user skills collection lazily"""
        if self._user_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._user_collection = db["user_skills"]
        return self._user_collection

    def _get_preferences_collection(self) -> "AsyncIOMotorCollection":
        """Get user skill preferences collection lazily"""
        if self._preferences_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._preferences_collection = db["user_skill_preferences"]
        return self._preferences_collection

    # ==========================================
    # System Skills (Admin)
    # ==========================================

    async def list_system_skills(self) -> list[SystemSkill]:
        """List all system skills"""
        collection = self._get_system_collection()
        skills = []
        async for doc in collection.find({}):
            skills.append(self._doc_to_system_skill(doc))
        return skills

    async def get_system_skill(self, name: str) -> Optional[SystemSkill]:
        """Get a system skill by name"""
        collection = self._get_system_collection()
        doc = await collection.find_one({"name": name})
        if doc:
            return self._doc_to_system_skill(doc)
        return None

    async def create_system_skill(self, skill: SkillCreate, admin_user_id: str) -> SystemSkill:
        """Create a system skill (admin only)"""
        collection = self._get_system_collection()

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "name": skill.name,
            "description": skill.description,
            "content": skill.content,
            "files": skill.files,
            "enabled": skill.enabled,
            "source": skill.source.value,
            "github_url": skill.github_url,
            "version": skill.version,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
            "updated_by": admin_user_id,
        }

        await collection.insert_one(doc)

        # Sync files to PostgreSQL with "system" user_id
        if skill.files:
            await self.sync_skill_files(skill.name, skill.files, user_id="system")
        elif skill.content:
            await self.sync_skill_files(skill.name, {"SKILL.md": skill.content}, user_id="system")

        # Invalidate all users' cache since system skill affects everyone
        await self._invalidate_all_skills_cache()

        return self._doc_to_system_skill(doc)

    async def update_system_skill(
        self, name: str, updates: SkillUpdate, admin_user_id: str
    ) -> Optional[SystemSkill]:
        """Update a system skill (admin only)"""
        collection = self._get_system_collection()

        doc = await collection.find_one({"name": name})
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": admin_user_id,
        }

        if updates.name is not None:
            update_data["name"] = updates.name
        if updates.description is not None:
            update_data["description"] = updates.description
        if updates.content is not None:
            update_data["content"] = updates.content
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled
        if updates.version is not None:
            update_data["version"] = updates.version
        if updates.files is not None:
            update_data["files"] = updates.files

        # If renaming, update by old name then find by new name
        query_name = name
        if updates.name and updates.name != name:
            await collection.update_one({"name": name}, {"$set": update_data})
            query_name = updates.name
        else:
            await collection.update_one({"name": name}, {"$set": update_data})

        updated_doc = await collection.find_one({"name": query_name})

        # Invalidate all users' cache since system skill affects everyone
        await self._invalidate_all_skills_cache()

        return self._doc_to_system_skill(updated_doc) if updated_doc else None

    async def delete_system_skill(self, name: str) -> bool:
        """Delete a system skill (admin only)"""
        collection = self._get_system_collection()
        result = await collection.delete_one({"name": name})

        # Delete files from PostgreSQL with "system" user_id
        if result.deleted_count > 0:
            await self.delete_skill_files(name, user_id="system")
            # Invalidate all users' cache since system skill affects everyone
            await self._invalidate_all_skills_cache()

        return result.deleted_count > 0

    # ==========================================
    # User Skills
    # ==========================================

    async def list_user_skills(self, user_id: str) -> list[UserSkill]:
        """List all skills for a specific user"""
        collection = self._get_user_collection()
        skills = []
        async for doc in collection.find({"user_id": user_id}):
            skills.append(self._doc_to_user_skill(doc))
        return skills

    async def get_user_skill(self, name: str, user_id: str) -> Optional[UserSkill]:
        """Get a user's skill by name"""
        collection = self._get_user_collection()
        doc = await collection.find_one({"name": name, "user_id": user_id})
        if doc:
            return self._doc_to_user_skill(doc)
        return None

    async def create_user_skill(self, skill: SkillCreate, user_id: str) -> UserSkill:
        """Create a user skill"""
        collection = self._get_user_collection()

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "name": skill.name,
            "description": skill.description,
            "content": skill.content,
            "files": skill.files,
            "enabled": skill.enabled,
            "source": skill.source.value,
            "github_url": skill.github_url,
            "version": skill.version,
            "user_id": user_id,
            "is_system": False,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)

        # Sync files to PostgreSQL with user_id
        files_to_sync = skill.files or {}
        if skill.content and not skill.files:
            files_to_sync = {"SKILL.md": skill.content}

        if files_to_sync:
            await self.sync_skill_files(skill.name, files_to_sync, user_id=user_id)

        # Invalidate cache for this user
        await self._invalidate_user_skills_cache(user_id)

        return self._doc_to_user_skill(doc)

    async def update_user_skill(
        self, name: str, updates: SkillUpdate, user_id: str
    ) -> Optional[UserSkill]:
        """Update a user skill"""
        collection = self._get_user_collection()

        doc = await collection.find_one({"name": name, "user_id": user_id})
        if not doc:
            return None

        update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if updates.name is not None:
            update_data["name"] = updates.name
        if updates.description is not None:
            update_data["description"] = updates.description
        if updates.content is not None:
            update_data["content"] = updates.content
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled
        if updates.version is not None:
            update_data["version"] = updates.version
        if updates.files is not None:
            update_data["files"] = updates.files

        # If renaming, update by old name then find by new name
        query_name = name
        if updates.name and updates.name != name:
            await collection.update_one({"name": name, "user_id": user_id}, {"$set": update_data})
            query_name = updates.name
        else:
            await collection.update_one({"name": name, "user_id": user_id}, {"$set": update_data})

        updated_doc = await collection.find_one({"name": query_name, "user_id": user_id})

        # Invalidate cache for this user
        await self._invalidate_user_skills_cache(user_id)

        return self._doc_to_user_skill(updated_doc) if updated_doc else None

    async def delete_user_skill(self, name: str, user_id: str) -> bool:
        """Delete a user skill"""
        collection = self._get_user_collection()
        result = await collection.delete_one({"name": name, "user_id": user_id})

        # Delete files from PostgreSQL with user_id
        if result.deleted_count > 0:
            await self.delete_skill_files(name, user_id=user_id)
            # Invalidate cache for this user
            await self._invalidate_user_skills_cache(user_id)

        return result.deleted_count > 0

    # ==========================================
    # Skill Type Conversion (Admin only)
    # ==========================================

    async def promote_to_system_skill(
        self, name: str, user_id: str, admin_user_id: str
    ) -> Optional[SystemSkill]:
        """
        Promote a user skill to system skill (admin only).

        This moves the skill from user collection to system collection.
        Returns the new system skill, or None if user skill not found.
        """
        # Get the user skill
        user_skill = await self.get_user_skill(name, user_id)
        if not user_skill:
            return None

        # Check if system skill with same name exists
        existing_system = await self.get_system_skill(name)
        if existing_system:
            return None  # Conflict

        # Create system skill
        now = datetime.now(timezone.utc).isoformat()
        system_collection = self._get_system_collection()
        doc = {
            "name": user_skill.name,
            "description": user_skill.description,
            "content": user_skill.content,
            "files": user_skill.files,
            "enabled": user_skill.enabled,
            "source": user_skill.source.value,
            "github_url": user_skill.github_url,
            "version": user_skill.version,
            "is_system": True,
            "created_at": user_skill.created_at or now,
            "updated_at": now,
            "updated_by": admin_user_id,
            "promoted_from_user": user_id,  # Track origin
        }
        await system_collection.insert_one(doc)

        # Sync files to PostgreSQL with "system" user_id
        if user_skill.files:
            await self.sync_skill_files(name, user_skill.files, user_id="system")
        elif user_skill.content:
            await self.sync_skill_files(name, {"SKILL.md": user_skill.content}, user_id="system")

        # Delete the user skill (this will also delete files from PostgreSQL with user_id)
        await self.delete_user_skill(name, user_id)

        return self._doc_to_system_skill(doc)

    async def demote_to_user_skill(
        self,
        name: str,
        target_user_id: str,
        admin_user_id: str,  # noqa: ARG002
    ) -> Optional[UserSkill]:
        """
        Demote a system skill to user skill (admin only).

        This moves the skill from system collection to user collection.
        The skill will be owned by target_user_id.
        Returns the new user skill, or None if system skill not found.
        """
        # Get the system skill
        system_skill = await self.get_system_skill(name)
        if not system_skill:
            return None

        # Check if user skill with same name exists
        existing_user = await self.get_user_skill(name, target_user_id)
        if existing_user:
            return None  # Conflict

        # Create user skill
        now = datetime.now(timezone.utc).isoformat()
        user_collection = self._get_user_collection()
        doc = {
            "name": system_skill.name,
            "description": system_skill.description,
            "content": system_skill.content,
            "files": system_skill.files,
            "enabled": system_skill.enabled,
            "source": system_skill.source.value,
            "github_url": system_skill.github_url,
            "version": system_skill.version,
            "user_id": target_user_id,
            "is_system": False,
            "created_at": system_skill.created_at or now,
            "updated_at": now,
        }
        await user_collection.insert_one(doc)

        # Sync files to PostgreSQL with target_user_id
        if system_skill.files:
            await self.sync_skill_files(name, system_skill.files, user_id=target_user_id)
        elif system_skill.content:
            await self.sync_skill_files(
                name, {"SKILL.md": system_skill.content}, user_id=target_user_id
            )

        # Delete the system skill (this will also delete files from PostgreSQL with "system" user_id)
        await self.delete_system_skill(name)

        return self._doc_to_user_skill(doc)

    # ==========================================
    # User Preferences (for system skills)
    # ==========================================

    async def _get_user_preferences(self, user_id: str) -> dict[str, bool]:
        """Get user's enabled preferences for system skills"""
        collection = self._get_preferences_collection()
        preferences = {}
        async for doc in collection.find({"user_id": user_id}):
            preferences[doc["skill_name"]] = doc.get("enabled", True)
        return preferences

    async def _set_user_preference(self, skill_name: str, user_id: str, enabled: bool) -> None:
        """Set user's preference for a system skill"""
        collection = self._get_preferences_collection()
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )

        # Invalidate cache for this user
        await self._invalidate_user_skills_cache(user_id)

    # ==========================================
    # Combined Operations (for runtime)
    # ==========================================

    async def get_effective_skills(self, user_id: str) -> dict[str, Any]:
        """
        Get effective skills for a user (with Redis cache).

        Merges system and user configurations, with user preferences taking precedence.
        Only includes skills that are enabled (after applying user preferences).

        文件直接从 MongoDB 技能文档的 files 字段加载。
        """
        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"

        # 尝试从 Redis 获取缓存
        try:
            redis_client = get_redis_client()
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                result = json.loads(cached_data)
                logger.info(
                    f"[Skills Cache] Hit for user {user_id}, {len(result.get('skills', {}))} skills"
                )
                return result
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis get failed for user {user_id}: {e}")

        # 缓存未命中，从 MongoDB 加载
        logger.info(f"[Skills Cache] Miss for user {user_id}")

        # Get user preferences for system skills
        user_preferences = await self._get_user_preferences(user_id)

        # Get system skills and apply user preferences
        system_collection = self._get_system_collection()
        system_skills = {}
        async for doc in system_collection.find({}):
            skill_name = doc["name"]
            # Check if user has a preference, otherwise use system default
            if skill_name in user_preferences:
                is_enabled = user_preferences[skill_name]
            else:
                is_enabled = doc.get("enabled", True)

            if is_enabled:
                skill_data = self._doc_to_effective_dict(doc, is_system=True)
                # 直接从 MongoDB 文档的 files 字段获取文件
                skill_files = doc.get("files", {})
                if skill_files:
                    skill_data["files"] = skill_files
                    # Also set content for backward compatibility
                    if "SKILL.md" in skill_files:
                        skill_data["content"] = skill_files["SKILL.md"]
                system_skills[skill_name] = skill_data

        # Get enabled user skills
        user_collection = self._get_user_collection()
        user_skills = {}
        async for doc in user_collection.find({"user_id": user_id, "enabled": True}):
            skill_data = self._doc_to_effective_dict(doc, is_system=False)
            # 直接从 MongoDB 文档的 files 字段获取文件
            skill_files = doc.get("files", {})
            if skill_files:
                skill_data["files"] = skill_files
                # Also set content for backward compatibility
                if "SKILL.md" in skill_files:
                    skill_data["content"] = skill_files["SKILL.md"]
            user_skills[doc["name"]] = skill_data

        # Merge (user skills override system skills with same name)
        result = {**system_skills, **user_skills}
        response = {"skills": result}

        # 存入 Redis 缓存
        try:
            redis_client = get_redis_client()
            await redis_client.set(cache_key, json.dumps(response), ex=SKILLS_CACHE_TTL)
            logger.info(f"[Skills Cache] Cached {len(result)} skills for user {user_id}")
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis set failed for user {user_id}: {e}")

        return response

    async def get_visible_skills(
        self,
        user_id: str,
        is_admin: bool = False,  # noqa: ARG002
    ) -> list[SkillResponse]:
        """
        Get all skills visible to a user.

        Returns system skills (with user preferences applied) + user's own skills.
        """
        skills = []

        # Get user preferences for system skills
        user_preferences = await self._get_user_preferences(user_id)

        # Get system skills
        system_collection = self._get_system_collection()
        async for doc in system_collection.find({}):
            # Apply user preference if exists, otherwise use system default
            skill_name = doc["name"]
            if skill_name in user_preferences:
                doc = copy.deepcopy(doc)
                doc["enabled"] = user_preferences[skill_name]
            skill = self._doc_to_response(doc, is_system=True, can_edit=True)
            skills.append(skill)

        # Get user skills
        user_collection = self._get_user_collection()
        async for doc in user_collection.find({"user_id": user_id}):
            skill = self._doc_to_response(doc, is_system=False, can_edit=True)
            skills.append(skill)

        return skills

    async def toggle_skill(self, name: str, user_id: str) -> Optional[SkillResponse]:
        """
        Toggle a skill's enabled status.

        For user-created skills: toggles the skill directly.
        For system skills: toggles the user's preference for that skill.
        """
        # First try user-created skill
        user_collection = self._get_user_collection()
        user_doc = await user_collection.find_one({"name": name, "user_id": user_id})

        if user_doc:
            # Toggle user-created skill
            new_enabled = not user_doc.get("enabled", True)
            await user_collection.update_one(
                {"name": name, "user_id": user_id},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            # Invalidate cache for this user
            await self._invalidate_user_skills_cache(user_id)

            updated_doc = await user_collection.find_one({"name": name, "user_id": user_id})
            if updated_doc:
                return self._doc_to_response(updated_doc, is_system=False, can_edit=True)

        # Check if it's a system skill
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc:
            # For system skills, toggle user's preference
            # Get current user preference or system default
            preferences = await self._get_user_preferences(user_id)
            current_enabled = preferences.get(name, system_doc.get("enabled", True))
            new_enabled = not current_enabled

            # Save user preference
            await self._set_user_preference(name, user_id, new_enabled)

            # Return updated skill response with user's preference applied
            response_doc = copy.deepcopy(system_doc)
            response_doc["enabled"] = new_enabled
            return self._doc_to_response(response_doc, is_system=True, can_edit=True)

        return None

    async def toggle_system_skill(self, name: str) -> Optional[SkillResponse]:
        """Toggle a system skill's enabled status (admin only)"""
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc:
            new_enabled = not system_doc.get("enabled", True)
            await system_collection.update_one(
                {"name": name},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            # Invalidate all users' cache since system skill affects everyone
            await self._invalidate_all_skills_cache()

            updated_doc = await system_collection.find_one({"name": name})
            if updated_doc:
                return self._doc_to_response(updated_doc, is_system=True, can_edit=True)

        return None

    # ==========================================
    # Import/Export
    # ==========================================

    async def import_skills(
        self,
        import_data: SkillImportRequest,
        user_id: str,
        is_admin: bool = False,
    ) -> SkillImportResponse:
        """
        Import skills from JSON configuration.

        Returns SkillImportResponse with counts and errors.
        """
        imported = 0
        skipped = 0
        errors = []

        for name, config in import_data.skills.items():
            try:
                # Parse source
                source_str = config.get("source", "manual")
                try:
                    source = SkillSource(source_str)
                except ValueError:
                    source = SkillSource.MANUAL

                # Create skill object
                skill = SkillCreate(
                    name=name,
                    description=config.get("description", ""),
                    content=config.get("content", ""),
                    enabled=config.get("enabled", True),
                    source=source,
                    github_url=config.get("github_url"),
                    version=config.get("version"),
                )

                # Check if exists
                existing: Optional[SystemSkill | UserSkill] = None
                if is_admin:
                    existing = await self.get_system_skill(name)
                else:
                    existing = await self.get_user_skill(name, user_id)

                if existing and not import_data.overwrite:
                    skipped += 1
                    continue

                # Create or update
                if is_admin:
                    if existing:
                        await self.update_system_skill(
                            name,
                            SkillUpdate(
                                description=skill.description,
                                content=skill.content,
                                enabled=skill.enabled,
                                version=skill.version,
                                is_system=True,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_system_skill(skill, user_id)
                else:
                    if existing:
                        await self.update_user_skill(
                            name,
                            SkillUpdate(
                                description=skill.description,
                                content=skill.content,
                                enabled=skill.enabled,
                                version=skill.version,
                                is_system=False,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_user_skill(skill, user_id)

                imported += 1

            except Exception as e:
                errors.append(f"Error importing '{name}': {str(e)}")

        return SkillImportResponse(
            message=f"Imported {imported} skills, skipped {skipped}",
            imported_count=imported,
            skipped_count=skipped,
            errors=errors,
        )

    async def export_user_skills(self, user_id: str) -> SkillExportResponse:
        """Export user's skills as JSON configuration"""
        user_collection = self._get_user_collection()
        skills = {}

        async for doc in user_collection.find({"user_id": user_id}):
            skills[doc["name"]] = self._doc_to_export_dict(doc)

        return SkillExportResponse(skills=skills)

    async def export_all_skills(self) -> SkillExportResponse:
        """Export all skills (system only, admin)"""
        system_collection = self._get_system_collection()
        skills = {}

        async for doc in system_collection.find({}):
            skills[doc["name"]] = self._doc_to_export_dict(doc)

        return SkillExportResponse(skills=skills)

    # ==========================================
    # GitHub Install
    # ==========================================

    async def install_github_skills(
        self,
        install_request: GitHubInstallRequest,
        skills_data: list[dict[str, Any]],
        user_id: str,
        is_admin: bool = False,
    ) -> SkillImportResponse:
        """
        Install skills from GitHub repository.

        Args:
            install_request: GitHub install request
            skills_data: List of skill data from GitHub sync service
            user_id: User ID performing the install
            is_admin: Whether the user is an admin

        Returns:
            SkillImportResponse with counts and errors
        """
        imported = 0
        skipped = 0
        errors = []

        # Filter skills if specific names provided
        if install_request.skill_names:
            skills_data = [s for s in skills_data if s.get("name") in install_request.skill_names]

        for skill_data in skills_data:
            try:
                name = skill_data["name"]

                # Get content and files dict
                content = skill_data.get("content", "")
                # Use files from skill_data if available, otherwise create from content
                files = skill_data.get("files")
                if not files:
                    files = {"SKILL.md": content} if content else {}

                # Create skill object
                skill = SkillCreate(
                    name=name,
                    description=skill_data.get("description", ""),
                    content=content,
                    files=files,
                    enabled=True,
                    source=SkillSource.GITHUB,
                    github_url=install_request.repo_url,
                    version=skill_data.get("version"),
                )

                # Check if exists
                existing: Optional[SystemSkill | UserSkill] = None
                if is_admin:
                    existing = await self.get_system_skill(name)
                else:
                    existing = await self.get_user_skill(name, user_id)

                if existing:
                    skipped += 1
                    continue

                # Create skill (this will sync files internally)
                if is_admin:
                    await self.create_system_skill(skill, user_id)
                else:
                    await self.create_user_skill(skill, user_id)

                imported += 1

            except Exception as e:
                errors.append(f"Error installing '{skill_data.get('name', 'unknown')}': {str(e)}")

        return SkillImportResponse(
            message=f"Installed {imported} skills from GitHub, skipped {skipped}",
            imported_count=imported,
            skipped_count=skipped,
            errors=errors,
        )

    # ==========================================
    # Document Conversion
    # ==========================================

    def _doc_to_system_skill(self, doc: dict[str, Any]) -> SystemSkill:
        """Convert MongoDB document to SystemSkill"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        return SystemSkill(
            name=doc["name"],
            description=doc.get("description", ""),
            content=doc.get("content", ""),
            files=doc.get("files", {}),
            enabled=doc.get("enabled", True),
            source=SkillSource(doc.get("source", "manual")),
            github_url=doc.get("github_url"),
            version=doc.get("version"),
            is_system=True,
            created_at=created_at,
            updated_at=updated_at,
            updated_by=doc.get("updated_by"),
        )

    def _doc_to_user_skill(self, doc: dict[str, Any]) -> UserSkill:
        """Convert MongoDB document to UserSkill"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        return UserSkill(
            name=doc["name"],
            description=doc.get("description", ""),
            content=doc.get("content", ""),
            files=doc.get("files", {}),
            enabled=doc.get("enabled", True),
            source=SkillSource(doc.get("source", "manual")),
            github_url=doc.get("github_url"),
            version=doc.get("version"),
            user_id=doc["user_id"],
            is_system=False,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_response(
        self, doc: dict[str, Any], is_system: bool, can_edit: bool
    ) -> SkillResponse:
        """Convert MongoDB document to SkillResponse"""
        # Deep copy to avoid modifying original
        doc_copy = copy.deepcopy(doc)

        # Convert datetime to ISO string if needed
        created_at = doc_copy.get("created_at")
        updated_at = doc_copy.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        return SkillResponse(
            name=doc_copy["name"],
            description=doc_copy.get("description", ""),
            content=doc_copy.get("content", ""),
            files=doc_copy.get("files", {}),
            enabled=doc_copy.get("enabled", True),
            source=SkillSource(doc_copy.get("source", "manual")),
            github_url=doc_copy.get("github_url"),
            version=doc_copy.get("version"),
            is_system=is_system,
            can_edit=can_edit,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_effective_dict(self, doc: dict[str, Any], is_system: bool = True) -> dict[str, Any]:
        """Convert MongoDB document to effective dict format"""
        result = {
            "name": doc["name"],
            "description": doc.get("description", ""),
            "content": doc.get("content", ""),
            "is_system": is_system,
        }
        if doc.get("github_url"):
            result["github_url"] = doc["github_url"]
        if doc.get("version"):
            result["version"] = doc["version"]
        return result

    def _doc_to_export_dict(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to export dict format"""
        result = {
            "description": doc.get("description", ""),
            "content": doc.get("content", ""),
            "enabled": doc.get("enabled", True),
            "source": doc.get("source", "manual"),
        }
        if doc.get("github_url"):
            result["github_url"] = doc["github_url"]
        if doc.get("version"):
            result["version"] = doc["version"]
        return result

    # ==========================================
    # Skill Files (MongoDB files field)
    # ==========================================

    async def sync_skill_files(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Sync skill files to MongoDB files field.

        文件直接存储在技能文档的 files 字段中，不再使用 PostgreSQL。

        Args:
            skill_name: 技能名称
            files: 文件路径 -> 内容 的字典
            user_id: 用户 ID（系统技能为 None）
        """
        # 确定使用哪个集合
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            query = {"name": skill_name}
        else:
            collection = self._get_user_collection()
            query = {"name": skill_name, "user_id": user_id}

        # 更新 files 字段
        await collection.update_one(
            query,
            {
                "$set": {
                    "files": files,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    async def get_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Get all files for a skill from MongoDB files field.

        Args:
            skill_name: 技能名称
            user_id: 用户 ID（系统技能为 None）

        Returns:
            文件路径 -> 内容 的字典
        """
        # 确定使用哪个集合
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            doc = await collection.find_one({"name": skill_name})
        else:
            collection = self._get_user_collection()
            doc = await collection.find_one({"name": skill_name, "user_id": user_id})

        if doc:
            return doc.get("files", {})
        return {}

    async def delete_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Delete all files for a skill (clear files field).

        Args:
            skill_name: 技能名称
            user_id: 用户 ID（系统技能为 None）
        """
        # 确定使用哪个集合
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            query = {"name": skill_name}
        else:
            collection = self._get_user_collection()
            query = {"name": skill_name, "user_id": user_id}

        # 清空 files 字段
        await collection.update_one(
            query,
            {
                "$set": {
                    "files": {},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    # ==========================================
    # MCP Tools Cache (Redis)
    # ==========================================

    async def get_mcp_tools(
        self,
        user_id: str,
        fetch_func,
        cache_key_suffix: Optional[str] = None,
        ttl: int = MCP_TOOLS_METADATA_CACHE_TTL,
    ) -> list[dict[str, Any]]:
        """
        获取 MCP 工具（带 Redis 缓存）

        先检查 Redis 缓存，有缓存就返回，没有就调用 fetch_func 获取并存入缓存。

        Args:
            user_id: 用户 ID
            fetch_func: 异步函数，用于获取 MCP 工具，签名: async def fetch_func() -> list[dict]
            cache_key_suffix: 缓存键后缀（可选，用于区分不同类型的工具）
            ttl: 缓存过期时间（秒），默认 30 分钟

        Returns:
            MCP 工具列表
        """
        # 构建缓存键
        cache_key = f"{MCP_TOOLS_METADATA_KEY_PREFIX}{user_id}"
        if cache_key_suffix:
            cache_key = f"{cache_key}:{cache_key_suffix}"

        # 尝试从 Redis 获取缓存
        try:
            redis_client = get_redis_client()
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                tools = json.loads(cached_data)
                logger.info(f"[MCP Tools Cache] Hit for user {user_id}, {len(tools)} tools")
                return tools
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis get failed for user {user_id}: {e}")

        # 缓存未命中，调用 fetch_func 获取数据
        logger.info(f"[MCP Tools Cache] Miss for user {user_id}")
        tools = await fetch_func()

        # 存入 Redis 缓存
        try:
            redis_client = get_redis_client()
            await redis_client.set(cache_key, json.dumps(tools), ex=ttl)
            logger.info(f"[MCP Tools Cache] Cached {len(tools)} tools for user {user_id}")
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis set failed for user {user_id}: {e}")

        return tools

    async def invalidate_mcp_tools_cache(
        self, user_id: str, cache_key_suffix: Optional[str] = None
    ) -> bool:
        """
        使 MCP 工具缓存失效

        Args:
            user_id: 用户 ID
            cache_key_suffix: 缓存键后缀（可选）

        Returns:
            是否成功删除缓存
        """
        cache_key = f"{MCP_TOOLS_METADATA_KEY_PREFIX}{user_id}"
        if cache_key_suffix:
            cache_key = f"{cache_key}:{cache_key_suffix}"

        try:
            redis_client = get_redis_client()
            result = await redis_client.delete(cache_key)
            if result > 0:
                logger.info(f"[MCP Tools Cache] Invalidated cache for user {user_id}")
                return True
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis delete failed for user {user_id}: {e}")

        return False

    async def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._system_collection = None
            self._user_collection = None
            self._preferences_collection = None
