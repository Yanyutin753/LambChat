"""Owned, durable multipart tickets. Unverified objects never become attachments."""

import hashlib
import re
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.api.deps import get_current_user_required
from src.infra.async_utils import run_long_blocking_io
from src.infra.image_utils import needs_model_safe_transcode
from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.storage.s3.direct_upload import MAX_PARTS, PART_SIZE, URL_EXPIRES, validate_parts
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

router = APIRouter(prefix="/direct")
logger = get_logger(__name__)


def tickets():
    return get_mongo_client()[settings.MONGODB_DB]["direct_uploads"]


def storage_identity(storage) -> str:
    config = storage.direct_upload.config
    return hashlib.sha256(
        f"{config.provider}:{config.endpoint_url}:{config.region}:{config.bucket_name}".encode()
    ).hexdigest()


class StartUpload(BaseModel):
    name: str = Field(min_length=1, max_length=1024)
    mime_type: str = Field(default="application/octet-stream", max_length=255)
    size: int = Field(ge=0, le=PART_SIZE * MAX_PARTS)


async def owned_ticket(ticket_id: str, user: TokenPayload, storage) -> dict:
    ticket = await tickets().find_one({"_id": ticket_id, "owner": user.sub})
    if not ticket:
        raise AppError(ErrorCode.FILE_NOT_FOUND)
    if ticket["storage"] != storage_identity(storage):
        raise AppError(ErrorCode.DIRECT_UPLOAD_STORAGE_CHANGED)
    return ticket


async def cleanup_ticket(ticket: dict, storage) -> None:
    from src.api.routes.upload import _file_record_storage

    if ticket.get("upload_id"):
        await storage.direct_upload.abort(ticket["key"], ticket["upload_id"])
    # A worker may have committed the record immediately before crashing.
    record = await _file_record_storage.find_by_key(ticket["key"], ticket["owner"])
    if record:
        await _file_record_storage.schedule_owned_cleanup(ticket["key"], ticket["owner"])
    elif await storage.file_exists(ticket["key"]):
        await storage.delete_file(ticket["key"])
    await tickets().delete_one({"_id": ticket["_id"], "state": "cleanup"})


@router.post("")
async def start_upload(body: StartUpload, user: TokenPayload = Depends(get_current_user_required)):
    from src.api.routes.upload import get_or_init_storage, validate_upload_metadata

    category, limit = await validate_upload_metadata(body.name, body.mime_type, user)
    if not body.size:
        raise AppError(ErrorCode.EMPTY_FILE)
    if body.size > limit:
        raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": limit // (1024 * 1024)})
    storage = await get_or_init_storage()
    ext = body.name.rsplit(".", 1)[-1] if "." in body.name else ""
    if storage.is_local or (
        category.value == "image" and needs_model_safe_transcode(ext, body.mime_type)
    ):
        return {"mode": "proxy"}

    ticket_id = uuid.uuid4().hex
    key = f"{category.value}/{user.sub}/{uuid.uuid4().hex[:16]}"
    if re.fullmatch(r"[a-zA-Z0-9]{1,16}", ext):
        key += f".{ext}"
    ticket = {
        "_id": ticket_id,
        "owner": user.sub,
        "key": key,
        "name": body.name,
        "mime_type": body.mime_type,
        "size": body.size,
        "category": category.value,
        "storage": storage_identity(storage),
        "state": "initializing",
        "expires_at": utc_now() + timedelta(seconds=URL_EXPIRES),
    }
    await tickets().insert_one(ticket)
    try:
        upload_id = await storage.direct_upload.create(key, body.mime_type)
        ticket["upload_id"] = upload_id
        await tickets().update_one(
            {"_id": ticket_id}, {"$set": {"upload_id": upload_id, "state": "active"}}
        )
    except Exception:
        await tickets().update_one({"_id": ticket_id}, {"$set": {"state": "cleanup"}})
        if ticket.get("upload_id"):
            await cleanup_ticket(ticket, storage)
        raise
    return {
        "mode": "direct",
        "id": ticket_id,
        "part_size": PART_SIZE,
        "part_count": (body.size + PART_SIZE - 1) // PART_SIZE,
    }


