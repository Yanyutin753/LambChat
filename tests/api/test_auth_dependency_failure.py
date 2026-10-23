"""Authority lookups fail closed without misclassifying infrastructure outages as bad tokens."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from pymongo.errors import ServerSelectionTimeoutError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.api import deps
from src.api.routes.auth import core
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("entry", ["http", "websocket", "pat", "refresh"])
@pytest.mark.parametrize("failure", [ServerSelectionTimeoutError, RedisTimeoutError])
async def test_authority_dependency_outage_returns_sanitized_503(monkeypatch, entry, failure):
    deps.clear_auth_cache()
    payload = TokenPayload(sub="user-1", username="user")
    monkeypatch.setattr(deps, "_verify_token_async", AsyncMock(return_value=payload))
    lookup = AsyncMock(side_effect=failure("sensitive-connection-detail"))
    monkeypatch.setattr(deps, "UserStorage", lambda: SimpleNamespace(get_by_id=lookup))
    request = SimpleNamespace(
        state=SimpleNamespace(), json=AsyncMock(return_value={"refresh_token": "synthetic"})
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic")
    if entry == "pat":
        from src.infra.auth import pat

        monkeypatch.setattr(pat, "PATStorage", lambda: SimpleNamespace(verify=lookup))
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="lc_pat_synthetic")
    if entry == "refresh":
        monkeypatch.setattr(
            core, "decode_token", lambda _: {"type": "refresh", "sub": "user-1", "username": "user"}
        )
        monkeypatch.setattr(
            core, "UserManager", lambda: SimpleNamespace(storage=SimpleNamespace(get_by_id=lookup))
        )

    with pytest.raises(AppError) as raised:
        if entry == "http":
            await deps.get_current_user_required(request, credentials)
        elif entry == "websocket":
            await deps.get_current_user_from_websocket("synthetic")
        elif entry == "pat":
            await deps.get_current_user_pat_or_jwt(request, credentials)
        else:
            await core.refresh_token(request)

    assert raised.value.error_code is ErrorCode.SERVICE_UNAVAILABLE
    assert raised.value.http_status == 503
    assert "sensitive" not in raised.value.message
    assert not hasattr(request.state, "current_user")


@pytest.mark.parametrize("entry", ["http", "websocket"])
async def test_role_dependency_outage_is_not_token_rejection(monkeypatch, entry):
    deps.clear_auth_cache()
    monkeypatch.setattr(
        deps,
        "_verify_token_async",
        AsyncMock(return_value=TokenPayload(sub="user-1", username="user")),
    )
    monkeypatch.setattr(
        deps,
        "UserStorage",
        lambda: SimpleNamespace(
            get_by_id=AsyncMock(
                return_value=SimpleNamespace(username="user", is_active=True, roles=["user"])
            )
        ),
    )
    monkeypatch.setattr(
        deps,
        "_get_user_roles_and_permissions",
        AsyncMock(side_effect=RedisTimeoutError("private-role-connection")),
    )
    with pytest.raises(AppError) as raised:
        if entry == "http":
            await deps.get_current_user_required(
                SimpleNamespace(state=SimpleNamespace()),
                HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic"),
            )
        else:
            await deps.get_current_user_from_websocket("synthetic")
    assert raised.value.error_code is ErrorCode.SERVICE_UNAVAILABLE
    assert "private" not in raised.value.message


@pytest.mark.parametrize(
    "error",
    [
        AppError(ErrorCode.TOKEN_EXPIRED),
        AppError(ErrorCode.INVALID_TOKEN),
        asyncio.CancelledError(),
    ],
)
async def test_real_token_errors_and_cancellation_keep_original_semantics(monkeypatch, error):
    deps.clear_auth_cache()
    monkeypatch.setattr(deps, "_verify_token_async", AsyncMock(side_effect=error))
    lookup = AsyncMock()
    monkeypatch.setattr(deps, "UserStorage", lambda: SimpleNamespace(get_by_id=lookup))
    with pytest.raises(type(error)) as raised:
        await deps.get_current_user_required(
            SimpleNamespace(state=SimpleNamespace()),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic"),
        )
    assert raised.value is error
    lookup.assert_not_awaited()


async def test_unknown_authority_failure_is_sanitized_500_not_invalid_token(monkeypatch):
    deps.clear_auth_cache()
    monkeypatch.setattr(
        deps,
        "_verify_token_async",
        AsyncMock(return_value=TokenPayload(sub="user-1", username="user")),
    )
    monkeypatch.setattr(
        deps,
        "UserStorage",
        lambda: SimpleNamespace(
            get_by_id=AsyncMock(side_effect=RuntimeError("private-driver-detail"))
        ),
    )
    with pytest.raises(AppError) as raised:
        await deps.get_current_user_required(
            SimpleNamespace(state=SimpleNamespace()),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic"),
        )
    assert raised.value.error_code is ErrorCode.INTERNAL_ERROR
    assert "private" not in raised.value.message
