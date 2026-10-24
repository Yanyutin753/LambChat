"""Authorization must reject before contacting storage or starting an Agent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import agent, mcp, settings, usage
from src.infra.agent.model_access import resolve_user_allowed_model_ids
from src.kernel.schemas.permission import get_permissions_response
from src.kernel.schemas.user import TokenPayload
from src.kernel.types import Permission


def app_for(router, permissions):
    app = FastAPI()
    app.include_router(router, prefix="/resource")
    register_error_handlers(app)
    app.dependency_overrides[deps.get_current_user_required] = lambda: TokenPayload(
        sub="owner", username="owner", roles=["user"], permissions=permissions
    )
    return app


@pytest.mark.parametrize(
    "method,body", [("DELETE", None), ("PUT", {"url": "https://example.com/new"})]
)
async def test_mcp_reader_cannot_modify_configuration(method, body):
    storage = SimpleNamespace(
        delete_user_server=AsyncMock(return_value=True),
        get_user_server=AsyncMock(return_value=SimpleNamespace(transport="streamable_http")),
        update_user_server=AsyncMock(
            return_value=SimpleNamespace(
                name="server",
                transport="streamable_http",
                enabled=True,
                url="https://example.com",
                headers={},
                created_at=None,
                updated_at=None,
            )
        ),
    )
    app = app_for(mcp.router, ["mcp:read"])
    app.dependency_overrides[mcp.get_mcp_storage] = lambda: storage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, "/resource/server", json=body)
    assert response.status_code == 403
    storage.delete_user_server.assert_not_awaited()
    storage.update_user_server.assert_not_awaited()


async def test_global_usage_reader_cannot_reset_quota(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(usage, "_active_quota_target", check)
    app = app_for(usage.router, ["usage:admin"])
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post(
            "/resource/users/target/quota/reset",
            json={
                "window": "five_hour",
                "idempotency_key": "5c8bf234-714d-4cec-bd5c-aa3a8c675809",
            },
        )
    assert response.status_code == 403
    check.assert_not_awaited()


async def test_settings_maintainer_cannot_change_authentication_secrets():
    service = SimpleNamespace(set=AsyncMock(return_value=None))
    app = app_for(settings.router, ["settings:manage"])
    app.dependency_overrides[settings.get_settings_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/resource/ENABLE_REGISTRATION", json={"value": True})
    assert response.status_code == 403
    service.set.assert_not_awaited()


async def test_legacy_chat_cannot_dispatch_without_chat_permission(monkeypatch):
    get_agent = AsyncMock(return_value=SimpleNamespace(invoke=AsyncMock(return_value="unsafe")))
    monkeypatch.setattr(agent.AgentFactory, "get", get_agent)
    app = app_for(agent.router, [])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/resource/quick/chat", json={"message": "hello", "session_id": "foreign"}
        )
    assert response.status_code in {403, 404, 410}
    get_agent.assert_not_awaited()


async def test_no_roles_cannot_resolve_unrestricted_models():
    assert await resolve_user_allowed_model_ids(TokenPayload(sub="u", username="u")) == []


def test_retired_permissions_are_not_in_editable_catalog():
    values = {p.value for p in get_permissions_response().all_permissions}
    assert values.isdisjoint({"chat:read", "session:admin", "skill:admin", "role:manage"})


def test_permission_catalog_exposes_distinct_administrative_duties():
    values = {p.value for p in Permission}
    assert {
        "user:create",
        "user:assign_roles",
        "role:grant",
        "usage:quota_manage",
        "settings:security",
        "mcp:export",
        "envvar:reveal",
        "model:assign",
    } <= values
