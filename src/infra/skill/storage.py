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

from src.infra.skill.cache import SkillCacheMixin
from src.infra.skill.converters import (
    doc_to_effective_dict,
    doc_to_export_dict,
    doc_to_response,
    doc_to_system_skill,
    doc_to_user_skill,
)
from src.infra.skill.files import SkillFilesMixin
from src.infra.skill.import_export import SkillImportExportMixin
from src.infra.skill.preferences import SkillPreferencesMixin
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.skill import (
    SkillCreate,
    SkillResponse,
    SkillUpdate,
    SystemSkill,
    UserSkill,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class SkillStorage(
    SkillCacheMixin,
    SkillFilesMixin,
    SkillImportExportMixin,
    SkillPreferencesMixin,
):
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
    # MongoDB Collection Access
    # ==========================================

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
    # Document Conversion (using converters module)
    # ==========================================

    def _doc_to_system_skill(self, doc: dict[str, Any]) -> SystemSkill:
        """Convert MongoDB document to SystemSkill"""
        return doc_to_system_skill(doc)

    def _doc_to_user_skill(self, doc: dict[str, Any]) -> UserSkill:
        """Convert MongoDB document to UserSkill"""
        return doc_to_user_skill(doc)

    def _doc_to_response(
        self, doc: dict[str, Any], is_system: bool, can_edit: bool
    ) -> SkillResponse:
        """Convert MongoDB document to SkillResponse"""
        return doc_to_response(doc, is_system, can_edit)

    def _doc_to_effective_dict(self, doc: dict[str, Any], is_system: bool = True) -> dict[str, Any]:
        """Convert MongoDB document to effective dict format"""
        return doc_to_effective_dict(doc, is_system)

    def _doc_to_export_dict(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to export dict format"""
        return doc_to_export_dict(doc)

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
    # Combined Operations (for runtime)
    # ==========================================

    async def get_effective_skills(self, user_id: str) -> dict[str, Any]:
        """
        Get effective skills for a user (with Redis cache).

        Merges system and user configurations, with user preferences taking precedence.
        Only includes skills that are enabled (after applying user preferences).

        Files are loaded directly from the MongoDB skill document's files field.
        """
        from src.infra.skill.constants import SKILLS_CACHE_KEY_PREFIX, SKILLS_CACHE_TTL

        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"

        # Try to get from Redis cache
        try:
            from src.infra.storage.redis import get_redis_client

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

        # Cache miss, load from MongoDB
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
                # Get files directly from MongoDB document's files field
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
            # Get files directly from MongoDB document's files field
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

        # Store in Redis cache
        try:
            from src.infra.storage.redis import get_redis_client

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

    async def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._system_collection = None
            self._user_collection = None
            self._preferences_collection = None
