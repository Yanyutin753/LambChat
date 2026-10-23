"""TOTP enrollment, single-use login challenges and recovery codes."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from collections.abc import Awaitable
from typing import Any, cast
from urllib.parse import quote, urlencode

from bson import ObjectId

from src.infra.async_utils import run_blocking_io
from src.infra.auth.jwt import create_access_token, create_refresh_token
from src.infra.auth.password import verify_password
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.redis import get_redis_client
from src.infra.user.storage import UserStorage
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import PairingToken, Token, TwoFactorChallenge

_RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def totp(secret: str, step: int) -> str:
    digest = hmac.digest(base64.b32decode(secret), struct.pack(">Q", step), "sha1")
    offset = digest[-1] & 15
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1000000:06d}"


def recovery_hash(user_id: str, code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").lower()
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        f"lambchat:mfa:recovery:{user_id}:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _challenge_key(token: str) -> str:
    return "auth:mfa:challenge:" + hashlib.sha256(token.encode()).hexdigest()


async def rate_limit(scope: str, identity: str, maximum: int) -> None:
    key = f"auth:mfa:limit:{scope}:" + hashlib.sha256(identity.casefold().encode()).hexdigest()
    try:
        count = await cast(Awaitable[Any], get_redis_client().eval(_RATE_SCRIPT, 1, key, "300"))
    except Exception as exc:
        raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
    if int(count) > maximum:
        raise AppError(ErrorCode.TOO_MANY_REQUESTS)


def issue_tokens(user) -> Token:
    version = getattr(user, "auth_version", None)
    return Token(
        access_token=create_access_token(user.id, auth_version=version),
        refresh_token=create_refresh_token(user.id, user.username, auth_version=version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )


async def begin_login(user) -> Token | TwoFactorChallenge:
    if user.is_active is False:
        raise AppError(ErrorCode.ACCOUNT_NOT_ACTIVE)
    if not getattr(user, "two_factor_enabled", False):
        return issue_tokens(user)
    challenge = secrets.token_urlsafe(32)
    try:
        await get_redis_client().set(
            _challenge_key(challenge),
            json.dumps({"user_id": user.id, "auth_version": user.auth_version}),
            ex=300,
        )
    except Exception as exc:
        raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
    return TwoFactorChallenge(challenge_token=challenge)


class TwoFactorService:
    def __init__(self):
        self.storage = UserStorage()

    @staticmethod
    def _query(user) -> dict:
        return {"_id": ObjectId(user.id), "auth_version": user.auth_version}

    async def get_user(self, user_id):
        user = await self.storage.get_by_id(user_id)
        if not user or user.is_active is False:
            raise AppError(ErrorCode.INVALID_CREDENTIALS)
        return user

    async def check_password(self, user, password):
        await rate_limit("manage", user.id, 10)
        if not user.password_hash or not await run_blocking_io(
            verify_password, password, user.password_hash
        ):
            raise AppError(ErrorCode.INVALID_CREDENTIALS)

    @staticmethod
    def _matching_step(secret, code):
        if re.fullmatch(r"[0-9]{6}", code):
            step = int(time.time()) // 30
            for candidate in (step, step - 1, step + 1):
                if candidate >= 0 and hmac.compare_digest(totp(secret, candidate), code):
                    return candidate
        return None

    async def verify_factor(self, user, code):
        query = {**self._query(user), "two_factor_enabled": True}
        hashed = recovery_hash(user.id, code)
        if hashed in user.two_factor.get("recovery_hashes", []):
            query["two_factor.recovery_hashes"] = hashed
            update = {"$pull": {"two_factor.recovery_hashes": hashed}}
        else:
            secret = decrypt_value(user.two_factor["secret"])["secret"]
            step = self._matching_step(secret, code)
            if step is None:
                raise AppError(ErrorCode.TWO_FACTOR_INVALID)
            query["$or"] = [
                {"two_factor.last_step": {"$lt": step}},
                {"two_factor.last_step": {"$exists": False}},
            ]
            update = {"$set": {"two_factor.last_step": step}}
        result = await self.storage.collection.update_one(query, update)
        if not result.modified_count:
            raise AppError(ErrorCode.TWO_FACTOR_INVALID)

    async def complete_login(self, challenge_token, code, *, for_pairing=False):
        redis = get_redis_client()
        key = _challenge_key(challenge_token)
        try:
            raw = await redis.get(key)
        except Exception as exc:
            raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
        if not raw:
            raise AppError(ErrorCode.TWO_FACTOR_EXPIRED)
        challenge = json.loads(raw)
        user = await self.get_user(challenge["user_id"])
        await rate_limit("verify", user.id, 10)
        if not user.two_factor_enabled or challenge["auth_version"] != user.auth_version:
            raise AppError(ErrorCode.TWO_FACTOR_EXPIRED)
        await self.verify_factor(user, code)
        # GETDEL makes the challenge single-use across all API instances.
        try:
            consumed = await redis.getdel(key)
        except Exception as exc:
            raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
        if not consumed:
            raise AppError(ErrorCode.TWO_FACTOR_EXPIRED)
        tokens = issue_tokens(user)
        if for_pairing:
            grant = secrets.token_urlsafe(32)
            try:
                await redis.set(
                    self._pairing_key(grant),
                    json.dumps({"user_id": user.id, "auth_version": user.auth_version}),
                    ex=60,
                )
            except Exception as exc:
                raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
            return PairingToken(**tokens.model_dump(), pairing_token=grant)
        return tokens

    @staticmethod
    def _pairing_key(token):
        return "auth:mfa:pairing:" + hashlib.sha256(token.encode()).hexdigest()

    async def consume_pairing(self, user, token):
        try:
            raw = await get_redis_client().getdel(self._pairing_key(token))
        except Exception as exc:
            raise AppError(ErrorCode.TWO_FACTOR_UNAVAILABLE) from exc
        if not raw or json.loads(raw) != {"user_id": user.id, "auth_version": user.auth_version}:
            raise AppError(ErrorCode.TWO_FACTOR_EXPIRED)

    async def setup(self, user, password):
        await self.check_password(user, password)
        if user.two_factor_enabled:
            raise AppError(ErrorCode.TWO_FACTOR_STATE)
        secret = base64.b32encode(secrets.token_bytes(20)).decode()
        pending = {"secret": encrypt_value({"secret": secret}), "expires": time.time() + 600}
        result = await self.storage.collection.update_one(
            {
                **self._query(user),
                "two_factor_enabled": {"$ne": True},
                "password_hash": user.password_hash,
            },
            {"$set": {"two_factor_pending": pending}},
        )
        if not result.matched_count:
            raise AppError(ErrorCode.TWO_FACTOR_STATE)
        uri = (
            "otpauth://totp/"
            + quote(f"LambChat:{user.email}", safe="")
            + "?"
            + urlencode(
                {
                    "secret": secret,
                    "issuer": "LambChat",
                    "algorithm": "SHA1",
                    "digits": 6,
                    "period": 30,
                }
            )
        )
        return {"secret": secret, "otpauth_uri": uri}

    @staticmethod
    def _recovery_codes(user):
        codes = ["-".join(re.findall(r".{5}", secrets.token_hex(10))) for _ in range(10)]
        return codes, [recovery_hash(user.id, code) for code in codes]

    async def enable(self, user, password, code):
        await self.check_password(user, password)
        pending = user.two_factor_pending
        if user.two_factor_enabled or not pending or pending["expires"] <= time.time():
            raise AppError(ErrorCode.TWO_FACTOR_EXPIRED)
        secret = decrypt_value(pending["secret"])["secret"]
        step = self._matching_step(secret, code)
        if step is None:
            raise AppError(ErrorCode.TWO_FACTOR_INVALID)
        codes, hashes = self._recovery_codes(user)
        version = secrets.token_urlsafe(24)
        result = await self.storage.collection.update_one(
            {
                **self._query(user),
                "two_factor_enabled": {"$ne": True},
                "two_factor_pending": pending,
                "password_hash": user.password_hash,
            },
            {
                "$set": {
                    "two_factor_enabled": True,
                    "two_factor": {
                        "secret": pending["secret"],
                        "recovery_hashes": hashes,
                        "last_step": step,
                    },
                    "auth_version": version,
                    "pat_version": version,
                },
                "$unset": {"two_factor_pending": ""},
            },
        )
        if not result.modified_count:
            raise AppError(ErrorCode.TWO_FACTOR_STATE)
        user.auth_version = version
        return {"recovery_codes": codes, **issue_tokens(user).model_dump()}

    async def manage(self, user, password, code, *, disable=False):
        await self.check_password(user, password)
        if not user.two_factor_enabled:
            raise AppError(ErrorCode.TWO_FACTOR_STATE)
        await self.verify_factor(user, code)
        version = secrets.token_urlsafe(24)
        codes, hashes = self._recovery_codes(user)
        fields: dict = {"auth_version": version}
        if disable:
            fields.update({"two_factor_enabled": False, "two_factor": {}})
        else:
            fields["two_factor.recovery_hashes"] = hashes
            fields["pat_version"] = version
        result = await self.storage.collection.update_one(
            {**self._query(user), "two_factor_enabled": True, "password_hash": user.password_hash},
            {"$set": fields, "$unset": {"two_factor_pending": ""}},
        )
        if not result.modified_count:
            raise AppError(ErrorCode.TWO_FACTOR_STATE)
        user.auth_version = version
        return {"recovery_codes": [] if disable else codes, **issue_tokens(user).model_dump()}
