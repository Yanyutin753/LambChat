"""Persona preset manager."""

from datetime import datetime
from typing import Optional

from src.infra.persona_preset.storage import PersonaPresetStorage
from src.infra.skill.storage import SkillStorage
from src.kernel.exceptions import AuthorizationError, NotFoundError
from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetCreate,
    PersonaPresetScope,
    PersonaPresetSnapshot,
    PersonaPresetStatus,
    PersonaPresetUpdate,
    PersonaPresetVisibility,
)


class PersonaPresetManager:
    """Business logic for persona presets."""

    def __init__(
        self,
        storage: PersonaPresetStorage | None = None,
        skill_storage: SkillStorage | None = None,
    ) -> None:
        self.storage = storage or PersonaPresetStorage()
        self.skill_storage = skill_storage or SkillStorage()

    @staticmethod
    def _can_view(doc: dict, *, user_id: str, is_admin: bool) -> bool:
        if is_admin:
            return True
        if doc.get("scope") == PersonaPresetScope.USER.value:
            return doc.get("owner_user_id") == user_id
        return (
            doc.get("scope") == PersonaPresetScope.GLOBAL.value
            and doc.get("visibility") == PersonaPresetVisibility.PUBLIC.value
            and doc.get("status") == PersonaPresetStatus.PUBLISHED.value
        )

    @staticmethod
    def _can_edit(doc: dict, *, user_id: str, is_admin: bool) -> bool:
        if doc.get("scope") == PersonaPresetScope.GLOBAL.value:
            return is_admin
        return doc.get("owner_user_id") == user_id

    async def create_preset(
        self,
        preset_data: PersonaPresetCreate,
        *,
        user_id: str,
        is_admin: bool,
    ) -> PersonaPreset:
        if preset_data.scope == PersonaPresetScope.GLOBAL and not is_admin:
            raise AuthorizationError("persona_preset_no_admin_permission")

        now = datetime.now()
        data = preset_data.model_dump(mode="json")
        data.update(
            {
                "owner_user_id": None
                if preset_data.scope == PersonaPresetScope.GLOBAL
                else user_id,
                "version": 1,
                "usage_count": 0,
                "created_by": user_id,
                "updated_by": user_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        created = await self.storage.create(data)
        return PersonaPreset(**created)

    async def get_preset(self, preset_id: str, *, user_id: str, is_admin: bool) -> PersonaPreset:
        doc = await self.storage.get_by_id(preset_id)
        if not doc or not self._can_view(doc, user_id=user_id, is_admin=is_admin):
            raise NotFoundError("persona_preset_not_found")
        return PersonaPreset(**doc)

    async def list_presets(
        self,
        *,
        user_id: str,
        is_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PersonaPreset]:
        docs = await self.storage.list_visible(
            user_id=user_id,
            include_admin=is_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
            skip=skip,
            limit=limit,
        )
        return [PersonaPreset(**doc) for doc in docs]

    async def count_presets(
        self,
        *,
        user_id: str,
        is_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> int:
        del skip, limit
        return await self.storage.count_visible(
            user_id=user_id,
            include_admin=is_admin,
            scope=scope,
            status=status,
            tag=tag,
            q=q,
        )

    async def update_preset(
        self,
        preset_id: str,
        preset_data: PersonaPresetUpdate,
        *,
        user_id: str,
        is_admin: bool,
    ) -> PersonaPreset:
        doc = await self.storage.get_by_id(preset_id)
        if not doc:
            raise NotFoundError("persona_preset_not_found")
        if not self._can_edit(doc, user_id=user_id, is_admin=is_admin):
            raise AuthorizationError("persona_preset_no_edit_permission")

        update = preset_data.model_dump(mode="json", exclude_unset=True)
        update["version"] = int(doc.get("version", 1)) + 1
        update["updated_by"] = user_id
        updated = await self.storage.update(preset_id, update)
        if not updated:
            raise NotFoundError("persona_preset_not_found")
        return PersonaPreset(**updated)

    async def delete_preset(self, preset_id: str, *, user_id: str, is_admin: bool) -> bool:
        doc = await self.storage.get_by_id(preset_id)
        if not doc:
            raise NotFoundError("persona_preset_not_found")
        if not self._can_edit(doc, user_id=user_id, is_admin=is_admin):
            raise AuthorizationError("persona_preset_no_delete_permission")
        return await self.storage.delete(preset_id)

    async def copy_preset(
        self,
        preset_id: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> PersonaPreset:
        source = await self.get_preset(preset_id, user_id=user_id, is_admin=is_admin)
        now = datetime.now()
        copied_data = {
            "scope": PersonaPresetScope.USER.value,
            "owner_user_id": user_id,
            "name": source.name,
            "description": source.description,
            "avatar": source.avatar,
            "tags": source.tags,
            "system_prompt": source.system_prompt,
            "skill_names": source.skill_names,
            "visibility": PersonaPresetVisibility.PRIVATE.value,
            "status": PersonaPresetStatus.DRAFT.value,
            "source_preset_id": source.id,
            "copied_from_version": source.version,
            "version": 1,
            "usage_count": 0,
            "created_by": user_id,
            "updated_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
        created = await self.storage.create(copied_data)
        return PersonaPreset(**created)

    async def use_preset(
        self,
        preset_id: str,
        *,
        user_id: str,
        is_admin: bool,
    ) -> PersonaPresetSnapshot:
        preset = await self.get_preset(preset_id, user_id=user_id, is_admin=is_admin)
        available = await self._get_available_skill_names(user_id)
        skill_names = [name for name in preset.skill_names if name in available]
        missing = [name for name in preset.skill_names if name not in available]

        await self.storage.increment_usage(preset_id)
        return PersonaPresetSnapshot(
            preset_id=preset.id,
            name=preset.name,
            system_prompt=preset.system_prompt,
            skill_names=skill_names,
            missing_skill_names=missing,
            version=preset.version,
            avatar=preset.avatar,
        )

    async def _get_available_skill_names(self, user_id: str) -> set[str]:
        """Return skill names that can actually be loaded for this user."""
        get_effective_skills = getattr(self.skill_storage, "get_effective_skills", None)
        if get_effective_skills is not None:
            effective = await get_effective_skills(user_id)
            if isinstance(effective, dict):
                skills = effective.get("skills")
                if isinstance(skills, dict):
                    return set(skills.keys())
                return set(effective.keys())

        return set(await self.skill_storage.get_all_user_skill_names(user_id))


_persona_preset_manager: Optional[PersonaPresetManager] = None


def get_persona_preset_manager() -> PersonaPresetManager:
    """Get singleton persona preset manager."""
    global _persona_preset_manager
    if _persona_preset_manager is None:
        _persona_preset_manager = PersonaPresetManager()
    return _persona_preset_manager
