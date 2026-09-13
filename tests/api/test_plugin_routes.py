from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.api.routes import plugin as plugin_routes
from src.infra.plugin.types import PluginCreate
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


def _user(perms: list[str]) -> TokenPayload:
    return TokenPayload(sub="user-1", username="tester", roles=["user"], permissions=perms)


def _plugin_doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": "research-kit",
        "display_name": "Research Kit",
        "description": "Research toolset",
        "version": "1.0.0",
        "author_name": "",
        "tags": ["research"],
        "skills": [{"skill_name": "deep-research", "description": "Deep", "tags": ["research"]}],
        "mcp_servers": [
            {"name": "arxiv", "transport": "streamable_http", "url": "https://arxiv", "ref": False}
        ],
        "persona": None,
        "status": "active",
        "created_by": "user-1",
        "install_count": 0,
    }
    doc.update(overrides)
    return doc


class FakePluginStorage:
    def __init__(self, docs: dict[str, dict[str, Any]]) -> None:
        self.docs = docs
        self.installs: dict[tuple[str, str], str] = {}
        self.install_counts: dict[str, int] = {}

    async def plugin_name_exists(self, name: str) -> bool:
        return name in self.docs

    async def get_plugin_doc(self, name: str) -> dict[str, Any] | None:
        doc = self.docs.get(name)
        return dict(doc) if doc else None

    async def create_plugin(self, doc: dict[str, Any]) -> dict[str, Any]:
        self.docs[doc["name"]] = doc
        return doc

    async def get_plugin_response(self, name, **_kwargs):
        doc = self.docs.get(name)
        if not doc:
            return None
        return SimpleNamespace(name=name, status=doc.get("status"))

    async def get_install(self, user_id: str, plugin_name: str):
        version = self.installs.get((user_id, plugin_name))
        if version is None:
            return None
        return SimpleNamespace(version=version)

    async def upsert_install(self, user_id: str, plugin_name: str, version: str) -> None:
        self.installs[(user_id, plugin_name)] = version

    async def delete_install(self, user_id: str, plugin_name: str) -> bool:
        return self.installs.pop((user_id, plugin_name), None) is not None

    async def increment_install_count(self, plugin_name: str) -> None:
        self.install_counts[plugin_name] = self.install_counts.get(plugin_name, 0) + 1

    async def list_skill_file_paths(self, plugin_name: str, skill_name: str):
        return ["SKILL.md"]

    async def iter_skill_file_batches(self, plugin_name: str, skill_name: str):
        yield {"SKILL.md": "# Plugin skill"}

    async def set_plugin_status(self, name: str, status):
        self.docs[name]["status"] = status.value
        return self.docs[name]


class FakeSkillStorage:
    def __init__(self) -> None:
        self.synced: list[tuple[str, dict[str, str], str]] = []
        self.meta_calls: list[tuple[str, str, str]] = []
        self.invalidated: list[str] = []

    async def sync_skill_files(self, name, files, user_id):
        self.synced.append((name, files, user_id))

    async def set_skill_meta(self, name, user_id, installed_from):
        self.meta_calls.append((name, user_id, installed_from))

    async def invalidate_user_cache(self, user_id):
        self.invalidated.append(user_id)


