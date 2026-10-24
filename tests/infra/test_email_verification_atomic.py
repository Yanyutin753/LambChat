from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.auth import verification
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import (
    ForgotPasswordRequest,
    ResendVerificationRequest,
    UserInDB,
    UserUpdate,
    VerifyEmailRequest,
)


def account(**changes):
    return UserInDB(
        **{
            "id": "507f1f77bcf86cd799439011",
            "username": "a",
            "email": "a@example.com",
            "password_hash": "old",
            "roles": ["user"],
            "is_active": False,
            "email_verified": False,
            "verification_token": "verification-secret",
            "verification_token_expires": utc_now() + timedelta(hours=1),
            **changes,
        }
    )


async def test_profile_update_preserves_unrelated_verification_and_reset_links():
    user = account()
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(
            return_value={"_id": user.id, **user.model_dump(exclude={"id"})}
        )
    )
    store = UserStorage()
    store._collection = collection
    await store.update(user.id, UserUpdate(username="renamed"))
    fields = collection.find_one_and_update.call_args.args[1]["$set"]
    assert (
        not {
            "verification_token",
            "verification_token_expires",
            "reset_token",
            "reset_token_expires",
        }
        & fields.keys()
    )


async def test_explicit_clear_removes_verification_token():
    user = account()
    store = UserStorage()
    store._collection = SimpleNamespace(
        find_one_and_update=AsyncMock(
            return_value={"_id": user.id, **user.model_dump(exclude={"id"})}
        )
    )
    await store.update(
        user.id, UserUpdate(verification_token=None, verification_token_expires=None)
    )
    fields = store.collection.find_one_and_update.call_args.args[1]["$set"]
    assert fields["verification_token"] is None
    assert fields["verification_token_expires"] is None


@pytest.mark.parametrize("expires", [None, utc_now() - timedelta(seconds=1)])
async def test_expired_or_legacy_nonexpiring_verification_is_rejected(expires):
    user = account(verification_token_expires=expires)
    store = UserStorage()
    store._collection = SimpleNamespace(
        find_one=AsyncMock(return_value={"_id": user.id, **user.model_dump(exclude={"id"})})
    )
    assert await store.get_by_verification_token(user.verification_token) is None


async def test_empty_verification_does_not_query_null_or_empty_tokens():
    store = UserStorage()
    store._collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
    assert await store.get_by_verification_token("") is None
    store.collection.find_one.assert_not_awaited()


@pytest.mark.parametrize("flags", [{"email_verified": True}, {"email_verification_blocked": True}])
async def test_verified_or_admin_disabled_accounts_cannot_use_verification(flags):
    user = account()
    store = UserStorage()
    store._collection = SimpleNamespace(
        find_one=AsyncMock(
            return_value={"_id": user.id, **user.model_dump(exclude={"id"}), **flags}
        )
    )
    assert await store.get_by_verification_token(user.verification_token) is None


@pytest.mark.parametrize(
    "update,fields",
    [
        (
            UserUpdate(email="new@example.com"),
            [
                "verification_token",
                "verification_token_expires",
                "reset_token",
                "reset_token_expires",
            ],
        ),
        (UserUpdate(password="new-secret"), ["reset_token", "reset_token_expires"]),
    ],
)
async def test_identity_changes_revoke_old_proof_links(update, fields):
    user = account()
    store = UserStorage()
    store._collection = SimpleNamespace(
        find_one_and_update=AsyncMock(
            return_value={"_id": user.id, **user.model_dump(exclude={"id"})}
        )
    )
    await store.update(user.id, update)
    changes = store.collection.find_one_and_update.call_args.args[1]["$set"]
    for field in fields:
        assert changes[field] is None


async def test_verification_consumes_link_and_activates_atomically():
    store = UserStorage()
    store._collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    user = account()
    assert await store.verify_email(user, ["user"])
    query, change = store.collection.update_one.call_args.args
    assert query["verification_token"] == user.verification_token
    assert query["verification_token_expires"]["$gt"] <= utc_now()
    assert query["email_verified"] is False
    assert query["email"] == user.email
    assert query["roles"] == user.roles
    assert query["email_verification_blocked"] == {"$ne": True}
    assert change["$set"]["verification_token"] is None
    assert change["$set"]["verification_token_expires"] is None
    assert change["$set"]["email_verified"] is True
    assert change["$set"]["is_active"] is True


