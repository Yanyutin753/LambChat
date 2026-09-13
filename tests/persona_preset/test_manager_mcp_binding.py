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


class FakeMCPStorage:
    def __init__(self, visible_names: set[str]) -> None:
        self._visible = visible_names

    async def get_visible_servers(self, user_id, is_admin=False, user_roles=None, limit=None):
        return [type("S", (), {"name": n})() for n in sorted(self._visible)]


class FakeSkillStorage:
    def __init__(self, names: set[str]) -> None:
        self._names = names

    async def get_effective_skills(self, user_id: str) -> dict:
        return {"skills": {name: {} for name in self._names}}

    async def get_all_user_skill_names(self, user_id: str) -> list[str]:
        return sorted(self._names)

    async def close(self) -> None:
        return None


def _make_manager(
    skill_names: set[str],
    visible_mcp: set[str] | None = None,
    quota_admin: bool = False,
) -> PersonaPresetManager:
    import src.infra.mcp.quota as quota_module

    original = quota_module.resolve_user_mcp_access

    async def _fake_resolve(user_id: str):
        return ["user"], quota_admin

    quota_module.resolve_user_mcp_access = _fake_resolve
    manager = PersonaPresetManager(
        storage=FakePresetStorage(),
        skill_storage=FakeSkillStorage(skill_names),
        mcp_storage=FakeMCPStorage(visible_mcp or set()),
    )
    manager.__dict__["_restore_quota"] = lambda: setattr(
        quota_module, "resolve_user_mcp_access", original
    )
    return manager


async def test_use_preset_passes_mcp_whitelist_into_snapshot() -> None:
    manager = _make_manager({"own-skill"}, visible_mcp={"arxiv", "weather"})
    try:
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
    finally:
        manager.__dict__["_restore_quota"]()

    # 技能/MCP 均与用户实际可用集合求交集，缺失分别记录
    assert snapshot.skill_names == ["own-skill"]
    assert snapshot.missing_skill_names == ["gone-skill"]
    assert snapshot.mcp_server_names == ["arxiv", "weather"]
    assert snapshot.missing_mcp_server_names == []


async def test_use_preset_drops_invisible_mcp_and_records_missing() -> None:
    manager = _make_manager(set(), visible_mcp={"arxiv"})
    try:
        preset_id = (
            await manager.storage.create(
                {
                    "scope": "user",
                    "owner_user_id": "user-1",
                    "name": "Partial",
                    "system_prompt": "You chat.",
                    "starter_prompts": [],
                    "skill_names": [],
                    "mcp_server_names": ["arxiv", "ghost"],
                    "visibility": "private",
                    "status": "published",
                    "version": 1,
                }
            )
        )["id"]
        snapshot = await manager.use_preset(preset_id, user_id="user-1", is_admin=False)
    finally:
        manager.__dict__["_restore_quota"]()
    assert snapshot.mcp_server_names == ["arxiv"]
    assert snapshot.missing_mcp_server_names == ["ghost"]


async def test_use_preset_all_mcp_missing_keeps_lenient_no_whitelist() -> None:
    """全缺放行：绑定的 MCP 一个都不可见时快照白名单为空（请求侧回落为不限制）。"""
    from src.api.routes.chat_request_config import (
        _persona_enabled_mcp_servers_from_snapshot,
    )

    manager = _make_manager(set(), visible_mcp=set())
    try:
        preset_id = (
            await manager.storage.create(
                {
                    "scope": "user",
                    "owner_user_id": "user-1",
                    "name": "Ghost",
                    "system_prompt": "You chat.",
                    "starter_prompts": [],
                    "skill_names": [],
                    "mcp_server_names": ["ghost"],
                    "visibility": "private",
                    "status": "published",
                    "version": 1,
                }
            )
        )["id"]
        snapshot = await manager.use_preset(preset_id, user_id="user-1", is_admin=False)
    finally:
        manager.__dict__["_restore_quota"]()
    assert snapshot.mcp_server_names == []
    assert snapshot.missing_mcp_server_names == ["ghost"]
    assert _persona_enabled_mcp_servers_from_snapshot(snapshot) is None


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
