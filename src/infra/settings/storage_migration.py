"""An authoritative storage-settings bundle and its verified cutover gate."""

import hashlib
import json
import re
import uuid
from pathlib import Path

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3.cutover import STORAGE_STATE_ID, StorageGate
from src.infra.storage.s3.migration import verify_contents
from src.infra.storage.s3.types import S3Config, S3Provider
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import SETTING_DEFINITIONS, settings
from src.kernel.errors import AppError, ErrorCode

logger = get_logger(__name__)

STORAGE_KEYS = frozenset(
    {
        "S3_ENABLED",
        "S3_PROVIDER",
        "S3_ENDPOINT_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_REGION",
        "S3_BUCKET_NAME",
        "S3_PATH_STYLE",
        "S3_PUBLIC_BUCKET",
        "LOCAL_STORAGE_PATH",
    }
)


def runtime_values() -> dict:
    return {key: getattr(settings, key) for key in STORAGE_KEYS}


def make_config(values: dict) -> S3Config:
    enabled = values["S3_ENABLED"]
    if isinstance(enabled, str):
        enabled = enabled.lower() in {"true", "1", "yes", "on"}
    provider = S3Provider(values["S3_PROVIDER"]) if enabled else S3Provider.LOCAL
    return S3Config(
        provider=provider,
        endpoint_url=values["S3_ENDPOINT_URL"] or None,
        access_key=values["S3_ACCESS_KEY"] or "",
        secret_key=values["S3_SECRET_KEY"] or "",
        region=values["S3_REGION"] or "us-east-1",
        bucket_name=values["S3_BUCKET_NAME"] or "",
        path_style=values["S3_PATH_STYLE"],
        public_bucket=values["S3_PUBLIC_BUCKET"],
        storage_path=values["LOCAL_STORAGE_PATH"] or "./uploads",
        custom_domain=settings.S3_CUSTOM_DOMAIN or None,
        max_file_size=settings.S3_MAX_FILE_SIZE,
        internal_max_upload_size=settings.S3_INTERNAL_UPLOAD_MAX_SIZE,
        presigned_url_expires=settings.S3_PRESIGNED_URL_EXPIRES,
    )


def config_identity(config: S3Config) -> str:
    if config.provider == S3Provider.LOCAL:
        identity = {"provider": "local", "path": str(Path(config.storage_path).resolve())}
    else:
        identity = config.model_dump(
            include={
                "provider",
                "endpoint_url",
                "access_key",
                "secret_key",
                "region",
                "bucket_name",
                "path_style",
                "public_bucket",
            },
            mode="json",
        )
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def collection():
    from src.infra.storage.mongodb import get_mongo_client

    return get_mongo_client()[settings.MONGODB_DB]["system_settings"]


async def ensure_state(store=None) -> dict:
    store = collection() if store is None else store
    existing = await store.find_one({"_id": STORAGE_STATE_ID})
    if existing is not None:
        return existing
    # Bootstrap from the running configuration, not stale values in a cloned database.
    values = runtime_values()
    boot_identity = config_identity(make_config(values))
    local_path = await store.find_one({"_id": "LOCAL_STORAGE_PATH"})
    if local_path and local_path.get("value"):
        values["LOCAL_STORAGE_PATH"] = local_path["value"]
    identity = config_identity(make_config(values))
    await store.update_one(
        {"_id": STORAGE_STATE_ID},
        {
            "$setOnInsert": {
                "values": values,
                "identity": identity,
                "boot_identity": boot_identity,
                "revision": 0,
                "writers": [],
                "updated_at": utc_now_iso(),
                "updated_by": "system:storage-bootstrap",
            }
        },
        upsert=True,
    )
    state = await store.find_one({"_id": STORAGE_STATE_ID})
    if state is None:
        raise RuntimeError("Storage cutover state could not be initialized")
    return state


def overlay_settings(docs: dict) -> None:
    state = docs.get(STORAGE_STATE_ID)
    if state is not None:
        for key, value in state["values"].items():
            docs[key] = {
                "_id": key,
                "value": value,
                "updated_at": state.get("updated_at"),
                "updated_by": state.get("updated_by"),
            }


def normalize_changes(changes: dict) -> dict:
    if not changes or not changes.keys() <= STORAGE_KEYS:
        raise ValueError("Only storage connection settings may be changed atomically")
    result = {}
    for key, value in changes.items():
        definition = SETTING_DEFINITIONS[key]
        if value == "********":
            raise ValueError("Cannot set masked value")
        kind = definition["type"].value
        if kind == "boolean" and type(value) is not bool:
            raise ValueError(f"Setting {key} expects a boolean")
        if kind in {"string", "select"}:
            value = str(value)
        if kind == "select" and value not in definition["options"]:
            raise ValueError(f"Invalid storage provider for {key}")
        result[key] = value
    return result


async def required_keys(db) -> dict[str, str | None]:
    required = {}
    async for row in db.file_records.find({"reference_count": {"$gt": 0}}, {"key": 1, "hash": 1}):
        digest = row.get("hash") or ""
        required[row["key"]] = digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None
    async for row in db.revealed_files.find({}, {"file_key": 1, "content_hash": 1}):
        key = row.get("file_key")
        if not key or "://" in key:
            continue
        digest = row.get("content_hash", "")
        required.setdefault(key, digest if re.fullmatch(r"[0-9a-f]{64}", digest or "") else None)
    return required


async def change_storage(changes: dict, user_id: str, store=None) -> dict:
    from src.infra.storage.s3.service import S3StorageService

    changes = normalize_changes(changes)
    store = collection() if store is None else store
    snapshot = await ensure_state(store)
    values = {**snapshot["values"], **changes}
    if values == snapshot["values"]:
        return snapshot
    candidate_config = make_config(values)
    source = S3StorageService(make_config(snapshot["values"]))
    candidate = S3StorageService(candidate_config)
    try:
        if snapshot["writers"] or await store.database.direct_uploads.find_one(
            {"state": {"$ne": "completed"}}, {"_id": 1}
        ):
            raise AppError(ErrorCode.STORAGE_MIGRATION_BUSY)
        identity = config_identity(candidate_config)
        if identity == snapshot["identity"]:
            report = snapshot.get("verification", {})
        else:
            try:
                if source.is_local and not await run_long_blocking_io(
                    Path(source._config.storage_path).is_dir
                ):
                    raise ValueError("Storage migration source directory is unavailable")
                backend = candidate._get_backend()
                probe_key = f"storage-migration-probe/{uuid.uuid4().hex}"
                probe = uuid.uuid4().bytes
                try:
                    await backend.upload_bytes(probe, probe_key)
                    if await backend.download(probe_key) != probe:
                        raise ValueError("Storage destination read/write verification failed")
                finally:
                    if not await backend.delete(probe_key):
                        raise ValueError("Storage destination cleanup failed")
                report = await verify_contents(
                    source._get_backend(), backend, await required_keys(store.database)
                )
            except Exception as exc:
                logger.warning("Storage migration verification refused (%s)", type(exc).__name__)
                raise AppError(ErrorCode.STORAGE_MIGRATION_BLOCKED) from exc
        try:
            return await StorageGate(store).commit(snapshot, values, identity, user_id, report)
        except ValueError as exc:
            raise AppError(ErrorCode.STORAGE_MIGRATION_BUSY) from exc
    finally:
        await source.close()
        await candidate.close()