async def test_verification_losing_a_race_does_not_report_success(monkeypatch):
    store = SimpleNamespace(
        get_by_verification_token=AsyncMock(return_value=account()),
        verify_email=AsyncMock(return_value=False),
        update=AsyncMock(),
    )
    monkeypatch.setattr(verification, "UserManager", lambda: SimpleNamespace(storage=store))
    with pytest.raises(AppError) as error:
        await verification.verify_email(VerifyEmailRequest(token="verification-secret"))
    assert error.value.error_code is ErrorCode.INVALID_VERIFICATION_TOKEN
    store.update.assert_not_awaited()


async def test_admin_disable_revokes_verification_and_blocks_reissuing():
    user = account()
    store = UserStorage()
    store._collection = SimpleNamespace(
        find_one_and_update=AsyncMock(
            return_value={"_id": user.id, **user.model_dump(exclude={"id"})}
        ),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=0)),
    )
    await store.update(user.id, UserUpdate(is_active=False))
    fields = store.collection.find_one_and_update.call_args.args[1]["$set"]
    assert fields["verification_token"] is None
    assert fields["verification_token_expires"] is None
    assert fields["email_verification_blocked"] is True
    assert not await store.set_verification_token(
        user.id, user.email, "new", utc_now() + timedelta(hours=1)
    )
    query = store.collection.update_one.call_args.args[0]
    assert query["email_verification_blocked"] == {"$ne": True}
    assert query["email_verified"] is False
    assert query["email"] == user.email


@pytest.mark.parametrize("method", ["set_verification_token", "set_reset_token"])
async def test_proof_issuance_is_bound_to_the_address_that_receives_the_email(method):
    user = account()
    store = UserStorage()
    store._collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=0))
    )
    assert not await getattr(store, method)(
        user.id, user.email, "fresh", utc_now() + timedelta(hours=1)
    )
    query = store.collection.update_one.call_args.args[0]
    assert query["email"] == "a@example.com"


async def test_verification_accepts_missing_legacy_roles_without_overwriting_a_concurrent_role():
    user = account(roles=[])
    store = UserStorage()
    store._collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    assert await store.verify_email(user, ["user"])
    query = store.collection.update_one.call_args.args[0]
    assert query["$or"] == [{"roles": []}, {"roles": {"$exists": False}}]


@pytest.mark.parametrize(
    "route,method,sender,request_type",
    [
        (
            "resend_verification",
            "set_verification_token",
            "send_verification_email",
            ResendVerificationRequest,
        ),
        ("forgot_password", "set_reset_token", "send_password_reset_email", ForgotPasswordRequest),
    ],
)
async def test_email_link_is_not_sent_after_eligibility_or_address_changes(
    monkeypatch, route, method, sender, request_type
):
    from starlette.requests import Request

    from src.infra import email

    store = SimpleNamespace(
        get_by_email=AsyncMock(return_value=account()),
        set_verification_token=AsyncMock(return_value=False),
        set_reset_token=AsyncMock(return_value=False),
    )
    mail = SimpleNamespace(
        is_enabled=lambda: True,
        generate_token=lambda: "fresh",
        get_token_expiry=lambda **_: utc_now() + timedelta(hours=1),
        send_verification_email=AsyncMock(),
        send_password_reset_email=AsyncMock(),
    )
    limiter = SimpleNamespace(
        build_key=lambda *args: ":".join(args),
        check_rate_limit=AsyncMock(return_value=(True, 0)),
    )
    monkeypatch.setattr(verification, "UserManager", lambda: SimpleNamespace(storage=store))
    monkeypatch.setattr(verification, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(email, "get_email_service", AsyncMock(return_value=mail))
    request = Request({"type": "http", "client": ("203.0.113.8", 1), "headers": []})
    result = await getattr(verification, route)(request_type(email="a@example.com"), request)
    assert "message" in result
    getattr(store, method).assert_awaited_once()
    assert getattr(store, method).call_args.args[:2] == (account().id, "a@example.com")
    getattr(mail, sender).assert_not_awaited()
