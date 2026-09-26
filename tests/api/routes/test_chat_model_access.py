from __future__ import annotations

import pytest

from src.api.routes.chat import validate_agent_model_access
from src.infra.agent import model_access
from src.kernel.exceptions import AuthorizationError
from src.kernel.schemas.model import ModelConfig, ModelProfile
from src.kernel.schemas.user import TokenPayload


class _ModelStorage:
    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []

    async def get_many_by_ids_and_values(
        self, model_ids_or_values: list[str]
    ) -> tuple[dict[str, ModelConfig], dict[str, ModelConfig]]:
        self.batch_calls.append(list(model_ids_or_values))
        by_id: dict[str, ModelConfig] = {}
        by_value: dict[str, ModelConfig] = {}
        for allowed_id in model_ids_or_values:
            model = await self.get(allowed_id)
            if model is not None:
                by_id[allowed_id] = model
            by_value_model = await self.get_by_value(allowed_id)
            if by_value_model is not None and by_value_model.enabled:
                by_value.setdefault(allowed_id, by_value_model)
        return by_id, by_value

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
        if model_id == "disabled-model":
            return ModelConfig(
                id=model_id,
                value="openai/gpt-disabled",
                label="Disabled",
                enabled=False,
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
        if role_id == "role-multi":
            return ["allowed-enabled", "blocked-enabled", "by-value-only"]
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
        if role_name == "multi":
            return type("MultiRole", (), {"id": "role-multi"})()
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


def _apply_storage_monkeypatches(monkeypatch: pytest.MonkeyPatch, storage: _ModelStorage) -> None:
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )


@pytest.mark.asyncio
async def test_default_model_branch_uses_single_batch_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _ModelStorage()
    _apply_storage_monkeypatches(monkeypatch, storage)
    user = TokenPayload(sub="user-1", username="tester", roles=["multi"])
    agent_options = {}

    await validate_agent_model_access(agent_options, user)

    # 单次批量查询解析默认模型，而不是对 allowed 列表逐个 get/get_by_value
    assert storage.batch_calls == [["allowed-enabled", "blocked-enabled", "by-value-only"]]
    assert agent_options["model_id"] == "allowed-enabled"
    assert agent_options["model"] == "openai/gpt-allowed"


@pytest.mark.asyncio
async def test_default_model_branch_falls_through_disabled_id_to_next_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _ModelStorage()

    async def _get(model_id: str) -> ModelConfig | None:
        if model_id == "allowed-enabled":
            # id 命中但禁用：语义上不得回落到 value 查找，应跳到下一个 allowed
            return ModelConfig(
                id=model_id, value="openai/gpt-allowed", label="Allowed", enabled=False
            )
        if model_id == "blocked-enabled":
            return ModelConfig(
                id=model_id, value="openai/gpt-blocked", label="Blocked", enabled=True
            )
        return None

    async def _get_by_value(value: str) -> ModelConfig | None:
        if value == "openai/gpt-allowed":
            return ModelConfig(id="allowed-enabled", value=value, label="Allowed", enabled=True)
        return None

    storage.get = _get  # type: ignore[method-assign]
    storage.get_by_value = _get_by_value  # type: ignore[method-assign]
    _apply_storage_monkeypatches(monkeypatch, storage)
    user = TokenPayload(sub="user-1", username="tester", roles=["multi"])
    agent_options = {}

    await validate_agent_model_access(agent_options, user)

    assert agent_options["model_id"] == "blocked-enabled"
    assert agent_options["model"] == "openai/gpt-blocked"


@pytest.mark.asyncio
async def test_default_model_branch_resolves_value_only_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _ModelStorage()

    async def _get(model_id: str) -> ModelConfig | None:
        if model_id in ("allowed-enabled", "blocked-enabled"):
            # allowed 前两个 id 均未命中，应回落到 value 查找再继续列表
            return None
        if model_id == "by-value-only":
            return None
        return None

    async def _get_by_value(value: str) -> ModelConfig | None:
        if value == "by-value-only":
            return ModelConfig(id="value-only-1", value=value, label="ValueOnly", enabled=True)
        return None

    storage.get = _get  # type: ignore[method-assign]
    storage.get_by_value = _get_by_value  # type: ignore[method-assign]
    _apply_storage_monkeypatches(monkeypatch, storage)
    user = TokenPayload(sub="user-1", username="tester", roles=["multi"])
    agent_options = {}

    await validate_agent_model_access(agent_options, user)

    assert agent_options["model_id"] == "value-only-1"
    assert agent_options["model"] == "by-value-only"


@pytest.mark.asyncio
async def test_validate_agent_model_access_missing_model_reports_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式选择的模型已被删除时报 model_not_found，而非误导性的 model_disabled。"""
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

    with pytest.raises(AuthorizationError, match="model_not_found"):
        await validate_agent_model_access(
            {"model_id": "deleted-model", "model": "openai/gpt-deleted"},
            user,
        )


@pytest.mark.asyncio
async def test_validate_agent_model_access_disabled_model_reports_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型存在但 enabled=False 时保持 model_disabled 语义不变。"""
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

    with pytest.raises(AuthorizationError, match="model_disabled"):
        await validate_agent_model_access(
            {"model_id": "disabled-model"},
            user,
        )
