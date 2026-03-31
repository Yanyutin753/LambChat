from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.agents.fast_agent.context import FastAgentContext
from src.api.routes import marketplace as marketplace_routes
from src.api.routes import skill as skill_routes
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.storage import SkillStorage
from src.infra.skill.types import InstalledFrom
from src.kernel.schemas.user import TokenPayload


@pytest.mark.asyncio
async def test_toggle_user_skill_rejects_missing_skill(monkeypatch):
    storage = AsyncMock()
    storage.list_skill_file_paths.return_value = []

    user_storage = AsyncMock()
    user_storage.get_by_id.return_value = SimpleNamespace(metadata={})

    monkeypatch.setattr(skill_routes, "UserStorage", lambda: user_storage)

    user = TokenPayload(sub="user-1", username="tester")

    with pytest.raises(HTTPException) as exc_info:
        await skill_routes.toggle_user_skill("missing-skill", None, user, storage)

    assert exc_info.value.status_code == 404
    assert "missing-skill" in exc_info.value.detail
    user_storage.update_metadata.assert_not_awaited()
    storage.invalidate_user_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_toggle_skills_rejects_missing_skills(monkeypatch):
    storage = AsyncMock()
    storage.list_skill_file_paths.side_effect = [["SKILL.md"], []]

    user_storage = AsyncMock()
    user_storage.get_by_id.return_value = SimpleNamespace(metadata={})

    monkeypatch.setattr(skill_routes, "UserStorage", lambda: user_storage)

    user = TokenPayload(sub="user-1", username="tester")
    body = skill_routes.BatchToggleRequest(names=["existing-skill", "missing-skill"], enabled=False)

    with pytest.raises(HTTPException) as exc_info:
        await skill_routes.batch_toggle_skills(body, user, storage)

    assert exc_info.value.status_code == 404
    assert "missing-skill" in exc_info.value.detail
    user_storage.update_metadata.assert_not_awaited()
    storage.invalidate_user_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_effective_skills_uses_user_disabled_metadata_when_not_provided(monkeypatch):
    storage = SkillStorage()

    fake_redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
    )

    async def fake_get_by_id(_user_id):
        return SimpleNamespace(metadata={"disabled_skills": ["disabled-skill"]})

    monkeypatch.setattr("src.infra.storage.redis.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage.get_by_id",
        fake_get_by_id,
    )

    async def fake_get_all_user_skill_names(self, user_id):
        assert user_id == "user-1"
        return ["enabled-skill", "disabled-skill"]

    async def fake_batch_get_skill_files(self, skill_keys):
        return {
            ("enabled-skill", "user-1"): {"SKILL.md": "---\ndescription: enabled\n---\n"},
        }

    monkeypatch.setattr(SkillStorage, "get_all_user_skill_names", fake_get_all_user_skill_names)
    monkeypatch.setattr(SkillStorage, "batch_get_skill_files", fake_batch_get_skill_files)

    result = await storage.get_effective_skills("user-1")

    assert sorted(result["skills"].keys()) == ["enabled-skill"]
    fake_redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_fast_agent_context_respects_disabled_skills(monkeypatch):
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_SKILLS", True)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_MCP", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_MEMORY", False)

    monkeypatch.setattr("src.agents.fast_agent.context.get_human_tool", lambda session_id: "human")
    monkeypatch.setattr("src.agents.fast_agent.context.get_reveal_file_tool", lambda: "reveal_file")
    monkeypatch.setattr(
        "src.agents.fast_agent.context.get_reveal_project_tool",
        lambda: "reveal_project",
    )

    manager = AsyncMock()
    manager.get_effective_skills.return_value = {
        "enabled-skill": {
            "name": "enabled-skill",
            "description": "enabled",
            "files": {"SKILL.md": "# Enabled"},
            "enabled": True,
        }
    }
    monkeypatch.setattr("src.agents.fast_agent.context.SkillManager", lambda user_id: manager)

    context = FastAgentContext(user_id="user-1")
    await context.setup()

    assert [skill["name"] for skill in context.skills] == ["enabled-skill"]
    manager.get_effective_skills.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_from_marketplace_rejects_manual_skill_copy():
    storage = AsyncMock()
    storage.get_skill_meta.return_value = SimpleNamespace(
        installed_from=InstalledFrom.MANUAL,
        published_marketplace_name=None,
    )

    marketplace = AsyncMock()
    marketplace.get_marketplace_skill.return_value = SimpleNamespace(
        skill_name="shared-skill",
        is_active=True,
    )

    user = TokenPayload(sub="user-1", username="tester")

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_routes.update_from_marketplace(
            "shared-skill",
            user,
            marketplace,
            storage,
        )

    assert exc_info.value.status_code == 409
    storage.sync_skill_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_marketplace_skill_rejects_manual_name_conflict():
    storage = AsyncMock()
    storage.get_skill_meta.return_value = SimpleNamespace(
        installed_from=InstalledFrom.MANUAL,
        published_marketplace_name=None,
    )

    marketplace = AsyncMock()
    marketplace.get_marketplace_skill.return_value = SimpleNamespace(
        skill_name="shared-skill",
        is_active=True,
    )

    user = TokenPayload(sub="user-1", username="tester")

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_routes.install_marketplace_skill(
            "shared-skill",
            user,
            marketplace,
            storage,
        )

    assert exc_info.value.status_code == 409
    storage.create_user_skill.assert_not_awaited()


@pytest.mark.asyncio
async def test_marketplace_username_lookup_uses_object_id(monkeypatch):
    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        def __aiter__(self):
            self._iter = iter(self._docs)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    captured_query = {}

    class FakeCollection:
        def find(self, query, projection):
            captured_query["query"] = query
            captured_query["projection"] = projection
            return FakeCursor([{"_id": "507f1f77bcf86cd799439011", "username": "alice"}])

    storage = MarketplaceStorage()
    monkeypatch.setattr(storage, "_get_users_collection", lambda: FakeCollection())

    result = await storage._batch_get_usernames(["507f1f77bcf86cd799439011"])

    assert result == {"507f1f77bcf86cd799439011": "alice"}
    assert "_id" in captured_query["query"]


def test_marketplace_build_response_defaults_null_version():
    storage = MarketplaceStorage()

    response = storage._build_response(
        {
            "skill_name": "shared-skill",
            "description": "demo",
            "tags": ["utility"],
            "version": None,
            "created_by": "user-1",
            "is_active": True,
        },
        file_count=3,
        username_map={"user-1": "alice"},
        viewer_id="user-1",
    )

    assert response.version == "1.0.0"
