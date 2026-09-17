from __future__ import annotations

import pytest

from src.api.routes.chat import validate_agent_model_access
from src.infra.agent import model_access
from src.kernel.exceptions import AuthorizationError
from src.kernel.schemas.model import ModelConfig, ModelProfile
from src.kernel.schemas.user import TokenPayload


class _ModelStorage:
    async def get(self, model_id: str) -> ModelConfig | None:
        if model_id == "allowed-enabled":
            return ModelConfig(
                id=model_id,
                value="openai/gpt-allowed",
                label="Allowed",
                api_key="sk-secret",
                fallback_model="fallback-enabled",
                profile=ModelProfile(supports_vision=True, image_url_to_base64=True),
                enabled=True,
            )
        if model_id == "fallback-enabled":
            return ModelConfig(
                id=model_id,
                value="openai/gpt-fallback",
                label="Fallback",
                enabled=True,
            )
        if model_id == "blocked-enabled":
            return ModelConfig(
                id=model_id,
                value="openai/gpt-blocked",
                label="Blocked",
                enabled=True,
            )
        return None

    async def get_by_value(self, value: str) -> ModelConfig | None:
        if value == "openai/gpt-allowed":
            return ModelConfig(
                id="allowed-enabled",
                value=value,
                label="Allowed",
                enabled=True,
            )
        if value == "openai/gpt-blocked":
            return ModelConfig(
                id="blocked-enabled",
                value=value,
                label="Blocked",
                enabled=True,
            )
        return None


class _AgentConfigStorage:
    async def get_role_models(self, role_id: str) -> list[str] | None:
        if role_id == "role-user":
            return ["allowed-enabled"]
        if role_id == "role-empty":
            return []
        if role_id == "role-large":
            return [f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT + 25)]
        return None


class _Role:
    id = "role-user"


class _EmptyRole:
    id = "role-empty"


class _RoleManager:
    async def get_role_by_name(self, role_name: str) -> _Role | None:
        if role_name == "user":
            return _Role()
        if role_name == "empty":
            return _EmptyRole()
        if role_name == "large":
            return type("LargeRole", (), {"id": "role-large"})()
        return None


@pytest.mark.asyncio
async def test_validate_agent_model_access_rejects_model_id_outside_user_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _ModelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    with pytest.raises(AuthorizationError, match="model_not_allowed"):
        await validate_agent_model_access(
            {"model_id": "blocked-enabled"},
            user,
        )


@pytest.mark.asyncio
async def test_validate_agent_model_access_allows_role_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _ModelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    agent_options = {"model_id": "allowed-enabled"}

    await validate_agent_model_access(agent_options, user)

    assert agent_options["model"] == "openai/gpt-allowed"
    assert agent_options["_resolved_model_config"]["id"] == "allowed-enabled"
    assert agent_options["_resolved_model_config"]["api_key"] is None
    assert agent_options["_resolved_fallback_model"] == "openai/gpt-fallback"
    assert agent_options["_resolved_supports_vision"] is True
    assert agent_options["_resolved_image_url_mode"] == "base64"


@pytest.mark.asyncio
async def test_validate_agent_model_access_selects_role_default_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _ModelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])
    agent_options = {}

    await validate_agent_model_access(agent_options, user)

    assert agent_options["model_id"] == "allowed-enabled"
    assert agent_options["model"] == "openai/gpt-allowed"


@pytest.mark.asyncio
async def test_validate_agent_model_access_rejects_when_role_allows_no_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: _ModelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["empty"])

    with pytest.raises(AuthorizationError, match="model_not_allowed"):
        await validate_agent_model_access(
            {"model_id": "allowed-enabled"},
            user,
        )


@pytest.mark.asyncio
async def test_resolve_user_allowed_model_ids_caps_large_role_model_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["large"])

    allowed = await model_access.resolve_user_allowed_model_ids(user)

    assert allowed == [f"model-{index}" for index in range(model_access.ROLE_MODEL_ACCESS_LIMIT)]
