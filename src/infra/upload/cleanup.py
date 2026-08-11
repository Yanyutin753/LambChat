"""Bounded runtime lifecycle for delayed file-record cleanup."""

from __future__ import annotations

import asyncio
from typing import Any

from src.infra.storage.s3.service import get_or_init_storage
from src.infra.upload.file_record import FileRecordStorage

_file_record_storage = FileRecordStorage()
_cleanup_lock = asyncio.Lock()
_active_cleanup_tasks: set[asyncio.Task[Any]] = set()


async def run_file_record_cleanup() -> int:
    """Run one bounded cleanup batch using the shared object-storage service."""
    current = asyncio.current_task()
    if current is not None:
        _active_cleanup_tasks.add(current)
    try:
        async with _cleanup_lock:
            object_storage = await get_or_init_storage()
            return await _file_record_storage.cleanup_scheduled_records(object_storage)
    finally:
        if current is not None:
            _active_cleanup_tasks.discard(current)


async def close_file_record_cleanup() -> None:
    """Cancel in-flight cleanup before releasing this module's Mongo wrapper."""
    current = asyncio.current_task()
    tasks = [task for task in _active_cleanup_tasks if task is not current]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await _file_record_storage.close()

