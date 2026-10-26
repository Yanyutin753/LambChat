"""Small, persistent media covers; decode local bytes without network protocols."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import tempfile
from pathlib import Path
from weakref import WeakKeyDictionary

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger

logger = get_logger(__name__)
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "aac", "flac", "m4a", "wma"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v", "avi", "mkv", "wmv", "flv"}
MAX_SOURCE_BYTES = 512 * 1024 * 1024
_slots: WeakKeyDictionary = WeakKeyDictionary()


def media_cover_key(key: str) -> str | None:
    if key.rsplit(".", 1)[-1].lower() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        return f"covers/560x315/{key}.jpg"
    return None


async def _run(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        output, _ = await process.communicate()
        if process.returncode:
            raise ValueError("Media cover decoding failed")
        return output
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _copy_source(source, destination: Path) -> None:
    position = source.tell()
    try:
        total = 0
        with destination.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("Media cover source too large")
                target.write(chunk)
    finally:
        source.seek(position)


async def render_video_cover(source) -> bytes:
    with tempfile.TemporaryDirectory(prefix="lambchat-poster-") as directory:
        path = Path(directory) / "source"
        await run_long_blocking_io(_copy_source, source, path)
        async with asyncio.timeout(15):
            restricted = (
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "mov,matroska,webm,avi,asf,flv",
            )
            probe = json.loads(
                await _run(
                    "ffprobe",
                    "-v",
                    "error",
                    *restricted,
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(path),
                )
            )
            duration = float(probe.get("format", {}).get("duration", 0))
            seek = min(3, duration * 0.1) if math.isfinite(duration) and duration > 0 else 0
            return await _run(
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                *restricted,
                "-threads",
                "1",
                "-ss",
                str(seek),
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-an",
                "-filter_threads",
                "1",
                "-vf",
                "scale=560:315:force_original_aspect_ratio=decrease,thumbnail=12",
                "-frames:v",
                "1",
                "-threads",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            )


async def render_audio_cover(source) -> bytes:
    with tempfile.TemporaryDirectory(prefix="lambchat-waveform-") as directory:
        path = Path(directory) / "source"
        await run_long_blocking_io(_copy_source, source, path)
        async with asyncio.timeout(15):
            return await _run(
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "mp3,wav,ogg,aac,flac,mov,asf",
                "-threads",
                "1",
                "-i",
                str(path),
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                "[0:a:0]atrim=duration=60,aformat=channel_layouts=mono,showwavespic=s=560x315:colors=0x78716c:scale=sqrt,format=rgb24[out]",
                "-map",
                "[out]",
                "-frames:v",
                "1",
                "-threads",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            )


async def _prepare_media_cover(storage, key: str, source=None) -> bool:
    cover_key = media_cover_key(key)
    if not cover_key:
        return False
    render = (
        render_audio_cover
        if key.rsplit(".", 1)[-1].lower() in AUDIO_EXTENSIONS
        else render_video_cover
    )
    try:
        if await storage.file_exists(cover_key):
            return True
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return False
        if source is None:
            size = await storage.get_size(key)
            if size is None or size > MAX_SOURCE_BYTES:
                return False
            with tempfile.TemporaryFile() as downloaded:
                await storage.download_to_file(key, downloaded)
                await run_long_blocking_io(downloaded.seek, 0)
                body = await render(downloaded)
        else:
            body = await render(source)
        if not body:
            return False
        await storage.upload_to_key(
            body, cover_key, content_type="image/jpeg", skip_size_limit=True
        )
        return True
    except Exception:
        logger.warning("Media cover unavailable for %s", key, exc_info=True)
        return False


async def prepare_media_cover(storage, key: str, source=None) -> bool:
    if not media_cover_key(key):
        return False
    loop = asyncio.get_running_loop()
    semaphore = _slots.setdefault(loop, asyncio.Semaphore(2))
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=8)
    except TimeoutError:
        return False
    try:
        return await _prepare_media_cover(storage, key, source)
    finally:
        semaphore.release()
