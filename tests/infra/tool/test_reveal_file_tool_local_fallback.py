from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.tool import reveal_file_tool


@pytest.mark.asyncio
async def test_upload_local_resource_skips_filesystem_fallback_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        raise AssertionError("filesystem fallback should be disabled")

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=False),
    )

    result = await reveal_file_tool._upload_local_resource(
        "./chart.png",
        "/workspace",
        backend=object(),
        storage=object(),
        base_url="http://example.com",
    )

    assert result is None


@pytest.mark.asyncio
async def test_upload_local_resource_uses_filesystem_fallback_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded: list[tuple[bytes, str, str]] = []

    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        return b"png-bytes"

    class _FakeStorage:
        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            uploaded.append((data, folder, filename))
            return SimpleNamespace(key=f"{folder}/{filename}")

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=True),
    )

    result = await reveal_file_tool._upload_local_resource(
        "./chart.png",
        "/workspace",
        backend=object(),
        storage=_FakeStorage(),
        base_url="http://example.com",
    )

    assert result == "http://example.com/api/upload/file/revealed_files/chart.png"
    assert uploaded == [(b"png-bytes", "revealed_files", "chart.png")]
