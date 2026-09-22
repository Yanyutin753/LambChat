from __future__ import annotations

import asyncio
import builtins
import io

import pytest

from src.infra.storage.s3 import service as s3_service
from src.infra.storage.s3.backends.aliyun import AliyunOssBackend
from src.infra.storage.s3.backends.local import LocalStorageBackend
from src.infra.storage.s3.backends.minio import MinioS3Backend
from src.infra.storage.s3.base import S3StorageBackend
from src.infra.storage.s3.service import (
    close_storage,
    get_or_init_storage,
    get_storage_service,
    init_storage,
)
from src.infra.storage.s3.types import S3Config, S3Provider
from src.kernel.config import settings


class _FakeBackend:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_get_s3_config_from_settings_preserves_internal_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "S3_ENABLED", True)
    monkeypatch.setattr(settings, "S3_PROVIDER", "minio")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "https://s3.example.com")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "access")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "bucket")
    monkeypatch.setattr(settings, "S3_CUSTOM_DOMAIN", "")
    monkeypatch.setattr(settings, "S3_PATH_STYLE", True)
    monkeypatch.setattr(settings, "S3_PUBLIC_BUCKET", False)
    monkeypatch.setattr(settings, "S3_MAX_FILE_SIZE", 123)
    monkeypatch.setattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 456)
    monkeypatch.setattr(settings, "S3_PRESIGNED_URL_EXPIRES", 789)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", "/tmp/uploads")

    config = await s3_service.get_s3_config_from_settings()

    assert config.max_file_size == 123
    assert config.internal_max_upload_size == 456
    assert config.presigned_url_expires == 789


class _FlakyStreamBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.payloads: list[bytes] = []

    async def upload(self, file, key, content_type=None, metadata=None):
        from src.infra.storage.s3.types import UploadResult

        self.calls += 1
        self.payloads.append(file.read())
        if self.calls == 1:
            raise OSError("temporary network failure")
        return UploadResult(
            key=key,
            url=f"https://example.test/{key}?signed=1",
            size=len(self.payloads[-1]),
            content_type=content_type or "application/octet-stream",
        )

    async def upload_bytes(self, *args, **kwargs):
        raise AssertionError("upload_stream_to_key must not materialize bytes")

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        return f"https://example.test/{key}?signed=1"

    async def close(self) -> None:
        pass


class _DownloadToFileBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def download(self, key: str) -> bytes:
        raise AssertionError("download_to_file must not materialize bytes")

    async def download_to_file(self, key: str, file, *, chunk_size: int = 1024 * 1024) -> int:
        self.calls.append((key, chunk_size))
        file.write(b"ab")
        file.write(b"cd")
        file.seek(0)
        return 4

    async def close(self) -> None:
        pass


class _DownloadGuardBackend:
    def __init__(self) -> None:
        self.download_called = False

    async def get_size(self, key: str) -> int:
        assert key == "documents/huge.bin"
        return 11

    async def download(self, key: str) -> bytes:
        self.download_called = True
        return b"x" * 11

    async def close(self) -> None:
        pass


class _PagedDeleteBackend:
    def __init__(self, objects: list[str]) -> None:
        self.objects = set(objects)
        self._client = _PagedDeleteClient(self)
        self.list_calls: list[str] = []

    async def list_objects(self, prefix: str = "") -> list[str]:
        self.list_calls.append(prefix)
        return sorted(key for key in self.objects if key.startswith(prefix))[:1000]

    async def delete(self, key: str) -> bool:
        existed = key in self.objects
        self.objects.discard(key)
        return existed

    async def close(self) -> None:
        pass


class _PagedDeleteClient:
    def __init__(self, backend: _PagedDeleteBackend) -> None:
        self.backend = backend

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        assert bucket_name == "bucket"
        self.backend.objects.discard(object_name)


class _StuckDeleteBackend:
    def __init__(self) -> None:
        self.list_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def list_objects(self, prefix: str = "") -> list[str]:
        self.list_calls.append(prefix)
        await asyncio.sleep(0)
        if prefix == "avatars/user-1":
            return ["avatars/user-1/stuck.png"]
        return []

    async def delete(self, key: str) -> bool:
        self.delete_calls.append(key)
        await asyncio.sleep(0)
        return False

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_get_or_init_storage_switches_to_local_when_s3_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )
    existing = get_storage_service()
    existing._backend = _FakeBackend()

    monkeypatch.setattr(settings, "S3_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"), raising=False)

    storage = await get_or_init_storage()

    assert storage.is_local
    assert storage._config.storage_path == str(tmp_path / "uploads")


