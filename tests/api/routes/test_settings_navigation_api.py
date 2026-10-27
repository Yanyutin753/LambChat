from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_current_user_required
from src.api.error_handlers import register_error_handlers
from src.api.routes.settings import router
from src.infra.settings.service import get_settings_service
from src.kernel.schemas.setting import SettingCategory, SettingItem, SettingType
from src.kernel.schemas.user import TokenPayload


@pytest.fixture
def settings_app():
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/settings")
    service = AsyncMock()
    service.reset.return_value = 2
    user = TokenPayload(
        sub="test",
        username="test",
        permissions=[
            "settings:read",
            "settings:manage",
            "settings:reset",
            "settings:security",
            "system:admin",
        ],
    )
    app.dependency_overrides[get_current_user_required] = lambda: user
    app.dependency_overrides[get_settings_service] = lambda: service
    return app, service, user


@pytest.mark.parametrize(
    "body", [None, {}, {"confirmed": False}, {"confirmed": "true"}, {"confirmed": 1}]
)
async def test_reset_all_rejects_requests_without_explicit_boolean_confirmation(settings_app, body):
    app, service, _ = settings_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/settings/reset", json=body)
    assert response.status_code == 422
    service.reset.assert_not_awaited()


async def test_confirmed_reset_still_requires_management_permission(settings_app):
    app, service, user = settings_app
    user.permissions = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/settings/reset", json={"confirmed": True})
    assert response.status_code == 403
    service.reset.assert_not_awaited()


async def test_confirmed_admin_reset_runs_once(settings_app):
    app, service, _ = settings_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/settings/reset", json={"confirmed": True})
    assert response.status_code == 200
    assert response.json()["reset_count"] == 2
    service.reset.assert_awaited_once_with()


@pytest.mark.parametrize("admin", [True, False])
async def test_list_returns_navigation_for_permission_filtered_settings(settings_app, admin):
    app, service, user = settings_app
    user.permissions = ["settings:read"] if admin else []
    service.get_all.return_value = {
        "scheduled_task": [
            SettingItem(
                key="ENABLE_SCHEDULED_TASK",
                value=True,
                type=SettingType.BOOLEAN,
                category=SettingCategory.SCHEDULED_TASK,
                frontend_visible=True,
            )
        ]
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/settings/")
    assert response.status_code == 200
    assert response.json()["navigation"] == [
        {"id": "intelligence", "categories": ["scheduled_task"]}
    ]
    service.get_all.assert_awaited_once_with(admin_mode=admin)


async def test_storage_migration_requires_management_permission(settings_app):
    app, service, user = settings_app
    user.permissions = ["settings:read"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/settings/storage/migrate", json={"changes": {"S3_BUCKET_NAME": "new"}}
        )
    assert response.status_code == 403
    service.migrate_storage.assert_not_awaited()


async def test_storage_migration_returns_only_verification_counts(settings_app):
    app, service, _ = settings_app
    service.migrate_storage.return_value = {"objects": 2, "bytes": 100}
    changes = {"S3_BUCKET_NAME": "new", "S3_SECRET_KEY": "secret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/settings/storage/migrate", json={"changes": changes})
    assert response.status_code == 200
    assert response.json() == {"verified": True, "objects": 2, "bytes": 100}
    service.migrate_storage.assert_awaited_once_with(changes, "test")


async def test_incomplete_storage_migration_reports_conflict(settings_app):
    from src.kernel.errors import AppError, ErrorCode

    app, service, _ = settings_app
    service.migrate_storage.side_effect = AppError(ErrorCode.STORAGE_MIGRATION_BLOCKED)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/settings/storage/migrate", json={"changes": {"S3_BUCKET_NAME": "new"}}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "storage_migration_blocked"


async def test_unchanged_unverified_storage_does_not_claim_successful_verification(settings_app):
    app, service, _ = settings_app
    service.migrate_storage.return_value = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/settings/storage/migrate", json={"changes": {"S3_BUCKET_NAME": "current"}}
        )
    assert response.status_code == 200
    assert response.json() == {"verified": False}