@router.post("/{ticket_id}/parts/{number}")
async def sign_part(
    ticket_id: str, number: int, user: TokenPayload = Depends(get_current_user_required)
):
    from src.api.routes.upload import get_or_init_storage, validate_upload_metadata

    storage = await get_or_init_storage()
    ticket = await owned_ticket(ticket_id, user, storage)
    _, limit = await validate_upload_metadata(ticket["name"], ticket["mime_type"], user)
    if ticket["size"] > limit:
        raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": limit // (1024 * 1024)})
    count = (ticket["size"] + PART_SIZE - 1) // PART_SIZE
    if (
        ticket["state"] != "active"
        or ticket.get("cancel_requested")
        or ticket["expires_at"].replace(tzinfo=utc_now().tzinfo) <= utc_now()
    ):
        raise AppError(ErrorCode.DIRECT_UPLOAD_INACTIVE)
    if not 1 <= number <= count:
        raise AppError(ErrorCode.DIRECT_UPLOAD_INVALID)
    return {
        "url": await storage.direct_upload.sign_part(
            ticket["key"],
            ticket["upload_id"],
            number,
            min(PART_SIZE, ticket["size"] - (number - 1) * PART_SIZE),
        )
    }


@router.post("/{ticket_id}/complete")
async def complete_upload(
    ticket_id: str, request: Request, user: TokenPayload = Depends(get_current_user_required)
):
    from src.api.routes.upload import (
        _build_upload_response,
        _file_record_storage,
        _get_live_record_by_hash,
        get_or_init_storage,
        validate_upload_metadata,
    )

    storage = await get_or_init_storage()
    ticket = await owned_ticket(ticket_id, user, storage)
    if ticket["state"] == "completed":
        return ticket["result"]
    category, limit = await validate_upload_metadata(ticket["name"], ticket["mime_type"], user)
    if ticket["size"] > limit:
        raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": limit // (1024 * 1024)})
    ticket = await tickets().find_one_and_update(
        {
            "_id": ticket_id,
            "owner": user.sub,
            "state": "active",
            "expires_at": {"$gt": utc_now()},
            "cancel_requested": {"$ne": True},
        },
        {"$set": {"state": "completing", "expires_at": utc_now() + timedelta(hours=1)}},
        return_document=ReturnDocument.AFTER,
    )
    if not ticket:
        raise AppError(ErrorCode.DIRECT_UPLOAD_INACTIVE)
    try:
        parts = await storage.direct_upload.list_parts(ticket["key"], ticket["upload_id"])
        try:
            verified = validate_parts(parts, ticket["size"])
        except ValueError as exc:
            raise AppError(ErrorCode.DIRECT_UPLOAD_INVALID) from exc
        await storage.direct_upload.complete(ticket["key"], ticket["upload_id"], verified)
        if await storage.get_size(ticket["key"]) != ticket["size"]:
            raise AppError(ErrorCode.DIRECT_UPLOAD_INVALID)

        digest = hashlib.sha256()
        size = 0
        async for chunk in storage.download_stream(ticket["key"]):
            size += len(chunk)
            if size > ticket["size"]:
                raise AppError(ErrorCode.DIRECT_UPLOAD_INVALID)
            await run_long_blocking_io(digest.update, chunk)
            current = await tickets().find_one(
                {"_id": ticket_id}, {"state": 1, "cancel_requested": 1}
            )
            if not current or current.get("cancel_requested") or current["state"] != "completing":
                raise AppError(ErrorCode.UPLOAD_CANCELED)
            await tickets().update_one(
                {"_id": ticket_id, "state": "completing"},
                {"$set": {"expires_at": utc_now() + timedelta(hours=1)}},
            )
        if size != ticket["size"]:
            raise AppError(ErrorCode.DIRECT_UPLOAD_INVALID)
        # Cancellation and committing compete atomically, across replicas.
        claimed = await tickets().update_one(
            {"_id": ticket_id, "state": "completing", "cancel_requested": {"$ne": True}},
            {"$set": {"state": "committing"}},
        )
        if not claimed.modified_count:
            raise AppError(ErrorCode.UPLOAD_CANCELED)
        file_hash = digest.hexdigest()
        existing = await _get_live_record_by_hash(file_hash, user.sub, storage)
        if not existing:
            try:
                existing = await _file_record_storage.create(
                    file_hash=file_hash,
                    key=ticket["key"],
                    name=ticket["name"],
                    mime_type=ticket["mime_type"],
                    size=size,
                    category=category.value,
                    uploaded_by=user.sub,
                )
            except DuplicateKeyError:
                existing = await _get_live_record_by_hash(file_hash, user.sub, storage)
                if not existing:
                    raise
        if existing["key"] != ticket["key"]:
            await storage.delete_file(ticket["key"])
        result = _build_upload_response(
            request,
            key=existing["key"],
            name=existing["name"],
            file_type=existing["category"],
            mime_type=existing["mime_type"],
            size=existing["size"],
        )
        completed = await tickets().update_one(
            {"_id": ticket_id, "state": "committing", "cancel_requested": {"$ne": True}},
            {
                "$set": {
                    "state": "completed",
                    "result": result,
                    "expires_at": utc_now() + timedelta(days=1),
                }
            },
        )
        if not completed.modified_count:
            raise AppError(ErrorCode.UPLOAD_CANCELED)
        return result
    except Exception:
        await tickets().update_one({"_id": ticket_id}, {"$set": {"state": "cleanup"}})
        try:
            await cleanup_ticket(ticket, storage)
        except Exception:
            logger.exception("Direct upload cleanup failed for %s", ticket_id)
        raise


