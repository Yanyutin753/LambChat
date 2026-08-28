"""16:9 cover thumbnails for the file proxy route (?cover=1).

File-library cards must never download the original file just to show a
cover: Aliyun OSS processes the crop/snapshot server-side behind a
long-lived signed URL, local storage resizes with Pillow, everything else
404s so clients can fall back to a generated cover without any traffic.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3 import S3Provider

logger = get_logger(__name__)

COVER_WIDTH = 560
COVER_HEIGHT = 315
_DAY = 24 * 3600


# ── CJK font availability ────────────────────────────────────────────────
# pypdfium2's bundled pdfium substitutes fonts for PDFs that don't embed
# them (the common case for WPS/browser exports). It scans a fixed set of
# system directories — no fontconfig, no $HOME/.fonts. Docker images ship
# fonts-noto-cjk; for bare venv deployments the bundled Noto Sans CJK is
# installed into /usr/local/share/fonts on first render so Chinese covers
# never degrade to tofu boxes on any Linux host.

_BUNDLED_CJK_FONT = (
    Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSansCJK-Regular.ttc"
)
_FONT_SCAN_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/usr/share/X11/fonts/TTF",
    "/usr/share/X11/fonts/Type1",
]
_CJK_FONT_NAME_RE = re.compile(
    r"noto.*cjk|wqy|wenquanyi|source\s?han|simsun|simhei|yahei|"
    r"song|hei|kai|ming|droid.*fallback",
    re.IGNORECASE,
)
_cjk_fonts_ensured = False


def _scan_dirs_have_cjk_font(scan_dirs: list[str]) -> bool:
    for scan_dir in scan_dirs:
        root = Path(scan_dir)
        if not root.is_dir():
            continue
        for font_path in root.rglob("*"):
            if _CJK_FONT_NAME_RE.search(font_path.name):
                return True
    return False


def ensure_cjk_fonts_available(
    scan_dirs: list[str] | None = None,
    install_dir: Path | None = None,
) -> bool:
    """Best-effort, run-once font bootstrap. Returns True when a CJK font is
    (or was made) available in a pdfium-scanned directory."""
    global _cjk_fonts_ensured
    if _cjk_fonts_ensured:
        return True
    _cjk_fonts_ensured = True

    if sys.platform != "linux":
        # Windows/macOS render via OS font APIs and always ship CJK fonts.
        return True

    dirs = scan_dirs or _FONT_SCAN_DIRS
    if _scan_dirs_have_cjk_font(dirs):
        return True

    target_dir = install_dir or Path("/usr/local/share/fonts")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _BUNDLED_CJK_FONT.name
        if not target.exists():
            shutil.copy2(_BUNDLED_CJK_FONT, target)
        logger.info(f"Installed bundled CJK font for cover rendering: {target}")
    except OSError as e:
        logger.warning(
            "No CJK font found for PDF cover rendering and auto-install failed "
            f"({e}); non-embedded CJK text will render as tofu. Install "
            "fonts-noto-cjk or make /usr/local/share/fonts writable."
        )
        _cjk_fonts_ensured = False
        return False
    return True


def cover_signature_expiry() -> int:
    """Day-aligned expiry: every request within a day yields the identical
    signed URL, so browsers/CDNs disk-cache the thumbnail itself instead of
    re-fetching a fresh signature per visit. Valid until end of tomorrow."""
    now = int(time.time())
    return ((now // _DAY) + 2) * _DAY


_COVER_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp"}
# gif keeps its animation and svg is vector data — neither crops well
_COVER_VIDEO_EXTS = {"mp4", "webm", "mov", "m4v"}
_COVER_PDF_EXTS = {"pdf"}
_COVER_CACHE_PREFIX = f"covers/{COVER_WIDTH}x{COVER_HEIGHT}"
# Rendering downloads the source PDF server-side; skip absurdly large files
_PDF_MAX_SOURCE_BYTES = 30 * 1024 * 1024


def cover_process_for_key(key: str, t_ms: int) -> str | None:
    """OSS processing directive for a key, or None when unsupported."""
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    if ext in _COVER_IMAGE_EXTS:
        return f"image/resize,m_fill,w_{COVER_WIDTH},h_{COVER_HEIGHT}"
    if ext in _COVER_VIDEO_EXTS:
        return f"video/snapshot,t_{t_ms},f_jpg,w_{COVER_WIDTH},h_{COVER_HEIGHT},m_fast"
    return None


def _key_ext(key: str) -> str:
    return key.rsplit(".", 1)[-1].lower() if "." in key else ""


def render_pdf_cover(data: bytes) -> bytes:
    """Render the first PDF page letterboxed on a white 16:9 canvas.

    Rendered at 2x and served as JPEG so grids only ever load a small
    raster image, never the PDF itself.
    """
    import io

    import pypdfium2 as pdfium
    from PIL import Image

    ensure_cjk_fonts_available()

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[0]
        target_w = COVER_WIDTH * 2
        scale = max(target_w / page.get_width(), 0.5)
        img = page.render(scale=scale).to_pil().convert("RGB")
    finally:
        pdf.close()

    canvas = Image.new("RGB", (COVER_WIDTH * 2, COVER_HEIGHT * 2), "white")
    ratio = min(canvas.width / img.width, canvas.height / img.height)
    fitted = img.resize(
        (round(img.width * ratio), round(img.height * ratio)),
    )
    canvas.paste(
        fitted,
        (
            (canvas.width - fitted.width) // 2,
            (canvas.height - fitted.height) // 2,
        ),
    )
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def _get_pdf_cover_response(storage: Any, key: str) -> Response:
    """PDF covers need real content: render page 1 once, cache beside the
    original (uploads are content-addressed and immutable, so the cache
    never goes stale), and serve the small JPEG from then on."""
    thumb_key = f"{_COVER_CACHE_PREFIX}/{key}.jpg"
    expires = cover_signature_expiry()

    if storage.is_local:
        file_path = storage.get_file_path(key)
        if not await run_blocking_io(_path_exists, file_path):
            raise HTTPException(status_code=404, detail="File not found")

        def _read_and_render() -> bytes:
            with open(file_path, "rb") as fh:
                return render_pdf_cover(fh.read())

        try:
            body = await run_blocking_io(_read_and_render)
        except Exception as e:
            logger.error(f"Failed to render local PDF cover for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to render cover")
        return Response(
            content=body,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    try:
        if await storage.file_exists(thumb_key):
            url = await storage.get_presigned_url(thumb_key, expires)
            return Response(
                status_code=302,
                headers={
                    "Location": url,
                    "Cache-Control": "public, max-age=86400",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to check cached PDF cover for {key}: {e}")

    try:
        source_size = await storage.get_size(key)
        if source_size and source_size > _PDF_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to stat PDF for cover {key}: {e}")

    try:
        data = await storage.download_file(key)
    except Exception as e:
        logger.error(f"Failed to download PDF for cover {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    try:
        body = await run_blocking_io(render_pdf_cover, data)
    except Exception as e:
        logger.error(f"Failed to render PDF cover for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to render cover")

    try:
        await storage.upload_to_key(
            body,
            thumb_key,
            content_type="image/jpeg",
            skip_size_limit=True,
        )
        url = await storage.get_presigned_url(thumb_key, expires)
        return Response(
            status_code=302,
            headers={"Location": url, "Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        # Cache write is best-effort; serve the rendered bytes directly.
        logger.warning(f"Failed to cache PDF cover for {key}: {e}")
        return Response(
            content=body,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


def _render_local_cover(file_path) -> bytes:
    import io

    from PIL import Image, ImageOps

    with Image.open(file_path) as opened:
        img: Image.Image = ImageOps.exif_transpose(opened)
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
    if _key_ext(key) in _COVER_PDF_EXTS:
        return await _get_pdf_cover_response(storage, key)

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
        url = await storage.get_presigned_url(key, cover_signature_expiry(), process=process)
    except TypeError:
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")
    except Exception as e:
        logger.error(f"Failed to generate cover URL for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    return Response(
        status_code=302,
        headers={"Location": url, "Cache-Control": "public, max-age=86400"},
    )
