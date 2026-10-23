"""Owner checks and short-lived capabilities for application files."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import jwt

from src.infra.upload.file_record import get_file_record_storage
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

UPLOAD_PATH = "/api/upload/file/"


def validate_file_key(key: str) -> None:
    if (
        not key
        or len(key.encode("utf-8")) > 1024
        or "\\" in key
        or "\x00" in key
        or any(p in ("", ".", "..") for p in key.split("/"))
    ):
        raise AppError(ErrorCode.FILE_NOT_FOUND)


def upload_key_from_url(url: str, base_url: str | None = None) -> str | None:
    parsed = urlsplit(url)
    origin = urlsplit(base_url or settings.APP_BASE_URL)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc and (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
        return None
    if not parsed.path.startswith(UPLOAD_PATH):
        return None
    key = unquote(parsed.path[len(UPLOAD_PATH) :])
    validate_file_key(key)
    return key


def file_access_url(url: str, key: str, *, expires: int = 3600, share=None) -> str:
    """Call only after ownership authorization; tokens cannot authenticate as users."""
    validate_file_key(key)
    claims: dict[str, Any] = {
        "type": "file",
        "key": key,
        "aud": "lambchat-file",
        "exp": int(time.time()) + expires,
    }
    if share is not None:
        claims.update(share_id=share.share_id, share_version=share.updated_at.isoformat())
    token = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    parsed = urlsplit(url)
    query = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "file_token"
    ]
    query.append(("file_token", token))
    return urlunsplit(parsed._replace(query=urlencode(query)))


async def _owns_generated_file(key: str, user_id: str) -> bool:
    from src.infra.upload.shared_files import owned_file_keys

    return key in await owned_file_keys({key}, user_id)


async def require_file_access(
    key: str, user_id: str | None, *, session_id: str | None = None, token: str | None = None
):
    validate_file_key(key)
    records = get_file_record_storage()
    if await records.is_private_key(key):
        await records.require_private_access(key, user_id, session_id)
        return
    # Avatars are explicitly published by the profile-upload flow.
    if key.startswith("avatars/"):
        return
    if token:
        try:
            claims = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                audience="lambchat-file",
                options={"require": ["exp", "key", "type"]},
            )
            if claims["type"] != "file" or claims["key"] != key:
                raise ValueError("wrong file")
            if claims.get("share_id"):
                from src.infra.share.storage import ShareStorage

                share = await ShareStorage().get_by_share_id(claims["share_id"])
                if not share or share.updated_at.isoformat() != claims.get("share_version"):
                    raise ValueError("revoked share")
                return share
            return
        except (jwt.InvalidTokenError, ValueError, KeyError):
            raise AppError(ErrorCode.FILE_NOT_FOUND) from None
    if user_id:
        record = await records.find_by_key(key)
        if record and record.get("uploaded_by") == user_id and not record.get("deleting_at"):
            return
        if not record and await _owns_generated_file(key, user_id):
            return
    raise AppError(ErrorCode.FILE_NOT_FOUND)


async def authorize_file_url(
    url: str, user_id: str | None, session_id: str | None = None, *, base_url: str | None = None
) -> str:
    key = upload_key_from_url(url, base_url)
    if key is None:
        return url
    await require_file_access(key, user_id, session_id=session_id)
    # Private captures must be read as authenticated bytes, never handed to third parties.
    if await get_file_record_storage().is_private_key(key):
        raise AppError(ErrorCode.FILE_NOT_FOUND)
    return file_access_url(url, key)
