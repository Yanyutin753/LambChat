"""16:9 cover thumbnails for the file proxy route (?cover=1).

File-library cards must never download the original file just to show a
cover: Aliyun OSS processes the crop/snapshot server-side behind a
long-lived signed URL, local storage resizes with Pillow, and every other
S3 provider renders once server-side (Pillow) and caches the small JPEG
beside the original. Video snapshots stay Aliyun-only (no server-side
ffmpeg) and unsupported types 404 so clients fall back to a generated
cover without any traffic.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import threading
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

# ── Render concurrency protection ────────────────────────────────────────
# Rendering (PDF pages / spreadsheet tables) is CPU-heavy and holds a slot
# in the app-wide 8-thread blocking-io pool shared with every storage
# operation. Cap concurrent renders and shed load fast so a burst of first
# views degrades to the client-side paper cover instead of starving the
# shared pool for everyone.

_RENDER_CONCURRENCY = 2
_RENDER_ACQUIRE_TIMEOUT = 8.0
# Per-event-loop semaphores (primitives bind to the loop that first awaits
# them; tests swap loops between cases)
_render_sems: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_render_inflight: dict[str, asyncio.Task] = {}


def _get_render_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _render_sems.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(_RENDER_CONCURRENCY)
        _render_sems[loop] = semaphore
    return semaphore


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
_font_install_lock = threading.Lock()
# FreeTypeFont is not shareable across threads; cache per rendering thread
# so the 18MB TTC is parsed once per worker instead of per render.
_sheet_font_cache = threading.local()


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
        with _font_install_lock:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / _BUNDLED_CJK_FONT.name
            if not target.exists():
                shutil.copy2(_BUNDLED_CJK_FONT, target)
        logger.info(
            f"Installed bundled CJK font for cover rendering: {target_dir / _BUNDLED_CJK_FONT.name}"
        )
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
# Legacy .xls (binary BIFF) needs xlrd; only OOXML sheets are parsed
_COVER_SHEET_EXTS = {"xlsx", "xlsm"}
_COVER_CACHE_PREFIX = f"covers/{COVER_WIDTH}x{COVER_HEIGHT}"
# Rendering downloads the source PDF server-side; skip absurdly large files
_RENDER_MAX_SOURCE_BYTES = 30 * 1024 * 1024


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
    """Render the top slice of the first PDF page, cover-cropped to 16:9.

    Only a slice is shown (the title area carries the visual identity), the
    page is scaled up to fill the full canvas — no letterbox bars. Rendered
    at 2x and served as JPEG so grids only ever load a small raster image,
    never the PDF itself.
    """
    import io

    import pypdfium2 as pdfium

    ensure_cjk_fonts_available()

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[0]
        target_w = COVER_WIDTH * 2
        target_h = COVER_HEIGHT * 2
        # Cover-crop semantics: scale so BOTH dimensions overflow the canvas
        scale = max(target_w / page.get_width(), target_h / page.get_height())
        img = page.render(scale=scale).to_pil().convert("RGB")
    finally:
        pdf.close()

    # Documents read top-first: crop from the top edge, centered horizontally.
    left = max((img.width - target_w) // 2, 0)
    top = 0
    cover = img.crop((left, top, left + target_w, top + target_h))

    buf = io.BytesIO()
    cover.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _sheet_preview_rows(data: bytes) -> list[list[str]]:
    """First rows of the first sheet, stringified."""
    import io

    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        rows: list[list[str]] = []
        if workbook.worksheets:
            sheet = workbook.worksheets[0]
            for row in sheet.iter_rows(min_row=1, max_row=7, max_col=5, values_only=True):
                rows.append(["" if cell is None else str(cell) for cell in row])
        return rows
    finally:
        workbook.close()


def _cached_sheet_font(size: int) -> Any:
    """FreeTypeFont per rendering thread (18MB TTC parsed once per worker)."""
    from PIL import ImageFont

    cache = getattr(_sheet_font_cache, "fonts", None)
    if cache is None:
        cache = {}
        _sheet_font_cache.fonts = cache
    font = cache.get(size)
    if font is None:
        font = ImageFont.truetype(str(_BUNDLED_CJK_FONT), size, index=0)
        cache[size] = font
    return font


def render_sheet_cover(data: bytes) -> bytes:
    """Draw the leading spreadsheet rows as a full-bleed 16:9 table.

    Text is set with the bundled Noto Sans CJK so headers like 「季度」
    render identically on every host; only a slice of the sheet is shown,
    laid out to fill the canvas.
    """
    import io

    from PIL import Image, ImageDraw

    ensure_cjk_fonts_available()

    rows = _sheet_preview_rows(data)
    width, height = COVER_WIDTH * 2, COVER_HEIGHT * 2

    header_bg = (243, 243, 245)
    header_fg = (55, 60, 70)
    body_fg = (90, 95, 105)
    grid = (228, 228, 232)
    accent = (70, 100, 220)

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    header_font = _cached_sheet_font(30)
    body_font = _cached_sheet_font(28)

    cols = max((len(r) for r in rows), default=0) or 1
    row_count = max(len(rows), 2)
    row_h = height // row_count
    col_w = [width // 5 + width // 10] + [
        (width - (width // 5 + width // 10)) // max(cols - 1, 1)
    ] * (cols - 1)

    def _grid_row(y: int) -> None:
        draw.line([(0, y + row_h - 1), (width, y + row_h - 1)], fill=grid, width=2)
        x = col_w[0]
        for c in range(1, cols):
            draw.line([(x, y), (x, y + row_h)], fill=grid, width=2)
            x += col_w[c]

    y = 0
    for r, row in enumerate(rows):
        is_header = r == 0
        if is_header:
            draw.rectangle([0, y, width, y + row_h], fill=header_bg)
        x = 0
        for c in range(cols):
            text = (row[c] if c < len(row) else "")[:18]
            if text:
                font = header_font if is_header else body_font
                color = header_fg if is_header else body_fg
                draw.text((x + 18, y + (row_h - 34) // 2), text, font=font, fill=color)
            x += col_w[c]
        _grid_row(y)
        if is_header:
            draw.line([(0, row_h - 2), (width, row_h - 2)], fill=accent, width=4)
        y += row_h

    # Empty gridded rows fill the leftover height so the canvas stays full
    while y + row_h <= height + row_h:
        _grid_row(min(y, height - row_h))
        y += row_h
        if y >= height:
            break

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def _serve_cached_cover(storage: Any, thumb_key: str, expires: int) -> Response:
    """Aliyun 302s to a day-aligned signed URL; other providers stream the
    small cached JPEG through the app (their presigned URLs rotate per
    request and self-hosted endpoints are often not browser-reachable)."""
    provider = getattr(getattr(storage, "_config", None), "provider", None)
    if provider == S3Provider.ALIYUN:
        url = await storage.get_cover_presigned_url(thumb_key, expires)
        return Response(
            status_code=302,
            headers={"Location": url, "Cache-Control": "public, max-age=86400"},
        )
    data = await storage.download_file(thumb_key)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _get_rendered_cover_response(storage: Any, key: str, kind: str, render: Any) -> Response:
    """Shared flow for covers rendered server-side from the original file
    (PDF pages, spreadsheet rows, images on providers without x-oss-process):
    render once, cache beside the original (uploads are content-addressed
    and immutable, so the cache never goes stale), and serve the small JPEG
    from then on."""
    thumb_key = f"{_COVER_CACHE_PREFIX}/{key}.jpg"
    expires = cover_signature_expiry()

    if storage.is_local:
        file_path = storage.get_file_path(key)
        if not await run_blocking_io(_path_exists, file_path):
            raise HTTPException(status_code=404, detail="File not found")
        try:
            stat = await run_blocking_io(file_path.stat)
        except OSError:
            raise HTTPException(status_code=404, detail="File not found")
        if stat.st_size > _RENDER_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")

        def _read_and_render() -> bytes:
            with open(file_path, "rb") as fh:
                return render(fh.read())

        try:
            body = await run_blocking_io(_read_and_render)
        except Exception as e:
            logger.error(f"Failed to render local {kind} cover for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to render cover")
        return Response(
            content=body,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    try:
        if await storage.file_exists(thumb_key):
            return await _serve_cached_cover(storage, thumb_key, expires)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to check cached {kind} cover for {key}: {e}")

    try:
        source_size = await storage.get_size(key)
        if source_size and source_size > _RENDER_MAX_SOURCE_BYTES:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to stat {kind} for cover {key}: {e}")

    return await _render_and_cache_cover(storage, key, thumb_key, kind, render, expires)


async def _render_and_cache_cover(
    storage: Any, key: str, thumb_key: str, kind: str, render: Any, expires: int
) -> Response:
    """Download → render → cache, guarded against bursts.

    - Same thumbnail is rendered once: concurrent first requests join the
      in-flight task instead of piling duplicate work onto the pool.
    - At most `_RENDER_CONCURRENCY` renders run at once; beyond that,
      requests fail fast with 404 so the client shows its zero-traffic
      paper cover and the shared blocking-io pool keeps serving everyone.
    """
    existing = _render_inflight.get(thumb_key)
    if existing is not None:
        return await asyncio.shield(existing)

    semaphore = _get_render_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_RENDER_ACQUIRE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.info(f"Cover render slots saturated for {key}; falling back")
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")

    try:
        existing = _render_inflight.get(thumb_key)
        if existing is not None:
            return await asyncio.shield(existing)

        task = asyncio.create_task(
            _do_render_and_cache(storage, key, thumb_key, kind, render, expires)
        )
        _render_inflight[thumb_key] = task
        task.add_done_callback(lambda _t: _render_inflight.pop(thumb_key, None))
        return await asyncio.shield(task)
    finally:
        semaphore.release()


async def _do_render_and_cache(
    storage: Any, key: str, thumb_key: str, kind: str, render: Any, expires: int
) -> Response:
    try:
        data = await storage.download_file(key)
    except Exception as e:
        logger.error(f"Failed to download {kind} for cover {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    try:
        body = await run_blocking_io(render, data)
    except Exception as e:
        logger.error(f"Failed to render {kind} cover for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to render cover")

    try:
        await storage.upload_to_key(
            body,
            thumb_key,
            content_type="image/jpeg",
            skip_size_limit=True,
        )
        provider = getattr(getattr(storage, "_config", None), "provider", None)
        if provider == S3Provider.ALIYUN:
            url = await storage.get_cover_presigned_url(thumb_key, expires)
            return Response(
                status_code=302,
                headers={"Location": url, "Cache-Control": "public, max-age=86400"},
            )
    except Exception as e:
        # Cache write is best-effort; serve the rendered bytes directly.
        logger.warning(f"Failed to cache {kind} cover for {key}: {e}")
    return Response(
        content=body,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


def render_cover_jpeg(data: bytes) -> bytes:
    """16:9 cover-crop render from raw image bytes (local storage and
    non-Aliyun S3 providers — no x-oss-process available)."""
    import io

    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as opened:
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
    ext = _key_ext(key)
    if ext in _COVER_PDF_EXTS:
        return await _get_rendered_cover_response(storage, key, "PDF", render_pdf_cover)
    if ext in _COVER_SHEET_EXTS:
        return await _get_rendered_cover_response(storage, key, "sheet", render_sheet_cover)

    t_ms = t if t is not None else 1000
    process = cover_process_for_key(key, t_ms)
    if not process:
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")

    if storage.is_local:
        # Local storage has no server-side processing; resize via Pillow.
        # Videos can't be snapshot without ffmpeg — clients fall back.
        if ext not in _COVER_IMAGE_EXTS:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")
        return await _get_rendered_cover_response(storage, key, "image", render_cover_jpeg)

    provider = getattr(getattr(storage, "_config", None), "provider", None)
    if provider == S3Provider.ALIYUN:
        try:
            exists = await storage.file_exists(key)
            if not exists:
                raise HTTPException(status_code=404, detail="File not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to check file existence for {key}: {e}")

        try:
            url = await storage.get_cover_presigned_url(
                key, cover_signature_expiry(), process=process
            )
        except TypeError:
            raise HTTPException(status_code=404, detail="Cover thumbnail not available")
        except Exception as e:
            logger.error(f"Failed to generate cover URL for {key}: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate file URL")

        return Response(
            status_code=302,
            headers={"Location": url, "Cache-Control": "public, max-age=86400"},
        )

    # Other S3 providers have no x-oss-process: images render and cache
    # like PDF/sheet covers; videos would need server-side ffmpeg — 404.
    if ext not in _COVER_IMAGE_EXTS:
        raise HTTPException(status_code=404, detail="Cover thumbnail not available")
    return await _get_rendered_cover_response(storage, key, "image", render_cover_jpeg)
