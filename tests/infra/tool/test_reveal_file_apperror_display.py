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
        result = await rfs._download_file_from_backend(_Backend(), "/workspace/x.py")

    assert result is None
    joined = caplog.text
    assert "after 300s" in joined
    assert "{{" not in joined


@pytest.mark.asyncio
async def test_sync_download_failure_log_interpolates_apperror(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="src.infra.tool._reveal_file_support"):
        result = await rfs._download_file_from_backend(_SyncBackend(), "/workspace/x.py")

    assert result is None
    joined = caplog.text
    assert "after 300s" in joined
    assert "{{" not in joined
