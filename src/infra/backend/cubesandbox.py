"""CubeSandbox backend adapter for deepagents sandbox protocol."""

from __future__ import annotations

import base64
import os
import shlex
from typing import Any, cast

from src.infra.backend.e2b import (
    SANDBOX_BATCH_FILES_LIMIT,
    SANDBOX_DOWNLOAD_MAX_BYTES,
    SANDBOX_READ_MAX_BYTES,
    SANDBOX_UPLOAD_MAX_BYTES,
    E2BBackend,
    _slice_text_content,
    _slice_text_read,
)
from src.infra.backend.protocol_compat import (
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    LsResult,
    ReadResult,
    WriteResult,
    file_download_response,
    is_read_result,
)
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)
_DEFAULT_TIMEOUT = 30 * 60


class CubeSandboxBackend(E2BBackend):
    """Backend wrapper for the native CubeSandbox Python SDK.

    CubeSandbox intentionally exposes an E2B-like ``commands`` and ``files`` API,
    so LambChat can reuse the mature command, file, glob, upload, and download
    behavior from ``E2BBackend`` while keeping lifecycle/configuration native.
    """

    def __init__(
        self,
        sandbox,
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
        work_dir: str | None = None,
    ):
        super().__init__(
            sandbox=sandbox,
            timeout=timeout
            or settings.CUBE_TIMEOUT
            or int(os.environ.get("CUBE_TIMEOUT", _DEFAULT_TIMEOUT)),
            env_vars=env_vars,
            work_dir=work_dir,
        )
        self._ensured_parent_dirs: set[str] = set()

    def get_info(self) -> dict[str, Any]:
        try:
            info = self._sandbox.get_info()
            if isinstance(info, dict):
                return {
                    "sandbox_id": info.get("sandboxID") or info.get("sandbox_id") or self.id,
                    "state": str(info.get("state", "unknown")).lower(),
                    "template": info.get("templateID") or info.get("template_id"),
                    "metadata": info.get("metadata") or {},
                    "started_at": info.get("startedAt") or info.get("started_at"),
                    "end_at": info.get("endAt") or info.get("end_at"),
                }
            return super().get_info()
        except Exception as e:
            logger.warning("Failed to get CubeSandbox info: %s", e)
            return {"sandbox_id": self.id, "state": "unknown"}

    def pause(self) -> None:
        self._sandbox.pause()
        logger.info("[CubeSandbox] Paused sandbox %s", self.id)

    def _ensure_parent_dir(self, file_path: str) -> None:
        file_path = self._resolve_path(file_path)
        parent = os.path.dirname(file_path)
        if not parent or parent in self._ensured_parent_dirs:
            return
        self.execute(f"mkdir -p {shlex.quote(parent)}")
        self._ensured_parent_dirs.add(parent)

    def ls_info(self, path: str) -> list[FileInfo]:
        path = self._resolve_path(path)
        quoted = shlex.quote(path)
        command = (
            "python3 -c "
            + shlex.quote(
                "import json, os, sys\n"
                "path = sys.argv[1]\n"
                "items = []\n"
                "for name in sorted(os.listdir(path)):\n"
                "    full = os.path.join(path, name)\n"
                "    try:\n"
                "        st = os.lstat(full)\n"
                "    except OSError:\n"
                "        continue\n"
                "    item = {'path': full, 'size': st.st_size}\n"
                "    if os.path.isdir(full):\n"
                "        item['is_dir'] = True\n"
                "    items.append(item)\n"
                "print(json.dumps(items))\n"
            )
            + f" {quoted}"
        )
        result = self.execute(command)
        if result.exit_code != 0:
            return []
        try:
            import json

            return json.loads(result.output or "[]")
        except Exception as e:
            logger.warning("Failed to parse CubeSandbox ls output for %s: %s", path, e)
            return []

    async def als_info(self, path: str) -> list[FileInfo]:
        from src.infra.async_utils import run_blocking_io

        return await run_blocking_io(self.ls_info, path)

    def ls(self, path: str) -> LsResult:
        return LsResult(entries=self.ls_info(path))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:  # type: ignore[override]
        file_path = self._resolve_path(file_path)
        try:
            size = self._file_size(file_path)
            if size is not None and size > SANDBOX_READ_MAX_BYTES:
                return ReadResult(
                    error=(
                        f"file too large to read directly: {size} bytes "
                        f"(limit {SANDBOX_READ_MAX_BYTES} bytes)"
                    )
                )
            content = self._sandbox.files.read(file_path)
            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8")
                except UnicodeDecodeError:
                    data_uri = (
                        "data:application/octet-stream;base64,"
                        + base64.standard_b64encode(content).decode()
                    )
                    return ReadResult(
                        file_data={"content": data_uri, "encoding": "data_uri"},
                        rendered_content=data_uri,
                    )
            sliced_content = _slice_text_content(str(content), offset, limit)
            if is_read_result(sliced_content):
                return sliced_content  # type: ignore[return-value]
            rendered = _slice_text_read(str(content), offset, limit)
            if is_read_result(rendered):
                return rendered  # type: ignore[return-value]
            text_content = cast(str, sliced_content)
            rendered_content = cast(str, rendered)
            return ReadResult(
                file_data={"content": text_content, "encoding": "utf-8"},
                rendered_content=rendered_content,
            )
        except Exception as e:
            logger.warning("CubeSandbox files.read(%s) failed: %s", file_path, e)
            return ReadResult(error=str(e))

    def write(self, file_path: str, content: str) -> WriteResult:
        file_path = self._resolve_path(file_path)
        try:
            self._ensure_parent_dir(file_path)
            self._sandbox.files.write(file_path, content)
            return WriteResult(path=file_path)
        except Exception as e:
            logger.error("CubeSandbox files.write(%s) failed: %s", file_path, e)
            return WriteResult(path=file_path, error="file_not_found")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        if len(files) > SANDBOX_BATCH_FILES_LIMIT:
            return [FileUploadResponse(path=path, error="too_many_files") for path, _ in files]

        responses: list[FileUploadResponse] = []
        for path, content in files:
            path = self._resolve_path(path)
            if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                responses.append(FileUploadResponse(path=path, error="file_too_large"))
                continue
            try:
                self._ensure_parent_dir(path)
                self._sandbox.files.write(path, content)
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                logger.error("CubeSandbox upload %s failed: %s", path, e)
                responses.append(FileUploadResponse(path=path, error="file_not_found"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        if len(paths) > SANDBOX_BATCH_FILES_LIMIT:
            return [
                file_download_response(path=path, content=None, error="too_many_files")
                for path in paths
            ]

        responses: list[FileDownloadResponse] = []
        for path in paths:
            path = self._resolve_path(path)
            try:
                size = self._file_size(path)
                if size is not None and size > SANDBOX_DOWNLOAD_MAX_BYTES:
                    responses.append(
                        file_download_response(path=path, content=None, error="file_not_found")
                    )
                    continue
                raw_content = self._sandbox.files.read(path)
                content_bytes = (
                    raw_content.encode("utf-8")
                    if isinstance(raw_content, str)
                    else bytes(raw_content)
                )
                responses.append(file_download_response(path=path, content=content_bytes))
            except Exception as e:
                logger.error("CubeSandbox download %s failed: %s", path, e)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
        return responses

    def _file_size(self, path: str) -> int | None:
        command = f"stat -c %s {shlex.quote(path)} 2>/dev/null"
        result = self.execute(command, timeout=5)
        if result.exit_code != 0:
            return None
        try:
            return int((result.output or "").strip())
        except ValueError:
            return None
