"""Fence storage writes and atomically publish a verified configuration."""

import asyncio
import os
import socket
import uuid
from contextlib import asynccontextmanager
from functools import wraps

from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now_iso

STORAGE_STATE_ID = "__settings_atomic__:storage"
_writes: set[asyncio.Task] = set()


class StorageConfigurationChangedError(ValueError):
    pass


class StorageGate:
    def __init__(self, collection):
        self.collection = collection

    @asynccontextmanager
    async def write(self, identity: str):
        token = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        state = await self.collection.find_one_and_update(
            {"_id": STORAGE_STATE_ID, "identity": identity},
            {"$push": {"writers": token}, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if state is None:
            raise StorageConfigurationChangedError(
                "Storage configuration changed; retry the operation"
            )
        cancelled = False
        try:
            yield
        except asyncio.CancelledError:
            # SDK threads can still write after their awaiting coroutine is cancelled.
            cancelled = True
            raise
        finally:
            if not cancelled:
                await asyncio.shield(
                    self.collection.update_one(
                        {"_id": STORAGE_STATE_ID}, {"$pull": {"writers": token}}
                    )
                )

    async def commit(self, snapshot: dict, values: dict, identity: str, user_id: str, report: dict):
        result = await self.collection.find_one_and_update(
            {
                "_id": STORAGE_STATE_ID,
                "identity": snapshot["identity"],
                "revision": snapshot["revision"],
                "writers": [],
            },
            {
                "$set": {
                    "values": values,
                    "identity": identity,
                    "verification": report,
                    "updated_at": utc_now_iso(),
                    "updated_by": user_id,
                },
                "$inc": {"revision": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise ValueError("Storage changed during verification; cutover refused")
        return result


def storage_write(method):
    async def write(self, *args, **kwargs):
        from src.infra.settings.storage_migration import collection, config_identity, ensure_state

        config = getattr(self, "_config", None) or self.config
        await ensure_state()
        try:
            async with StorageGate(collection()).write(config_identity(config)):
                return await method(self, *args, **kwargs)
        except StorageConfigurationChangedError as exc:
            from src.kernel.errors import AppError, ErrorCode

            raise AppError(ErrorCode.STORAGE_CONFIGURATION_STALE) from exc

    def finished(task):
        _writes.discard(task)
        if not task.cancelled():
            task.exception()

    @wraps(method)
    async def guarded(self, *args, **kwargs):
        if not getattr(self, "_managed", False):
            return await method(self, *args, **kwargs)
        # A disconnected request must not release the fence while its SDK thread still writes.
        task = asyncio.create_task(write(self, *args, **kwargs))
        _writes.add(task)
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    return guarded
