"""Associate resources actually uploaded while revealing a generated document."""

from src.infra.upload.access import validate_file_key
from src.infra.upload.file_record import get_file_record_storage
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode


async def link_generated_resources(
    parent_key: str, user_id: str | None, resource_keys: list[str]
) -> None:
    if not resource_keys:
        return
    keys = list(dict.fromkeys(resource_keys))
    if not user_id or parent_key in keys:
        raise AppError(ErrorCode.FILE_NOT_FOUND)
    for key in [parent_key, *keys]:
        validate_file_key(key)
        if not key.startswith("revealed_files/"):
            raise AppError(ErrorCode.FILE_NOT_FOUND)

    records = get_file_record_storage()
    documents = {
        record["key"]: record
        async for record in records.collection.find({"key": {"$in": [parent_key, *keys]}})
    }
    for key in [parent_key, *keys]:
        record = documents.get(key)
        if (
            not record
            or record.get("uploaded_by") != user_id
            or record.get("hash") != "generated:" + key
            or "deleting_at" in record
            or "private_session_id" in record
            or (key != parent_key and record.get("resource_parent_key") not in (None, parent_key))
        ):
            raise AppError(ErrorCode.FILE_NOT_FOUND)

    def write_guard(key: str) -> dict:
        return {
            "key": key,
            "uploaded_by": user_id,
            "hash": "generated:" + key,
            "deleting_at": {"$exists": False},
            "private_session_id": {"$exists": False},
        }

    # Publish the parent allowlist last; an interrupted update grants no new resources.
    for key in keys:
        query = write_guard(key)
        query["$or"] = [
            {"resource_parent_key": {"$exists": False}},
            {"resource_parent_key": parent_key},
        ]
        result = await records.collection.update_one(
            query,
            {"$set": {"resource_parent_key": parent_key, "updated_at": utc_now()}},
        )
        if result.matched_count != 1:
            raise AppError(ErrorCode.FILE_NOT_FOUND)
    result = await records.collection.update_one(
        write_guard(parent_key),
        {"$addToSet": {"resource_keys": {"$each": keys}}, "$set": {"updated_at": utc_now()}},
    )
    if result.matched_count != 1:
        raise AppError(ErrorCode.FILE_NOT_FOUND)
