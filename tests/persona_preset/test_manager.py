from __future__ import annotations

from datetime import datetime

import pytest

from src.infra.persona_preset.manager import PersonaPresetManager
from src.kernel.exceptions import AuthorizationError, NotFoundError
from src.kernel.schemas.persona_preset import (
    PersonaPresetCreate,
    PersonaPresetScope,
    PersonaPresetStatus,
    PersonaPresetUpdate,
    PersonaPresetVisibility,
)


class FakePresetStorage:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.next_id = 1

    async def create(self, data: dict) -> dict:
        preset_id = f"preset-{self.next_id}"
        self.next_id += 1
        doc = {
            **data,
            "id": preset_id,
            "created_at": data.get("created_at") or datetime(2026, 1, 1),
            "updated_at": data.get("updated_at") or datetime(2026, 1, 1),
        }
        self.docs[preset_id] = doc
        return dict(doc)

    async def get_by_id(self, preset_id: str) -> dict | None:
        doc = self.docs.get(preset_id)
        return dict(doc) if doc else None

    async def list_visible(
        self,
        *,
        user_id: str,
        include_admin: bool = False,
        scope: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        rows = []
        for doc in self.docs.values():
            visible = (
                include_admin
                or (
                    doc["scope"] == "global"
                    and doc["visibility"] == "public"
                    and doc["status"] == "published"
                )
                or (doc["scope"] == "user" and doc.get("owner_user_id") == user_id)
            )
            if not visible:
                continue
            if scope and doc["scope"] != scope:
                continue
            if status and doc["status"] != status:
                continue
            if tag and tag not in doc.get("tags", []):
                continue
            if q:
                haystack = f"{doc.get('name', '')} {doc.get('description', '')}".lower()
                if q.lower() not in haystack:
                    continue
            rows.append(dict(doc))
        return rows[skip : skip + limit]

    async def update(self, preset_id: str, update: dict) -> dict | None:
        if preset_id not in self.docs:
            return None
        self.docs[preset_id].update(update)
        self.docs[preset_id]["updated_at"] = datetime(2026, 1, 2)
        return dict(self.docs[preset_id])

    async def delete(self, preset_id: str) -> bool:
        return self.docs.pop(preset_id, None) is not None

    async def increment_usage(self, preset_id: str) -> None:
        self.docs[preset_id]["usage_count"] = self.docs[preset_id].get("usage_count", 0) + 1


class FakeSkillStorage:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    async def get_all_user_skill_names(self, user_id: str) -> list[str]:
        return sorted(self.names)


class FakeEffectiveSkillStorage(FakeSkillStorage):
    async def get_effective_skills(self, user_id: str) -> dict:
        return {"skills": {name: {"enabled": True} for name in sorted(self.names)}}


@pytest.mark.asyncio
async def test_non_admin_cannot_create_global_preset() -> None:
    manager = PersonaPresetManager(FakePresetStorage(), FakeSkillStorage(set()))

    with pytest.raises(AuthorizationError):
        await manager.create_preset(
            PersonaPresetCreate(
                name="Official",
                scope=PersonaPresetScope.GLOBAL,
                visibility=PersonaPresetVisibility.PUBLIC,
                status=PersonaPresetStatus.PUBLISHED,
                system_prompt="Official prompt",
            ),
            user_id="user-1",
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_global_published_preset_is_visible_and_copy_is_private() -> None:
    storage = FakePresetStorage()
    manager = PersonaPresetManager(storage, FakeSkillStorage({"planner"}))
    official = await manager.create_preset(
        PersonaPresetCreate(
            name="Official",
            scope=PersonaPresetScope.GLOBAL,
            visibility=PersonaPresetVisibility.PUBLIC,
            status=PersonaPresetStatus.PUBLISHED,
            system_prompt="Official prompt",
            skill_names=["planner"],
            tags=["coding"],
        ),
        user_id="admin-1",
        is_admin=True,
    )

    visible = await manager.list_presets(user_id="user-1", is_admin=False)
    assert [preset.id for preset in visible] == [official.id]

    copied = await manager.copy_preset(official.id, user_id="user-1", is_admin=False)

    assert copied.scope == PersonaPresetScope.USER
    assert copied.owner_user_id == "user-1"
    assert copied.visibility == PersonaPresetVisibility.PRIVATE
    assert copied.source_preset_id == official.id
    assert copied.system_prompt == "Official prompt"
    assert copied.skill_names == ["planner"]


@pytest.mark.asyncio
async def test_update_increments_version_and_checks_ownership() -> None:
    manager = PersonaPresetManager(FakePresetStorage(), FakeSkillStorage(set()))
    preset = await manager.create_preset(
        PersonaPresetCreate(name="Mine", system_prompt="Initial"),
        user_id="user-1",
        is_admin=False,
    )

    updated = await manager.update_preset(
        preset.id,
        PersonaPresetUpdate(system_prompt="Updated"),
        user_id="user-1",
        is_admin=False,
    )

    assert updated.system_prompt == "Updated"
    assert updated.version == 2

    with pytest.raises(AuthorizationError):
        await manager.update_preset(
            preset.id,
            PersonaPresetUpdate(name="Stolen"),
            user_id="user-2",
            is_admin=False,
        )


@pytest.mark.asyncio
async def test_use_preset_returns_snapshot_and_filters_missing_skills() -> None:
    storage = FakePresetStorage()
    manager = PersonaPresetManager(storage, FakeEffectiveSkillStorage({"planner"}))
    preset = await manager.create_preset(
        PersonaPresetCreate(
            name="Planner",
            system_prompt="Plan carefully.",
            skill_names=["planner", "missing"],
        ),
        user_id="user-1",
        is_admin=False,
    )

    snapshot = await manager.use_preset(preset.id, user_id="user-1", is_admin=False)

    assert snapshot.skill_names == ["planner"]
    assert snapshot.missing_skill_names == ["missing"]
    assert snapshot.system_prompt == "Plan carefully."
    assert storage.docs[preset.id]["usage_count"] == 1


@pytest.mark.asyncio
async def test_invisible_preset_raises_not_found() -> None:
    manager = PersonaPresetManager(FakePresetStorage(), FakeSkillStorage(set()))
    preset = await manager.create_preset(
        PersonaPresetCreate(name="Mine", system_prompt="Private"),
        user_id="user-1",
        is_admin=False,
    )

    with pytest.raises(NotFoundError):
        await manager.get_preset(preset.id, user_id="user-2", is_admin=False)
