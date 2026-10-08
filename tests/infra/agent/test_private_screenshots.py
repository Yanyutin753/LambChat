"""Desktop screenshots stay owner/session scoped, including model reads."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.upload.file_record import FileRecordStorage


async def test_private_upload_registers_owned_session_and_uses_delete_fence(monkeypatch):
    from src.infra.session.storage import SessionStorage
    from src.infra.storage.s3 import service

    sessions = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"user_id": "owner"})),
        acquire_trace_write=AsyncMock(return_value=True),
        release_trace_write=AsyncMock(),
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    storage = SimpleNamespace(
        is_local=True,
        upload_file=AsyncMock(
            return_value=SimpleNamespace(key="cua_screenshots/owner/session/a.png")
        ),
        delete_file=AsyncMock(),
    )
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    create = AsyncMock()
    monkeypatch.setattr(FileRecordStorage, "create", create)
    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": base64.b64encode(b"synthetic").decode(),
            }
        ]
    }
    await upload_binary_blocks(result, "", private_user_id="owner", private_session_id="session")
    assert result["blocks"][0]["url"].startswith("/api/upload/file/cua_screenshots/")
    assert "base64" not in result["blocks"][0]
    assert create.call_args.kwargs["private_session_id"] == "session"
    assert create.call_args.kwargs["uploaded_by"] == "owner"
    sessions.acquire_trace_write.assert_awaited_once_with("session")
    sessions.release_trace_write.assert_awaited_once_with("session")


async def test_private_upload_requires_both_owner_and_session():
    result = {"blocks": [{"base64": "YQ=="}]}
    await upload_binary_blocks(result, "", private_user_id="owner")
    assert result["blocks"][0] == {"upload_error": "binary_upload_failed"}


async def test_private_capture_cleanup_deletes_object_and_record(monkeypatch):
    from src.infra.storage.s3 import service

    async def records():
        yield {"key": "cua_screenshots/owner/session/a.png", "uploaded_by": "owner"}

    storage = SimpleNamespace(delete_file=AsyncMock())
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    files = FileRecordStorage()
    files._collection = SimpleNamespace(find=lambda query: records())
    files.delete_by_key = AsyncMock()
    await files.delete_private_session_files("session")
    storage.delete_file.assert_awaited_once_with("cua_screenshots/owner/session/a.png")
    files.delete_by_key.assert_awaited_once_with("cua_screenshots/owner/session/a.png", "owner")


async def test_generic_internal_image_download_does_not_bypass_capture_authorization(monkeypatch):
    from src.agents.core.node_utils import _download_image_url_as_data_url
    from src.infra.storage.s3 import service

    storage = SimpleNamespace(download_to_file=AsyncMock())
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    assert (
        await _download_image_url_as_data_url(
            "/api/upload/file/cua_screenshots/owner/session/a.png", "image/png"
        )
        is None
    )
    storage.download_to_file.assert_not_awaited()


async def test_explicit_private_upload_cannot_fall_back_to_public_without_context():
    result = {"blocks": [{"base64": "YQ=="}]}
    await upload_binary_blocks(
        result, "", private=True, private_user_id=None, private_session_id=None
    )
    assert result["blocks"][0] == {"upload_error": "binary_upload_failed"}


async def test_private_capture_registration_failure_rolls_back_object(monkeypatch):
    from src.infra.agent.events.binary_uploads import _upload_private_screenshot
    from src.infra.session.storage import SessionStorage

    sessions = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"user_id": "owner"})),
        acquire_trace_write=AsyncMock(return_value=True),
        release_trace_write=AsyncMock(),
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    storage = SimpleNamespace(
        is_local=True,
        upload_file=AsyncMock(
            return_value=SimpleNamespace(key="cua_screenshots/owner/session/a.png")
        ),
        delete_file=AsyncMock(),
    )
    monkeypatch.setattr(
        FileRecordStorage, "create", AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    with pytest.raises(RuntimeError):
        await _upload_private_screenshot(storage, None, "a.png", "image/png", 1, "owner", "session")
    storage.delete_file.assert_awaited_once_with("cua_screenshots/owner/session/a.png")
    sessions.release_trace_write.assert_awaited_once_with("session")


async def test_private_capture_cleanup_failure_retains_record_for_retry(monkeypatch):
    from src.infra.storage.s3 import service

    async def records():
        yield {"key": "cua_screenshots/owner/session/a.png", "uploaded_by": "owner"}

    storage = SimpleNamespace(delete_file=AsyncMock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    files = FileRecordStorage()
    files._collection = SimpleNamespace(find=lambda query: records())
    files.delete_by_key = AsyncMock()
    with pytest.raises(RuntimeError):
        await files.delete_private_session_files("session")
    files.delete_by_key.assert_not_awaited()


@pytest.mark.parametrize("session_id", ["session", "another-session", None])
async def test_private_model_image_is_authorized_and_inlined_only_for_its_session(
    monkeypatch, session_id
):
    import json

    from langchain_core.messages import ToolMessage

    from src.infra.agent.middleware.tool_interception import ToolResultBinaryMiddleware
    from src.infra.session.storage import SessionStorage
    from src.infra.storage.s3 import service

    record = {"uploaded_by": "owner", "private_session_id": "session"}
    monkeypatch.setattr(FileRecordStorage, "find_by_key", AsyncMock(return_value=record))
    sessions = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"user_id": "owner"}))
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)

    async def download(key, file):
        file.write(b"synthetic")
        return 9

    storage = SimpleNamespace(download_to_file=AsyncMock(side_effect=download))
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))

    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs["messages"])

    message = ToolMessage(
        content=json.dumps(
            {
                "screenshot": {
                    "mime_type": "image/png",
                    "url": "/api/upload/file/cua_screenshots/owner/session/a.png",
                }
            }
        ),
        name="computer_use",
        tool_call_id="cua",
    )
    request = Request([message])

    async def handler(req):
        return req

    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example", supports_vision=True, user_id="owner", session_id=session_id
    ).awrap_model_call(request, handler)
    if session_id == "session":
        assert (
            result.messages[-1].content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        )
        assert "base64" not in message.content
    else:
        assert result is request
        storage.download_to_file.assert_not_awaited()


async def test_capture_started_before_clear_is_rolled_back_if_it_finishes_after_clear(monkeypatch):
    from src.infra.agent.events.binary_uploads import _upload_private_screenshot
    from src.infra.session.storage import SessionStorage

    sessions = SimpleNamespace(
        collection=SimpleNamespace(
            find_one=AsyncMock(
                side_effect=[
                    {"user_id": "owner", "private_capture_epoch": 0},
                    {"user_id": "owner", "private_capture_epoch": 1},
                ]
            )
        ),
        acquire_trace_write=AsyncMock(return_value=True),
        release_trace_write=AsyncMock(),
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    storage = SimpleNamespace(
        is_local=True,
        upload_file=AsyncMock(
            return_value=SimpleNamespace(key="cua_screenshots/owner/session/a.png")
        ),
        delete_file=AsyncMock(),
    )
    create = AsyncMock()
    delete_record = AsyncMock()
    monkeypatch.setattr(FileRecordStorage, "create", create)
    monkeypatch.setattr(FileRecordStorage, "delete_by_key", delete_record)
    with pytest.raises(ValueError, match="cleared"):
        await _upload_private_screenshot(storage, None, "a.png", "image/png", 1, "owner", "session")
    storage.delete_file.assert_awaited_once_with("cua_screenshots/owner/session/a.png")
    delete_record.assert_awaited_once_with("cua_screenshots/owner/session/a.png", "owner")


async def test_old_capture_is_unreadable_immediately_when_clear_epoch_advances(monkeypatch):
    from src.infra.session.storage import SessionStorage
    from src.kernel.errors import AppError

    monkeypatch.setattr(
        FileRecordStorage,
        "find_by_key",
        AsyncMock(
            return_value={
                "uploaded_by": "owner",
                "private_session_id": "session",
                "private_capture_epoch": 0,
            }
        ),
    )
    sessions = SimpleNamespace(
        collection=SimpleNamespace(
            find_one=AsyncMock(return_value={"user_id": "owner", "private_capture_epoch": 1})
        )
    )
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    with pytest.raises(AppError):
        await FileRecordStorage().require_private_access(
            "cua_screenshots/owner/session/a.png", "owner"
        )
