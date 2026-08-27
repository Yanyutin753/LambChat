"""
Aliyun OSS storage backend using official oss2 library.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from typing import Optional

import oss2

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3.base import LIST_OBJECTS_LIMIT, BinaryReadFile, S3StorageBackend
from src.infra.storage.s3.types import S3Config, UploadResult
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
DOWNLOAD_COMPAT_CHUNK_SIZE = 1024 * 1024


class AliyunOssBackend(S3StorageBackend):
    """Aliyun OSS storage backend using official oss2 library"""

    def __init__(self, config: S3Config):
        self.config = config
        self._bucket = None

    def _get_bucket(self):
        """Get or create Aliyun OSS bucket"""
        if self._bucket is None:
            endpoint = self.config.endpoint_url or f"oss-{self.config.region}.aliyuncs.com"
            endpoint = endpoint.replace("https://", "").replace("http://", "")

            auth = oss2.Auth(self.config.access_key, self.config.secret_key)

            logger.info(
                f"Aliyun OSS client config: endpoint={endpoint}, bucket={self.config.bucket_name}, "
                f"region={self.config.region}"
            )

            self._bucket = oss2.Bucket(
                auth,
                f"https://{endpoint}",
                self.config.bucket_name,
                connect_timeout=30,
            )

        return self._bucket

    async def upload(
        self,
        file: BinaryReadFile,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        def _measure_size() -> int:
            current_pos = file.tell()
            file.seek(0, 2)
            file_size = file.tell() - current_pos
            file.seek(current_pos)
            return file_size

        file_size = await run_blocking_io(_measure_size)

        bucket = await run_blocking_io(self._get_bucket)

        def _put_object():
            headers = {}
            if content_type:
                headers["Content-Type"] = content_type
            if metadata:
                headers.update(metadata)
            return bucket.put_object(key, file, headers=headers)

        result = await run_blocking_io(_put_object)

        return UploadResult(
            key=key,
            url=self.config.get_public_url(key),
            size=file_size,
            content_type=content_type or "application/octet-stream",
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
        bucket = await run_blocking_io(self._get_bucket)

        oss_stream = await run_blocking_io(lambda: bucket.get_object(key))
        return await self._read_stream_chunks(
            oss_stream,
            DOWNLOAD_COMPAT_CHUNK_SIZE,
            max_bytes=self.config.internal_max_upload_size,
        )

    async def get_size(self, key: str) -> int:
        bucket = await run_blocking_io(self._get_bucket)

        def _head():
            head = bucket.head_object(key)
            return head.content_length

        return await run_blocking_io(_head)

    async def download_range(self, key: str, start: int, end: int) -> bytes:
        bucket = await run_blocking_io(self._get_bucket)
        length = end - start + 1
        if length > self.config.internal_max_upload_size:
            max_mb = self.config.internal_max_upload_size / (1024 * 1024)
            raise ValueError(
                f"Range size ({length / (1024 * 1024):.1f}MB) exceeds "
                f"internal download limit ({max_mb:.0f}MB)"
            )

        oss_stream = await run_blocking_io(lambda: bucket.get_object(key, byte_range=(start, end)))
        return await self._read_stream_chunks(
            oss_stream,
            min(length, DOWNLOAD_COMPAT_CHUNK_SIZE),
            max_bytes=self.config.internal_max_upload_size,
        )

    async def _read_stream_chunks(self, oss_stream, chunk_size: int, *, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total_size = 0
        try:
            while True:
                chunk = await run_blocking_io(lambda: oss_stream.read(chunk_size))
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
            await run_blocking_io(oss_stream.close)

    async def download_stream(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """Stream download from OSS using chunked reads."""
        bucket = await run_blocking_io(self._get_bucket)
        oss_stream = await run_blocking_io(lambda: bucket.get_object(key))
        try:
            while True:
                chunk = await run_blocking_io(lambda: oss_stream.read(chunk_size))
                if not chunk:
                    break
                yield chunk
        finally:
            await run_blocking_io(oss_stream.close)

    async def download_range_stream(
        self, key: str, start: int, end: int, chunk_size: int = 256 * 1024
    ) -> AsyncIterator[bytes]:
        """Stream a byte range from OSS using chunked reads."""
        bucket = await run_blocking_io(self._get_bucket)
        oss_stream = await run_blocking_io(lambda: bucket.get_object(key, byte_range=(start, end)))
        try:
            while True:
                chunk = await run_blocking_io(lambda: oss_stream.read(chunk_size))
                if not chunk:
                    break
                yield chunk
        finally:
            await run_blocking_io(oss_stream.close)

    async def delete(self, key: str) -> bool:
        bucket = await run_blocking_io(self._get_bucket)

        def _delete_object():
            bucket.delete_object(key)
            return True

        return await run_blocking_io(_delete_object)

    async def exists(self, key: str) -> bool:
        bucket = await run_blocking_io(self._get_bucket)

        def _exists():
            return bucket.object_exists(key)

        return await run_blocking_io(_exists)

    async def get_url(self, key: str) -> str:
        return self.config.get_public_url(key)

    async def get_presigned_url(
        self, key: str, expires: int = 3600, process: str | None = None
    ) -> str:
        bucket = await run_blocking_io(self._get_bucket)

        def _get_url():
            params = {"response-content-disposition": "inline"}
            if process:
                # Signed server-side processing (image crop / video snapshot)
                params["x-oss-process"] = process
            return bucket.sign_url("GET", key, expires, params=params)

        return await run_blocking_io(_get_url)

    async def list_objects(self, prefix: str = "") -> list[str]:
        bucket = await run_blocking_io(self._get_bucket)

        def _list_objects():
            objects = []
            for obj in oss2.ObjectIterator(bucket, prefix=prefix):
                objects.append(obj.key)
                if len(objects) >= LIST_OBJECTS_LIMIT:
                    break
            return objects

        return await run_blocking_io(_list_objects)

    async def close(self) -> None:
        self._bucket = None