@pytest.mark.asyncio
async def test_close_storage_closes_backend_and_releases_global_service() -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )
    storage = get_storage_service()
    backend = _FakeBackend()
    storage._backend = backend

    await close_storage()

    assert backend.closed is True
    assert storage._backend is None
    assert s3_service._storage_service is None
    assert s3_service.S3StorageService._instance is None


@pytest.mark.asyncio
async def test_get_or_init_storage_treats_string_false_as_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )

    monkeypatch.setattr(settings, "S3_ENABLED", "false", raising=False)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"), raising=False)

    storage = await get_or_init_storage()

    assert storage.is_local


class _ChunkRecordingFile(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


@pytest.mark.asyncio
async def test_local_storage_upload_streams_file_without_full_read(tmp_path) -> None:
    backend = LocalStorageBackend(
        S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads"))
    )
    source = _ChunkRecordingFile(b"a" * 1024 * 1024 + b"tail")

    result = await backend.upload(source, "documents/user/file.txt", "text/plain")

    assert result.size == 1024 * 1024 + 4
    assert (tmp_path / "uploads" / "documents" / "user" / "file.txt").read_bytes() == (
        b"a" * 1024 * 1024 + b"tail"
    )
    assert -1 not in source.read_sizes


@pytest.mark.asyncio
async def test_local_storage_list_objects_checks_missing_prefix_in_blocking_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from src.infra.storage.s3.backends import local as local_backend_module

    backend = LocalStorageBackend(
        S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads"))
    )
    blocking_calls: list[str] = []

    async def fake_run_long_blocking_io(func, *args, **kwargs):
        del args, kwargs
        blocking_calls.append(func.__name__)
        return func()

    monkeypatch.setattr(local_backend_module, "run_long_blocking_io", fake_run_long_blocking_io)

    objects = await backend.list_objects("missing")

    assert objects == []
    assert "_list" in blocking_calls


@pytest.mark.asyncio
async def test_local_storage_list_objects_limits_large_prefix(tmp_path) -> None:
    backend = LocalStorageBackend(
        S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads"))
    )
    folder = tmp_path / "uploads" / "bulk"
    folder.mkdir(parents=True)
    for index in range(1100):
        (folder / f"{index:04d}.txt").write_text("x")

    objects = await backend.list_objects("bulk")

    assert len(objects) == 1000
    assert objects[0] == "bulk/0000.txt"
    assert objects[-1] == "bulk/0999.txt"


@pytest.mark.asyncio
async def test_local_storage_download_stream_reads_file_in_chunks(tmp_path) -> None:
    backend = LocalStorageBackend(
        S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads"))
    )
    object_path = tmp_path / "uploads" / "documents" / "file.txt"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"abcdef")

    chunks = [chunk async for chunk in backend.download_stream("documents/file.txt", chunk_size=2)]

    assert chunks == [b"ab", b"cd", b"ef"]


@pytest.mark.asyncio
async def test_local_storage_download_range_reads_only_requested_bytes(tmp_path) -> None:
    backend = LocalStorageBackend(
        S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads"))
    )
    object_path = tmp_path / "uploads" / "documents" / "file.txt"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"0123456789")

    data = await backend.download_range("documents/file.txt", 3, 6)

    assert data == b"3456"


@pytest.mark.asyncio
async def test_local_storage_download_rejects_large_file_before_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    backend = LocalStorageBackend(
        S3Config(
            provider=S3Provider.LOCAL,
            storage_path=str(tmp_path / "uploads"),
            internal_max_upload_size=8,
        )
    )
    object_path = tmp_path / "uploads" / "documents" / "huge.bin"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"x" * 9)
    original_open = builtins.open

    def _guarded_open(file, *args, **kwargs):
        if file == object_path:
            raise AssertionError("oversized local object should not be opened")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)

    with pytest.raises(ValueError, match="exceeds internal download limit"):
        await backend.download("documents/huge.bin")


