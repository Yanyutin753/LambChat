"""Retain prior bindings independently of the current session and runtime."""

import hashlib
import json

from src.infra.backend.workspace_selection import WORKSPACE_OPTION_KEYS
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings


def workspace_options(options: dict) -> dict:
    return {key: options[key] for key in WORKSPACE_OPTION_KEYS if key in options}


def _collection():
    return get_mongo_client()[settings.MONGODB_DB]["workspace_locations"]


async def remember_workspace_location(user_id: str, session_id: str, options: dict) -> None:
    binding = workspace_options(options)
    identity = json.dumps([user_id, session_id, binding], sort_keys=True, ensure_ascii=True)
    key = hashlib.sha256(identity.encode()).hexdigest()
    # Immutable source reference, not a claim that a transfer or binding change succeeded.
    await _collection().update_one(
        {"_id": key},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "session_id": session_id,
                "options": binding,
                "saved_at": utc_now(),
            }
        },
        upsert=True,
    )


async def list_workspace_locations(user_id: str, session_id: str, limit: int = 100) -> list[dict]:
    rows = (
        await _collection()
        .find(
            {"user_id": user_id, "session_id": session_id},
        )
        .sort("saved_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [
        {"id": row["_id"], "options": row["options"], "saved_at": row["saved_at"]} for row in rows
    ]


async def update_workspace_binding(
    collection, original: dict, session_id: str, metadata: dict, update_dict: dict
):
    """Retain the old reference before comparing and replacing the binding."""
    from src.kernel.errors import AppError, ErrorCode

    old_options = (original.get("metadata") or {}).get("agent_options")
    old_options = old_options if isinstance(old_options, dict) else {}
    candidate = metadata.get("agent_options", old_options)
    candidate = dict(candidate) if isinstance(candidate, dict) else {}
    for key in WORKSPACE_OPTION_KEYS:
        if f"agent_options.{key}" in metadata:
            candidate[key] = metadata[f"agent_options.{key}"]
    if workspace_options(candidate) != workspace_options(old_options):
        await remember_workspace_location(original["user_id"], session_id, old_options)
    query = {"_id": original["_id"], "user_id": original["user_id"]}
    raw_options = (original.get("metadata") or {}).get("agent_options")
    query["metadata.agent_options"] = raw_options
    result = await collection.find_one_and_update(
        query, {"$set": update_dict}, return_document=True
    )
    if result is None:
        raise AppError(ErrorCode.CONFLICT)
    return result
