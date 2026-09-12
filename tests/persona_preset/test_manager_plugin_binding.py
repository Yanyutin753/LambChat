from __future__ import annotations

from src.infra.persona_preset.manager import PersonaPresetManager


class FakePresetStorage:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.usage_increments: list[str] = []
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
        self.usage_increments.append(preset_id)

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


class FakePluginStorage:
    def __init__(self, docs: dict[str, dict]) -> None:
        self.docs = docs

    async def get_plugin_doc(self, name: str) -> dict | None:
        doc = self.docs.get(name)
        return dict(doc) if doc else None

    async def close(self) -> None:
        return None


async def test_use_preset_expands_plugin_bindings() -> None:
    preset_storage = FakePresetStorage()
    preset_id = (
        await preset_storage.create(
            {
                "scope": "user",
                "owner_user_id": "user-1",
                "name": "Researcher",
                "system_prompt": "You research.",
                "starter_prompts": [],
                "skill_names": ["own-skill"],
                "plugin_names": ["research-kit", "missing-plugin"],
                "mcp_server_names": ["weather"],
                "visibility": "private",
                "status": "published",
                "version": 1,
            }
        )
    )["id"]

    manager = PersonaPresetManager(
        storage=preset_storage,
        skill_storage=FakeSkillStorage({"own-skill", "plugin-skill"}),
        plugin_storage=FakePluginStorage(
            {
                "research-kit": {
                    "name": "research-kit",
                    "status": "active",
                    "skills": [{"skill_name": "plugin-skill", "description": "", "tags": []}],
                    "mcp_servers": [{"name": "arxiv", "transport": "sse", "ref": False}],
                },
                "inactive-kit": {
                    "name": "inactive-kit",
                    "status": "deactivated",
                    "skills": [],
                    "mcp_servers": [],
                },
            }
        ),
    )

    snapshot = await manager.use_preset(preset_id, user_id="user-1", is_admin=False)

    # 插件技能并入白名单，并与用户实际可用技能求交集
    assert sorted(snapshot.skill_names) == ["own-skill", "plugin-skill"]
    assert snapshot.missing_skill_names == []
    # 插件的 MCP server 并入白名单，直接绑定的也保留
    assert sorted(snapshot.mcp_server_names) == ["arxiv", "weather"]
    # 缺失/停用的插件被记录，且不进入生效绑定
    assert snapshot.missing_plugin_names == ["missing-plugin"]
    assert snapshot.plugin_names == ["research-kit"]


async def test_use_preset_without_plugins_keeps_legacy_behavior() -> None:
    preset_storage = FakePresetStorage()
    preset_id = (
        await preset_storage.create(
            {
                "scope": "user",
                "owner_user_id": "user-1",
                "name": "Plain",
                "system_prompt": "You chat.",
                "starter_prompts": [],
                "skill_names": ["gone-skill"],
                "plugin_names": [],
                "mcp_server_names": [],
                "visibility": "private",
                "status": "published",
                "version": 1,
            }
        )
    )["id"]

    manager = PersonaPresetManager(
        storage=preset_storage,
        skill_storage=FakeSkillStorage(set()),
        plugin_storage=FakePluginStorage({}),
    )
    snapshot = await manager.use_preset(preset_id, user_id="user-1", is_admin=False)
    assert snapshot.skill_names == []
    assert snapshot.missing_skill_names == ["gone-skill"]
    assert snapshot.mcp_server_names == []
    assert snapshot.missing_plugin_names == []


async def test_copy_preset_carries_plugin_and_mcp_bindings() -> None:
    preset_storage = FakePresetStorage()
    source_id = (
        await preset_storage.create(
            {
                "scope": "global",
                "owner_user_id": None,
                "name": "Global Persona",
                "system_prompt": "You assist.",
                "starter_prompts": [],
                "skill_names": [],
                "plugin_names": ["research-kit"],
                "mcp_server_names": ["arxiv"],
                "visibility": "public",
                "status": "published",
                "version": 3,
            }
        )
    )["id"]
    manager = PersonaPresetManager(
        storage=preset_storage,
        skill_storage=FakeSkillStorage(set()),
        plugin_storage=FakePluginStorage({}),
    )
    copied = await manager.copy_preset(source_id, user_id="user-1", is_admin=True)
    assert copied.plugin_names == ["research-kit"]
    assert copied.mcp_server_names == ["arxiv"]
