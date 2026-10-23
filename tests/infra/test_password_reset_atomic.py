from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.auth import verification
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import ResetPasswordRequest, UserInDB


def account():
    return UserInDB(
        id="507f1f77bcf86cd799439011",
        username="a",
        email="a@example.com",
        password_hash="old",
        auth_version="v1",
        reset_token="reset-secret",
        reset_token_expires=utc_now() + timedelta(minutes=10),
        two_factor_enabled=True,
    )


async def test_reset_consumes_exact_token_and_version_atomically_preserving_mfa():
    store = UserStorage()
    store._collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    user = account()
    assert await store.reset_password(user, "new-password")
    query, change = store.collection.update_one.call_args.args
    assert query["reset_token"] == user.reset_token
    assert query["auth_version"] == "v1"
    assert query["password_hash"] == "old"
    assert query["reset_token_expires"]["$gt"] <= utc_now()
    assert change["$set"]["auth_version"] != "v1"
    assert change["$set"]["reset_token"] is None
    assert change["$set"]["two_factor_pending"] is None
    assert "two_factor_enabled" not in change["$set"]
    assert "two_factor" not in change["$set"]


async def test_losing_reset_race_is_not_reported_as_success(monkeypatch):
    store = SimpleNamespace(
        get_by_reset_token=AsyncMock(return_value=account()),
        reset_password=AsyncMock(return_value=False),
        update=AsyncMock(),
    )
    monkeypatch.setattr(verification, "UserManager", lambda: SimpleNamespace(storage=store))
    with pytest.raises(AppError) as error:
        await verification.reset_password(
            ResetPasswordRequest(token="reset-secret", new_password="new-password")
        )
    assert error.value.error_code is ErrorCode.INVALID_RESET_TOKEN
    store.update.assert_not_awaited()


async def test_reset_without_expiration_fails_closed(monkeypatch):
    user = account()
    user.reset_token_expires = None
    store = SimpleNamespace(get_by_reset_token=AsyncMock(return_value=user), update=AsyncMock())
    monkeypatch.setattr(verification, "UserManager", lambda: SimpleNamespace(storage=store))
    with pytest.raises(AppError):
        await verification.reset_password(
            ResetPasswordRequest(token="reset-secret", new_password="new-password")
        )
    store.update.assert_not_awaited()
