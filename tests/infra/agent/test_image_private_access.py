"""Private uploads remain authorized across every outbound model image mode."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents.core import node_utils
from src.infra.agent.middleware import image_url
from src.infra.logging.context import TraceContext
from src.kernel.errors import AppError


class Request:
    def __init__(self, messages):
        self.messages = messages
        self.runtime = SimpleNamespace(
            context=SimpleNamespace(user_id="owner", session_id="session")
        )

    def override(self, **kwargs):
        return Request(kwargs["messages"])


@pytest.fixture
def owned_image(monkeypatch):
    from src.infra.upload.file_record import FileRecordStorage

    monkeypatch.setattr("src.kernel.config.settings.APP_BASE_URL", "https://app.example")
    monkeypatch.setattr(
        "src.infra.upload.access._owns_generated_file", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(FileRecordStorage, "is_private_key", AsyncMock(return_value=False))
    monkeypatch.setattr(
        FileRecordStorage, "find_by_key", AsyncMock(return_value={"uploaded_by": "owner"})
    )
    TraceContext.clear_request_context()
    yield
    TraceContext.clear_request_context()


def test_foreign_origin_upload_shape_is_not_a_local_storage_key(monkeypatch):
    monkeypatch.setattr("src.kernel.config.settings.APP_BASE_URL", "https://app.example")
    assert (
        node_utils._upload_key_from_image_url("https://foreign.example/api/upload/file/secret")
        is None
    )
    assert (
        node_utils._upload_key_from_image_url("https://app.example.evil/api/upload/file/secret")
        is None
    )
    assert (
        node_utils._upload_key_from_image_url("https://app.example/other/api/upload/file/secret")
        is None
    )
    assert (
        node_utils._upload_key_from_image_url("/api/upload/file/image/owned.png")
        == "image/owned.png"
    )


async def test_internal_storage_download_requires_owner_before_reading(owned_image):
    storage = SimpleNamespace(download_to_file=AsyncMock())
    with pytest.raises(AppError):
        await node_utils._download_image_as_data_url(storage, "image/owner/a.png", "image/png")
    storage.download_to_file.assert_not_awaited()


@pytest.mark.parametrize("mode", [None, "url", "proxy_direct", "storage_direct", "base64"])
async def test_outgoing_modes_check_owner_and_preserve_original(monkeypatch, owned_image, mode):
    from src.infra.storage.s3 import service

    async def download(key, target):
        target.write(b"image")
        return 5

    storage = SimpleNamespace(
        is_local=False,
        download_to_file=AsyncMock(side_effect=download),
        get_presigned_url=AsyncMock(return_value="https://storage.example/signed"),
    )
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    original = "https://app.example/api/upload/file/image/owner/a.png?thumb=1"
    message = HumanMessage(content=[{"type": "image_url", "image_url": {"url": original}}])
    handler = AsyncMock(side_effect=lambda request: request)
    middleware = image_url.image_url_middleware_for_mode(mode)
    assert middleware is not None
    result = await middleware.awrap_model_call(Request([message, message]), handler)
    outgoing = result.messages[0].content[0]["image_url"]["url"]
    if mode == "base64":
        assert outgoing.startswith("data:image/png;base64,")
        storage.download_to_file.assert_awaited_once()
    elif mode == "storage_direct":
        assert outgoing == "https://storage.example/signed"
        storage.get_presigned_url.assert_awaited_once()
    else:
        assert "file_token=" in outgoing
        assert "thumb=1" in outgoing
        if mode == "proxy_direct":
            assert "proxy=true" in outgoing
    assert message.content[0]["image_url"]["url"] == original
    assert result.messages[1].content == result.messages[0].content


@pytest.mark.parametrize("mode", ["url", "proxy_direct", "storage_direct", "base64"])
async def test_foreign_owner_stops_before_provider_or_storage(monkeypatch, owned_image, mode):
    from src.infra.storage.s3 import service
    from src.infra.upload.file_record import FileRecordStorage

    monkeypatch.setattr(FileRecordStorage, "find_by_key", AsyncMock(return_value=None))
    storage = AsyncMock()
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {"url": "https://app.example/api/upload/file/image/other/a.png"},
            }
        ]
    )
    handler = AsyncMock()
    middleware = image_url.image_url_middleware_for_mode(mode)
    assert middleware is not None
    with pytest.raises(AppError):
        await middleware.awrap_model_call(Request([message]), handler)
    handler.assert_not_awaited()
    storage.get_presigned_url.assert_not_awaited()
    storage.download_to_file.assert_not_awaited()


async def test_storage_presign_does_not_swallow_access_denial(monkeypatch, owned_image):
    from src.infra.upload.file_record import FileRecordStorage

    monkeypatch.setattr(FileRecordStorage, "find_by_key", AsyncMock(return_value=None))
    TraceContext.set_request_context(user_id="owner", session_id="session")
    with pytest.raises(AppError):
        await image_url._resolve_storage_image_url(
            "https://app.example/api/upload/file/image/other/a.png"
        )


async def test_outbound_foreign_upload_shape_is_untouched(owned_image):
    original = "https://foreign.example/api/upload/file/image/owner/a.png"
    message = HumanMessage(content=[{"type": "image_url", "image_url": {"url": original}}])
    handler = AsyncMock(side_effect=lambda request: request)
    request = Request([message])
    result = await image_url.image_url_middleware_for_mode("proxy_direct").awrap_model_call(
        request, handler
    )
    assert result is request
    assert message.content[0]["image_url"]["url"] == original
