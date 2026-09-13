"""Persona preset manager."""

from typing import Optional

from src.infra.persona_preset.storage import PersonaPresetStorage
from src.infra.plugin.storage import PluginStorage
from src.infra.skill.storage import SkillStorage
from src.infra.utils.datetime import utc_now
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
        plugin_storage: PluginStorage | None = None,
    ) -> None:
        self.storage = storage or PersonaPresetStorage()
        self.skill_storage = skill_storage or SkillStorage()
        self.plugin_storage = plugin_storage or PluginStorage()

    @staticmethod
    def _can_view(doc: dict, *, user_id: str, is_admin: bool) -> bool:
        if doc.get("scope") == PersonaPresetScope.USER.value:
            owner_user_id = doc.get("owner_user_id")
            if owner_user_id:
                return owner_user_id == user_id
            return doc.get("created_by") == user_id
        if is_admin:
            return doc.get("scope") == PersonaPresetScope.GLOBAL.value
        return (
            doc.get("scope") == PersonaPresetScope.GLOBAL.value
            and doc.get("visibility") == PersonaPresetVisibility.PUBLIC.value
            and doc.get("status") == PersonaPresetStatus.PUBLISHED.value
        )

    @staticmethod
    def _can_edit(doc: dict, *, user_id: str, is_admin: bool) -> bool:
        if doc.get("scope") == PersonaPresetScope.GLOBAL.value:
            return is_admin
        owner_user_id = doc.get("owner_user_id")
        if owner_user_id:
            return owner_user_id == user_id
        return doc.get("created_by") == user_id

    async def create_preset(
        self,
        preset_data: PersonaPresetCreate,
        *,
        user_id: str,
        is_admin: bool,
    ) -> PersonaPreset:
        if preset_data.scope == PersonaPresetScope.GLOBAL and not is_admin:
            raise AuthorizationError("persona_preset_no_admin_permission")

        now = utc_now()
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

    async def batch_create_presets(
        self,
        items: list[PersonaPresetCreate],
        *,
        user_id: str,
        is_admin: bool,
    ) -> list[PersonaPreset]:
        now = utc_now()
        docs = []
        for item in items:
            if item.scope == PersonaPresetScope.GLOBAL and not is_admin:
                continue
            data = item.model_dump(mode="json")
            data.update(
                {
                    "owner_user_id": None if item.scope == PersonaPresetScope.GLOBAL else user_id,
                    "version": 1,
                    "usage_count": 0,
                    "created_by": user_id,
                    "updated_by": user_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            docs.append(data)
        if not docs:
            return []
        inserted = await self.storage.insert_many(docs)
        return [PersonaPreset(**doc) for doc in inserted]

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
        favorite: bool | None = None,
        pinned: bool | None = None,
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
            favorite=favorite,
            pinned=pinned,
            skip=skip,
            limit=limit,
        )
        return [PersonaPreset(**doc) for doc in docs]

    async def update_preference(
        self,
        preset_id: str,
        *,
        user_id: str,
        is_admin: bool,
        is_favorite: bool | None = None,
        is_pinned: bool | None = None,
    ) -> PersonaPreset:
        preset = await self.get_preset(preset_id, user_id=user_id, is_admin=is_admin)
        preference = await self.storage.update_user_preference(
            user_id=user_id,
            preset_id=preset_id,
            update={
                "is_favorite": is_favorite,
                "is_pinned": is_pinned,
            },
        )
        return preset.model_copy(update=preference)

    async def count_presets(
        self,
        *,
        user_id: str,
        is_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        favorite: bool | None = None,
        pinned: bool | None = None,
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
            favorite=favorite,
            pinned=pinned,
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
        target_scope = update.get("scope")
        if target_scope == PersonaPresetScope.GLOBAL.value:
            if not is_admin:
                raise AuthorizationError("persona_preset_no_admin_permission")
            update["owner_user_id"] = None
        elif target_scope == PersonaPresetScope.USER.value:
            update["owner_user_id"] = user_id

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
        now = utc_now()
        copied_data = {
            "scope": PersonaPresetScope.USER.value,
            "owner_user_id": user_id,
            "name": source.name,
            "description": source.description,
            "avatar": source.avatar,
            "tags": source.tags,
            "system_prompt": source.system_prompt,
            "starter_prompts": [
                prompt.model_dump(mode="json") for prompt in source.starter_prompts
            ],
            "skill_names": source.skill_names,
            "plugin_names": source.plugin_names,
            "mcp_server_names": source.mcp_server_names,
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

        plugin_skill_names, plugin_mcp_names, missing_plugins = await self._resolve_plugins(
            preset.plugin_names
        )
        requested = list(dict.fromkeys([*preset.skill_names, *plugin_skill_names]))
        skill_names = [name for name in requested if name in available]
        missing = [name for name in preset.skill_names if name not in available]
        mcp_server_names = list(dict.fromkeys([*preset.mcp_server_names, *plugin_mcp_names]))

        await self.storage.increment_usage(preset_id)
        await self.storage.touch_user_preference(user_id=user_id, preset_id=preset_id)
        return PersonaPresetSnapshot(
            preset_id=preset.id,
            name=preset.name,
            system_prompt=preset.system_prompt,
            starter_prompts=preset.starter_prompts,
            skill_names=skill_names,
            missing_skill_names=missing,
            plugin_names=[name for name in preset.plugin_names if name not in missing_plugins],
            missing_plugin_names=missing_plugins,
            mcp_server_names=mcp_server_names,
            version=preset.version,
            avatar=preset.avatar,
        )

    async def _resolve_plugins(
        self, plugin_names: list[str]
    ) -> tuple[list[str], list[str], list[str]]:
        """展开插件绑定为（技能名, MCP server 名, 缺失插件名）。"""
        if not plugin_names:
            return [], [], []
        skill_names: list[str] = []
        mcp_names: list[str] = []
        missing: list[str] = []
        for name in plugin_names:
            doc = await self.plugin_storage.get_plugin_doc(name)
            if not doc or doc.get("status") != "active":
                missing.append(name)
                continue
            for skill in doc.get("skills", []) or []:
                skill_name = skill.get("skill_name")
                if skill_name:
                    skill_names.append(skill_name)
            for server in doc.get("mcp_servers", []) or []:
                server_name = server.get("name")
                if server_name:
                    mcp_names.append(server_name)
        return skill_names, mcp_names, missing

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

    async def close(self) -> None:
        await self.storage.close()
        await self.skill_storage.close()
        await self.plugin_storage.close()


_persona_preset_manager: Optional[PersonaPresetManager] = None


def get_persona_preset_manager() -> PersonaPresetManager:
    """Get singleton persona preset manager."""
    global _persona_preset_manager
    if _persona_preset_manager is None:
        _persona_preset_manager = PersonaPresetManager()
    return _persona_preset_manager


async def close_persona_preset_manager() -> None:
    global _persona_preset_manager
    manager = _persona_preset_manager
    _persona_preset_manager = None
    if manager is not None:
        await manager.close()
