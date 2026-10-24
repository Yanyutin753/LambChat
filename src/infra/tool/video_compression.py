"""Bound native video request size while retaining the full timeline and audio."""

import asyncio
import json
import math
import shutil
import tempfile
from pathlib import Path

from src.infra.async_utils import run_long_blocking_io


async def _run(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        output, _ = await process.communicate()
        if process.returncode:
            raise ValueError("video_compression_failed")
        return output
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def compress_video(content: bytes, max_bytes: int, timeout: float) -> bytes:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("video_compression_unavailable")
    with tempfile.TemporaryDirectory(prefix="lambchat-video-") as directory:
        source = Path(directory) / "source"
        target = Path(directory) / "analysis.mp4"
        await run_long_blocking_io(source.write_bytes, content)
        async with asyncio.timeout(timeout):
            probe = json.loads(
                await _run(
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-format_whitelist",
                    "mov,matroska,webm,avi",
                    "-show_entries",
                    "format=duration,format_name",
                    "-of",
                    "json",
                    str(source),
                )
            )
            container = probe.get("format", {})
            if not {"mov", "matroska", "webm", "avi"}.intersection(
                str(container.get("format_name", "")).split(",")
            ):
                raise ValueError("unsupported_video_container")
            duration = float(container.get("duration", 0))
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("video_duration_unavailable")
            # Reserve mux/audio overhead; never truncate to meet the byte limit.
            bitrate = int(max_bytes * 8 * 0.85 / duration) - 96000
            if bitrate < 128000:
                raise ValueError("video_too_long_for_inline_limit")
            await _run(
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "mov,matroska,webm,avi",
                "-threads",
                "1",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-filter_threads",
                "1",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-threads",
                "1",
                "-b:v",
                str(bitrate),
                "-maxrate",
                str(bitrate),
                "-bufsize",
                str(bitrate * 2),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(target),
            )
            size = (await run_long_blocking_io(target.stat)).st_size
            if not 0 < size <= max_bytes:
                raise ValueError("video_exceeds_inline_limit_after_compression")
            return await run_long_blocking_io(target.read_bytes)