@pytest.mark.asyncio
async def test_local_storage_download_range_rejects_large_range_before_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    backend = LocalStorageBackend(
        S3Config(
            provider=S3Provider.LOCAL,
            storage_path=str(tmp_path / "uploads"),
            internal_max_upload_size=8,
        )
    )
    object_path = tmp_path / "uploads" / "documents" / "file.bin"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"x" * 32)
    original_open = builtins.open

    def _guarded_open(file, *args, **kwargs):
        if file == object_path:
            raise AssertionError("oversized range should not open local object")
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _guarded_open)

    with pytest.raises(ValueError, match="exceeds internal download limit"):
        await backend.download_range("documents/file.bin", 0, 8)


@pytest.mark.asyncio
async def test_storage_service_upload_stream_to_key_preserves_caller_key(tmp_path) -> None:
    await init_storage(S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path / "uploads")))
    storage = get_storage_service()
    source = _ChunkRecordingFile(b"abcdef")

    result = await storage.upload_stream_to_key(source, "image/user/stable.png", "image/png")

    assert result.key == "image/user/stable.png"
    assert (tmp_path / "uploads" / "image" / "user" / "stable.png").read_bytes() == b"abcdef"
    assert -1 not in source.read_sizes


@pytest.mark.asyncio
async def test_storage_service_upload_stream_to_key_rewinds_between_retries() -> None:
    storage = get_storage_service()
    backend = _FlakyStreamBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL))
    storage._backend = backend  # type: ignore[assignment]
    source = io.BytesIO(b"abcdef")

    result = await storage.upload_stream_to_key(source, "image/user/retry.png", "image/png")

    assert result.key == "image/user/retry.png"
    assert backend.payloads == [b"abcdef", b"abcdef"]


@pytest.mark.asyncio
async def test_storage_service_upload_stream_to_key_offloads_file_positioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.storage.s3 import service as s3_service_module

    inside_blocking_io = False

    class _GuardedFile(io.BytesIO):
        def tell(self) -> int:
            assert inside_blocking_io, "upload stream tell must be offloaded"
            return super().tell()

        def seek(self, pos: int, whence: int = 0) -> int:
            assert inside_blocking_io, "upload stream seek must be offloaded"
            return super().seek(pos, whence)

        def read(self, size: int = -1) -> bytes:
            assert inside_blocking_io, "backend stream read must be offloaded"
            return super().read(size)

    class _GuardedUploadBackend:
        def __init__(self) -> None:
            self.payloads: list[bytes] = []

        async def upload(self, file, key, content_type=None, metadata=None):
            data = await fake_run_long_blocking_io(file.read)
            self.payloads.append(data)
            from src.infra.storage.s3.types import UploadResult

            return UploadResult(
                key=key,
                url=f"https://example.test/{key}",
                size=len(data),
                content_type=content_type or "application/octet-stream",
            )

        async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
            return f"https://example.test/{key}?expires={expires}"

        async def close(self) -> None:
            pass

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    monkeypatch.setattr(s3_service_module, "run_long_blocking_io", fake_run_long_blocking_io)

    storage = get_storage_service()
    backend = _GuardedUploadBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL))
    storage._backend = backend  # type: ignore[assignment]
    source = _GuardedFile(b"abcdef")

    result = await storage.upload_stream_to_key(
        source,
        "image/user/stable.png",
        "image/png",
        skip_size_limit=False,
    )

    assert result.key == "image/user/stable.png"
    assert backend.payloads == [b"abcdef"]


@pytest.mark.asyncio
async def test_storage_service_upload_bytes_uses_streaming_backend_upload() -> None:
    storage = get_storage_service()
    backend = _FlakyStreamBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL))
    storage._backend = backend  # type: ignore[assignment]

    result = await storage.upload_bytes(b"abcdef", "image/user", "avatar.png", "image/png")

    assert result.key.startswith("image/user/")
    assert backend.payloads == [b"abcdef", b"abcdef"]


@pytest.mark.asyncio
async def test_storage_service_upload_to_key_uses_streaming_backend_upload() -> None:
    storage = get_storage_service()
    backend = _FlakyStreamBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL))
    storage._backend = backend  # type: ignore[assignment]

    result = await storage.upload_to_key(b"abcdef", "image/user/stable.png", "image/png")

    assert result.key == "image/user/stable.png"
    assert backend.payloads == [b"abcdef", b"abcdef"]


