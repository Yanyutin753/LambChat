"""16:9 cover thumbnails for the file proxy route (?cover=1).

File-library cards must never download the original file just to show a
cover: Aliyun OSS processes the crop/snapshot server-side behind a
long-lived signed URL, local storage resizes with Pillow, everything else
404s so clients can fall back to a generated cover without any traffic.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3 import S3Provider

logger = get_logger(__name__)

COVER_WIDTH = 560
COVER_HEIGHT = 315
COVER_SIGNED_EXPIRES = 7 * 24 * 3600  # stable URL → browser/CDN can cache

_COVER_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp"}
# gif keeps its animation and svg is vector data — neither crops well
_COVER_VIDEO_EXTS = {"mp4", "webm", "mov", "m4v"}


def cover_process_for_key(key: str, t_ms: int) -> str | None:
    """OSS processing directive for a key, or None when unsupported."""
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    if ext in _COVER_IMAGE_EXTS:
        return f"image/resize,m_fill,w_{COVER_WIDTH},h_{COVER_HEIGHT}"
    if ext in _COVER_VIDEO_EXTS:
        return f"video/snapshot,t_{t_ms},f_jpg,w_{COVER_WIDTH},h_{COVER_HEIGHT},m_fast"
    return None


def _render_local_cover(file_path) -> bytes:
    import io

    from PIL import Image, ImageOps

    with Image.open(file_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        fitted = ImageOps.fit(img, (COVER_WIDTH, COVER_HEIGHT))
        buf = io.BytesIO()
        fitted.save(buf, format="JPEG", quality=85)
        return buf.getvalue()


def _path_exists(file_path) -> bool:
    import os

    return os.path.exists(file_path)


async def get_file_cover_response(storage: Any, key: str, t: int | None) -> Response:
    t_ms = t if t is not None else 1000
    process = cover_process_for_key(key, t_ms)
    if not process:
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")

    if storage.is_local:
        # Local storage has no server-side processing; resize via Pillow.
        if key.rsplit(".", 1)[-1].lower() not in _COVER_IMAGE_EXTS:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")
        file_path = storage.get_file_path(key)
        if not await run_blocking_io(_path_exists, file_path):
            raise HTTPException(status_code=404, detail="File not found")
        try:
            body = await run_blocking_io(_render_local_cover, file_path)
        except Exception as e:
            logger.error(f"Failed to render local cover for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to render cover")
        return Response(
            content=body,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    provider = getattr(getattr(storage, "_config", None), "provider", None)
    if provider != S3Provider.ALIYUN:
        # Only Aliyun OSS supports x-oss-process; other providers fall back
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")

    try:
        exists = await storage.file_exists(key)
        if not exists:
            raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to check file existence for {key}: {e}")

    try:
        url = await storage.get_presigned_url(key, COVER_SIGNED_EXPIRES, process=process)
    except TypeError:
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")
    except Exception as e:
        logger.error(f"Failed to generate cover URL for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    return Response(
        status_code=302,
        headers={"Location": url, "Cache-Control": "public, max-age=86400"},
    )
