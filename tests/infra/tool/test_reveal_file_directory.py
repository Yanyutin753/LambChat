from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.infra.tool import reveal_file_tool


class _SandboxBackend:
    pass


@pytest.mark.asyncio
async def test_reveal_file_returns_directory_hint_for_sandbox_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reveal_file on a sandbox directory returns path_is_directory + a hint
    to use reveal_project, not the generic file_not_found (issue #196)."""

    async def _no_content(backend, file_path):
        return None

    async def _probe_is_directory(backend, file_path):
        return "is_directory"

    async def _no_size(backend, file_path):
        return None

    async def _fake_storage():
        return SimpleNamespace()

    monkeypatch.setattr(reveal_file_tool, "_is_remote_url", lambda _p: False)
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _fake_storage)
    monkeypatch.setattr(
        reveal_file_tool, "get_backend_from_runtime", lambda _runtime: _SandboxBackend()
    )
    monkeypatch.setattr(reveal_file_tool, "_get_backend_file_size", _no_size)
    monkeypatch.setattr(reveal_file_tool, "_get_reveal_file_upload_max_bytes", lambda: 10**9)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda _backend: True)
    monkeypatch.setattr(reveal_file_tool, "_download_file_from_backend", _no_content)
    monkeypatch.setattr(reveal_file_tool, "_probe_download_error", _probe_is_directory)

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/home/user/project", description="a dir", runtime=object()
        )
    )

    assert result["file"]["error"] == "path_is_directory"
    assert "reveal_project" in result["file"]["hint"]
