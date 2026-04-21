"""Upload binary MCP result blocks and replace inline base64 with URLs."""

import base64
import mimetypes
import uuid

from src.infra.logging import get_logger

logger = get_logger(__name__)


async def upload_binary_blocks(result: dict, base_url: str) -> None:
    """Upload base64 blocks in-place, replacing each `base64` payload with a URL."""
    blocks = result.get("blocks")
    if not isinstance(blocks, list):
        return

    if not any(isinstance(block, dict) and block.get("base64") for block in blocks):
        return

    try:
        from src.infra.storage.s3.service import get_or_init_storage

        storage = await get_or_init_storage()
    except Exception as exc:
        logger.warning("Failed to initialize storage for binary upload: %s", exc)
        return

    for block in blocks:
        if not isinstance(block, dict):
            continue

        b64_data = block.get("base64")
        if not b64_data or not isinstance(b64_data, str):
            continue

        try:
            raw_bytes = base64.b64decode(b64_data)
            mime_type = block.get("mime_type", "application/octet-stream")
            ext = (mimetypes.guess_extension(mime_type) or ".bin").lstrip(".")
            filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

            upload_result = await storage.upload_bytes(
                data=raw_bytes,
                folder="tool_binaries",
                filename=filename,
                content_type=mime_type,
            )

            proxy_url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )
            block.pop("base64", None)
            block["url"] = proxy_url
            logger.info(
                "Uploaded binary block to storage: %s (%d bytes)",
                upload_result.key,
                len(raw_bytes),
            )
        except Exception as exc:
            logger.warning("Failed to upload binary block: %s", exc)
