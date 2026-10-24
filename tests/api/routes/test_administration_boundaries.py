"""Configuration maintenance does not imply pricing or unbounded delegation."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.routes.agent import config as config_routes
from src.api.routes.agent import model as model_routes
from src.kernel.schemas.model import ModelConfig, mask_api_key
from src.kernel.schemas.role import Role
from src.kernel.schemas.user import TokenPayload


@pytest.fixture
def admin_case(monkeypatch):
    actor = TokenPayload(
        sub="operator",
        username="operator",
        roles=["operator"],
        permissions=["model:admin", "model:assign", "agent:assign"],
        assignable_role_ids=["target-id"],
    )
    target = Role(id="target-id", name="target", permissions=[])
    own = Role(id="operator-id", name="operator", permissions=[], allowed_agents=["search"])
    saved = []
    model = ModelConfig(
        id="m1",
        value="model-1",
        label="First",
        api_key="super-secret-key",
        request_headers={"Authorization": "Bearer private", "x-app": "app"},
    )

    class Roles:
        async def get_role(self, role_id):
            return target.model_copy(update={"id": role_id})

        async def get_roles_by_names(self, names):
            return [own] if names == ["operator"] else []

    class Config:
        async def set_role_agents(self, role_id, name, values):
            saved.append({"agents": values})
            return values

        async def set_role_models(self, role_id, name, values, **kwargs):
            saved.append({"models": values, **kwargs})
            return values

        async def get_role_agents_by_ids(self, ids):
            return {"operator-id": ["search"]}

        async def get_role_models_by_ids(self, ids):
            return {"operator-id": ["m1"]}

        async def get_catalog_config(self):
            return []

        async def get_global_config(self):
            return []

        async def set_catalog_config(self, values):
            saved.append({"catalog": values})
            return values

    class Models:
        async def list_enabled_by_ids_or_values(self, values):
            return [model] if "m1" in values else []

        async def get(self, model_id):
            return model if model_id == "m1" else None

        async def update(self, model_id, data):
            saved.append(data)
            return model.model_copy(update=data)

        async def create(self, data):
            saved.append(data.model_dump())
            return data

    @asynccontextmanager
    async def mutation(_):
        yield actor

    storage = Config()
    monkeypatch.setattr(config_routes, "get_role_manager", Roles)
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes, "authority_mutation", mutation, raising=False)
    monkeypatch.setattr(
        config_routes.AgentFactory,
        "list_agents",
        lambda *args: [{"id": "search", "name": "Search"}],
    )
    monkeypatch.setattr(config_routes, "list_registered_agents", lambda: ["search", "team"])
    monkeypatch.setattr(model_routes, "get_model_storage", Models)
    monkeypatch.setattr("src.infra.agent.model_storage.get_model_storage", Models)
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", AsyncMock())
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    monkeypatch.setattr("src.infra.role.manager.get_role_manager", Roles)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(config_routes.router, prefix="/config")
    app.include_router(model_routes.router, prefix="/models")
    app.dependency_overrides[deps.get_current_user_required] = lambda: actor
    return SimpleNamespace(app=app, actor=actor, own=own, target=target, saved=saved, model=model)


async def call(case, method, path, body=None):
    async with AsyncClient(transport=ASGITransport(app=case.app), base_url="http://test") as client:
        return await client.request(method, path, json=body)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", "/models/m1", {"pricing": {"input": 1}}),
        ("PUT", "/models/m1", {"pricing": {}}),
        ("POST", "/models/", {"value": "new-model", "label": "New", "pricing": {"input": 1}}),
        (
            "POST",
            "/models/import",
            [{"value": "new-model", "label": "New", "pricing": {"input": 1}}],
        ),
    ],
)
async def test_model_maintainer_cannot_change_billing_prices(admin_case, method, path, body):
    response = await call(admin_case, method, path, body)
    assert response.status_code == 403
    assert admin_case.saved == []


async def test_masked_credentials_survive_unrelated_configuration_save(admin_case):
    visible = mask_api_key(admin_case.model)
    response = await call(
        admin_case,
        "PUT",
        "/models/m1",
        {
            "label": "Renamed",
            "api_key": visible.api_key,
            "request_headers": visible.request_headers,
        },
    )
    assert response.status_code == 200
    stored = admin_case.saved[0]
    assert stored.get("api_key", admin_case.model.api_key) == "super-secret-key"
    assert stored["request_headers"] == {"Authorization": "Bearer private", "x-app": "app"}
    assert "Bearer private" not in response.text


@pytest.mark.parametrize(
    "suffix,body", [("", {"allowed_agents": ["search"]}), ("/models", {"allowed_models": ["m1"]})]
)
async def test_assignment_cannot_target_unscoped_role(admin_case, suffix, body):
    response = await call(admin_case, "PUT", "/config/roles/unscoped" + suffix, body)
    assert response.status_code == 403
    assert admin_case.saved == []


@pytest.mark.parametrize(
    "suffix,body", [("", {"allowed_agents": ["team"]}), ("/models", {"allowed_models": ["m2"]})]
)
async def test_assignment_cannot_grant_access_caller_does_not_have(admin_case, suffix, body):
    response = await call(admin_case, "PUT", "/config/roles/target-id" + suffix, body)
    assert response.status_code == 403
    assert admin_case.saved == []


async def test_restricted_delegator_cannot_grant_unrestricted_models(admin_case):
    response = await call(
        admin_case,
        "PUT",
        "/config/roles/target-id/models",
        {"allowed_models": [], "unrestricted_models": True},
    )
    assert response.status_code == 403
    assert admin_case.saved == []


async def test_explicit_empty_model_assignment_clears_unrestricted_access(admin_case):
    admin_case.target.unrestricted_models = True
    response = await call(
        admin_case,
        "PUT",
        "/config/roles/target-id/models",
        {"allowed_models": [], "unrestricted_models": False},
    )
    assert response.status_code == 200
    assert response.json()["unrestricted_models"] is False
    assert admin_case.saved == [{"models": [], "unrestricted_models": False}]


async def test_agent_catalog_reader_does_not_persist_configuration(admin_case):
    admin_case.actor.permissions = ["agent:config_read"]
    response = await call(admin_case, "GET", "/config/catalog")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["agents"]] == ["search"]
    assert admin_case.saved == []


@pytest.mark.parametrize(
    "permissions,method,path,body",
    [
        (["settings:read"], "PUT", "/settings/APP_NAME", {"value": "changed"}),
        (["settings:manage"], "PUT", "/settings/ENABLE_REGISTRATION", {"value": True}),
        (["settings:security"], "PUT", "/settings/DEFAULT_USER_ROLE", {"value": "admin"}),
        (["settings:reset", "settings:security"], "POST", "/settings/init", None),
        (["settings:reset"], "POST", "/settings/reset/JWT_SECRET_KEY", None),
        (["settings:manage", "settings:reset"], "POST", "/settings/reset", {"confirmed": True}),
        (["notification:read"], "POST", "/notifications/", {"title": "Test", "content": "Test"}),
        (["notification:manage"], "DELETE", "/notifications/507f1f77bcf86cd799439011", None),
        (["feedback:read"], "DELETE", "/feedback/507f1f77bcf86cd799439011", None),
        (["feedback:admin"], "GET", "/feedback/", None),
    ],
)
async def test_read_and_maintenance_duties_do_not_imply_sensitive_mutation(
    permissions, method, path, body
):
    from src.api.routes import feedback, notification, settings
    from src.infra.settings.service import get_settings_service

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(settings.router, prefix="/settings")
    app.include_router(notification.router, prefix="/notifications")
    app.include_router(feedback.router, prefix="/feedback")
    app.dependency_overrides[deps.get_current_user_required] = lambda: TokenPayload(
        sub="operator", username="operator", permissions=permissions
    )
    app.dependency_overrides[get_settings_service] = lambda: None
    app.dependency_overrides[notification.get_notification_manager] = lambda: None
    app.dependency_overrides[feedback.get_feedback_manager] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == 403


async def test_model_id_grant_cannot_be_expanded_to_all_channels_by_value(admin_case):
    response = await call(
        admin_case,
        "PUT",
        "/config/roles/target-id/models",
        {"allowed_models": ["model-1"]},
    )
    assert response.status_code == 403
    assert admin_case.saved == []


async def test_model_assigner_can_read_assignable_public_models_without_agent_read(admin_case):
    response = await call(admin_case, "GET", "/models/available")
    assert response.status_code == 200
    assert response.json()["models"][0]["id"] == "m1"
    assert "super-secret-key" not in response.text
