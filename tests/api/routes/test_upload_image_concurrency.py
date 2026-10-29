"""Cloud image preparation bounds live decoded buffers even after HTTP cancellation."""

import asyncio
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.api.routes import upload, upload_image


async def test_image_preparation_limits_original_reads_to_two_concurrent_jobs(monkeypatch):
    loop = asyncio.get_running_loop()
    two_started = asyncio.Event()
    third_started = asyncio.Event()
    release = threading.Event()
    lock = threading.Lock()
    reads = 0

    def blocked_read(file):
        nonlocal reads
        with lock:
            reads += 1
            if reads == 2:
                loop.call_soon_threadsafe(two_started.set)
            if reads == 3:
                loop.call_soon_threadsafe(third_started.set)
        assert release.wait(5)
        return file.read()

    monkeypatch.setattr(upload_image, "_read_all", blocked_read)
    monkeypatch.setattr(
        upload_image,
        "prepare_upload_image_bytes",
        lambda content, mime, **_: (b"jpeg", "image/jpeg"),
    )
    originals = [upload.SpooledUpload(io.BytesIO(b"original"), "source", 8) for _ in range(4)]
    tasks = [
        asyncio.create_task(
            upload._prepare_spooled_image(
                original,
                max_size_bytes=1024,
                max_size_mb=1,
                source_ext="tiff",
                source_mime_type="image/tiff",
            )
        )
        for original in originals
    ]
    try:
        await asyncio.wait_for(two_started.wait(), 3)
        try:
            await asyncio.wait_for(third_started.wait(), 0.2)
        except TimeoutError:
            pass
        assert not third_started.is_set(), "third original was read while two decoders held slots"
    finally:
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                result[0].close()
        for original in originals:
            original.close()
    assert all(isinstance(result, tuple) for result in results)


async def test_cancelled_upload_keeps_its_live_decoder_slot_and_closes_abandoned_spools(
    monkeypatch,
):
    loop = asyncio.get_running_loop()
    two_started = asyncio.Event()
    third_started = asyncio.Event()
    first_started = asyncio.Event()
    result_closed = asyncio.Event()
    release = threading.Event()
    lock = threading.Lock()
    preparations = 0
    spools = []
    original_factory = upload.SpooledTemporaryFile

    def tracking_spool(*args, **kwargs):
        spool = original_factory(*args, **kwargs)
        spools.append(spool)
        original_close = spool.close

        def close():
            original_close()
            if len(spools) >= 4 and all(item.closed for item in spools):
                loop.call_soon_threadsafe(result_closed.set)

        spool.close = close
        return spool

    def blocked_prepare(content, mime, **kwargs):
        nonlocal preparations
        with lock:
            preparations += 1
            if preparations == 1:
                loop.call_soon_threadsafe(first_started.set)
            if preparations == 2:
                loop.call_soon_threadsafe(two_started.set)
            if preparations == 3:
                loop.call_soon_threadsafe(third_started.set)
        assert release.wait(5)
        return b"jpeg", "image/jpeg"

    monkeypatch.setattr(upload, "SpooledTemporaryFile", tracking_spool)
    monkeypatch.setattr(upload_image, "SpooledTemporaryFile", tracking_spool)
    monkeypatch.setattr(upload_image, "prepare_upload_image_bytes", blocked_prepare)
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 1, "video": 1, "audio": 1, "document": 1}),
    )
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        SimpleNamespace(find_by_hash=AsyncMock(return_value=None), create=AsyncMock()),
    )
    monkeypatch.setattr(
        upload,
        "get_or_init_storage",
        AsyncMock(
            return_value=SimpleNamespace(
                upload_stream_to_key=AsyncMock(
                    return_value=SimpleNamespace(key="image/owner/result.jpg")
                )
            )
        ),
    )

    def start_upload():
        return asyncio.create_task(
            upload.upload_file(
                SimpleNamespace(headers={}, base_url="http://testserver/"),
                UploadFile(
                    io.BytesIO(b"original"),
                    filename="photo.tiff",
                    headers=Headers({"content-type": "image/tiff"}),
                ),
                SimpleNamespace(sub="owner", permissions=["file:upload"], roles=[]),
            )
        )

    first = start_upload()
    others = []
    try:
        await asyncio.wait_for(first_started.wait(), 3)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not spools[0].closed, "request closed a spool still owned by preparation"
        others = [start_upload(), start_upload()]
        await asyncio.wait_for(two_started.wait(), 3)
        try:
            await asyncio.wait_for(third_started.wait(), 0.2)
        except TimeoutError:
            pass
        assert not third_started.is_set(), "cancelled request released a still-running decoder slot"
    finally:
        release.set()
        if not first.done():
            first.cancel()
        results = await asyncio.gather(first, *others, return_exceptions=True)
    assert all(isinstance(result, dict) for result in results[1:])
    await asyncio.wait_for(result_closed.wait(), 3)
    assert all(spool.closed for spool in spools)
