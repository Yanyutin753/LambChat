import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.tool import video_compression as module


async def test_compression_cancellation_kills_child(monkeypatch):
    process = SimpleNamespace(returncode=None, killed=False)

    async def communicate():
        await asyncio.Event().wait()

    def kill():
        process.killed = True
        process.returncode = -9

    process.communicate = communicate
    process.kill = kill
    process.wait = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await module._run("ffmpeg")
    assert process.killed
    process.wait.assert_awaited_once()


async def test_compression_keeps_audio_and_entire_timeline_and_cleans_tempfiles(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: name)
    target = None

    async def run(*args):
        nonlocal target
        assert args[args.index("-format_whitelist") + 1] == "mov,matroska,webm,avi"
        if args[0] == "ffprobe":
            return json.dumps(
                {"format": {"duration": "36.8", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"}}
            ).encode()
        assert args[args.index("-map") + 1] == "0:v:0"
        assert "0:a:0?" in args
        assert not {"-t", "-ss", "-fs", "-an"}.intersection(args)
        target = Path(args[-1])
        target.write_bytes(b"compact-video")
        return b""

    monkeypatch.setattr(module, "_run", run)
    assert await module.compress_video(b"original", 16 * 1024 * 1024, 1) == b"compact-video"
    assert target and not target.parent.exists()


async def test_compression_refuses_unusable_duration_without_encoding(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: name)
    run = AsyncMock(return_value=b'{"format":{"duration":"nan","format_name":"mov"}}')
    monkeypatch.setattr(module, "_run", run)
    with pytest.raises(ValueError, match="video_duration_unavailable"):
        await module.compress_video(b"original", 16 * 1024 * 1024, 1)
    assert run.await_count == 1


async def test_reference_container_is_refused_before_encoding(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: name)
    run = AsyncMock(return_value=b'{"format":{"duration":"10","format_name":"hls"}}')
    monkeypatch.setattr(module, "_run", run)
    with pytest.raises(ValueError, match="unsupported_video_container"):
        await module.compress_video(b"#EXTM3U", 16 * 1024 * 1024, 1)
    assert run.await_count == 1
