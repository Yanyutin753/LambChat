from __future__ import annotations

import pytest

from src.api.routes.agent import model as model_routes
from src.kernel.errors import AppError
from src.kernel.schemas.model import ModelConfig, ModelProfile
from src.kernel.schemas.user import TokenPayload


class _ModelStorage:
    async def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
        models = [
            ModelConfig(
                id="allowed-model",
                value="openai/gpt-allowed",
                provider="openai",
                icon="qwen",
                label="Allowed",
                description="Visible",
                profile=ModelProfile(supports_vision=True),
                api_key="sk-secret-allowed",
                api_base="https://api.example.test",
                temperature=0.2,
                max_tokens=1024,
                enabled=True,
                order=1,
            ),
            ModelConfig(
                id="blocked-model",
                value="openai/gpt-blocked",
                provider="openai",
                label="Blocked",
                description="Hidden",
                api_key="sk-secret-blocked",
                api_base="https://api.hidden.test",
                temperature=0.9,
                max_tokens=2048,
                enabled=True,
                order=2,
            ),
        ]
        if include_disabled:
            return models
        return [model for model in models if model.enabled]

    async def count(self) -> dict[str, int]:
        return {"total": 2, "enabled": 2}

    async def list_enabled_by_ids_or_values(
        self, model_ids_or_values: list[str]
    ) -> list[ModelConfig]:
        allowed = set(model_ids_or_values)
        return [
            model
            for model in await self.list_models(include_disabled=False)
            if model.id in allowed or model.value in allowed
        ]


class _RestrictedModelStorage(_ModelStorage):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
        raise AssertionError("restricted model listing should not load all enabled models")

    async def list_enabled_by_ids_or_values(
        self, model_ids_or_values: list[str]
    ) -> list[ModelConfig]:
        self.calls.append(model_ids_or_values)
        return [
            ModelConfig(
                id="allowed-model",
                value="openai/gpt-allowed",
                provider="openai",
                label="Allowed",
                enabled=True,
                order=1,
            )
        ]


class _AgentConfigStorage:
    async def get_role_models(self, role_id: str) -> list[str] | None:
        if role_id == "role-user":
            return ["allowed-model"]
        if role_id == "role-empty":
            return []
        return None


class _Role:
    id = "role-user"


class _EmptyRole:
    id = "role-empty"


class _RoleManager:
    async def get_role_by_name(self, role_name: str) -> _Role | _EmptyRole | None:
        if role_name == "user":
            return _Role()
        if role_name == "empty":
            return _EmptyRole()
        return None


@pytest.mark.asyncio
async def test_list_available_models_filters_by_role_allowed_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    assert [model.id for model in response.models] == ["allowed-model"]
    assert response.count == 1
    assert response.enabled_count == 1


@pytest.mark.asyncio
async def test_list_available_models_uses_bounded_lookup_for_restricted_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RestrictedModelStorage()
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    assert [model.id for model in response.models] == ["allowed-model"]
    assert storage.calls == [["allowed-model"]]


@pytest.mark.asyncio
async def test_list_available_models_returns_public_fields_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)
    payload = response.model_dump()

    assert payload["models"] == [
        {
            "id": "allowed-model",
            "value": "openai/gpt-allowed",
            "provider": "openai",
            "icon": "qwen",
            "label": "Allowed",
            "description": "Visible",
            "profile": {
                "max_input_tokens": None,
                "supports_vision": True,
                "image_url_to_base64": False,
            },
            "supports_thinking": False,
        }
    ]
    assert payload["default_model_id"] == "allowed-model"


@pytest.mark.asyncio
async def test_list_available_models_exposes_thinking_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ThinkingModelStorage(_ModelStorage):
        async def list_models(self, include_disabled: bool = False) -> list[ModelConfig]:
            return [
                ModelConfig(
                    id=m["id"],
                    value=m["value"],
                    provider=m["provider"],
                    label=m["id"],
                    enabled=True,
                    order=index,
                )
                for index, m in enumerate(
                    [
                        {"id": "gpt", "value": "openai/gpt-5.5", "provider": "openai"},
                        {"id": "glm", "value": "zhipu/glm-4.6", "provider": "zhipu"},
                        {"id": "glm-zai", "value": "glm-5.3", "provider": "zai"},
                        {"id": "claude", "value": "claude-opus-5", "provider": "anthropic"},
                        {"id": "gemini", "value": "gemini-2.5-flash", "provider": "google"},
                        {"id": "plain", "value": "deepseek-chat", "provider": "deepseek"},
                    ]
                )
            ]

    async def _no_model_restrictions(_user) -> list[str] | None:
        return None

    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ThinkingModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.model_access.resolve_user_allowed_model_ids",
        _no_model_restrictions,
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    capability = {model.id: model.supports_thinking for model in response.models}
    assert capability == {
        "gpt": True,
        "glm": True,
        "glm-zai": True,
        "claude": True,
        "gemini": True,
        "plain": False,
    }


@pytest.mark.asyncio
async def test_list_available_models_returns_empty_when_role_allows_no_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["empty"])

    response = await model_routes.list_available_models(user)

    assert response.models == []
    assert response.count == 0
    assert response.enabled_count == 0


@pytest.mark.asyncio
async def test_list_available_models_marks_effective_admin_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _AgentConfigStorage(),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager",
        lambda: _RoleManager(),
    )
    monkeypatch.setattr(
        "src.infra.llm.models_service.settings.DEFAULT_MODEL_ID",
        "blocked-model",
    )
    user = TokenPayload(sub="user-1", username="tester", roles=["user"])

    response = await model_routes.list_available_models(user)

    assert response.default_model_id == "allowed-model"


@pytest.mark.asyncio
async def test_import_models_rejects_large_batches_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def bulk_upsert_by_value(self, *_args, **_kwargs):
            raise AssertionError("large import should be rejected before storage access")

    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _StorageShouldNotBeCalled())

    with pytest.raises(AppError) as exc:
        await model_routes.import_models(
            [
                {
                    "value": f"provider/model-{index}",
                    "label": f"Model {index}",
                }
                for index in range(model_routes.MODEL_BATCH_MAX_ITEMS + 1)
            ],
            TokenPayload(sub="admin", username="admin", roles=["admin"]),
        )

    assert exc.value.error_code.code == "model_batch_limit"
    assert exc.value.http_status == 413


@pytest.mark.asyncio
async def test_batch_create_models_rejects_large_batches_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def create(self, *_args, **_kwargs):
            raise AssertionError("large batch should be rejected before storage access")

    monkeypatch.setattr(model_routes, "get_model_storage", lambda: _StorageShouldNotBeCalled())

    with pytest.raises(AppError) as exc:
        await model_routes.batch_create_models(
            {
                "shared": {},
                "models": [
                    {"value": f"provider/model-{index}", "label": f"Model {index}"}
                    for index in range(model_routes.MODEL_BATCH_MAX_ITEMS + 1)
                ],
            },
            TokenPayload(sub="admin", username="admin", roles=["admin"]),
        )

    assert exc.value.error_code.code == "model_batch_limit"
    assert exc.value.http_status == 413
