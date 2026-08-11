from __future__ import annotations

import asyncio

import pytest

from src.infra.upload import cleanup


@pytest.mark.asyncio
async def test_run_file_record_cleanup_uses_shared_object_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    objects = object()
    calls: list[object] = []

    class _FileRecords:
        async def cleanup_scheduled_records(self, object_storage: object) -> int:
            calls.append(object_storage)
            return 2

    async def _get_objects() -> object:
        return objects

    monkeypatch.setattr(cleanup, "_file_record_storage", _FileRecords())
    monkeypatch.setattr(cleanup, "get_or_init_storage", _get_objects)

    deleted = await cleanup.run_file_record_cleanup()

    assert deleted == 2
    assert calls == [objects]


@pytest.mark.asyncio
async def test_close_file_record_cleanup_cancels_active_run_before_closing_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()
    closed = False

    class _FileRecords:
        async def cleanup_scheduled_records(self, object_storage: object) -> int:
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def close(self) -> None:
            nonlocal closed
            assert cancelled.is_set()
            closed = True

    async def _get_objects() -> object:
        return object()

    monkeypatch.setattr(cleanup, "_file_record_storage", _FileRecords())
    monkeypatch.setattr(cleanup, "get_or_init_storage", _get_objects)
    cleanup._active_cleanup_tasks.clear()
    task = asyncio.create_task(cleanup.run_file_record_cleanup())
    await started.wait()

    await cleanup.close_file_record_cleanup()

    assert task.cancelled()
    assert closed is True

