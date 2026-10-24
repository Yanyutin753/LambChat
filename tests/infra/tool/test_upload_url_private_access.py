"""Internal URL downloads cannot bypass private-file checks with storage credentials."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.tool import upload_url_tool
from src.infra.upload.file_record import FileRecordStorage


@pytest.mark.parametrize("suffix", ["", "?thumb=1", "?file_token=forged", "?proxy=true"])
async def test_foreign_upload_url_is_never_presigned_or_downloaded(monkeypatch, suffix):
    from src.infra.storage.s3 import service

    monkeypatch.setattr(
        "src.infra.upload.access._owns_generated_file", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=False))
    monkeypatch.setattr(FileRecordStorage, "find_by_key", AsyncMock(return_value=None))
    storage = SimpleNamespace(
        is_local=False, get_presigned_url=AsyncMock(return_value="https://storage/signed")
    )
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    backend = SimpleNamespace(aexecute=AsyncMock(), aupload_files=AsyncMock())
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "backend": backend,
                "base_url": "https://app.example",
                "context": SimpleNamespace(user_id="intruder"),
                "session_id": "session",
            }
        }
    )
    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="https://app.example/api/upload/file/document/owner/secret.pdf" + suffix,
            file_path="/workspace/secret.pdf",
            runtime=runtime,
        )
    )
    assert result == {"success": False, "error": "File unavailable"}
    storage.get_presigned_url.assert_not_awaited()
    backend.aexecute.assert_not_awaited()
    backend.aupload_files.assert_not_awaited()


async def test_owned_private_file_rechecks_read_permission_before_download(monkeypatch):
    monkeypatch.setattr(
        "src.infra.auth.tool_authority.has_tool_permission", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=True))
    private_access = AsyncMock()
    monkeypatch.setattr(FileRecordStorage, "require_private_access", private_access)
    backend = SimpleNamespace(aupload_files=AsyncMock())
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "backend": backend,
                "base_url": "https://app.example",
                "context": SimpleNamespace(user_id="owner"),
                "session_id": "session",
            }
        }
    )
    result = json.loads(
        await upload_url_tool.upload_url_to_sandbox.coroutine(
            url="/api/upload/file/cua_screenshots/owner/session/a.png",
            file_path="/workspace/a.png",
            runtime=runtime,
        )
    )
    assert result["success"] is False
    private_access.assert_not_awaited()
    backend.aupload_files.assert_not_awaited()
