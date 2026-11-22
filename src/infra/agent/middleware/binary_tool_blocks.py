"""File types, size estimates and redaction for binary tool results."""

import base64
from typing import Any

_BASE64_DECODE_CHUNK_CHARS = 4 * 1024 * 1024

# Binary file extensions — read_file should upload these to S3 instead of returning garbled text
_BINARY_EXTENSIONS = frozenset(
    (
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".ico",
        ".svg",
        ".avif",
        ".tiff",
        ".tif",
        # Videos
        ".mp4",
        ".webm",
        ".mov",
        ".avi",
        ".wmv",
        ".mkv",
        ".ogv",
        # Audio
        ".mp3",
        ".wav",
        ".ogg",
        ".aac",
        ".flac",
        ".m4a",
        ".opus",
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    )
)


def _redact_failed_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_failed"
    return redacted


def _redact_oversized_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_too_large"
    return redacted


def _redact_excess_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_too_many_blocks"
    return redacted


def _estimated_base64_decoded_size(b64_data: str) -> int:
    stripped = b64_data.rstrip("=")
    return (len(stripped) * 3) // 4


def _decode_base64_to_file(b64_data: str, file, *, max_bytes: int) -> int:
    total = 0
    carry = ""
    for start in range(0, len(b64_data), _BASE64_DECODE_CHUNK_CHARS):
        chunk = carry + b64_data[start : start + _BASE64_DECODE_CHUNK_CHARS]
        decode_len = (len(chunk) // 4) * 4
        if decode_len == 0:
            carry = chunk
            continue
        decoded = base64.b64decode(chunk[:decode_len])
        file.write(decoded)
        total += len(decoded)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")
        carry = chunk[decode_len:]
    if carry:
        decoded = base64.b64decode(carry)
        file.write(decoded)
        total += len(decoded)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")
    file.seek(0)
    return total


def _write_bytes_to_file(data: bytes, file) -> int:
    file.write(data)
    size = len(data)
    file.seek(0)
    return size
