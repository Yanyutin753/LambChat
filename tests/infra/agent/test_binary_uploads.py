import base64

import pytest

from src.infra.agent.events import binary_uploads
from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.storage.s3.types import UploadResult


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def write(self, chunk: bytes) -> int:
        if not getattr(binary_uploads, "_inside_fake_blocking_io", False):
            raise AssertionError("binary upload writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(binary_uploads, "_inside_fake_blocking_io", False):
            raise AssertionError("binary upload seek must run in blocking IO executor")
        self.position = position
        return position

    def read(self) -> bytes:
        return bytes(self.data)


class FakeStorage:
    def __init__(self):
        self.uploaded = None

    async def upload_bytes(self, **_kwargs):
        raise AssertionError("binary blocks should use upload_file")

    async def upload_file(
        self,
        file,
        folder: str,
        filename: str,
        content_type: str,
        skip_size_limit: bool = False,
    ):
        data = file.read()
        self.uploaded = {
            "data": data,
            "folder": folder,
            "filename": filename,
            "content_type": content_type,
            "skip_size_limit": skip_size_limit,
        }
        return UploadResult(
            key=f"{folder}/{filename}",
            url=f"/api/upload/file/{folder}/{filename}",
            size=len(data),
            content_type=content_type,
        )


class FailingStorage:
    async def upload_file(self, **_kwargs):
        raise RuntimeError("upload failed")


@pytest.mark.asyncio
async def test_upload_binary_blocks_spools_decoded_bytes_to_storage_file(monkeypatch):
    storage = FakeStorage()
    blocking_calls: list[str] = []

    async def fake_get_or_init_storage():
        return storage

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        monkeypatch.setattr(binary_uploads, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(binary_uploads, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(binary_uploads, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(binary_uploads, "run_long_blocking_io", fake_run_long_blocking_io)
    monkeypatch.setattr(binary_uploads, "_inside_fake_blocking_io", False, raising=False)

    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": base64.b64encode(b"image-data").decode("ascii"),
            }
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    block = result["blocks"][0]
    assert "base64" not in block
    assert block["url"].startswith("https://app.example.com/api/upload/file/tool_binaries/")
    assert storage.uploaded == {
        "data": b"image-data",
        "folder": "tool_binaries",
        "filename": storage.uploaded["filename"],
        "content_type": "image/png",
        "skip_size_limit": True,
    }
    assert blocking_calls == ["_decode_base64_to_file"]


@pytest.mark.asyncio
async def test_upload_binary_blocks_redacts_base64_when_upload_fails(monkeypatch):
    async def fake_get_or_init_storage():
        return FailingStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    b64_image = base64.b64encode(b"image-data").decode("ascii")
    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": b64_image,
            }
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    assert result["blocks"] == [
        {
            "type": "image",
            "mime_type": "image/png",
            "upload_error": "binary_upload_failed",
        }
    ]


@pytest.mark.asyncio
async def test_upload_binary_blocks_redacts_all_remaining_base64_when_storage_init_fails(
    monkeypatch,
):
    async def fake_get_or_init_storage():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )

    first_b64 = base64.b64encode(b"first-image").decode("ascii")
    second_b64 = base64.b64encode(b"second-image").decode("ascii")
    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": first_b64,
            },
            {"type": "text", "text": "keep me"},
            {
                "type": "image",
                "mime_type": "image/jpeg",
                "base64": second_b64,
            },
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    assert result["blocks"] == [
        {
            "type": "image",
            "mime_type": "image/png",
            "upload_error": "binary_upload_failed",
        },
        {"type": "text", "text": "keep me"},
        {
            "type": "image",
            "mime_type": "image/jpeg",
            "upload_error": "binary_upload_failed",
        },
    ]


@pytest.mark.asyncio
async def test_upload_binary_blocks_rejects_oversized_decoded_payload_before_storage(
    monkeypatch,
):
    storage_init_calls = 0

    async def fake_get_or_init_storage():
        nonlocal storage_init_calls
        storage_init_calls += 1
        return FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(binary_uploads, "_BINARY_UPLOAD_MAX_BYTES", 4, raising=False)

    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": base64.b64encode(b"image-data").decode("ascii"),
            }
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    assert storage_init_calls == 0
    assert result["blocks"] == [
        {
            "type": "image",
            "mime_type": "image/png",
            "upload_error": "binary_upload_too_large",
        }
    ]


@pytest.mark.asyncio
async def test_upload_binary_blocks_redacts_blocks_over_batch_count_limit(monkeypatch):
    storage = FakeStorage()
    storage_init_calls = 0

    async def fake_get_or_init_storage():
        nonlocal storage_init_calls
        storage_init_calls += 1
        return storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(binary_uploads, "_BINARY_UPLOAD_MAX_BLOCKS", 1, raising=False)

    first_b64 = base64.b64encode(b"first-image").decode("ascii")
    second_b64 = base64.b64encode(b"second-image").decode("ascii")
    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": first_b64,
            },
            {
                "type": "image",
                "mime_type": "image/jpeg",
                "base64": second_b64,
            },
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    assert storage_init_calls == 1
    assert "base64" not in result["blocks"][0]
    assert result["blocks"][0]["url"].startswith(
        "https://app.example.com/api/upload/file/tool_binaries/"
    )
    assert result["blocks"][1] == {
        "type": "image",
        "mime_type": "image/jpeg",
        "upload_error": "binary_upload_too_many_blocks",
    }


@pytest.mark.asyncio
async def test_upload_binary_blocks_redacts_blocks_over_batch_byte_limit(monkeypatch):
    storage_init_calls = 0

    async def fake_get_or_init_storage():
        nonlocal storage_init_calls
        storage_init_calls += 1
        return FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        fake_get_or_init_storage,
    )
    monkeypatch.setattr(binary_uploads, "_BINARY_UPLOAD_TOTAL_MAX_BYTES", 8, raising=False)

    result = {
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": base64.b64encode(b"first").decode("ascii"),
            },
            {
                "type": "image",
                "mime_type": "image/jpeg",
                "base64": base64.b64encode(b"second").decode("ascii"),
            },
        ]
    }

    await upload_binary_blocks(result, "https://app.example.com")

    assert storage_init_calls == 1
    assert "base64" not in result["blocks"][0]
    assert result["blocks"][1] == {
        "type": "image",
        "mime_type": "image/jpeg",
        "upload_error": "binary_upload_too_large",
    }
