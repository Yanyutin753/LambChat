from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from src.api import deps
from src.kernel.schemas.user import TokenPayload, UserInDB


@pytest.fixture(autouse=True)
def _isolated_auth_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "_auth_cache", {})


class _UserStorage:
    async def get_by_id(self, user_id: str) -> UserInDB | None:
        assert user_id == "user-1"
        return UserInDB(
            id="user-1",
            username="from-storage",
            email="user@example.com",
            password_hash="hash",
            roles=["user"],
            is_active=True,
            email_verified=True,
        )


async def _fake_roles(_roles: list[str]) -> tuple[list[str], list[str]]:
    return ["user"], ["chat:write"]


@pytest.mark.asyncio
async def test_get_current_user_required_reuses_request_state_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"verify": 0}

    def fail_verify(_token: str) -> TokenPayload:
        calls["verify"] += 1
        raise AssertionError("verify_token should not run when middleware already parsed auth")

    monkeypatch.setattr(deps, "verify_token", fail_verify)
    monkeypatch.setattr(deps, "UserStorage", lambda: _UserStorage())
    monkeypatch.setattr(deps, "_get_user_roles_and_permissions", _fake_roles)

    request = SimpleNamespace(
        state=SimpleNamespace(
            auth_payload=TokenPayload(sub="user-1", username="from-token"),
        )
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    user = await deps.get_current_user_required(request, credentials)

    assert user.username == "from-storage"
    assert calls["verify"] == 0


@pytest.mark.asyncio
async def test_get_current_user_required_offloads_token_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps.clear_auth_cache()
    inside_blocking_io = False
    calls: list[object] = []

    async def fake_run_blocking_io(func, /, *args: Any, **kwargs: Any) -> Any:
        nonlocal inside_blocking_io
        calls.append(func)
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    def fake_verify_token(token: str) -> TokenPayload:
        assert inside_blocking_io, "verify_token must be offloaded"
        assert token == "token-1"
        return TokenPayload(sub="user-1", username="from-token")

    monkeypatch.setattr(deps, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(deps, "verify_token", fake_verify_token)
    monkeypatch.setattr(deps, "UserStorage", lambda: _UserStorage())
    monkeypatch.setattr(deps, "_get_user_roles_and_permissions", _fake_roles)

    request = SimpleNamespace(state=SimpleNamespace())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-1")

    user = await deps.get_current_user_required(request, credentials)

    assert user.sub == "user-1"
    assert calls == [fake_verify_token]


@pytest.mark.asyncio
async def test_get_current_user_from_websocket_offloads_token_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inside_blocking_io = False

    async def fake_run_blocking_io(func, /, *args: Any, **kwargs: Any) -> Any:
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    def fake_verify_token(token: str) -> TokenPayload:
        assert inside_blocking_io, "websocket verify_token must be offloaded"
        assert token == "token-1"
        return TokenPayload(sub="user-1", username="from-token")

    monkeypatch.setattr(deps, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(deps, "verify_token", fake_verify_token)
    monkeypatch.setattr(deps, "UserStorage", lambda: _UserStorage())
    monkeypatch.setattr(deps, "_get_user_roles_and_permissions", _fake_roles)

    user = await deps.get_current_user_from_websocket("token-1")

    assert user.sub == "user-1"
    assert user.username == "from-storage"
