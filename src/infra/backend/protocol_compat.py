from __future__ import annotations

from typing import Any, Literal, TypeGuard, cast

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)


def is_read_result(value: object) -> TypeGuard[ReadResult]:
    """Return whether *value* is a deepagents v0.7 read result."""
    return isinstance(value, ReadResult)


def read_result_to_string(value: object) -> str:
    """Return raw text or a normalized error from a v0.7 read result."""
    if not is_read_result(value):
        return str(value)

    error = value.error
    if error:
        return error if error.startswith("Error:") else f"Error: {error}"

    if value.file_data is None:
        return ""
    return str(value.file_data["content"])


ExtendedFileError = Literal[
    "file_not_found",
    "permission_denied",
    "is_directory",
    "invalid_path",
    "too_many_files",
    "file_too_large",
]


def file_upload_response(
    *,
    path: str,
    error: ExtendedFileError | None = None,
) -> FileUploadResponse:
    """Create an upload response with LambChat's extended sandbox error codes."""
    return FileUploadResponse(path=path, error=cast(Any, error))


def file_download_response(
    *,
    path: str,
    content: bytes | None = None,
    error: ExtendedFileError | None = None,
) -> FileDownloadResponse:
    """Create a download response with LambChat's extended sandbox error codes."""
    return FileDownloadResponse(path=path, content=content, error=cast(Any, error))


__all__ = [
    "BackendProtocol",
    "DeleteResult",
    "EditResult",
    "ExecuteResponse",
    "ExtendedFileError",
    "FileData",
    "FileDownloadResponse",
    "FileInfo",
    "FileUploadResponse",
    "GlobResult",
    "GrepMatch",
    "GrepResult",
    "LsResult",
    "ReadResult",
    "WriteResult",
    "file_download_response",
    "file_upload_response",
    "is_read_result",
    "read_result_to_string",
]