@router.delete("/{ticket_id}")
async def cancel_upload(ticket_id: str, user: TokenPayload = Depends(get_current_user_required)):
    from src.api.routes.upload import get_or_init_storage

    storage = await get_or_init_storage()
    await owned_ticket(ticket_id, user, storage)
    processing = await tickets().find_one_and_update(
        {"_id": ticket_id, "owner": user.sub},
        {"$set": {"cancel_requested": True}},
        return_document=ReturnDocument.AFTER,
    )
    if (
        processing
        and processing["state"] == "completed"
        and processing["result"]["key"] == processing["key"]
    ):
        from src.api.routes.upload import _file_record_storage

        await _file_record_storage.schedule_owned_cleanup(processing["key"], user.sub)
    claimed = await tickets().find_one_and_update(
        {"_id": ticket_id, "state": {"$in": ["active", "cleanup"]}},
        {"$set": {"state": "cleanup"}},
        return_document=ReturnDocument.AFTER,
    )
    if claimed:
        await cleanup_ticket(claimed, storage)
    return {"canceled": True}


async def cleanup_expired_uploads() -> None:
    from src.api.routes.upload import get_or_init_storage

    storage = await get_or_init_storage()
    identity = storage_identity(storage)
    collection = tickets()
    await collection.create_index("expires_at")
    # Terminal ticket metadata can expire; active tickets must first clean up storage.
    await collection.delete_many({"state": "completed", "expires_at": {"$lte": utc_now()}})
    for _ in range(100):
        ticket = await collection.find_one_and_update(
            {"storage": identity, "state": {"$ne": "completed"}, "expires_at": {"$lte": utc_now()}},
            {"$set": {"state": "cleanup", "expires_at": utc_now() + timedelta(minutes=5)}},
            return_document=ReturnDocument.AFTER,
        )
        if not ticket:
            break
        try:
            await cleanup_ticket(ticket, storage)
        except Exception:
            logger.exception("Expired direct upload cleanup failed for %s", ticket["_id"])
