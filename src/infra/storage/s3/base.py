"""
Abstract base class for S3 storage backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Optional, Protocol

from src.infra.async_utils import run_blocking_io
from src.infra.storage.s3.types import UploadResult

LIST_OBJECTS_LIMIT = 1000


class BinaryReadFile(Protocol):
    """Binary file-like object used as an upload source."""

    def read(self, size: int = -1, /) -> bytes: ...

    def seek(self, offset: int, whence: int = 0, /) -> int: ...

    def tell(self) -> int: ...


class BinaryWriteFile(Protocol):
    """Binary file-like object used as a download sink."""

    def write(self, data: bytes, /) -> object: ...

    def seek(self, offset: int, whence: int = 0, /) -> int: ...

    def tell(self) -> int: ...


class S3StorageBackend(ABC):
    """Abstract base class for S3 storage backends"""

    @abstractmethod
    async def upload(
        self,
        file: BinaryReadFile,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload a file"""
        pass

    @abstractmethod
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        """Upload bytes"""
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a file"""
        pass

    async def get_size(self, key: str) -> int:
        """Get file size in bytes. Override for efficient stat."""
        raise NotImplementedError("S3 backends must implement get_size without downloading bytes")

    async def download_range(self, key: str, start: int, end: int) -> bytes:
        """Download a byte range [start, end]. Override for efficient range reads."""
        raise NotImplementedError(
            "S3 backends must implement download_range without downloading full objects"
        )

    async def download_stream(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """Stream download a file in chunks. Override for memory-efficient streaming."""
        raise NotImplementedError(
            "S3 backends must implement download_stream without downloading full objects"
        )
        yield b""

    async def download_to_file(
        self,
        key: str,
        file: BinaryWriteFile,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> int:
        """Download an object into a file-like sink without returning full bytes."""
        total_size = 0
        async for chunk in self.download_stream(key, chunk_size=chunk_size):
            await run_blocking_io(file.write, chunk)
            total_size += len(chunk)
        await run_blocking_io(file.seek, 0)
        return total_size

    async def download_range_stream(
        self, key: str, start: int, end: int, chunk_size: int = 256 * 1024
    ) -> AsyncIterator[bytes]:
        """Stream a byte range in chunks. Override for memory-efficient range streaming."""
        data = await self.download_range(key, start, end)
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a file"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a file exists"""
        pass

    @abstractmethod
    async def get_url(self, key: str) -> str:
        """Get public URL for a file"""
        pass

    @abstractmethod
    async def get_presigned_url(
        self, key: str, expires: int = 3600, process: str | None = None
    ) -> str:
        """Get presigned URL for a file (for private buckets).

        `process` requests provider-side processing (e.g. OSS image crop)
        and is signed into the URL; backends without support may ignore it.
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
