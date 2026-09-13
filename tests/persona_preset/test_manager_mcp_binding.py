from __future__ import annotations

from src.infra.persona_preset.manager import PersonaPresetManager


class FakePresetStorage:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.next_id = 1

    async def create(self, data: dict) -> dict:
        preset_id = f"preset-{self.next_id}"
        self.next_id += 1
        doc = {**data, "id": preset_id}
        self.docs[preset_id] = doc
        return dict(doc)

    async def get_by_id(self, preset_id: str) -> dict | None:
        doc = self.docs.get(preset_id)
        return dict(doc) if doc else None

    async def list_visible(self, **_kwargs) -> list[dict]:
        return list(self.docs.values())

    async def count_visible(self, **_kwargs) -> int:
        return len(self.docs)

    async def update(self, preset_id: str, update: dict) -> dict | None:
        doc = self.docs.get(preset_id)
        if not doc:
            return None
        doc.update(update)
        return dict(doc)

    async def delete(self, preset_id: str) -> bool:
        return self.docs.pop(preset_id, None) is not None

    async def increment_usage(self, preset_id: str) -> None:
        return None

    async def touch_user_preference(self, *, user_id: str, preset_id: str) -> None:
        return None

    async def update_user_preference(self, **_kwargs) -> dict:
        return {"is_favorite": False, "is_pinned": False}

    async def close(self) -> None:
        return None


class FakeSkillStorage:
    def __init__(self, names: set[str]) -> None:
        self._names = names

    async def get_effective_skills(self, user_id: str) -> dict:
        return {"skills": {name: {} for name in self._names}}

    async def get_all_user_skill_names(self, user_id: str) -> list[str]:
        return sorted(self._names)

    async def close(self) -> None:
        return None


def _make_manager(skill_names: set[str]) -> PersonaPresetManager:
    return PersonaPresetManager(
        storage=FakePresetStorage(),
        skill_storage=FakeSkillStorage(skill_names),
    )


async def test_use_preset_passes_mcp_whitelist_into_snapshot() -> None:
    manager = _make_manager({"own-skill"})
    preset_id = (
        await manager.storage.create(
            {
                "scope": "user",
                "owner_user_id": "user-1",
                "name": "Researcher",
                "system_prompt": "You research.",
                "starter_prompts": [],
                "skill_names": ["own-skill", "gone-skill"],
                "mcp_server_names": ["arxiv", "weather"],
                "visibility": "private",
                "status": "published",
                "version": 1,
            }
        )
    )["id"]

    snapshot = await manager.use_preset(preset_id, user_id="user-1", is_admin=False)

    # 技能与用户实际可用技能求交集（缺失记录）；MCP 白名单原样透传给运行时
    assert snapshot.skill_names == ["own-skill"]
    assert snapshot.missing_skill_names == ["gone-skill"]
    assert snapshot.mcp_server_names == ["arxiv", "weather"]


async def test_copy_preset_carries_mcp_bindings() -> None:
    manager = _make_manager(set())
    source_id = (
        await manager.storage.create(
            {
                "scope": "global",
                "owner_user_id": None,
                "name": "Global Persona",
                "system_prompt": "You assist.",
                "starter_prompts": [],
                "skill_names": [],
                "mcp_server_names": ["arxiv"],
                "visibility": "public",
                "status": "published",
                "version": 3,
            }
        )
    )["id"]
    copied = await manager.copy_preset(source_id, user_id="user-1", is_admin=True)
    assert copied.mcp_server_names == ["arxiv"]
