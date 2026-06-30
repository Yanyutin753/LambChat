from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from src.agents.core import node_utils
from src.agents.core.node_utils import (
    build_human_message,
    inline_image_attachments_as_data_urls,
    resolve_model_image_url_to_base64,
)


def image_attachment(**overrides):
    return {
        "id": "img-1",
        "key": "uploads/img.png",
        "name": "img.png",
        "type": "image",
        "mime_type": "image/png",
        "size": 1234,
        "url": "/api/upload/file/uploads/img.png",
        **overrides,
    }


def image_attachment_with_data_url(**overrides):
    return image_attachment(data_url="data:image/png;base64,aW1hZ2UtYnl0ZXM=", **overrides)


def doc_attachment(**overrides):
    return {
        "id": "doc-1",
        "key": "uploads/doc.pdf",
        "name": "doc.pdf",
        "type": "document",
        "mime_type": "application/pdf",
        "size": 2048,
        "url": "/api/upload/file/uploads/doc.pdf",
        **overrides,
    }


def test_vision_model_sends_image_attachment_as_multimodal_block():
    message = build_human_message(
        "what is this?",
        [image_attachment()],
        supports_vision=True,
    )

    assert isinstance(message, HumanMessage)
    assert isinstance(message.content, list)
    assert message.content[0] == {"type": "text", "text": "what is this?"}
    assert message.content[1] == {
        "type": "image_url",
        "image_url": {"url": "/api/upload/file/uploads/img.png"},
    }


def test_non_vision_model_keeps_image_attachment_as_text_summary():
    message = build_human_message("what is this?", [image_attachment()], supports_vision=False)

    assert isinstance(message.content, str)
    assert "User Uploaded Attachments" in message.content
    assert "img.png" in message.content
    assert "/api/upload/file/uploads/img.png" in message.content


def test_vision_model_keeps_document_attachments_in_text_summary():
    message = build_human_message(
        "compare these",
        [image_attachment(), doc_attachment()],
        supports_vision=True,
    )

    assert isinstance(message.content, list)
    assert message.content[0]["type"] == "text"
    assert "doc.pdf" in message.content[0]["text"]
    assert message.content[1]["type"] == "image_url"


def test_vision_model_skips_image_blocks_without_url():
    message = build_human_message("what is this?", [image_attachment(url="")], supports_vision=True)

    assert isinstance(message.content, str)
    assert message.content == "what is this?"


@pytest.mark.asyncio
async def test_inline_image_attachments_uses_existing_url_without_download(monkeypatch):
    async def fail_get_or_init_storage():
        raise AssertionError("storage download should not be needed when attachment URL exists")

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fail_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls([image_attachment()])

    assert attachments[0]["url"] == "/api/upload/file/uploads/img.png"
    assert "data_url" not in attachments[0]


