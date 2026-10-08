"""PAT scopes and revocation must bound every sandbox connection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.routes import sandbox
from src.infra.auth.pat import PATStorage
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("scopes", [[], ["sandbox:read"]])
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/machines", None),
        ("GET", "/status", None),
        ("PUT", "/machines/m1/confirm-policy", {"policy": "none"}),
        ("GET", "/fs/read?session_id=s1&path=private.txt", None),
        ("GET", "/fs/cloud/status?session_id=s1", None),
        ("GET", "/fs/cloud/list?session_id=s1", None),
        ("GET", "/fs/cloud/read?session_id=s1&path=private.txt", None),
    ],
)
async def test_insufficient_pat_scope_cannot_manage_or_read_sandbox(
    monkeypatch, scopes, method, path, body
):
    def authenticate(request: Request):
        request.state.pat_scopes = scopes
        return TokenPayload(sub="u1", username="test", roles=["user"], permissions=[])

    registry = SimpleNamespace(
        list_machines=AsyncMock(return_value=[]),
        get_default_machine=AsyncMock(return_value=None),
        get_active=AsyncMock(return_value=None),
        is_online=AsyncMock(return_value=False),
        update_confirm_policy=AsyncMock(return_value=True),
    )
    resolve = AsyncMock(return_value=("/workspace/s1", "m1"))
    dispatch = AsyncMock(return_value={"content": "private"})
    monkeypatch.setattr(sandbox, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox, "_resolve_fs_target", resolve)
    monkeypatch.setattr(sandbox, "_dispatch_fs", dispatch)
    monkeypatch.setattr(sandbox, "publish_presence", AsyncMock())
    owned = AsyncMock()
    cloud = AsyncMock(
        return_value=(
            SimpleNamespace(
                als=AsyncMock(return_value=SimpleNamespace(error=None, entries=[])),
                aread=AsyncMock(return_value=SimpleNamespace(error=None, file_data={})),
            ),
            "/workspace/s1",
        )
    )
    monkeypatch.setattr(sandbox, "_owned_session", owned)
    monkeypatch.setattr(sandbox, "_cloud_backend", cloud)
    monkeypatch.setattr("src.infra.sandbox.idle_pause.touch_browse_lease", AsyncMock())
    monkeypatch.setattr("src.infra.sandbox.idle_pause.schedule_browse_reaper", Mock())
    monkeypatch.setattr(
        "src.infra.sandbox.session_manager.get_session_sandbox_manager",
        lambda: SimpleNamespace(cloud_status=AsyncMock(return_value={"state": "running"})),
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox.router, prefix="/api/sandbox")
    app.dependency_overrides[deps.get_current_user_pat_or_jwt] = authenticate
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, "/api/sandbox" + path, json=body)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "pat_scope_denied"
    registry.update_confirm_policy.assert_not_awaited()
    resolve.assert_not_awaited()
    dispatch.assert_not_awaited()
    owned.assert_not_awaited()
    cloud.assert_not_awaited()


@pytest.mark.parametrize("identity", ["jwt", "execute_pat"])
async def test_existing_jwt_and_execute_pat_keep_sandbox_access(monkeypatch, identity):
    def authenticate(request: Request):
        if identity == "execute_pat":
            request.state.pat_scopes = ["sandbox:execute"]
        return TokenPayload(sub="u1", username="test", roles=["user"], permissions=[])

    registry = SimpleNamespace(
        get_active=AsyncMock(return_value=None), is_online=AsyncMock(return_value=False)
    )
    monkeypatch.setattr(sandbox, "_registry", lambda: registry)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox.router, prefix="/api/sandbox")
    app.dependency_overrides[deps.get_current_user_pat_or_jwt] = authenticate
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/sandbox/status")
    assert response.status_code == 200
    assert response.json() == {"online": False}


@pytest.mark.parametrize("invalid", ["revoked", "expired", "scope", "owner", "unavailable"])
@pytest.mark.parametrize("next_frame", ["tool_call", "heartbeat"])
async def test_open_channel_stops_before_delivering_calls_after_pat_loses_access(
    monkeypatch, invalid, next_frame
):
    def authenticate(request: Request):
        request.state.pat_scopes = ["sandbox:execute"]
        return TokenPayload(sub="u1", username="test", roles=["user"], permissions=[])

    async def frames(*args, **kwargs):
        yield 'event: hello\ndata: {"client_id":"client"}\n\n'
        yield 'event: tool_call\ndata: {"call_id":"first"}\n\n'
        if next_frame == "heartbeat":
            yield ": heartbeat\n\n"
        yield 'event: tool_call\ndata: {"call_id":"after-revocation"}\n\n'

    valid = SimpleNamespace(user_id="u1", scopes=["sandbox:execute"])
    if invalid in ("revoked", "expired"):
        next_result = (None, invalid)
    elif invalid == "scope":
        next_result = (SimpleNamespace(user_id="u1", scopes=[]), None)
    elif invalid == "owner":
        next_result = (SimpleNamespace(user_id="other", scopes=["sandbox:execute"]), None)
    else:
        next_result = RuntimeError("PAT store unavailable")
    verify = AsyncMock(side_effect=[(valid, None), next_result])
    monkeypatch.setattr(PATStorage, "verify", verify)
    registry = SimpleNamespace(register=AsyncMock(), unregister=AsyncMock())
    monkeypatch.setattr(sandbox, "_registry", lambda: registry)
    monkeypatch.setattr(sandbox, "_redis", lambda: SimpleNamespace(set=AsyncMock()))
    monkeypatch.setattr(
        sandbox, "create_redis_client", lambda **kwargs: SimpleNamespace(aclose=AsyncMock())
    )
    monkeypatch.setattr(sandbox, "publish_presence", AsyncMock())
    monkeypatch.setattr(sandbox, "channel_frames", frames)
    monkeypatch.setattr(sandbox.settings, "SANDBOX_MIN_DAEMON_VERSION", "0.0.1")
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sandbox.router, prefix="/api/sandbox")
    app.dependency_overrides[deps.get_current_user_pat_or_jwt] = authenticate
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/sandbox/channel?version=2.14.4&machine_id=m1",
            headers={"Authorization": "Bearer lc_pat_synthetic"},
        )
    assert '"call_id":"first"' in response.text
    assert "after-revocation" not in response.text
    assert verify.await_count == 2
    registry.unregister.assert_awaited_once()
