"""
S3-compatible storage service

Supports multiple S3-compatible providers:
- AWS S3
- Alibaba Cloud OSS
- Tencent Cloud COS
- MinIO
- Any S3-compatible storage
"""

from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, BinaryIO, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import minio

# Log configuration for debugging
logger = logging.getLogger(__name__)


class S3Provider(str, Enum):
    """S3-compatible storage providers"""

    AWS = "aws"
    ALIYUN = "aliyun"  # Alibaba Cloud OSS
    TENCENT = "tencent"  # Tencent Cloud COS
    MINIO = "minio"
    CUSTOM = "custom"


class S3Config(BaseModel):
    """S3 storage configuration"""

    provider: S3Provider = S3Provider.AWS
    endpoint_url: Optional[str] = None  # Required for non-AWS providers
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    bucket_name: str = ""
    # URL configuration
    custom_domain: Optional[str] = None  # Custom CDN domain
    path_style: bool = False  # Use path-style URLs (required for MinIO)
    public_bucket: bool = (
        False  # Whether bucket is publicly readable (if False, use presigned URLs)
    )
    # Upload settings
    max_file_size: int = 10 * 1024 * 1024  # 10MB default
    # URL expiration for presigned URLs (in seconds)
    presigned_url_expires: int = 7 * 24 * 3600  # 7 days default
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            # Images
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp",
            "svg",
            "bmp",
            "ico",
            # Documents
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "txt",
            "md",
            # Archives
            "zip",
            "tar",
            "gz",
            # Code
            "json",
            "yaml",
            "yml",
            "xml",
            "csv",
        ]
    )

    def get_endpoint_url(self) -> Optional[str]:
        """Get endpoint URL based on provider"""
        if self.endpoint_url:
            return self.endpoint_url

        if self.provider == S3Provider.AWS:
            return None  # boto3 will use default AWS endpoints
        elif self.provider == S3Provider.ALIYUN:
            return f"https://oss-{self.region}.aliyuncs.com"
        elif self.provider == S3Provider.TENCENT:
            return f"https://cos.{self.region}.myqcloud.com"
        elif self.provider == S3Provider.MINIO:
            # MinIO requires endpoint_url
            return self.endpoint_url

        return self.endpoint_url

    def get_public_url(self, key: str) -> str:
        """Generate public URL for an object"""
        if self.custom_domain:
            return f"https://{self.custom_domain}/{key}"

        if self.path_style or self.provider == S3Provider.MINIO:
            endpoint = self.get_endpoint_url() or f"https://s3.{self.region}.amazonaws.com"
            return f"{endpoint}/{self.bucket_name}/{key}"
        else:
            # Virtual-hosted style
            if self.provider == S3Provider.ALIYUN:
                return f"https://{self.bucket_name}.oss-{self.region}.aliyuncs.com/{key}"
            elif self.provider == S3Provider.TENCENT:
                return f"https://{self.bucket_name}.cos.{self.region}.myqcloud.com/{key}"
            else:
                return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"


class UploadResult(BaseModel):
    """Result of a file upload"""

    key: str  # Object key in bucket
    url: str  # Public URL
    size: int  # File size in bytes
    content_type: str
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None


