"""reveal_file 后端下载异常日志的 AppError 插值测试（#807 同族）。

`_download_file_from_backend` 的 except 分支直接 str(exc)，AppError 的
__str__ 是未插值的 {{param}} 模板，`{{seconds}}` 等占位符原文会进日志。
"""

from __future__ import annotations

import logging

import pytest

from src.infra.tool import _reveal_file_support as rfs
from src.kernel.errors import AppError, ErrorCode


class _Backend:
    async def adownload_files(self, paths):  # pragma: no cover - raises
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": 300})


class _SyncBackend:
    def download_files(self, paths):  # pragma: no cover - raises
        raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": 300})


@pytest.mark.asyncio
async def test_async_download_failure_log_interpolates_apperror(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="src.infra.tool._reveal_file_support"):
        with pytest.raises(AppError) as caught:
            await rfs._download_file_from_backend(_Backend(), "/workspace/x.py")

    assert caught.value.error_code == ErrorCode.SANDBOX_TIMEOUT
    joined = caplog.text
    assert "after 300s" in joined
    assert "{{" not in joined


@pytest.mark.asyncio
async def test_sync_download_failure_log_interpolates_apperror(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="src.infra.tool._reveal_file_support"):
        with pytest.raises(AppError) as caught:
            await rfs._download_file_from_backend(_SyncBackend(), "/workspace/x.py")

    assert caught.value.error_code == ErrorCode.SANDBOX_TIMEOUT
    joined = caplog.text
    assert "after 300s" in joined
    assert "{{" not in joined


async def test_reveal_file_preserves_offline_error_instead_of_missing_file(monkeypatch):
    import json
    from types import SimpleNamespace

    from src.infra.tool import reveal_file_tool

    async def storage():
        return SimpleNamespace()

    async def size(*args):
        return None

    async def download(*args):
        raise AppError(ErrorCode.SANDBOX_MACHINE_OFFLINE, args={"machine_id": "m1"})

    monkeypatch.setattr(reveal_file_tool, "_get_storage", storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(reveal_file_tool, "_get_backend_file_size", size)
    monkeypatch.setattr(reveal_file_tool, "_download_file_from_backend", download)
    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine("/workspace/screen.png", runtime=object())
    )
    assert result["file"]["code"] == "sandbox_machine_offline"
    assert result["file"]["args"] == {"machine_id": "m1"}
    assert "file_not_found" not in result["file"]["error"]