@pytest.fixture()
def persona_stub(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    created: list[dict] = []

    async def _fake_install_persona(plugin_doc, user_id):
        if plugin_doc.get("persona"):
            created.append({"plugin": plugin_doc["name"], "user": user_id})
            return True
        return False

    monkeypatch.setattr(plugin_routes, "_install_plugin_persona", _fake_install_persona)
    return created


async def test_install_plugin_syncs_skills_and_records_install(persona_stub) -> None:
    storage = FakePluginStorage({"research-kit": _plugin_doc()})
    skills = FakeSkillStorage()
    response = await plugin_routes.install_plugin(
        "research-kit", user=_user(["marketplace:read"]), storage=storage, skill_storage=skills
    )
    assert response.installed_skills == ["deep-research"]
    assert skills.synced == [("deep-research", {"SKILL.md": "# Plugin skill"}, "user-1")]
    assert skills.meta_calls == [("deep-research", "user-1", "plugin")]
    assert skills.invalidated == ["user-1"]
    assert storage.installs == {("user-1", "research-kit"): "1.0.0"}
    assert storage.install_counts == {"research-kit": 1}


async def test_install_plugin_rejects_inactive() -> None:
    storage = FakePluginStorage({"research-kit": _plugin_doc(status="deactivated")})
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.install_plugin(
            "research-kit",
            user=_user(["marketplace:read"]),
            storage=storage,
            skill_storage=FakeSkillStorage(),
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_INACTIVE


async def test_install_plugin_rejects_duplicate() -> None:
    storage = FakePluginStorage({"research-kit": _plugin_doc()})
    storage.installs[("user-1", "research-kit")] = "1.0.0"
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.install_plugin(
            "research-kit",
            user=_user(["marketplace:read"]),
            storage=storage,
            skill_storage=FakeSkillStorage(),
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_ALREADY_INSTALLED


async def test_uninstall_plugin_requires_prior_install() -> None:
    storage = FakePluginStorage({"research-kit": _plugin_doc()})
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.uninstall_plugin(
            "research-kit", user=_user(["marketplace:read"]), storage=storage
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_NOT_INSTALLED


async def test_create_plugin_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FakePluginStorage({"research-kit": _plugin_doc()})
    data = PluginCreate(
        name="research-kit",
        skills=[{"skill_name": "deep-research", "description": "", "tags": []}],
    )
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.create_plugin(
            data, user=_user(["marketplace:publish"]), storage=storage
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_NAME_EXISTS


async def test_create_plugin_without_admin_lands_as_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_materialize(*_args, **_kwargs):
        return []

    monkeypatch.setattr(plugin_routes, "materialize_plugin_mcp", _no_materialize)
    storage = FakePluginStorage({})
    data = PluginCreate(
        name="fresh-kit",
        activate=True,  # 非 admin：activate 被忽略，落为 draft
        skills=[{"skill_name": "s", "description": "", "tags": []}],
    )
    await plugin_routes.create_plugin(data, user=_user(["marketplace:publish"]), storage=storage)
    assert storage.docs["fresh-kit"]["status"] == "draft"


async def test_activate_rejects_empty_skill_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """声明了技能但没有任何负载文件时不可激活（防呆空技能）。"""

    class _EmptyFilesStorage(FakePluginStorage):
        async def list_skill_file_paths(self, plugin_name: str, skill_name: str):
            return []

    storage = _EmptyFilesStorage({"empty-kit": _plugin_doc(name="empty-kit", status="draft")})
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.activate_plugin(
            "empty-kit",
            plugin_routes.SetPluginActiveRequest(is_active=True),
            user=_user(["marketplace:admin"]),
            storage=storage,
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_INVALID_PAYLOAD
    assert storage.docs["empty-kit"]["status"] == "draft"


async def test_update_install_checks_before_status() -> None:
    """update 先查安装记录（not_installed），再查激活状态（inactive）。"""
    storage = FakePluginStorage({"research-kit": _plugin_doc()})
    storage.docs["research-kit"]["status"] = "draft"

    with pytest.raises(AppError) as excinfo:
        await plugin_routes.update_plugin_install(
            "research-kit",
            user=_user(["marketplace:read"]),
            storage=storage,
            skill_storage=FakeSkillStorage(),
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_NOT_INSTALLED

    storage.installs[("user-1", "research-kit")] = "1.0.0"
    with pytest.raises(AppError) as excinfo:
        await plugin_routes.update_plugin_install(
            "research-kit",
            user=_user(["marketplace:read"]),
            storage=storage,
            skill_storage=FakeSkillStorage(),
        )
    assert excinfo.value.error_code == ErrorCode.PLUGIN_INACTIVE
