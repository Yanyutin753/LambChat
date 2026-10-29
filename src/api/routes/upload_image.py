"""Bounded cloud preparation of uploaded images and owned temporary files."""

import asyncio
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import Any, Protocol

from src.api.routes.upload_cover import _get_render_semaphore
from src.infra.async_utils import run_long_blocking_io
from src.infra.image_utils import prepare_upload_image_bytes
from src.infra.storage.s3.base import BinaryReadFile
from src.infra.utils.hashing import sha256_hexdigest
from src.kernel.errors import AppError, ErrorCode

UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024
_upload_image_tasks: set[asyncio.Task] = set()


async def drain_upload_image_tasks() -> None:
    if _upload_image_tasks:
        await asyncio.gather(*tuple(_upload_image_tasks), return_exceptions=True)


class UploadSpool(BinaryReadFile, Protocol):
    def close(self) -> None: ...


@dataclass
class SpooledUpload:
    file: UploadSpool
    sha256_hex: str
    size: int

    def close(self) -> None:
        self.file.close()


def _read_all(file: Any) -> bytes:
    return file.read()


async def _prepare_spooled_image(
    spooled_upload: SpooledUpload,
    *,
    max_size_bytes: int,
    max_size_mb: int,
    source_ext: str,
    source_mime_type: str | None,
) -> tuple[SpooledUpload, str]:
    """Own the input spool and decoder slot until the actual preparation finishes."""

    async def prepare() -> tuple[SpooledUpload, str]:
        try:
            async with _get_render_semaphore():
                return await _do_prepare_spooled_image(
                    spooled_upload,
                    max_size_bytes=max_size_bytes,
                    max_size_mb=max_size_mb,
                    source_ext=source_ext,
                    source_mime_type=source_mime_type,
                )
        finally:
            spooled_upload.close()

    task = asyncio.create_task(prepare())
    _upload_image_tasks.add(task)
    task.add_done_callback(_upload_image_tasks.discard)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # The decoder thread still owns its slot and spool after HTTP cancellation.
        def close_abandoned_result(done: asyncio.Task[tuple[SpooledUpload, str]]) -> None:
            if not done.cancelled() and done.exception() is None:
                done.result()[0].close()

        task.add_done_callback(close_abandoned_result)
        raise


async def _do_prepare_spooled_image(
    spooled_upload: SpooledUpload,
    *,
    max_size_bytes: int,
    max_size_mb: int,
    source_ext: str,
    source_mime_type: str | None,
) -> tuple[SpooledUpload, str]:
    """Normalize an image in the blocking pool and hash its final stored bytes."""
    await run_long_blocking_io(spooled_upload.file.seek, 0)
    content = await run_long_blocking_io(_read_all, spooled_upload.file)
    try:
        transcoded, mime_type = await run_long_blocking_io(
            prepare_upload_image_bytes, content, source_mime_type, source_ext=source_ext
        )
    except ValueError:
        raise AppError(ErrorCode.IMAGE_TRANSCODE_FAILED, args={"ext": source_ext})
    if len(transcoded) > max_size_bytes:
        raise AppError(ErrorCode.FILE_TOO_LARGE, args={"max": max_size_mb})

    sha256_hex = await run_long_blocking_io(sha256_hexdigest, transcoded)
    replacement = SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_LIMIT, mode="w+b")
    try:
        await run_long_blocking_io(replacement.write, transcoded)
        await run_long_blocking_io(replacement.seek, 0)
        new_upload = SpooledUpload(
            file=replacement,
            sha256_hex=sha256_hex,
            size=len(transcoded),
        )
    except Exception:
        replacement.close()
        raise
    return new_upload, mime_type
