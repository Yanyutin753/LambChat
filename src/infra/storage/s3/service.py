"""
S3 Storage Service - high-level interface for storage operations.

Supports multiple providers through configuration, with automatic backend selection.
Includes retry mechanism for transient upload failures.
"""

from __future__ import annotations

import asyncio
import random
import re
import uuid
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import BinaryIO, Callable, Optional, TypeVar

from src.infra.logging import get_logger
from src.infra.storage.s3.backends import (
    AliyunOssBackend,
    LocalStorageBackend,
    MinioS3Backend,
)
from src.infra.storage.s3.base import S3StorageBackend
from src.infra.storage.s3.types import S3Config, S3Provider, UploadResult

logger = get_logger(__name__)

T = TypeVar("T")

# Retry configuration
UPLOAD_MAX_RETRIES = 3
UPLOAD_RETRY_BACKOFF_BASE = 2  # seconds, exponential backoff base
UPLOAD_RETRY_BACKOFF_JITTER = 1  # seconds, random jitter


class S3StorageService:
    """
    S3 Storage Service

    Provides a high-level interface for S3-compatible storage operations.
    Supports multiple providers through configuration.
    """

    _instance: Optional["S3StorageService"] = None

    def __init__(self, config: Optional[S3Config] = None):
        self._backend: Optional[S3StorageBackend] = None
        if config:
            self._config = config
        else:
            self._config = S3Config()

    @classmethod
    def get_instance(cls) -> "S3StorageService":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def configure(self, config: S3Config) -> None:
        """Configure the storage service"""
        self._config = config
        self._backend = None

    @property
    def is_local(self) -> bool:
        """Whether the storage backend is local filesystem."""
        return self._config.provider == S3Provider.LOCAL

    @staticmethod
    async def _retry_async(
        func: Callable[..., "Awaitable[T]"],
        max_retries: int = UPLOAD_MAX_RETRIES,
        label: str = "operation",
    ) -> T:
        """
        Execute an async function with exponential backoff retry on transient errors.

        Retries on network/timeout errors; does NOT retry on validation errors.
        """
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return await func()
            except (ConnectionError, TimeoutError, OSError) as e:
                last_exc = e
                if attempt < max_retries:
                    backoff = UPLOAD_RETRY_BACKOFF_BASE**attempt + random.uniform(
                        0, UPLOAD_RETRY_BACKOFF_JITTER
                    )
                    logger.warning(
                        f"Upload {label} failed (attempt {attempt}/{max_retries}), "
                        f"retrying in {backoff:.1f}s: {e}"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Upload {label} failed after {max_retries} attempts: {e}")
            except Exception as e:
                # Non-transient errors (e.g. auth, validation) — raise immediately
                if "oss2" in type(e).__module__ or "minio" in type(e).__module__:
                    # Check if it's a server/network error from the SDK
                    err_lower = str(e).lower()
                    if any(
                        kw in err_lower
                        for kw in (
                            "connection",
                            "timeout",
                            "timed out",
                            "network",
                            "temporary",
                            "service unavailable",
                            "internal server error",
                            "503",
                            "500",
                            "502",
                        )
                    ):
                        last_exc = e
                        if attempt < max_retries:
                            backoff = UPLOAD_RETRY_BACKOFF_BASE**attempt + random.uniform(
                                0, UPLOAD_RETRY_BACKOFF_JITTER
                            )
                            logger.warning(
                                f"Upload {label} failed (attempt {attempt}/{max_retries}), "
                                f"retrying in {backoff:.1f}s: {e}"
                            )
                            await asyncio.sleep(backoff)
                            continue
                        logger.error(f"Upload {label} failed after {max_retries} attempts: {e}")
                raise

        raise last_exc  # type: ignore[misc]

    def _get_backend(self) -> S3StorageBackend:
        """Get or create the storage backend"""
        if self._backend is None:
            if self._config.provider == S3Provider.LOCAL:
                self._backend = LocalStorageBackend(self._config)
            elif self._config.provider == S3Provider.ALIYUN:
                try:
                    if AliyunOssBackend is None:
                        raise ImportError
                    self._backend = AliyunOssBackend(self._config)
                except ImportError:
                    logger.warning(
                        "Aliyun OSS SDK not available, falling back to minio "
                        "(may have compatibility issues)"
                    )
                    self._backend = MinioS3Backend(self._config)
            else:
                self._backend = MinioS3Backend(self._config)

        return self._backend

    async def upload_file(
        self,
        file: BinaryIO,
        folder: str,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        *,
        skip_size_limit: bool = False,
    ) -> UploadResult:
        """Upload a file to storage with retry on transient failures."""
        # Check file size via current position
        if not skip_size_limit:
            current_pos = file.tell()
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(current_pos)
            if file_size > self._config.internal_max_upload_size:
                max_mb = self._config.internal_max_upload_size / (1024 * 1024)
                raise ValueError(
                    f"File size ({file_size / (1024 * 1024):.1f}MB) exceeds "
                    f"internal upload limit ({max_mb:.0f}MB)"
                )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = self._sanitize_filename(filename)
        unique_suffix = uuid.uuid4().hex[:8]
        key = f"{folder}/{timestamp}_{unique_suffix}_{safe_filename}"

        backend = self._get_backend()
        return await self._retry_async(
            lambda: backend.upload(file, key, content_type, metadata),
            label=f"file://{key}",
        )

    async def upload_bytes(
        self,
        data: bytes,
        folder: str,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        *,
        skip_size_limit: bool = False,
    ) -> UploadResult:
        """Upload bytes to storage with retry on transient failures."""
        if not skip_size_limit and len(data) > self._config.internal_max_upload_size:
            max_mb = self._config.internal_max_upload_size / (1024 * 1024)
            raise ValueError(
                f"Data size ({len(data) / (1024 * 1024):.1f}MB) exceeds "
                f"internal upload limit ({max_mb:.0f}MB)"
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = self._sanitize_filename(filename)
        unique_suffix = uuid.uuid4().hex[:8]
        key = f"{folder}/{timestamp}_{unique_suffix}_{safe_filename}"

        return await self.upload_to_key(data, key, content_type, metadata, skip_size_limit=True)

    async def upload_to_key(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        *,
        skip_size_limit: bool = False,
    ) -> UploadResult:
        """Upload bytes to a specific key (caller controls the full key)."""
        if not skip_size_limit and len(data) > self._config.internal_max_upload_size:
            max_mb = self._config.internal_max_upload_size / (1024 * 1024)
            raise ValueError(
                f"Data size ({len(data) / (1024 * 1024):.1f}MB) exceeds "
                f"internal upload limit ({max_mb:.0f}MB)"
            )

        backend = self._get_backend()
        result = await self._retry_async(
            lambda: backend.upload_bytes(data, key, content_type, metadata),
            label=f"bytes://{key}",
        )

        if not self._config.public_bucket and "?" not in result.url:
            max_expires = 7 * 24 * 3600
            expires = min(self._config.presigned_url_expires, max_expires)
            result.url = await self._retry_async(
                lambda: backend.get_presigned_url(key, expires),
                label=f"presign://{key}",
            )

        return result

    async def upload_avatar(self, user_id: str, data: bytes, filename: str) -> UploadResult:
        """Upload user avatar"""
        return await self.upload_bytes(
            data=data,
            folder=f"avatars/{user_id}",
            filename=filename,
            content_type=self._get_image_content_type(filename),
        )

    async def delete_user_files(self, user_id: str) -> int:
        """Delete all files for a user. Returns number of files deleted."""
        deleted_count = 0
        backend = self._get_backend()

        if hasattr(backend, "_client"):
            try:
                client = backend._client
                bucket = self._config.bucket_name

                avatar_objects = await self.list_files(f"avatars/{user_id}")
                if avatar_objects:
                    loop = asyncio.get_running_loop()

                    def _remove_avatar_objects():
                        for key in avatar_objects:
                            client.remove_object(bucket_name=bucket, object_name=key)

                    await loop.run_in_executor(None, _remove_avatar_objects)
                    deleted_count += len(avatar_objects)

                user_objects = await self.list_files(user_id)
                if user_objects:
                    loop = asyncio.get_running_loop()

                    def _remove_user_objects():
                        for key in user_objects:
                            client.remove_object(bucket_name=bucket, object_name=key)

                    await loop.run_in_executor(None, _remove_user_objects)
                    deleted_count += len(user_objects)

                return deleted_count
            except Exception as e:
                logger.warning(f"Batch delete failed, falling back to individual deletes: {e}")

        # Fallback: individual deletes
        avatar_objects = await self.list_files(f"avatars/{user_id}")
        for key in avatar_objects:
            await self.delete_file(key)
            deleted_count += 1

        user_objects = await self.list_files(user_id)
        for key in user_objects:
            await self.delete_file(key)
            deleted_count += 1

        return deleted_count

    async def delete_file(self, key: str) -> bool:
        """Delete a file"""
        return await self._get_backend().delete(key)

    async def file_exists(self, key: str) -> bool:
        """Check if a file exists"""
        return await self._get_backend().exists(key)

    def get_file_path(self, key: str):
        """Get local filesystem path for a key (local backend only)."""
        backend = self._get_backend()
        if not isinstance(backend, LocalStorageBackend):
            raise RuntimeError("get_file_path is only available for local storage")
        return backend._get_file_path(key)

    async def get_file_url(self, key: str) -> str:
        """Get public URL for a file"""
        return await self._get_backend().get_url(key)

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Get presigned URL for a file (for private buckets)"""
        return await self._get_backend().get_presigned_url(key, expires)

    async def list_files(self, folder: str) -> list[str]:
        """List files in a folder"""
        return await self._get_backend().list_objects(prefix=folder)

    async def close(self) -> None:
        """Close the storage service"""
        if self._backend:
            await self._backend.close()
            self._backend = None

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        safe = re.sub(r"[^\w\-_\.]", "_", filename)
        if len(safe) > 200:
            name, ext = safe.rsplit(".", 1) if "." in safe else (safe, "")
            safe = name[: 200 - len(ext) - 1] + "." + ext if ext else name[:200]
        return safe

    def _get_image_content_type(self, filename: str) -> str:
        """Get content type for image files"""
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        content_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
            "bmp": "image/bmp",
            "ico": "image/x-icon",
        }
        return content_types.get(ext, "application/octet-stream")

    def validate_file(
        self,
        filename: str,
        file_size: int,
        allowed_extensions: Optional[list[str]] = None,
    ) -> tuple[bool, str]:
        """Validate file before upload. Returns (is_valid, error_message)."""
        if file_size > self._config.max_file_size:
            max_mb = self._config.max_file_size / (1024 * 1024)
            return False, f"File size exceeds maximum of {max_mb:.1f}MB"

        ext = filename.lower().split(".")[-1] if "." in filename else ""
        extensions = allowed_extensions or self._config.allowed_extensions
        if ext not in extensions:
            return False, f"File type '.{ext}' is not allowed"

        return True, ""


# Global storage service instance
_storage_service: Optional[S3StorageService] = None


def get_storage_service() -> S3StorageService:
    """Get the global storage service instance"""
    global _storage_service
    if _storage_service is None:
        _storage_service = S3StorageService.get_instance()
    return _storage_service


async def init_storage(config: S3Config) -> None:
    """Initialize storage service with configuration"""
    global _storage_service
    _storage_service = S3StorageService(config)


async def close_storage() -> None:
    """Close storage service"""
    global _storage_service
    if _storage_service:
        await _storage_service.close()
