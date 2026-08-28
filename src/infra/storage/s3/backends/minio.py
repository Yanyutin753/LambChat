"""
S3 storage backend using minio library.

Compatible with AWS S3, MinIO, Tencent COS, and any S3-compatible provider.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3.base import LIST_OBJECTS_LIMIT, BinaryReadFile, S3StorageBackend
from src.infra.storage.s3.types import S3Config, S3Provider, UploadResult
from src.infra.utils.datetime import utc_now

if TYPE_CHECKING:
    import minio

logger = get_logger(__name__)
UPLOAD_PART_SIZE = 10 * 1024 * 1024
DOWNLOAD_COMPAT_CHUNK_SIZE = 1024 * 1024


class MinioS3Backend(S3StorageBackend):
    """S3 storage backend using minio library"""

    def __init__(self, config: S3Config):
        self.config = config
        self._client: minio.Minio | None = None

    def _get_client(self):
        """Get or create minio S3 client"""
        if self._client is None:
            import minio

            endpoint: str | None = self.config.endpoint_url or self.config.get_endpoint_url()
            if endpoint:
                endpoint = endpoint.replace("https://", "").replace("http://", "")
            else:
                endpoint = "localhost:9000"

            logger.info(
                f"Minio client config: endpoint={endpoint}, bucket={self.config.bucket_name}, "
                f"region={self.config.region}, access_key length={len(self.config.access_key)}"
            )

            self._client = minio.Minio(
                endpoint=endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=True,
                region=(self.config.region if self.config.provider != S3Provider.AWS else None),
            )

        return self._client

    async def upload(
        self,
        file: BinaryReadFile,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        import mimetypes

        if not content_type:
            content_type, _ = mimetypes.guess_type(key)
            if not content_type:
                content_type = "application/octet-stream"

        def _measure_size() -> int:
            current_pos = file.tell()
            file.seek(0, 2)
            file_size = file.tell() - current_pos
            file.seek(current_pos)
            return file_size

        file_size = await run_blocking_io(_measure_size)

        client = await run_blocking_io(self._get_client)

        def _put_object():
            return client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
                data=file,
                length=file_size,
                part_size=UPLOAD_PART_SIZE,
                content_type=content_type,
                metadata=metadata or {},
            )

        result = await run_blocking_io(_put_object)

        return UploadResult(
            key=key,
            url=self.config.get_public_url(key),
            size=file_size,
            content_type=content_type,
            etag=result.etag,
            last_modified=utc_now(),
        )

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        return await self.upload(io.BytesIO(data), key, content_type, metadata)

    async def download(self, key: str) -> bytes:
        client = await run_blocking_io(self._get_client)

        response = await run_blocking_io(
            lambda: client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
        )
        return await self._read_response_chunks(
            response,
            DOWNLOAD_COMPAT_CHUNK_SIZE,
            max_bytes=self.config.internal_max_upload_size,
        )

    async def get_size(self, key: str) -> int:
        client = await run_blocking_io(self._get_client)

        def _stat():
            stat = client.stat_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
            return stat.size

        return await run_blocking_io(_stat)

    async def download_range(self, key: str, start: int, end: int) -> bytes:
        client = await run_blocking_io(self._get_client)
        length = end - start + 1
        if length > self.config.internal_max_upload_size:
            max_mb = self.config.internal_max_upload_size / (1024 * 1024)
            raise ValueError(
                f"Range size ({length / (1024 * 1024):.1f}MB) exceeds "
                f"internal download limit ({max_mb:.0f}MB)"
            )

        response = await run_blocking_io(
            lambda: client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
                offset=start,
                length=length,
            )
        )
        return await self._read_response_chunks(
            response,
            min(length, DOWNLOAD_COMPAT_CHUNK_SIZE),
            max_bytes=self.config.internal_max_upload_size,
        )

    async def _read_response_chunks(self, response, chunk_size: int, *, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total_size = 0
        try:
            while True:
                chunk = await run_blocking_io(lambda: response.read(chunk_size))
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_bytes:
                    max_mb = max_bytes / (1024 * 1024)
                    raise ValueError(
                        f"Response size ({total_size / (1024 * 1024):.1f}MB) exceeds "
                        f"internal download limit ({max_mb:.0f}MB)"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                await run_blocking_io(close)
            release_conn = getattr(response, "release_conn", None)
            if release_conn is not None:
                await run_blocking_io(release_conn)

    async def download_stream(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        client = await run_blocking_io(self._get_client)
        response = await run_blocking_io(
            lambda: client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
        )
        try:
            while True:
                chunk = await run_blocking_io(lambda: response.read(chunk_size))
                if not chunk:
                    break
                yield chunk
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                await run_blocking_io(close)
            release_conn = getattr(response, "release_conn", None)
            if release_conn is not None:
                await run_blocking_io(release_conn)

    async def delete(self, key: str) -> bool:
        client = await run_blocking_io(self._get_client)

        def _delete_object():
            client.remove_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
            return True

        return await run_blocking_io(_delete_object)

    async def exists(self, key: str) -> bool:
        client = await run_blocking_io(self._get_client)

        def _stat_object():
            try:
                client.stat_object(
                    bucket_name=self.config.bucket_name,
                    object_name=key,
                )
                return True
            except Exception:
                return False

        return await run_blocking_io(_stat_object)

    async def get_url(self, key: str) -> str:
        return self.config.get_public_url(key)

    async def get_presigned_url(
        self, key: str, expires: int = 3600, process: str | None = None
    ) -> str:
        client = await run_blocking_io(self._get_client)

        def _presigned_url():
            from datetime import timedelta

            return client.presigned_get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
                expires=timedelta(seconds=expires),
            )

        return await run_blocking_io(_presigned_url)

    async def list_objects(self, prefix: str = "") -> list[str]:
        client = await run_blocking_io(self._get_client)

        def _list_objects():
            objects = []
            for obj in client.list_objects(
                bucket_name=self.config.bucket_name,
                prefix=prefix,
                recursive=True,
            ):
                objects.append(obj.object_name)
                if len(objects) >= LIST_OBJECTS_LIMIT:
                    break
            return objects

        return await run_blocking_io(_list_objects)

    async def close(self) -> None:
        self._client = None
