from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.api import deps
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("channel", ["jwt", "cached-jwt", "pat", "websocket"])
async def test_disabled_account_cannot_use_existing_credentials(monkeypatch, channel):
    from src.infra.auth.pat import PATStorage

    deps.clear_auth_cache()
    user = SimpleNamespace(username="disabled", roles=["user"], is_active=False)
    monkeypatch.setattr(
        deps, "UserStorage", lambda: SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    )
    monkeypatch.setattr(
        deps,
        "_verify_token_async",
        AsyncMock(return_value=TokenPayload(sub="owner", username="disabled")),
    )
    monkeypatch.setattr(
        deps, "_get_user_roles_and_permissions", AsyncMock(return_value=(["user"], []))
    )
    monkeypatch.setattr(
        PATStorage,
        "verify",
        AsyncMock(
            return_value=(
                SimpleNamespace(user_id="owner", scopes=["sandbox:execute"], pat_id="pat"),
                "",
            )
        ),
    )
    request = SimpleNamespace(state=SimpleNamespace())
    if channel == "cached-jwt":
        deps._set_cached_user("jwt", TokenPayload(sub="owner", username="disabled"))
    credential = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="lc_pat_test" if channel == "pat" else "jwt"
    )
    with pytest.raises(AppError) as failure:
        if channel == "websocket":
            await deps.get_current_user_from_websocket("jwt")
        elif channel == "pat":
            await deps.get_current_user_pat_or_jwt(request, credential)
        else:
            await deps.get_current_user_required(request, credential)
    assert failure.value.error_code is ErrorCode.ACCOUNT_NOT_ACTIVE


async def test_disabled_account_cannot_refresh_existing_token(monkeypatch):
    from src.api.routes.auth import core

    monkeypatch.setattr(
        core, "decode_token", lambda _: {"type": "refresh", "sub": "owner", "username": "disabled"}
    )
    monkeypatch.setattr(
        core,
        "UserManager",
        lambda: SimpleNamespace(
            get_user=AsyncMock(return_value=SimpleNamespace(username="disabled", is_active=False))
        ),
    )
    issue_access = MagicMock(return_value="access")
    monkeypatch.setattr(core, "create_refresh_token", MagicMock(return_value="refresh2"))
    monkeypatch.setattr(core, "create_access_token", issue_access)
    request = SimpleNamespace(json=AsyncMock(return_value={"refresh_token": "refresh"}))
    with pytest.raises(AppError) as failure:
        await core.refresh_token(request)
    assert failure.value.error_code is ErrorCode.ACCOUNT_NOT_ACTIVE
    issue_access.assert_not_called()


def test_cached_auth_never_outlives_token_expiration():
    from datetime import datetime, timedelta, timezone

    deps.clear_auth_cache()
    deps._set_cached_user(
        "expired",
        TokenPayload(
            sub="owner", username="owner", exp=datetime.now(timezone.utc) - timedelta(seconds=1)
        ),
    )
    assert deps._get_cached_user("expired") is None


async def test_optional_auth_does_not_grant_disabled_account_identity(monkeypatch):
    deps.clear_auth_cache()
    user = SimpleNamespace(username="disabled", roles=["user"], is_active=False)
    monkeypatch.setattr(
        deps, "UserStorage", lambda: SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    )
    monkeypatch.setattr(
        deps,
        "_verify_token_async",
        AsyncMock(return_value=TokenPayload(sub="owner", username="disabled")),
    )
    monkeypatch.setattr(
        deps, "_get_user_roles_and_permissions", AsyncMock(return_value=(["user"], []))
    )
    request = SimpleNamespace(state=SimpleNamespace())
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="jwt")
    assert await deps.get_current_user(request, credential) is None