@pytest.mark.asyncio
async def test_inline_image_attachments_converts_existing_url_when_enabled(monkeypatch):
    storage = FakeImageStorage()

    async def fake_get_or_init_storage():
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment()],
        force_data_url=True,
    )

    assert storage.downloaded_keys == ["uploads/img.png"]
    assert attachments[0]["url"] is None
    assert attachments[0]["data_url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="


class FakeImageStorage:
    def __init__(self) -> None:
        self.downloaded_keys: list[str] = []

    async def download_file(self, key):
        raise AssertionError("image inline fallback should download into a spool file")

    async def download_to_file(self, key, file, *, chunk_size=1024 * 1024):
        del chunk_size
        assert key == "uploads/img.png"
        self.downloaded_keys.append(key)
        file.write(b"image-bytes")
        file.seek(0)
        return len(b"image-bytes")


class FailingImageStorage:
    async def download_file(self, _key):
        raise FileNotFoundError("missing")


@pytest.mark.asyncio
async def test_inline_image_attachments_as_data_urls_reads_storage_key(monkeypatch):
    storage = FakeImageStorage()

    async def fake_get_or_init_storage():
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls([image_attachment(url="")])

    assert storage.downloaded_keys == ["uploads/img.png"]
    assert attachments[0]["data_url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="


@pytest.mark.asyncio
async def test_inline_image_attachments_offloads_base64_file_encoding(monkeypatch):
    storage = FakeImageStorage()
    calls: list[str] = []

    async def fake_get_or_init_storage():
        return storage

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(
        node_utils,
        "run_blocking_io",
        fake_run_blocking_io,
        raising=False,
    )

    attachments = await inline_image_attachments_as_data_urls([image_attachment(url="")])

    assert attachments[0]["data_url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="
    assert calls == ["seek", "_base64_encode_file"]


@pytest.mark.asyncio
async def test_inline_image_attachments_uses_base_url_and_key_without_download(monkeypatch):
    async def fail_get_or_init_storage():
        raise AssertionError("storage download should not be needed when base_url can expose key")

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fail_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment(url="")],
        base_url="https://app.example.com",
    )

    assert attachments[0]["url"] == "https://app.example.com/api/upload/file/uploads/img.png"
    assert "data_url" not in attachments[0]


@pytest.mark.asyncio
async def test_inline_image_attachments_skips_large_key_without_download(monkeypatch):
    async def fail_get_or_init_storage():
        raise AssertionError("large images should not be downloaded for data URL fallback")

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fail_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment(url="", size=64)],
        max_inline_bytes=8,
    )

    assert "url" not in {key: value for key, value in attachments[0].items() if value}.keys()
    assert "data_url" not in attachments[0]


@pytest.mark.asyncio
async def test_inline_image_attachments_skips_encoding_when_downloaded_file_exceeds_limit(
    monkeypatch,
):
    class LargeImageStorage:
        async def download_to_file(self, key, file, *, chunk_size=1024 * 1024):
            del chunk_size
            assert key == "uploads/img.png"
            file.write(b"x" * 16)
            file.seek(0)
            return 16

    async def fake_get_or_init_storage():
        return LargeImageStorage()

    encode_calls: list[str] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        encode_calls.append(func.__name__)
        return "encoded-too-large"

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(node_utils, "run_blocking_io", fake_run_blocking_io, raising=False)

    attachment = image_attachment(url="")
    attachment.pop("size")

    attachments = await inline_image_attachments_as_data_urls(
        [attachment],
        max_inline_bytes=8,
    )

    assert "data_url" not in attachments[0]
    assert encode_calls == []


@pytest.mark.asyncio
async def test_inline_image_attachments_falls_back_without_data_url_on_download_error(
    monkeypatch,
):
    async def fake_get_or_init_storage():
        return FailingImageStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls([image_attachment(url="")])

    assert "data_url" not in attachments[0]
    message = build_human_message("what is this?", attachments, supports_vision=True)
    assert isinstance(message.content, str)
    assert message.content == "what is this?"


class FakeStorage:
    async def get(self, model_id):
        if model_id == "vision-id":
            return SimpleNamespace(profile=SimpleNamespace(supports_vision=True))
        if model_id == "base64-id":
            return SimpleNamespace(profile=SimpleNamespace(image_url_to_base64=True))
        return None

    async def get_by_value(self, value):
        if value == "text-model":
            return SimpleNamespace(profile=SimpleNamespace(supports_vision=False))
        if value == "base64-model":
            return SimpleNamespace(profile=SimpleNamespace(image_url_to_base64=True))
        return None


@pytest.mark.asyncio
async def test_resolve_model_supports_vision_uses_model_id(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: FakeStorage(),
    )

    assert await node_utils.resolve_model_supports_vision("vision-id", None) is True


@pytest.mark.asyncio
async def test_resolve_model_supports_vision_defaults_false(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: FakeStorage(),
    )

    assert await node_utils.resolve_model_supports_vision(None, "text-model") is False
    assert await node_utils.resolve_model_supports_vision(None, "missing") is False


@pytest.mark.asyncio
async def test_resolve_model_image_url_to_base64_uses_model_profile(monkeypatch):
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: FakeStorage(),
    )

    assert await resolve_model_image_url_to_base64("base64-id", None) is True
    assert await resolve_model_image_url_to_base64(None, "base64-model") is True
    assert await resolve_model_image_url_to_base64(None, "missing") is False


