"""Real ASGI requests bound authority and completion reads and cancel their downstream waits."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import task_completions
from src.api.routes.auth import core
from src.infra.auth import authority, pat
from src.kernel.schemas.user import TokenPayload


def _app(monkeypatch, get_user, get_role, verify_pat=None, list_completions=None):
    deps.clear_auth_cache()
    monkeypatch.setattr(authority, "AUTHORITY_LOOKUP_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(task_completions, "COMPLETION_READ_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(
        deps,
        "_verify_token_async",
        AsyncMock(return_value=TokenPayload(sub="owner", username="owner")),
    )
    monkeypatch.setattr(deps, "UserStorage", lambda: SimpleNamespace(get_by_id=get_user))

    async def get_roles(names):
        return [role for name in names if (role := await get_role(name)) is not None]

    monkeypatch.setattr(deps, "RoleManager", lambda: SimpleNamespace(get_roles_by_names=get_roles))
    monkeypatch.setattr(
        core, "UserManager", lambda: SimpleNamespace(storage=SimpleNamespace(get_by_id=get_user))
    )
    monkeypatch.setattr(
        core, "decode_token", lambda _: {"type": "refresh", "sub": "owner", "username": "owner"}
    )
    if verify_pat:
        monkeypatch.setattr(pat, "PATStorage", lambda: SimpleNamespace(verify=verify_pat))
    if list_completions:
        monkeypatch.setattr(
            task_completions,
            "TaskCompletionStore",
            lambda: SimpleNamespace(list_for_user=list_completions),
        )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(core.router, prefix="/api/auth")
    app.include_router(task_completions.router, prefix="/api")

    @app.get("/api/authority")
    async def authority_route(user=Depends(deps.get_current_user_pat_or_jwt)):
        return {"owner": user.sub}

    return app


def _healthy_user():
    return SimpleNamespace(username="owner", is_active=True, roles=["user"])


def _healthy_role():
    return SimpleNamespace(name="user", permissions=[])


@pytest.mark.parametrize("stage", ["user", "role", "pat", "refresh", "completion"])
async def test_asgi_read_deadline_returns_503_and_cancels_downstream(monkeypatch, stage):
    cancelled = asyncio.Event()
    entered = asyncio.Event()

    async def hanging(*_args, **_kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    user = hanging if stage in {"user", "refresh"} else AsyncMock(return_value=_healthy_user())
    role = hanging if stage == "role" else AsyncMock(return_value=_healthy_role())
    app = _app(
        monkeypatch,
        user,
        role,
        verify_pat=hanging if stage == "pat" else None,
        list_completions=hanging if stage == "completion" else None,
    )
    path = "/api/task-completions" if stage == "completion" else "/api/authority"
    token = "lc_pat_synthetic" if stage == "pat" else "synthetic"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://owned-test"
    ) as client:
        request = (
            client.post("/api/auth/refresh", json={"refresh_token": "synthetic"})
            if stage == "refresh"
            else client.get(path, headers={"Authorization": f"Bearer {token}"})
        )
        response = await asyncio.wait_for(request, timeout=0.3)
    assert entered.is_set()
    assert cancelled.is_set()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "service_unavailable"
    assert "synthetic" not in response.text


@pytest.mark.parametrize("channel", ["jwt", "pat"])
async def test_asgi_authority_deadline_covers_serial_lookups_not_individual_calls(
    monkeypatch, channel
):
    role_cancelled = asyncio.Event()
    user_cancelled = asyncio.Event()

    async def user(*_args):
        try:
            await asyncio.sleep(0.007)
            return _healthy_user()
        finally:
            user_cancelled.set()

    async def role(*_args):
        try:
            await asyncio.sleep(0.007)
            return _healthy_role()
        finally:
            role_cancelled.set()

    async def verify(*_args):
        await asyncio.sleep(0.007)
        return SimpleNamespace(user_id="owner", scopes=[], pat_id="owned"), None

    app = _app(monkeypatch, user, role, verify_pat=verify if channel == "pat" else None)
    monkeypatch.setattr(deps, "_schedule_touch_last_used", lambda *_args: None)
    token = "lc_pat_synthetic" if channel == "pat" else "synthetic"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://owned-test"
    ) as client:
        response = await client.get("/api/authority", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "service_unavailable"
    assert user_cancelled.is_set()
    if channel == "jwt":
        assert role_cancelled.is_set()


async def test_asgi_healthy_authority_and_completion_keep_query_scope(monkeypatch):
    completion = AsyncMock(return_value={"events": [], "next_cursor": None})
    app = _app(
        monkeypatch,
        AsyncMock(return_value=_healthy_user()),
        AsyncMock(return_value=_healthy_role()),
        list_completions=completion,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://owned-test"
    ) as client:
        response = await client.get(
            "/api/task-completions?cursor=owned-cursor&limit=7",
            headers={"Authorization": "Bearer synthetic"},
        )
    assert response.status_code == 200
    completion.assert_awaited_once_with("owner", cursor="owned-cursor", since=None, limit=7)


async def test_asgi_external_cancellation_reaches_authority_without_becoming_503_or_401(
    monkeypatch,
):
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def user(*_args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    app = _app(monkeypatch, user, AsyncMock(return_value=_healthy_role()))
    monkeypatch.setattr(authority, "AUTHORITY_LOOKUP_TIMEOUT_SECONDS", 10.0, raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://owned-test"
    ) as client:
        task = asyncio.create_task(
            client.get("/api/authority", headers={"Authorization": "Bearer synthetic"})
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cancelled.is_set()
