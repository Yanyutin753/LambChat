"""Quota reset routes enforce admin visibility and owner-only card consumption."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.deps import get_current_user_required
from src.api.routes import usage
from src.kernel.errors import AppError
from src.kernel.schemas.user import TokenPayload


@pytest.fixture
async def reset_api(monkeypatch):
    from src.infra.usage import quota, reset
    from src.infra.user.storage import UserStorage

    service = SimpleNamespace(
        credits=AsyncMock(return_value={"available_count": 0, "credits": []}),
        reset=AsyncMock(return_value={"outcome": "reset"}),
        issue_card=AsyncMock(return_value={"outcome": "issued", "credit_id": "card"}),
        consume=AsyncMock(return_value={"outcome": "nothingToReset"}),
        notify=AsyncMock(),
    )
    monkeypatch.setattr(usage, "_broadcast_quota_changed", service.notify, raising=False)
    monkeypatch.setattr(reset, "QuotaReset", lambda: service)
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, 5)))
    monkeypatch.setattr(
        quota,
        "UsageQuota",
        lambda: SimpleNamespace(snapshot=AsyncMock(return_value={"currency": "USD"})),
    )
    monkeypatch.setattr(
        UserStorage, "get_by_id", AsyncMock(return_value=SimpleNamespace(is_active=True))
    )
    app = FastAPI()
    app.include_router(usage.router, prefix="/usage")
    user = TokenPayload(sub="owner", username="Owner", permissions=[])
    app.dependency_overrides[get_current_user_required] = lambda: user

    @app.exception_handler(AppError)
    async def handle_error(request, error):
        return JSONResponse(
            {"detail": {"code": error.error_code.code}}, status_code=error.http_status
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, service, user


async def test_admin_routes_require_usage_admin(reset_api):
    client, service, _ = reset_api
    for path, body in (
        ("/usage/users/target/quota", None),
        (
            "/usage/users/target/quota/reset",
            {"window": "weekly", "idempotency_key": str(uuid.uuid4())},
        ),
        ("/usage/users/target/quota/reset-cards", {"idempotency_key": str(uuid.uuid4())}),
    ):
        response = await client.get(path) if body is None else await client.post(path, json=body)
        assert response.status_code == 403
    service.reset.assert_not_awaited()
    service.issue_card.assert_not_awaited()


async def test_committed_mutations_notify_target_and_owner_only(reset_api):
    client, service, user = reset_api
    user.permissions = ["usage:admin"]
    response = await client.post(
        "/usage/users/target/quota/reset-cards", json={"idempotency_key": str(uuid.uuid4())}
    )
    assert response.status_code == 200
    service.notify.assert_awaited_once_with("target")
    service.notify.reset_mock()
    await client.post(
        "/usage/users/target/quota/reset",
        json={"window": "weekly", "idempotency_key": str(uuid.uuid4())},
    )
    service.notify.assert_awaited_once_with("target")
    service.notify.reset_mock()
    await client.post(
        "/usage/quota/reset-cards/consume", json={"idempotency_key": str(uuid.uuid4())}
    )
    service.notify.assert_awaited_once_with("owner")


async def test_quota_broadcast_failure_does_not_undo_commit(monkeypatch):
    from src.infra import websocket

    manager = SimpleNamespace(send_to_user_with_broadcast=AsyncMock(side_effect=OSError("offline")))
    monkeypatch.setattr(websocket, "get_connection_manager", lambda: manager)
    await usage._broadcast_quota_changed("target")


async def test_own_quota_contains_only_own_credits(reset_api):
    client, service, _ = reset_api
    response = await client.get("/usage/quota?user_id=victim")
    assert response.status_code == 200
    assert response.json()["reset_credits"] == {"available_count": 0, "credits": []}
    service.credits.assert_awaited_once_with("owner")


async def test_card_consume_never_uses_query_target(reset_api):
    client, service, _ = reset_api
    operation = str(uuid.uuid4())
    response = await client.post(
        "/usage/quota/reset-cards/consume?user_id=victim",
        json={"idempotency_key": operation, "credit_id": "card"},
    )
    assert response.status_code == 200
    service.consume.assert_awaited_once_with("owner", operation, (1, 5), credit_id="card")
    assert (
        await client.post(
            "/usage/quota/reset-cards/consume",
            json={"idempotency_key": str(uuid.uuid4()), "user_id": "victim"},
        )
    ).status_code == 422


async def test_admin_target_must_be_active_and_actor_is_audited(reset_api, monkeypatch):
    from src.infra.user.storage import UserStorage

    client, service, user = reset_api
    user.permissions = ["usage:admin"]
    operation = str(uuid.uuid4())
    response = await client.post(
        "/usage/users/target/quota/reset", json={"window": "weekly", "idempotency_key": operation}
    )
    assert response.status_code == 200
    service.reset.assert_awaited_once_with("target", "owner", "weekly", operation, (1, 5))
    for target in (None, SimpleNamespace(is_active=False)):
        monkeypatch.setattr(UserStorage, "get_by_id", AsyncMock(return_value=target))
        response = await client.post(
            "/usage/users/target/quota/reset-cards", json={"idempotency_key": str(uuid.uuid4())}
        )
        assert response.status_code in {403, 404}
    service.issue_card.assert_not_awaited()


async def test_issue_card_forwards_validated_window(reset_api):
    client, service, user = reset_api
    user.permissions = ["usage:admin"]
    key = str(uuid.uuid4())
    response = await client.post(
        "/usage/users/target/quota/reset-cards", json={"idempotency_key": key, "window": "weekly"}
    )
    assert response.status_code == 200
    service.issue_card.assert_awaited_once_with("target", "owner", key, window="weekly")
    response = await client.post(
        "/usage/users/target/quota/reset-cards",
        json={"idempotency_key": str(uuid.uuid4()), "window": "all"},
    )
    assert response.status_code == 422
