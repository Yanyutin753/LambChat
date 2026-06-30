"""
Local filesystem storage backend.

Stores files on disk when S3 is not configured.
"""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional, cast

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.s3.base import (
    LIST_OBJECTS_LIMIT,
    BinaryReadFile,
    BinaryWriteFile,
    S3StorageBackend,
)
from src.infra.storage.s3.types import S3Config, UploadResult
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
UPLOAD_COPY_CHUNK_SIZE = 1024 * 1024


class LocalStorageBackend(S3StorageBackend):
    """Local filesystem storage backend"""

    def __init__(self, config: S3Config):
        self.config = config
        self._base_path = Path(config.storage_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorageBackend initialized at: {self._base_path}")

    def _get_file_path(self, key: str) -> Path:
        """Get the local file path for a given key, preventing path traversal."""
        target = (self._base_path / key).resolve()
        if not str(target).startswith(str(self._base_path)):
            raise ValueError(f"Invalid key: path traversal detected: {key}")
        return target

    async def upload(
        self,
        file: BinaryReadFile,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> UploadResult:
        file_path = self._get_file_path(key)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        def _write_stream() -> int:
            current_pos = file.tell()
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file, f, length=UPLOAD_COPY_CHUNK_SIZE)
            file_size = file.tell() - current_pos
            try:
                file.seek(current_pos)
            except (OSError, ValueError):
                pass
            return file_size

        file_size = await run_blocking_io(_write_stream)

        return UploadResult(
            key=key,
            url=f"/api/upload/file/{key}",
            size=file_size,
            content_type=content_type or "application/octet-stream",
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
        file_path = self._get_file_path(key)

        def _read():
            size = file_path.stat().st_size
            if size > self.config.internal_max_upload_size:
                max_mb = self.config.internal_max_upload_size / (1024 * 1024)
                raise ValueError(
                    f"File size ({size / (1024 * 1024):.1f}MB) exceeds "
                    f"internal download limit ({max_mb:.0f}MB)"
                )
            with open(file_path, "rb") as f:
                return f.read()

        try:
            return await run_blocking_io(_read)
        except FileNotFoundError:
            raise FileNotFoundError(f"Object {key} not found")

    async def download_to_file(
        self,
        key: str,
        file: BinaryWriteFile,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> int:
        file_path = self._get_file_path(key)

        def _copy() -> int:
            with open(file_path, "rb") as source:
                shutil.copyfileobj(source, file, length=chunk_size)
            size = file.tell()
            file.seek(0)
            return size

        try:
            return await run_blocking_io(_copy)
        except FileNotFoundError:
            raise FileNotFoundError(f"Object {key} not found")

    async def get_size(self, key: str) -> int:
        file_path = self._get_file_path(key)
        return await run_blocking_io(lambda: file_path.stat().st_size)

    async def download_range(self, key: str, start: int, end: int) -> bytes:
        file_path = self._get_file_path(key)
        length = end - start + 1
        if length <= 0:
            return b""
        if length > self.config.internal_max_upload_size:
            max_mb = self.config.internal_max_upload_size / (1024 * 1024)
            raise ValueError(
                f"Range size ({length / (1024 * 1024):.1f}MB) exceeds "
                f"internal download limit ({max_mb:.0f}MB)"
            )

        def _read_range() -> bytes:
            with open(file_path, "rb") as f:
                f.seek(max(0, start))
                return f.read(length)

        try:
            return await run_blocking_io(_read_range)
        except FileNotFoundError:
            raise FileNotFoundError(f"Object {key} not found")

    async def download_stream(
        self, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        file_path = self._get_file_path(key)
        chunk_size = max(1, int(chunk_size))
        try:
            source = await run_blocking_io(open, file_path, "rb")
        except FileNotFoundError:
            raise FileNotFoundError(f"Object {key} not found")

        try:
            while True:
                chunk = cast(bytes, await run_blocking_io(source.read, chunk_size))
                if not chunk:
                    break
                yield chunk
        finally:
            await run_blocking_io(source.close)

    async def delete(self, key: str) -> bool:
        file_path = self._get_file_path(key)

        def _delete():
            if file_path.exists():
                file_path.unlink()
                parent = file_path.parent
                while parent != self._base_path and parent.exists():
                    try:
                        parent.rmdir()
                        parent = parent.parent
                    except OSError:
                        break
                return True
            return False

        return await run_blocking_io(_delete)

    async def exists(self, key: str) -> bool:
        return await run_blocking_io(self._get_file_path(key).exists)

    async def get_url(self, key: str) -> str:
        return f"/api/upload/file/{key}"

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        _ = expires
        return f"/api/upload/file/{key}"

    async def list_objects(self, prefix: str = "") -> list[str]:
        prefix_path = self._base_path / prefix

        def _list():
            if not prefix_path.exists():
                return []
            objects = []
            for root, _dirs, files in os.walk(prefix_path):
                for fname in sorted(files):
                    full_path = Path(root) / fname
                    rel = full_path.relative_to(self._base_path)
                    objects.append(rel.as_posix())
                    if len(objects) >= LIST_OBJECTS_LIMIT:
                        return objects
            return objects

        return await run_blocking_io(_list)

    async def close(self) -> None:
        pass