# ---------------------------------------------------------------------------
# Fix #1: build_human_message prefers data_url over url when url is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_data_url_emits_data_url_in_human_message(monkeypatch):
    """When force_data_url=True, build_human_message should use the data_url."""
    storage = FakeImageStorage()

    async def fake_get_or_init_storage():
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment()],
        force_data_url=True,
    )

    message = build_human_message("describe", attachments, supports_vision=True)
    assert isinstance(message.content, list)
    img_block = message.content[1]
    assert img_block["image_url"]["url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="


@pytest.mark.asyncio
async def test_force_data_url_keeps_original_url_in_text_summary(monkeypatch):
    """When URL is converted to data URL, the model should still receive the original URL."""
    storage = FakeImageStorage()

    async def fake_get_or_init_storage():
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment()],
        force_data_url=True,
    )

    message = build_human_message("describe", attachments, supports_vision=True)

    assert isinstance(message.content, list)
    assert "Corresponding image: #1" in message.content[0]["text"]
    assert "/api/upload/file/uploads/img.png" in message.content[0]["text"]
    assert message.content[1]["image_url"]["url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="


@pytest.mark.asyncio
async def test_force_data_url_cleared_url_not_double_downloaded_by_middleware(monkeypatch):
    """After force_data_url clears url, the middleware should skip data: URLs."""
    storage = FakeImageStorage()

    async def fake_get_or_init_storage():
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    attachments = await inline_image_attachments_as_data_urls(
        [image_attachment()],
        force_data_url=True,
    )
    # The middleware checks url.startswith("data:") — url is now None so no re-download
    assert attachments[0]["url"] is None
    assert attachments[0]["data_url"].startswith("data:")


# ---------------------------------------------------------------------------
# Fix #3: SSRF protection — private / non-http URLs are rejected
# ---------------------------------------------------------------------------


def test_is_private_url_blocks_loopback():
    from src.agents.core.node_utils import _is_private_url

    assert _is_private_url("http://127.0.0.1/image.png") is True
    assert _is_private_url("http://localhost/image.png") is True
    assert _is_private_url("http://169.254.169.254/meta") is True
    assert _is_private_url("http://10.0.0.1/img") is True
    assert _is_private_url("http://192.168.1.1/img") is True
    assert _is_private_url("ftp://evil.com/img") is True
    assert _is_private_url("file:///etc/passwd") is True


def test_is_private_url_allows_public():
    from src.agents.core.node_utils import _is_private_url

    assert _is_private_url("https://cdn.example.com/photo.jpg") is False
    assert _is_private_url("https://images.example.com/img.png") is False


@pytest.mark.asyncio
async def test_download_image_url_rejects_private_address():
    from src.agents.core.node_utils import _download_image_url_as_data_url

    # httpx is available but URL is private — should return None
    result = await _download_image_url_as_data_url(
        "http://127.0.0.1/secret.png", "image/png", max_bytes=1024
    )
    assert result is None


@pytest.mark.asyncio
async def test_download_image_url_rejects_non_http_scheme():
    from src.agents.core.node_utils import _download_image_url_as_data_url

    result = await _download_image_url_as_data_url(
        "file:///etc/passwd", "image/png", max_bytes=1024
    )
    assert result is None


# ---------------------------------------------------------------------------
# Fix #2: shared _resolve_model_profile_bool — verify both wrappers still work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_model_supports_vision_still_works_via_shared_helper(monkeypatch):
    """Ensure DRY refactor didn't break the existing resolve path."""
    monkeypatch.setattr(
        "src.infra.agent.model_storage.get_model_storage",
        lambda: FakeStorage(),
    )

    assert await node_utils.resolve_model_supports_vision("vision-id", None) is True
    assert await node_utils.resolve_model_supports_vision(None, "text-model") is False
    assert await node_utils.resolve_model_supports_vision(None, "missing") is False
