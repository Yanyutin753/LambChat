"""Persona preset manager."""

from typing import Optional

from src.infra.mcp.storage import MCPStorage
from src.infra.persona_preset.storage import PersonaPresetStorage
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
        mcp_storage: MCPStorage | None = None,
    ) -> None:
        self.storage = storage or PersonaPresetStorage()
        self.skill_storage = skill_storage or SkillStorage()
        self.mcp_storage = mcp_storage or MCPStorage()

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
        skill_names = [name for name in preset.skill_names if name in available]
        missing = [name for name in preset.skill_names if name not in available]

        # MCP 可见性校验：快照只保留当前用户可见的服务（全缺时不设白名单→放行全部，
        # 与技能语义一致）；不可见的记录进 missing 供前端提示。
        visible_mcp = await self._get_visible_mcp_server_names(user_id, is_admin=is_admin)
        if visible_mcp is None:
            mcp_server_names = list(preset.mcp_server_names)
            missing_mcp: list[str] = []
        else:
            mcp_server_names = [
                name for name in preset.mcp_server_names if name in visible_mcp
            ]
            missing_mcp = [
                name for name in preset.mcp_server_names if name not in visible_mcp
            ]

        await self.storage.increment_usage(preset_id)
        await self.storage.touch_user_preference(user_id=user_id, preset_id=preset_id)
        return PersonaPresetSnapshot(
            preset_id=preset.id,
            name=preset.name,
            system_prompt=preset.system_prompt,
            starter_prompts=preset.starter_prompts,
            skill_names=skill_names,
            missing_skill_names=missing,
            mcp_server_names=mcp_server_names,
            missing_mcp_server_names=missing_mcp,
            version=preset.version,
            avatar=preset.avatar,
        )

    async def _get_visible_mcp_server_names(
        self, user_id: str, *, is_admin: bool
    ) -> set[str] | None:
        """当前用户可见的 MCP server 名集合；查询失败返回 None（跳过校验不阻塞）。"""
        try:
            from src.infra.mcp.quota import resolve_user_mcp_access

            user_roles, quota_admin = await resolve_user_mcp_access(user_id)
            servers = await self.mcp_storage.get_visible_servers(
                user_id,
                is_admin=is_admin or quota_admin,
                user_roles=user_roles,
            )
            return {server.name for server in servers}
        except Exception:
            return None

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
