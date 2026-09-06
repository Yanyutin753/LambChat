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
    # 服务端统一确认门拒绝（用户未批准上传，非文件系统错误）
    "declined_by_user",
    # 上传失败但无标准码可映射（中继/SDK/存储异常）——如实上报，不得
    # 兜底成 file_not_found 误导（2026-09-06 生产事故教训）
    "upload_failed",
    # 文件操作失败但无标准码可映射（I/O 异常等未知错误文本）
    "io_error",
]


def classify_upload_error(error_text: str) -> ExtendedFileError:
    """把沙箱上传失败的异常文本映射为真实错误码。

    兜底是 ``upload_failed`` 而非 file_not_found——2026-09-06 生产事故里
    win32 命令超长的上传失败被标成「文件不存在」，agent/用户全被带偏
    （transfer 报 file_not_found、read_file 却正常）。真 ENOENT 仍归
    file_not_found（先于 directory 判定，"No such file or directory" 含
    "directory" 子串）。
    """
    lowered = error_text.lower()
    if "no such file" in lowered or "not found" in lowered:
        return "file_not_found"
    if "permission" in lowered:
        return "permission_denied"
    if "is a directory" in lowered or "is a dir" in lowered or "eisdir" in lowered:
        return "is_directory"
    return "upload_failed"


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
    error: ExtendedFileError | str | None = None,
) -> FileDownloadResponse:
    """Create a download response with LambChat's extended sandbox error codes.

    error 除标准字面量外接受自由文本（deepagents 契约本身是
    ``FileOperationError | str | None``），供解码失败等无标准码可映射的
    场景携带原始信息而非误报。
    """
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
    "classify_upload_error",
    "file_download_response",
    "file_upload_response",
    "is_read_result",
    "read_result_to_string",
]
