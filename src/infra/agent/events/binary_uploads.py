"""Upload binary MCP result blocks and replace inline base64 with URLs."""

import base64
import mimetypes
import uuid
from tempfile import SpooledTemporaryFile

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger

logger = get_logger(__name__)

_SPOOL_MAX_MEMORY_BYTES = 2 * 1024 * 1024
_BINARY_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
_BINARY_UPLOAD_TOTAL_MAX_BYTES = 50 * 1024 * 1024
_BINARY_UPLOAD_MAX_BLOCKS = 4
_BASE64_CHUNK_CHARS = 4 * 1024 * 1024


def _redact_failed_binary_upload(block: dict) -> None:
    block.pop("base64", None)
    block["upload_error"] = "binary_upload_failed"


def _redact_oversized_binary_upload(block: dict) -> None:
    block.pop("base64", None)
    block["upload_error"] = "binary_upload_too_large"


def _redact_excess_binary_upload(block: dict) -> None:
    block.pop("base64", None)
    block["upload_error"] = "binary_upload_too_many_blocks"


def _redact_all_base64_blocks(blocks: list) -> None:
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("base64"), str):
            _redact_failed_binary_upload(block)


def _estimated_base64_decoded_size(b64_data: str) -> int:
    stripped = b64_data.rstrip("=")
    return (len(stripped) * 3) // 4


def _decode_base64_to_file(b64_data: str, file, *, max_bytes: int) -> int:
    """Decode base64 data into a file-like object without building one large bytes."""
    total = 0
    carry = ""

    for start in range(0, len(b64_data), _BASE64_CHUNK_CHARS):
        chunk = carry + b64_data[start : start + _BASE64_CHUNK_CHARS]
        decode_len = (len(chunk) // 4) * 4
        if decode_len == 0:
            carry = chunk
            continue

        data = base64.b64decode(chunk[:decode_len])
        file.write(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")
        carry = chunk[decode_len:]

    if carry:
        data = base64.b64decode(carry)
        file.write(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")

    file.seek(0)
    return total


async def upload_binary_blocks(result: dict, base_url: str) -> None:
    """Upload base64 blocks in-place, replacing each `base64` payload with a URL."""
    blocks = result.get("blocks")
    if not isinstance(blocks, list):
        return

    storage = None
    uploaded_block_count = 0
    estimated_total_bytes = 0

    for block in blocks:
        if not isinstance(block, dict):
            continue

        b64_data = block.get("base64")
        if not b64_data or not isinstance(b64_data, str):
            continue

        estimated_bytes = _estimated_base64_decoded_size(b64_data)
        if estimated_bytes > _BINARY_UPLOAD_MAX_BYTES:
            _redact_oversized_binary_upload(block)
            continue
        if uploaded_block_count >= _BINARY_UPLOAD_MAX_BLOCKS:
            _redact_excess_binary_upload(block)
            continue
        if estimated_total_bytes + estimated_bytes > _BINARY_UPLOAD_TOTAL_MAX_BYTES:
            _redact_oversized_binary_upload(block)
            continue

        if storage is None:
            try:
                from src.infra.storage.s3.service import get_or_init_storage

                storage = await get_or_init_storage()
            except Exception as exc:
                logger.warning("Failed to initialize storage for binary upload: %s", exc)
                _redact_all_base64_blocks(blocks)
                return

        try:
            mime_type = block.get("mime_type", "application/octet-stream")
            ext = (mimetypes.guess_extension(mime_type) or ".bin").lstrip(".")
            filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

            with SpooledTemporaryFile(
                max_size=_SPOOL_MAX_MEMORY_BYTES,
                mode="w+b",
            ) as spooled:
                size = await run_long_blocking_io(
                    _decode_base64_to_file,
                    b64_data,
                    spooled,
                    max_bytes=_BINARY_UPLOAD_MAX_BYTES,
                )
                upload_result = await storage.upload_file(
                    file=spooled,
                    folder="tool_binaries",
                    filename=filename,
                    content_type=mime_type,
                    skip_size_limit=True,
                )

            proxy_url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )
            block.pop("base64", None)
            block["url"] = proxy_url
            uploaded_block_count += 1
            estimated_total_bytes += estimated_bytes
            logger.info(
                "Uploaded binary block to storage: %s (%d bytes)",
                upload_result.key,
                size,
            )
        except ValueError as exc:
            if str(exc) == "binary_upload_too_large":
                _redact_oversized_binary_upload(block)
                continue
            logger.warning("Failed to upload binary block: %s", exc)
            _redact_failed_binary_upload(block)
        except Exception as exc:
            logger.warning("Failed to upload binary block: %s", exc)
            _redact_failed_binary_upload(block)
