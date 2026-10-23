"""TOTP vectors and the second-factor security boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.auth import two_factor as mfa
from src.kernel.errors import AppError
from src.kernel.schemas.user import UserInDB


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_rfc6238_sha1_vectors(timestamp, expected):
    assert mfa.totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", timestamp // 30) == expected


def test_public_user_serialization_never_contains_mfa_secrets():
    from src.kernel.schemas.user import User

    user = UserInDB(
        id="abc",
        username="a",
        email="a@example.com",
        password_hash="hash",
        two_factor={"secret": "encrypted", "recovery_hashes": ["hash"]},
        auth_version="private",
        pat_version="private-pat",
    )
    assert "two_factor" not in user.model_dump()
    assert "auth_version" not in user.model_dump()
    assert "pat_version" not in user.model_dump()
    assert "two_factor" not in User.model_validate(user.model_dump()).model_dump()


async def test_enabled_account_gets_challenge_without_login_tokens(monkeypatch):
    user = SimpleNamespace(id="owner", is_active=True, two_factor_enabled=True, auth_version="v1")
    redis = SimpleNamespace(set=AsyncMock(return_value=True))
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    result = await mfa.begin_login(user)
    assert result.two_factor_required is True
    assert not hasattr(result, "access_token")
    assert len(result.challenge_token) >= 40
    assert redis.set.call_args.kwargs["ex"] == 300
    assert result.challenge_token not in redis.set.call_args.args[0]


async def test_rate_limiting_fails_closed(monkeypatch):
    redis = SimpleNamespace(eval=AsyncMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    with pytest.raises(AppError) as failure:
        await mfa.rate_limit("login", "owner", 10)
    assert failure.value.error_code.code == "two_factor_unavailable"


async def test_recovery_code_cannot_succeed_twice(monkeypatch):
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        auth_version="v1",
        two_factor_enabled=True,
        two_factor={"recovery_hashes": [mfa.recovery_hash("owner", "abcd")]},
    )
    user.two_factor["recovery_hashes"] = [mfa.recovery_hash(user.id, "abcd")]
    collection = SimpleNamespace(
        update_one=AsyncMock(
            side_effect=[SimpleNamespace(modified_count=1), SimpleNamespace(modified_count=0)]
        )
    )
    service = mfa.TwoFactorService()
    service.storage = SimpleNamespace(collection=collection)
    await service.verify_factor(user, "abcd")
    with pytest.raises(AppError):
        await service.verify_factor(user, "abcd")
    query, update = collection.update_one.call_args.args
    assert query["two_factor.recovery_hashes"] == mfa.recovery_hash(user.id, "abcd")
    assert "$pull" in update


async def test_totp_replay_is_rejected_atomically(monkeypatch):
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        auth_version="v1",
        two_factor_enabled=True,
        two_factor={"secret": {"encrypted": "value"}},
    )
    monkeypatch.setattr(
        mfa, "decrypt_value", lambda _: {"secret": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"}
    )
    monkeypatch.setattr(mfa.time, "time", lambda: 59)
    collection = SimpleNamespace(
        update_one=AsyncMock(
            side_effect=[SimpleNamespace(modified_count=1), SimpleNamespace(modified_count=0)]
        )
    )
    service = mfa.TwoFactorService()
    service.storage = SimpleNamespace(collection=collection)
    await service.verify_factor(user, "287082")
    with pytest.raises(AppError):
        await service.verify_factor(user, "287082")
    assert collection.update_one.call_args.args[0]["$or"][0] == {"two_factor.last_step": {"$lt": 1}}


async def test_expired_challenge_does_not_check_code_or_issue_tokens(monkeypatch):
    redis = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    service = mfa.TwoFactorService()
    service.verify_factor = AsyncMock()
    with pytest.raises(AppError) as failure:
        await service.complete_login("expired-challenge", "123456")
    assert failure.value.error_code.code == "two_factor_expired"
    service.verify_factor.assert_not_awaited()


@pytest.mark.parametrize("enabled,version", [(False, "v1"), (True, "changed")])
async def test_challenge_cannot_survive_account_security_change(monkeypatch, enabled, version):
    import json

    redis = SimpleNamespace(
        get=AsyncMock(return_value=json.dumps({"user_id": "owner", "auth_version": "v1"}))
    )
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    monkeypatch.setattr(mfa, "rate_limit", AsyncMock())
    service = mfa.TwoFactorService()
    service.get_user = AsyncMock(
        return_value=SimpleNamespace(id="owner", two_factor_enabled=enabled, auth_version=version)
    )
    service.verify_factor = AsyncMock()
    with pytest.raises(AppError):
        await service.complete_login("challenge", "123456")
    service.verify_factor.assert_not_awaited()


async def test_success_consumes_challenge_before_issuing_tokens(monkeypatch):
    import json

    from src.kernel.schemas.user import Token

    challenge = json.dumps({"user_id": "owner", "auth_version": "v1"})
    redis = SimpleNamespace(
        get=AsyncMock(return_value=challenge), getdel=AsyncMock(side_effect=[challenge, None])
    )
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    monkeypatch.setattr(mfa, "rate_limit", AsyncMock())
    service = mfa.TwoFactorService()
    user = SimpleNamespace(id="owner", two_factor_enabled=True, auth_version="v1")
    service.get_user = AsyncMock(return_value=user)
    service.verify_factor = AsyncMock()
    from unittest.mock import Mock

    issue = Mock(
        return_value=Token(access_token="access", refresh_token="refresh", expires_in=3600)
    )
    monkeypatch.setattr(mfa, "issue_tokens", issue)
    assert (await service.complete_login("challenge", "123456")).access_token == "access"
    with pytest.raises(AppError):
        await service.complete_login("challenge", "654321")
    assert issue.call_count == 1


async def test_enrollment_requires_confirmation_and_keeps_secret_encrypted(monkeypatch):
    monkeypatch.setattr(mfa, "rate_limit", AsyncMock())
    monkeypatch.setattr(mfa, "verify_password", lambda *_: True)
    monkeypatch.setattr(mfa, "encrypt_value", lambda value: {"cipher": "encrypted-secret"})
    user = UserInDB(
        id="507f1f77bcf86cd799439011", username="a", email="a@example.com", password_hash="hash"
    )
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))
    )
    service = mfa.TwoFactorService()
    service.storage = SimpleNamespace(collection=collection)
    setup = await service.setup(user, "password")
    assert setup["otpauth_uri"].startswith("otpauth://totp/LambChat%3Aa%40example.com?")
    fields = collection.update_one.call_args.args[1]["$set"]
    assert fields["two_factor_pending"]["secret"] == {"cipher": "encrypted-secret"}
    assert "two_factor_enabled" not in fields
    assert setup["secret"] not in str(fields)


async def test_enable_rotates_sessions_and_returns_only_hashed_recovery_storage(monkeypatch):
    monkeypatch.setattr(mfa, "rate_limit", AsyncMock())
    monkeypatch.setattr(mfa, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        mfa, "decrypt_value", lambda _: {"secret": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"}
    )
    monkeypatch.setattr(mfa.time, "time", lambda: 59)
    user = UserInDB(
        id="507f1f77bcf86cd799439011",
        username="a",
        email="a@example.com",
        password_hash="hash",
        two_factor_pending={"expires": 600, "secret": {"cipher": "encrypted"}},
    )
    service = mfa.TwoFactorService()
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    service.storage = SimpleNamespace(collection=collection)
    result = await service.enable(user, "password", "287082")
    assert len(set(result["recovery_codes"])) == 10
    fields = collection.update_one.call_args.args[1]["$set"]
    assert fields["two_factor_enabled"] is True
    assert fields["two_factor"]["last_step"] == 1
    assert fields["auth_version"]
    assert fields["pat_version"] == fields["auth_version"]
    assert set(result["recovery_codes"]).isdisjoint(fields["two_factor"]["recovery_hashes"])
    assert (
        mfa.recovery_hash(user.id, result["recovery_codes"][0])
        in fields["two_factor"]["recovery_hashes"]
    )
    from src.infra.auth.jwt import decode_token

    assert decode_token(result["access_token"])["auth_version"] == fields["auth_version"]


@pytest.mark.parametrize("code", ["", "123", "abcdef", "１２３４５６", "0000000", " 287082"])
def test_only_ascii_six_digit_totp_is_accepted(code, monkeypatch):
    monkeypatch.setattr(mfa.time, "time", lambda: 59)
    assert mfa.TwoFactorService._matching_step("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", code) is None


async def test_unverified_oauth_email_cannot_create_or_link_an_account(monkeypatch):
    from src.infra.auth.oauth import OAuthService, OAuthUserInfo

    service = OAuthService()
    service.storage = SimpleNamespace(
        get_by_oauth=AsyncMock(return_value=None), get_by_email=AsyncMock(), create=AsyncMock()
    )
    result = await service._find_or_create_user(
        OAuthUserInfo(
            provider="github",
            oauth_id="attacker",
            email="victim@example.com",
            username="attacker",
            email_verified=False,
        )
    )
    assert result is None
    service.storage.get_by_email.assert_not_awaited()
    service.storage.create.assert_not_awaited()


@pytest.mark.parametrize("disable", [True, False])
async def test_management_requires_both_password_and_second_factor(monkeypatch, disable):
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        auth_version="old",
        two_factor_enabled=True,
        password_hash="hash",
    )
    service = mfa.TwoFactorService()
    service.check_password = AsyncMock()
    service.verify_factor = AsyncMock(side_effect=AppError(mfa.ErrorCode.TWO_FACTOR_INVALID))
    collection = SimpleNamespace(update_one=AsyncMock())
    service.storage = SimpleNamespace(collection=collection)
    with pytest.raises(AppError):
        await service.manage(user, "password", "wrong", disable=disable)
    service.check_password.assert_awaited_once_with(user, "password")
    collection.update_one.assert_not_awaited()


async def test_expired_enrollment_cannot_be_enabled(monkeypatch):
    user = SimpleNamespace(id="owner", two_factor_enabled=False, two_factor_pending={"expires": 0})
    service = mfa.TwoFactorService()
    service.check_password = AsyncMock()
    service.storage = SimpleNamespace(collection=SimpleNamespace(update_one=AsyncMock()))
    with pytest.raises(AppError) as failure:
        await service.enable(user, "password", "123456")
    assert failure.value.error_code.code == "two_factor_expired"
    service.storage.collection.update_one.assert_not_awaited()


@pytest.mark.parametrize("disable", [True, False])
async def test_successful_management_rotates_session_version_and_replaces_codes(
    monkeypatch, disable
):
    user = SimpleNamespace(
        id="507f1f77bcf86cd799439011",
        username="a",
        auth_version="old",
        two_factor_enabled=True,
        password_hash="hash",
    )
    service = mfa.TwoFactorService()
    service.check_password = AsyncMock()
    service.verify_factor = AsyncMock()
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    service.storage = SimpleNamespace(collection=collection)
    result = await service.manage(user, "password", "123456", disable=disable)
    query, update = collection.update_one.call_args.args
    assert query["auth_version"] == "old"
    fields = update["$set"]
    assert fields["auth_version"] != "old"
    if disable:
        assert "pat_version" not in fields
        assert fields["two_factor_enabled"] is False
        assert fields["two_factor"] == {}
        assert result["recovery_codes"] == []
    else:
        assert fields["pat_version"] == fields["auth_version"]
        assert len(result["recovery_codes"]) == 10
        assert (
            mfa.recovery_hash(user.id, result["recovery_codes"][0])
            in fields["two_factor.recovery_hashes"]
        )
        assert "two_factor_enabled" not in fields
    from src.infra.auth.jwt import decode_token

    assert decode_token(result["refresh_token"])["auth_version"] == fields["auth_version"]


async def test_oauth_does_not_modify_mfa_account_before_second_factor():
    from src.infra.auth.oauth import OAuthService, OAuthUserInfo

    user = UserInDB(
        id="owner",
        username="a",
        email="a@example.com",
        password_hash="hash",
        two_factor_enabled=True,
    )
    service = OAuthService()
    service.storage = SimpleNamespace(
        get_by_oauth=AsyncMock(return_value=None),
        get_by_email=AsyncMock(return_value=user),
        update=AsyncMock(),
    )
    result = await service._find_or_create_user(
        OAuthUserInfo(
            provider="google",
            oauth_id="provider",
            email="a@example.com",
            username="a",
            email_verified=True,
        )
    )
    assert result is user
    service.storage.update.assert_not_awaited()


async def test_two_factor_is_opt_in_and_unenrolled_login_needs_no_challenge(monkeypatch):
    user = UserInDB(id="owner", username="a", email="a@example.com", password_hash="hash")
    assert user.two_factor_enabled is False

    def no_challenge_store():
        raise AssertionError("Unenrolled account must not need an MFA challenge")

    monkeypatch.setattr(mfa, "get_redis_client", no_challenge_store)
    result = await mfa.begin_login(user)
    assert result.access_token and result.refresh_token
    assert not hasattr(result, "challenge_token")


@pytest.mark.parametrize("owner,version", [("owner", "v1"), ("other", "v1"), ("owner", "v2")])
async def test_pairing_grant_is_single_use_and_bound_to_account_version(
    monkeypatch, owner, version
):
    import json

    redis = SimpleNamespace(
        getdel=AsyncMock(side_effect=[json.dumps({"user_id": "owner", "auth_version": "v1"}), None])
    )
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    service = mfa.TwoFactorService()
    user = SimpleNamespace(id=owner, auth_version=version)
    if owner == "owner" and version == "v1":
        await service.consume_pairing(user, "grant")
    else:
        with pytest.raises(AppError):
            await service.consume_pairing(user, "grant")
    with pytest.raises(AppError):
        await service.consume_pairing(user, "grant")
    assert redis.getdel.call_args.args[0] != mfa._challenge_key("grant")


async def test_pairing_grant_requires_explicit_verified_login_and_expires(monkeypatch):
    import json

    challenge = json.dumps({"user_id": "owner", "auth_version": "v1"})
    redis = SimpleNamespace(
        get=AsyncMock(return_value=challenge),
        getdel=AsyncMock(return_value=challenge),
        set=AsyncMock(),
    )
    monkeypatch.setattr(mfa, "get_redis_client", lambda: redis)
    monkeypatch.setattr(mfa, "rate_limit", AsyncMock())
    service = mfa.TwoFactorService()
    user = SimpleNamespace(id="owner", username="user", two_factor_enabled=True, auth_version="v1")
    service.get_user = AsyncMock(return_value=user)
    service.verify_factor = AsyncMock()
    normal = await service.complete_login("challenge", "123456")
    assert not hasattr(normal, "pairing_token")
    redis.set.assert_not_awaited()
    result = await service.complete_login("challenge2", "654321", for_pairing=True)
    assert len(result.pairing_token) >= 40
    assert redis.set.call_args.kwargs["ex"] == 60
    assert result.pairing_token not in redis.set.call_args.args[0]
    service.verify_factor.assert_awaited_with(user, "654321")


async def test_pairing_grant_redis_failure_never_authorizes(monkeypatch):
    monkeypatch.setattr(
        mfa,
        "get_redis_client",
        lambda: SimpleNamespace(getdel=AsyncMock(side_effect=ConnectionError())),
    )
    with pytest.raises(AppError) as failure:
        await mfa.TwoFactorService().consume_pairing(
            SimpleNamespace(id="owner", auth_version=None), "grant"
        )
    assert failure.value.error_code.code == "two_factor_unavailable"
