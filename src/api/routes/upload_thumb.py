"""Aspect-fit chat thumbnails for the file proxy route (?thumb=1).

Chat bubbles must never download originals just to render inline: Aliyun
OSS resizes server-side behind a day-aligned signed URL, local storage
resizes with Pillow, and every other S3 provider renders once with Pillow
and caches the small JPEG beside the original (uploads are
content-addressed and immutable, so the cache never goes stale).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response

from src.api.routes.upload_cover import (
    _RENDER_ACQUIRE_TIMEOUT,
    _RENDER_MAX_SOURCE_BYTES,
    _get_render_semaphore,
    _key_ext,
    _path_exists,
    cover_signature_expiry,
)
from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3 import S3Provider

logger = get_logger(__name__)

THUMB_SIZE = 560
_THUMB_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp"}
# gif keeps its animation and svg is vector data — neither fits a raster thumb
_THUMB_CACHE_PREFIX = f"thumbs/{THUMB_SIZE}"
_thumb_inflight: dict[str, asyncio.Task] = {}


def thumb_process_for_key(key: str) -> str | None:
    """OSS processing directive for a chat thumbnail, or None when unsupported."""
    if _key_ext(key) in _THUMB_IMAGE_EXTS:
        return f"image/resize,m_lfit,w_{THUMB_SIZE},h_{THUMB_SIZE}"
    return None


def render_chat_thumb(data: bytes) -> bytes:
    """Aspect-fit thumbnail (m_lfit semantics — never crops, whole image visible).

    Alpha is composited onto white: JPEG has no alpha and a plain convert()
    would turn transparent pixels black.
    """
    import io

    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as opened:
        img: Image.Image = ImageOps.exif_transpose(opened)
        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in opened.info
        )
        if has_alpha:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        fitted = ImageOps.contain(img, (THUMB_SIZE, THUMB_SIZE))
        buf = io.BytesIO()
        fitted.save(buf, format="JPEG", quality=82)
        return buf.getvalue()


def _thumb_cache_response(data: bytes) -> Response:
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def get_file_thumb_response(storage: Any, key: str) -> Response:
    if not thumb_process_for_key(key):
        # Unsupported formats (gif/svg/video/…) 404 so the <img> falls back
        # to the original URL without downloading anything extra.
        raise HTTPException(status_code=404, detail="Thumb not available")

    if storage.is_local:
        file_path = storage.get_file_path(key)
        if not await run_blocking_io(_path_exists, file_path):
            raise HTTPException(status_code=404, detail="File not found")

        def _read_and_render() -> bytes:
            with open(file_path, "rb") as fh:
                return render_chat_thumb(fh.read())

        try:
            body = await run_blocking_io(_read_and_render)
        except Exception as e:
            logger.error(f"Failed to render local thumb for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to render thumb")
        return _thumb_cache_response(body)

    provider = getattr(getattr(storage, "_config", None), "provider", None)
    if provider == S3Provider.ALIYUN:
        try:
            exists = await storage.file_exists(key)
            if not exists:
                raise HTTPException(status_code=404, detail="File not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to check file existence for thumb {key}: {e}")

        try:
            url = await storage.get_cover_presigned_url(
                key, cover_signature_expiry(), process=thumb_process_for_key(key)
            )
        except Exception as e:
            logger.error(f"Failed to generate thumb URL for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate file URL")
        return Response(
            status_code=302,
            headers={"Location": url, "Cache-Control": "public, max-age=86400"},
        )

    # Other S3 providers: render once, cache beside the original. The small
    # JPEG streams through the app (presigned URLs rotate per request and
    # self-hosted endpoints are often not browser-reachable).
    thumb_key = f"{_THUMB_CACHE_PREFIX}/{key}.jpg"
    if await storage.file_exists(thumb_key):
        data = await storage.download_file(thumb_key)
        return _thumb_cache_response(data)

    try:
        source_size = await storage.get_size(key)
        if source_size and source_size > _RENDER_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=404, detail="Thumb not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to stat source for thumb {key}: {e}")

    return await _render_and_cache_thumb(storage, key, thumb_key)


async def _render_and_cache_thumb(storage: Any, key: str, thumb_key: str) -> Response:
    """Download → render → cache, guarded against bursts (mirrors the cover
    flow: in-flight dedup + the shared render semaphore)."""
    existing = _thumb_inflight.get(thumb_key)
    if existing is not None:
        return await asyncio.shield(existing)

    semaphore = _get_render_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_RENDER_ACQUIRE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info(f"Thumb render slots saturated for {key}; falling back")
        raise HTTPException(status_code=404, detail="Thumb not available")

    try:
        existing = _thumb_inflight.get(thumb_key)
        if existing is not None:
            return await asyncio.shield(existing)

        task = asyncio.create_task(_do_render_and_cache_thumb(storage, key, thumb_key))
        _thumb_inflight[thumb_key] = task
        task.add_done_callback(lambda _t: _thumb_inflight.pop(thumb_key, None))
        return await asyncio.shield(task)
    finally:
        semaphore.release()


async def _do_render_and_cache_thumb(storage: Any, key: str, thumb_key: str) -> Response:
    try:
        data = await storage.download_file(key)
    except Exception as e:
        logger.error(f"Failed to download source for thumb {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    try:
        body = await run_blocking_io(render_chat_thumb, data)
    except Exception as e:
        logger.error(f"Failed to render thumb for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to render thumb")

    try:
        await storage.upload_to_key(
            body,
            thumb_key,
            content_type="image/jpeg",
            skip_size_limit=True,
        )
    except Exception as e:
        logger.warning(f"Failed to cache thumb for {key}: {e}")
    return _thumb_cache_response(body)