class S3StorageBackend(ABC):
    """Abstract base class for S3 storage backends"""

    @abstractmethod
    async def upload(
        self,
        file: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload a file to S3"""
        pass

    @abstractmethod
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload bytes to S3"""
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a file from S3"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a file from S3"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a file exists in S3"""
        pass

    @abstractmethod
    async def get_url(self, key: str) -> str:
        """Get public URL for a file"""
        pass

    @abstractmethod
    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Get presigned URL for a file (for private buckets)

        Args:
            key: Object key
            expires: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL that can be used to access the file
        """
        pass

    @abstractmethod
    async def list_objects(self, prefix: str = "") -> list[str]:
        """List objects with given prefix"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the backend connection"""
        pass


class MinioS3Backend(S3StorageBackend):
    """S3 storage backend using minio library - better compatibility with S3-compatible providers"""

    def __init__(self, config: S3Config):
        self.config = config
        self._client: minio.Minio | None = None
        self._loop = None

    def _get_client(self):
        """Get or create minio S3 client"""
        if self._client is None:
            import minio

            endpoint: str = self.config.endpoint_url or self.config.get_endpoint_url()
            if endpoint:
                # Remove protocol if present
                endpoint = endpoint.replace("https://", "").replace("http://", "")
            else:
                endpoint = "localhost:9000"  # Default MinIO endpoint

            logger.info(
                f"Minio client config: endpoint={endpoint}, bucket={self.config.bucket_name}, region={self.config.region}, access_key length={len(self.config.access_key)}"
            )

            # For Aliyun OSS, we need to set the region to avoid location query
            # and use virtual-hosted style automatically
            self._client = minio.Minio(
                endpoint=endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=True,  # Use HTTPS
                region=self.config.region if self.config.provider != S3Provider.AWS else None,
            )

        return self._client

    async def upload(
        self,
        file: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload a file to S3"""
        import mimetypes

        # Guess content type if not provided
        if not content_type:
            content_type, _ = mimetypes.guess_type(key)
            if not content_type:
                content_type = "application/octet-stream"

        # Read file content
        content = file.read()
        file_size = len(content)
        file.seek(0)

        # Run blocking minio call in thread pool
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _put_object():
            from io import BytesIO

            data = BytesIO(content)
            result = client.put_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
                data=data,
                length=file_size,
                content_type=content_type,
                metadata=metadata or {},
            )
            return result

        result = await loop.run_in_executor(None, _put_object)

        # Always return public URL - service layer will generate presigned URL if needed
        file_url = self.config.get_public_url(key)

        return UploadResult(
            key=key,
            url=file_url,
            size=file_size,
            content_type=content_type,
            etag=result.etag,
            last_modified=datetime.now(timezone.utc),
        )

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload bytes to S3"""
        file_obj = io.BytesIO(data)
        return await self.upload(file_obj, key, content_type, metadata)

    async def download(self, key: str) -> bytes:
        """Download a file from S3"""
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _get_object():
            response = client.get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
            return response.read()

        return await loop.run_in_executor(None, _get_object)

    async def delete(self, key: str) -> bool:
        """Delete a file from S3"""
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _delete_object():
            client.remove_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
            )
            return True

        return await loop.run_in_executor(None, _delete_object)

    async def exists(self, key: str) -> bool:
        """Check if a file exists in S3"""
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _stat_object():
            try:
                client.stat_object(
                    bucket_name=self.config.bucket_name,
                    object_name=key,
                )
                return True
            except Exception:
                return False

        return await loop.run_in_executor(None, _stat_object)

    async def get_url(self, key: str) -> str:
        """Get public URL for a file"""
        return self.config.get_public_url(key)

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Get presigned URL for a file (for private buckets)

        Args:
            key: Object key
            expires: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL that can be used to access the file
        """
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _presigned_url():
            from datetime import timedelta

            return client.presigned_get_object(
                bucket_name=self.config.bucket_name,
                object_name=key,
                expires=timedelta(seconds=expires),
            )

        return await loop.run_in_executor(None, _presigned_url)

    async def list_objects(self, prefix: str = "") -> list[str]:
        """List objects with given prefix"""
        import asyncio

        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _list_objects():
            objects = []
            for obj in client.list_objects(
                bucket_name=self.config.bucket_name,
                prefix=prefix,
                recursive=True,
            ):
                objects.append(obj.object_name)
            return objects

        return await loop.run_in_executor(None, _list_objects)

    async def close(self) -> None:
        """Close the backend connection"""
        self._client = None


class MockS3Backend(S3StorageBackend):
    """Mock S3 backend for testing/development"""

    def __init__(self, config: S3Config):
        self.config = config
        self._objects: dict[str, bytes] = {}

    def _get_mock_url(self, key: str) -> str:
        """Generate mock URL, handling empty bucket_name"""
        if self.config.bucket_name:
            return f"mock://storage/{self.config.bucket_name}/{key}"
        return f"mock://storage/{key}"

    async def upload(
        self,
        file: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        content = file.read()
        self._objects[key] = content
        return UploadResult(
            key=key,
            url=self._get_mock_url(key),
            size=len(content),
            content_type=content_type or "application/octet-stream",
            last_modified=datetime.now(timezone.utc),
        )

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        self._objects[key] = data
        return UploadResult(
            key=key,
            url=self._get_mock_url(key),
            size=len(data),
            content_type=content_type or "application/octet-stream",
            last_modified=datetime.now(timezone.utc),
        )

    async def download(self, key: str) -> bytes:
        if key not in self._objects:
            raise FileNotFoundError(f"Object {key} not found")
        return self._objects[key]

    async def delete(self, key: str) -> bool:
        if key in self._objects:
            del self._objects[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def get_url(self, key: str) -> str:
        return self._get_mock_url(key)

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Get presigned URL for mock storage (just returns regular URL)"""
        _ = expires  # Unused in mock
        return self._get_mock_url(key)

    async def list_objects(self, prefix: str = "") -> list[str]:
        return [k for k in self._objects.keys() if k.startswith(prefix)]

    async def close(self) -> None:
        self._objects.clear()


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
        # Reset backend to use new config
        self._backend = None

    def _get_backend(self) -> S3StorageBackend:
        """Get or create the storage backend"""
        if self._backend is None:
            # Try minio library first (better S3-compatible support)
            try:
                import minio  # noqa: F401

                self._backend = MinioS3Backend(self._config)
            except ImportError:
                # Fall back to mock backend
                self._backend = MockS3Backend(self._config)

        return self._backend

    async def upload_file(
        self,
        file: BinaryIO,
        folder: str,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """
        Upload a file to S3

        Args:
            file: File-like object to upload
            folder: Folder path (e.g., "avatars", "documents")
            filename: Original filename
            content_type: MIME type
            metadata: Optional metadata

        Returns:
            UploadResult with key and URL
        """
        # Generate unique key with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        key = f"{folder}/{timestamp}_{safe_filename}"

        backend = self._get_backend()
        return await backend.upload(file, key, content_type, metadata)

    async def upload_bytes(
        self,
        data: bytes,
        folder: str,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload bytes to S3"""
        # Generate unique key with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = self._sanitize_filename(filename)
        key = f"{folder}/{timestamp}_{safe_filename}"

        backend = self._get_backend()
        result = await backend.upload_bytes(data, key, content_type, metadata)

        # If bucket is private and no presigned URL was generated by backend,
        # generate one with appropriate expiration
        if not self._config.public_bucket and "?" not in result.url:
            # MinIO/S3 presigned URL max expiration is 7 days (604800 seconds)
            # Use configured value capped at 7 days
            max_expires = 7 * 24 * 3600  # 7 days in seconds
            expires = min(self._config.presigned_url_expires, max_expires)
            result.url = await backend.get_presigned_url(key, expires)

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
        """
        Delete all files for a user

        Args:
            user_id: User ID

        Returns:
            Number of files deleted
        """
        deleted_count = 0

        # Get backend client for batch operations
        backend = self._get_backend()

        # Check if backend supports batch delete (MinioS3Backend)
        if hasattr(backend, "_client"):
            try:
                import asyncio

                client = backend._client
                bucket = self._config.bucket_name

                # Delete avatar folder objects
                avatar_objects = await self.list_files(f"avatars/{user_id}")
                if avatar_objects:
                    loop = asyncio.get_event_loop()

                    def _remove_avatar_objects():
                        for key in avatar_objects:
                            client.remove_object(bucket_name=bucket, object_name=key)

                    await loop.run_in_executor(None, _remove_avatar_objects)
                    deleted_count += len(avatar_objects)

                # Delete user's general upload folder
                user_objects = await self.list_files(user_id)
                if user_objects:
                    loop = asyncio.get_event_loop()

                    def _remove_user_objects():
                        for key in user_objects:
                            client.remove_object(bucket_name=bucket, object_name=key)

                    await loop.run_in_executor(None, _remove_user_objects)
                    deleted_count += len(user_objects)

                return deleted_count
            except Exception:
                # Fall back to individual deletes if batch fails
                pass

        # Fallback: individual deletes (slower)
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
        """Delete a file from S3"""
        backend = self._get_backend()
        return await backend.delete(key)

    async def file_exists(self, key: str) -> bool:
        """Check if a file exists"""
        backend = self._get_backend()
        return await backend.exists(key)

    async def get_file_url(self, key: str) -> str:
        """Get public URL for a file"""
        backend = self._get_backend()
        return await backend.get_url(key)

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        """Get presigned URL for a file (for private buckets)

        Args:
            key: Object key
            expires: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL that can be used to access the file
        """
        backend = self._get_backend()
        return await backend.get_presigned_url(key, expires)

    async def list_files(self, folder: str) -> list[str]:
        """List files in a folder"""
        backend = self._get_backend()
        return await backend.list_objects(prefix=folder)

    async def close(self) -> None:
        """Close the storage service"""
        if self._backend:
            await self._backend.close()
            self._backend = None

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        import re

        # Remove path separators and unsafe characters
        safe = re.sub(r"[^\w\-_\.]", "_", filename)
        # Limit length
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
        """
        Validate file before upload

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file size
        if file_size > self._config.max_file_size:
            max_mb = self._config.max_file_size / (1024 * 1024)
            return False, f"File size exceeds maximum of {max_mb:.1f}MB"

        # Check extension
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
