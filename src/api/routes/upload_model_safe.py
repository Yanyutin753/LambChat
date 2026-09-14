"""Model-safe image serving for the file proxy route.

Vision providers reject formats like TIFF (GLM: 1210 "image input format/
parsing error"). Uploads are transcoded to JPEG going forward, but sessions
created before that still reference legacy keys by URL — this module heals
them on read: the original is transcoded once with Pillow and the JPEG is
cached beside the original (uploads are content-addressed and immutable, so
the cache never goes stale).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.responses import Response

from src.api.routes.upload_cover import (
    _RENDER_ACQUIRE_TIMEOUT,
    _RENDER_MAX_SOURCE_BYTES,
    _get_render_semaphore,
    _key_ext,
    _path_exists,
)
from src.infra.async_utils import run_blocking_io
from src.infra.image_utils import needs_model_safe_transcode, transcode_image_bytes
from src.infra.logging import get_logger
from src.kernel.errors import AppError, ErrorCode

logger = get_logger(__name__)

_MODEL_SAFE_CACHE_PREFIX = "model-safe"
_model_safe_inflight: dict[str, asyncio.Task] = {}


def model_safe_transcode_needed(key: str) -> bool:
    """True when *key* is an image upload in a vision-unsafe format.

    Only ``image/`` prefixed keys qualify — a TIFF stored as a document may
    be multi-page and must not be collapsed into a single JPEG.
    """
    if not key.startswith("image/"):
        return False
    return needs_model_safe_transcode(_key_ext(key))


def _model_safe_cache_response(data: bytes) -> Response:
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def get_model_safe_file_response(storage: Any, key: str) -> Response | None:
    """Serve a legacy unsafe image as JPEG, or None when not applicable."""
    if not model_safe_transcode_needed(key):
        return None

    if storage.is_local:
        file_path = storage.get_file_path(key)
        if not await run_blocking_io(_path_exists, file_path):
            raise AppError(ErrorCode.FILE_NOT_FOUND)

        def _read_and_transcode() -> bytes:
            with open(file_path, "rb") as fh:
                transcoded, _mime_type = transcode_image_bytes(fh.read())
                return transcoded

        try:
            body = await run_blocking_io(_read_and_transcode)
        except ValueError as exc:
            logger.error(f"Failed to transcode local image {key}: {exc}")
            raise AppError(ErrorCode.IMAGE_TRANSCODE_FAILED, args={"ext": _key_ext(key)})
        except Exception as exc:
            logger.error(f"Failed to read local image {key}: {exc}")
            raise AppError(ErrorCode.FILE_READ_FAILED)
        return _model_safe_cache_response(body)

    cache_key = f"{_MODEL_SAFE_CACHE_PREFIX}/{key}.jpg"
    if await storage.file_exists(cache_key):
        data = await storage.download_file(cache_key)
        return _model_safe_cache_response(data)

    try:
        source_size = await storage.get_size(key)
        if source_size and source_size > _RENDER_MAX_SOURCE_BYTES:
            raise AppError(ErrorCode.IMAGE_TRANSCODE_FAILED, args={"ext": _key_ext(key)})
    except AppError:
        raise
    except Exception as exc:
        logger.warning(f"Failed to stat source for model-safe transcode {key}: {exc}")

    return await _render_and_cache(storage, key, cache_key)


async def _render_and_cache(storage: Any, key: str, cache_key: str) -> Response:
    """Download → transcode → cache, guarded against bursts (mirrors the
    thumb flow: in-flight dedup + the shared render semaphore)."""
    existing = _model_safe_inflight.get(cache_key)
    if existing is not None:
        return await asyncio.shield(existing)

    semaphore = _get_render_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_RENDER_ACQUIRE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info(f"Model-safe transcode slots saturated for {key}; falling back")
        raise AppError(ErrorCode.IMAGE_TRANSCODE_FAILED, args={"ext": _key_ext(key)})

    try:
        existing = _model_safe_inflight.get(cache_key)
        if existing is not None:
            return await asyncio.shield(existing)

        task = asyncio.create_task(_do_render_and_cache(storage, key, cache_key))
        _model_safe_inflight[cache_key] = task
        task.add_done_callback(lambda _t: _model_safe_inflight.pop(cache_key, None))
        return await asyncio.shield(task)
    finally:
        semaphore.release()


async def _do_render_and_cache(storage: Any, key: str, cache_key: str) -> Response:
    try:
        data = await storage.download_file(key)
    except Exception as exc:
        logger.error(f"Failed to download source for model-safe transcode {key}: {exc}")
        raise AppError(ErrorCode.FILE_URL_FAILED)

    try:
        body, _mime_type = await run_blocking_io(transcode_image_bytes, data)
    except ValueError as exc:
        logger.error(f"Failed to transcode image {key}: {exc}")
        raise AppError(ErrorCode.IMAGE_TRANSCODE_FAILED, args={"ext": _key_ext(key)})

    try:
        await storage.upload_to_key(
            body,
            cache_key,
            content_type="image/jpeg",
            skip_size_limit=True,
        )
    except Exception as exc:
        logger.warning(f"Failed to cache model-safe transcode for {key}: {exc}")
    return _model_safe_cache_response(body)
