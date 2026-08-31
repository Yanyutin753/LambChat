from __future__ import annotations

import gc
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.api.routes import upload as upload_route
from src.api.routes.upload import (
    SignedUrlRequest,
    _read_upload_file_limited,
    _spool_upload_file_limited,
)
from src.kernel.errors import AppError


class ChunkedUpload:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.read_calls = 0

    async def read(self, size: int = -1) -> bytes:
        del size
        self.read_calls += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _TrackableChunk(bytearray):
    pass


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.closed = False
        self.position = 0

    def write(self, chunk: bytes) -> int:
        if not getattr(upload_route, "_inside_fake_blocking_io", False):
            raise AssertionError("spooled writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(upload_route, "_inside_fake_blocking_io", False):
            raise AssertionError("spooled seek must run in blocking IO executor")
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        data = bytes(self.data)
        if size >= 0:
            data = data[:size]
        return data

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_read_upload_file_limited_rejects_oversize_without_reading_rest() -> None:
    upload = ChunkedUpload([b"abcd", b"efgh", b"this-should-not-be-read"])

    with pytest.raises(AppError) as exc_info:
        await _read_upload_file_limited(upload, max_size_bytes=5, max_size_mb=1, purpose="File")

    assert exc_info.value.error_code.code == "file_too_large"
    assert exc_info.value.http_status == 413
    assert upload.read_calls == 2


@pytest.mark.asyncio
async def test_spool_upload_file_limited_offloads_spooled_file_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func.__name__)
        monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(upload_route, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(upload_route, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", False, raising=False)

    upload = ChunkedUpload([b"abc", b"def", b""])

    spooled = await _spool_upload_file_limited(upload, max_size_bytes=6, max_size_mb=1)

    try:
        assert bytes(spooled.file.data) == b"abcdef"
        assert calls == ["write", "write", "seek"]
    finally:
        spooled.close()


@pytest.mark.asyncio
async def test_read_upload_file_limited_returns_bytes_within_limit() -> None:
    upload = ChunkedUpload([b"abc", b"def", b""])

    data = await _read_upload_file_limited(upload, max_size_bytes=6, max_size_mb=1)

    assert data == b"abcdef"


@pytest.mark.asyncio
async def test_read_upload_file_limited_releases_previous_chunks_while_reading() -> None:
    first = _TrackableChunk(b"abc")
    second = _TrackableChunk(b"def")
    first_ref = weakref.ref(first)
    second_ref = weakref.ref(second)
    earlier_chunks_released_before_eof = False

    class _ReleasingUpload:
        def __init__(self) -> None:
            self._chunks = [first, second]

        async def read(self, size: int = -1) -> bytes:
            del size
            nonlocal first, second, earlier_chunks_released_before_eof
            if self._chunks:
                chunk = self._chunks.pop(0)
                if chunk is first:
                    first = None  # type: ignore[assignment]
                if chunk is second:
                    second = None  # type: ignore[assignment]
                return chunk
            gc.collect()
            earlier_chunks_released_before_eof = first_ref() is None
            return b""

    data = await _read_upload_file_limited(
        _ReleasingUpload(),
        max_size_bytes=6,
        max_size_mb=1,
    )

    assert data == b"abcdef"
    assert earlier_chunks_released_before_eof is True
    assert second_ref() is None


@pytest.mark.asyncio
async def test_spool_upload_file_limited_hashes_without_buffering_all_content() -> None:
    upload = ChunkedUpload([b"abc", b"def", b""])

    spooled = await _spool_upload_file_limited(upload, max_size_bytes=6, max_size_mb=1)

    try:
        assert spooled.size == 6
        assert spooled.sha256_hex == (
            "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"
        )
        assert spooled.file.read() == b"abcdef"
        assert upload.read_calls == 3
    finally:
        spooled.close()


@pytest.mark.asyncio
async def test_spool_upload_file_limited_rejects_empty_file_and_closes_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TrackingSpool(_BlockingOnlySpooledFile):
        def seek(self, position: int) -> int:
            self.position = position
            return position

    created: list[_TrackingSpool] = []

    def make_spool(*args, **kwargs):
        spool = _TrackingSpool(*args, **kwargs)
        created.append(spool)
        return spool

    monkeypatch.setattr(upload_route, "SpooledTemporaryFile", make_spool)

    with pytest.raises(AppError) as exc_info:
        await _spool_upload_file_limited(
            ChunkedUpload([b""]),
            max_size_bytes=6,
            max_size_mb=1,
        )

    assert exc_info.value.error_code.code == "empty_file"
    assert exc_info.value.http_status == 400
    assert len(created) == 1
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_spool_upload_file_limited_names_empty_avatar_uploads() -> None:
    with pytest.raises(AppError) as exc_info:
        await _spool_upload_file_limited(
            ChunkedUpload([b""]),
            max_size_bytes=6,
            max_size_mb=1,
            purpose="Avatar file",
        )

    assert exc_info.value.error_code.code == "empty_file"


@pytest.mark.asyncio
async def test_spool_upload_file_limited_rejects_oversize_and_closes_file() -> None:
    upload = ChunkedUpload([b"abcd", b"efgh", b"this-should-not-be-read"])

    with pytest.raises(AppError) as exc_info:
        await _spool_upload_file_limited(upload, max_size_bytes=5, max_size_mb=1, purpose="File")

    assert exc_info.value.error_code.code == "file_too_large"
    assert exc_info.value.http_status == 413
    assert upload.read_calls == 2


@pytest.mark.asyncio
async def test_local_file_proxy_checks_file_existence_in_blocking_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "uploads" / "docs" / "report.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("hello", encoding="utf-8")
    blocking_calls: list[str] = []

    class _FakeStorage:
        is_local = True

        def get_file_path(self, key: str) -> Path:
            assert key == "docs/report.txt"
            return file_path

    class _FakeRecordStorage:
        async def find_by_key(self, key: str):
            assert key == "docs/report.txt"
            return {"name": "report.txt", "mime_type": "text/plain"}

    async def fake_get_or_init_storage():
        return _FakeStorage()

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(upload_route, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(upload_route, "_file_record_storage", _FakeRecordStorage())
    monkeypatch.setattr(upload_route, "run_blocking_io", fake_run_blocking_io)

    response = await upload_route.get_file_proxy(
        "docs/report.txt",
        request=SimpleNamespace(
            base_url="https://app.example.com/",
            headers={},
        ),
    )

    assert response.path == str(file_path)
    assert "_path_exists" in blocking_calls


@pytest.mark.asyncio
async def test_s3_file_proxy_can_stream_through_app_for_preview_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        is_local = False
        _config = SimpleNamespace(public_bucket=False)

        async def file_exists(self, key: str) -> bool:
            assert key == "docs/report.txt"
            return True

        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            assert key == "docs/report.txt"
            del chunk_size
            yield b"hello "
            yield b"world"

        async def get_presigned_url(self, key: str, expires: int):
            raise AssertionError("proxy preview fetches should not redirect to object storage")

    class _FakeRecordStorage:
        async def find_by_key(self, key: str):
            assert key == "docs/report.txt"
            return {"name": "report.txt", "mime_type": "text/plain"}

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(upload_route, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(upload_route, "_file_record_storage", _FakeRecordStorage())

    response = await upload_route.get_file_proxy(
        "docs/report.txt",
        request=SimpleNamespace(
            base_url="https://app.example.com/",
            headers={},
        ),
        proxy=True,
    )

    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.media_type == "text/plain"
    assert body == b"hello world"
    assert response.headers["Cache-Control"] == "public, max-age=300"


def test_signed_url_request_rejects_too_many_keys() -> None:
    with pytest.raises(ValidationError):
        SignedUrlRequest.model_validate(
            {
                "keys": [f"uploads/file-{index}.png" for index in range(101)],
                "expires": 3600,
            }
        )


@pytest.mark.asyncio
async def test_upload_route_s3_config_preserves_internal_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_route.settings, "S3_ENABLED", True)
    monkeypatch.setattr(upload_route.settings, "S3_PROVIDER", "minio")
    monkeypatch.setattr(upload_route.settings, "S3_ENDPOINT_URL", "https://s3.example.com")
    monkeypatch.setattr(upload_route.settings, "S3_ACCESS_KEY", "access")
    monkeypatch.setattr(upload_route.settings, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(upload_route.settings, "S3_REGION", "us-east-1")
    monkeypatch.setattr(upload_route.settings, "S3_BUCKET_NAME", "bucket")
    monkeypatch.setattr(upload_route.settings, "S3_CUSTOM_DOMAIN", "")
    monkeypatch.setattr(upload_route.settings, "S3_PATH_STYLE", True)
    monkeypatch.setattr(upload_route.settings, "S3_PUBLIC_BUCKET", False)
    monkeypatch.setattr(upload_route.settings, "S3_MAX_FILE_SIZE", 123)
    monkeypatch.setattr(upload_route.settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 456)
    monkeypatch.setattr(upload_route.settings, "S3_PRESIGNED_URL_EXPIRES", 789)
    monkeypatch.setattr(upload_route.settings, "LOCAL_STORAGE_PATH", "/tmp/uploads")

    config = await upload_route.get_s3_config_from_settings()

    assert config.max_file_size == 123
    assert config.internal_max_upload_size == 456
    assert config.presigned_url_expires == 789


@pytest.mark.asyncio
async def test_upload_delete_unknown_key_never_starts_background_object_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _FakeStorage:
        async def delete_file(self, key: str) -> None:
            calls.append(key)

    class _FakeRecordStorage:
        async def find_by_key(self, key: str, uploaded_by: str):
            assert uploaded_by == "owner-a"
            return None

    async def fake_get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(upload_route, "get_or_init_storage", fake_get_or_init_storage)
    monkeypatch.setattr(upload_route, "_file_record_storage", _FakeRecordStorage())

    with pytest.raises(AppError) as exc_info:
        await upload_route.delete_file(
            "uploads/one.txt", current_user=SimpleNamespace(sub="owner-a")
        )

    assert exc_info.value.error_code.code == "file_not_found"
    assert exc_info.value.http_status == 404
    assert calls == []