@pytest.mark.asyncio
async def test_storage_service_download_to_file_uses_backend_streaming_path() -> None:
    storage = get_storage_service()
    backend = _DownloadToFileBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL))
    storage._backend = backend  # type: ignore[assignment]
    target = io.BytesIO()

    size = await storage.download_to_file("documents/user/file.txt", target, chunk_size=2)

    assert size == 4
    assert target.read() == b"abcd"
    assert backend.calls == [("documents/user/file.txt", 2)]


@pytest.mark.asyncio
async def test_default_backend_download_to_file_offloads_sink_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.storage.s3 import base as s3_base

    inside_blocking_io = False

    class _DefaultStreamingBackend(S3StorageBackend):
        async def upload(self, file, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def upload_bytes(self, data, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def download(self, key: str) -> bytes:
            raise AssertionError("download_to_file must not materialize bytes")

        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            assert key == "documents/file.txt"
            assert chunk_size == 2
            yield b"ab"
            yield b"cd"

        async def delete(self, key: str) -> bool:
            raise NotImplementedError

        async def exists(self, key: str) -> bool:
            raise NotImplementedError

        async def get_url(self, key: str) -> str:
            raise NotImplementedError

        async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
            raise NotImplementedError

        async def list_objects(self, prefix: str = "") -> list[str]:
            raise NotImplementedError

        async def close(self) -> None:
            pass

    class _GuardedFile(io.BytesIO):
        def write(self, data: bytes) -> int:
            assert inside_blocking_io, "download_to_file sink writes must be offloaded"
            return super().write(data)

        def seek(self, pos: int, whence: int = 0) -> int:
            assert inside_blocking_io, "download_to_file sink seeks must be offloaded"
            return super().seek(pos, whence)

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    monkeypatch.setattr(s3_base, "run_long_blocking_io", fake_run_long_blocking_io, raising=False)

    target = _GuardedFile()
    size = await _DefaultStreamingBackend().download_to_file(
        "documents/file.txt",
        target,
        chunk_size=2,
    )

    assert size == 4
    assert target.read() == b"abcd"


@pytest.mark.asyncio
async def test_default_backend_get_size_requires_efficient_stat() -> None:
    class _DownloadOnlyBackend(S3StorageBackend):
        async def upload(self, file, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def upload_bytes(self, data, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def download(self, key: str) -> bytes:
            raise AssertionError("default get_size must not materialize bytes via download")

        async def delete(self, key: str) -> bool:
            return True

        async def exists(self, key: str) -> bool:
            return True

        async def get_url(self, key: str) -> str:
            return key

        async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
            return key

        async def list_objects(self, prefix: str = "") -> list[str]:
            return []

        async def close(self) -> None:
            return None

    with pytest.raises(NotImplementedError):
        await _DownloadOnlyBackend().get_size("documents/file.txt")


@pytest.mark.asyncio
async def test_default_backend_download_stream_requires_streaming_override() -> None:
    class _DownloadOnlyBackend(S3StorageBackend):
        async def upload(self, file, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def upload_bytes(self, data, key, content_type=None, metadata=None):
            raise NotImplementedError

        async def download(self, key: str) -> bytes:
            raise AssertionError("default download_stream must not materialize bytes")

        async def delete(self, key: str) -> bool:
            return True

        async def exists(self, key: str) -> bool:
            return True

        async def get_url(self, key: str) -> str:
            return key

        async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
            return key

        async def list_objects(self, prefix: str = "") -> list[str]:
            return []

        async def close(self) -> None:
            return None

    with pytest.raises(NotImplementedError):
        async for _chunk in _DownloadOnlyBackend().download_stream("documents/file.txt"):
            pass


@pytest.mark.asyncio
async def test_storage_service_download_file_rejects_large_object_before_download() -> None:
    storage = get_storage_service()
    backend = _DownloadGuardBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL, internal_max_upload_size=10))
    storage._backend = backend  # type: ignore[assignment]

    with pytest.raises(ValueError, match="exceeds internal download limit"):
        await storage.download_file("documents/huge.bin")

    assert backend.download_called is False


@pytest.mark.asyncio
async def test_delete_user_files_deletes_prefixes_in_bounded_batches() -> None:
    objects = [
        *(f"avatars/user-1/{index:04d}.png" for index in range(1001)),
        *(f"user-1/{index:04d}.txt" for index in range(1201)),
    ]
    storage = get_storage_service()
    backend = _PagedDeleteBackend(objects)
    storage.configure(S3Config(provider=S3Provider.LOCAL, bucket_name="bucket"))
    storage._backend = backend  # type: ignore[assignment]

    deleted = await storage.delete_user_files("user-1")

    assert deleted == 2202
    assert backend.objects == set()
    assert backend.list_calls.count("avatars/user-1") >= 2
    assert backend.list_calls.count("user-1") >= 2


@pytest.mark.asyncio
async def test_delete_user_files_stops_when_delete_makes_no_progress() -> None:
    storage = get_storage_service()
    backend = _StuckDeleteBackend()
    storage.configure(S3Config(provider=S3Provider.LOCAL, bucket_name="bucket"))
    storage._backend = backend  # type: ignore[assignment]

    deleted = await asyncio.wait_for(storage.delete_user_files("user-1"), timeout=1)

    assert deleted == 0
    assert backend.delete_calls == ["avatars/user-1/stuck.png"]
    assert backend.list_calls == ["avatars/user-1", "user-1"]


class _FakeMinioObject:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.closed = False
        self.released = False
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("download paths must read object responses in bounded chunks")
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeAliyunObject:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.closed = False
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("download paths must read object responses in bounded chunks")
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_minio_download_stream_reads_chunks_and_releases_response() -> None:
    response = _FakeMinioObject([b"ab", b"cd"])

    class _FakeMinioClient:
        def get_object(self, **kwargs):
            assert kwargs["object_name"] == "documents/file.txt"
            return response

    backend = MinioS3Backend(S3Config(provider=S3Provider.MINIO, bucket_name="bucket"))
    backend._client = _FakeMinioClient()  # type: ignore[assignment]

    chunks = [chunk async for chunk in backend.download_stream("documents/file.txt", chunk_size=2)]

    assert chunks == [b"ab", b"cd"]
    assert response.read_sizes == [2, 2, 2]
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_minio_upload_offloads_lazy_client_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.storage.s3.backends import minio as minio_backend_module
    from src.infra.storage.s3.types import UploadResult

    calls: list[str] = []

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    class _FakeMinioClient:
        def put_object(self, **kwargs):
            return type("_Result", (), {"etag": "etag-1"})()

    class _Backend(MinioS3Backend):
        def _get_client(self):
            return _FakeMinioClient()

    monkeypatch.setattr(minio_backend_module, "run_long_blocking_io", fake_run_long_blocking_io)

    backend = _Backend(S3Config(provider=S3Provider.MINIO, bucket_name="bucket"))
    result = await backend.upload(io.BytesIO(b"abcd"), "documents/file.txt", "text/plain")

    assert isinstance(result, UploadResult)
    assert calls == ["_measure_size", "_get_client", "_put_object"]


@pytest.mark.asyncio
async def test_aliyun_upload_offloads_lazy_bucket_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.storage.s3.backends import aliyun as aliyun_backend_module
    from src.infra.storage.s3.types import UploadResult

    calls: list[str] = []

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    class _FakeBucket:
        def put_object(self, key, file, headers=None):
            del key, file, headers
            return type("_Result", (), {"etag": "etag-1"})()

    class _Backend(AliyunOssBackend):
        def _get_bucket(self):
            return _FakeBucket()

    monkeypatch.setattr(aliyun_backend_module, "run_long_blocking_io", fake_run_long_blocking_io)

    backend = _Backend(S3Config(provider=S3Provider.ALIYUN, bucket_name="bucket"))
    result = await backend.upload(io.BytesIO(b"abcd"), "documents/file.txt", "text/plain")

    assert isinstance(result, UploadResult)
    assert calls == ["_measure_size", "_get_bucket", "_put_object"]


@pytest.mark.asyncio
async def test_aliyun_download_compat_reads_chunks_and_closes_response() -> None:
    response = _FakeAliyunObject([b"ab", b"cd"])

    class _FakeBucket:
        def get_object(self, key, **kwargs):
            assert key == "documents/file.txt"
            assert kwargs == {}
            return response

    backend = AliyunOssBackend(S3Config(provider=S3Provider.ALIYUN, bucket_name="bucket"))
    backend._bucket = _FakeBucket()

    data = await backend.download("documents/file.txt")

    assert data == b"abcd"
    assert -1 not in response.read_sizes
    assert response.closed is True


@pytest.mark.asyncio
async def test_aliyun_download_compat_rejects_oversized_response_and_closes() -> None:
    response = _FakeAliyunObject([b"1234", b"56789"])

    class _FakeBucket:
        def get_object(self, key, **kwargs):
            assert key == "documents/large.bin"
            assert kwargs == {}
            return response

    backend = AliyunOssBackend(
        S3Config(
            provider=S3Provider.ALIYUN,
            bucket_name="bucket",
            internal_max_upload_size=8,
        )
    )
    backend._bucket = _FakeBucket()

    with pytest.raises(ValueError, match="exceeds internal download limit"):
        await backend.download("documents/large.bin")

    assert response.closed is True


@pytest.mark.asyncio
async def test_aliyun_download_range_reads_chunks_and_closes_response() -> None:
    response = _FakeAliyunObject([b"ab", b"cd"])

    class _FakeBucket:
        def get_object(self, key, **kwargs):
            assert key == "documents/file.txt"
            assert kwargs["byte_range"] == (10, 13)
            return response

    backend = AliyunOssBackend(S3Config(provider=S3Provider.ALIYUN, bucket_name="bucket"))
    backend._bucket = _FakeBucket()

    data = await backend.download_range("documents/file.txt", 10, 13)

    assert data == b"abcd"
    assert -1 not in response.read_sizes
    assert response.closed is True


@pytest.mark.asyncio
async def test_minio_download_compat_reads_chunks_and_releases_response() -> None:
    response = _FakeMinioObject([b"ab", b"cd"])

    class _FakeMinioClient:
        def get_object(self, **kwargs):
            assert kwargs["object_name"] == "documents/file.txt"
            return response

    backend = MinioS3Backend(S3Config(provider=S3Provider.MINIO, bucket_name="bucket"))
    backend._client = _FakeMinioClient()  # type: ignore[assignment]

    data = await backend.download("documents/file.txt")

    assert data == b"abcd"
    assert -1 not in response.read_sizes
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_minio_download_compat_rejects_oversized_response_and_releases() -> None:
    response = _FakeMinioObject([b"1234", b"56789"])

    class _FakeMinioClient:
        def get_object(self, **kwargs):
            assert kwargs["object_name"] == "documents/large.bin"
            return response

    backend = MinioS3Backend(
        S3Config(
            provider=S3Provider.MINIO,
            bucket_name="bucket",
            internal_max_upload_size=8,
        )
    )
    backend._client = _FakeMinioClient()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="exceeds internal download limit"):
        await backend.download("documents/large.bin")

    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_minio_download_range_reads_chunks_and_releases_response() -> None:
    response = _FakeMinioObject([b"ab", b"cd"])

    class _FakeMinioClient:
        def get_object(self, **kwargs):
            assert kwargs["object_name"] == "documents/file.txt"
            assert kwargs["offset"] == 10
            assert kwargs["length"] == 4
            return response

    backend = MinioS3Backend(S3Config(provider=S3Provider.MINIO, bucket_name="bucket"))
    backend._client = _FakeMinioClient()  # type: ignore[assignment]

    data = await backend.download_range("documents/file.txt", 10, 13)

    assert data == b"abcd"
    assert -1 not in response.read_sizes
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_minio_list_objects_limits_large_prefix() -> None:
    class _Object:
        def __init__(self, name: str) -> None:
            self.object_name = name

    class _FakeMinioClient:
        def list_objects(self, **kwargs):
            assert kwargs["prefix"] == "bulk"
            for index in range(1100):
                yield _Object(f"bulk/{index:04d}.txt")

    backend = MinioS3Backend(S3Config(provider=S3Provider.MINIO, bucket_name="bucket"))
    backend._client = _FakeMinioClient()  # type: ignore[assignment]

    objects = await backend.list_objects("bulk")

    assert len(objects) == 1000
    assert objects[-1] == "bulk/0999.txt"
