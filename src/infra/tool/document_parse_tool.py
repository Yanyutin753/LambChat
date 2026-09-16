"""Document parsing tool: parse PDF/DOCX/PPTX into Markdown via multi providers.

用户上传的 docx/pdf/pptx 附件原本只以链接形式进入对话，模型只能在沙箱里
手写解析代码，含图片的文档几乎必然翻车。本工具把文档发给已配置的解析
提供商（Mistral OCR / MinerU / Azure Document Intelligence / docling-serve /
Tika / PaddleOCR-VL / MarkItDown 本地兜底，见 document_parse_providers），
拿回页级 Markdown，并把内嵌图片上传到存储、回写成真实 URL——模型直接
得到可读文本 + 可分析图片，前端面板也能内联渲染。形态对齐 web_search
工具（settings 选 provider）。
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import time
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import unquote, urlparse

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import (
    get_base_url_from_runtime,
    get_user_id_from_runtime,
)
from src.infra.tool.document_parse_providers import (
    DocumentParseError,
    execute_document_parse,
)
from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

logger = get_logger(__name__)

_SPOOL_MAX_MEMORY_BYTES = 2 * 1024 * 1024

# Bound document downloads before forwarding them to the parse provider.
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024

# 提供商输入面的并集：Office/OpenDocument 文本格式 + PDF。
# 图片走多模态附件或 image_analyze，不进本工具。
_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".doc", ".ppt", ".odt"}

_IMAGE_MIME_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".avif": "image/avif",
}

_TRUNCATION_NOTICE = "\n\n...[truncated]"


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


def _resolve_url(url: str, runtime: ToolRuntime | None) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        base_url = get_base_url_from_runtime(runtime)
        if base_url:
            return f"{base_url}{url}"
    return url


def _guess_filename(url: str) -> str:
    path = unquote(urlparse(url).path.rstrip("/"))
    return path.split("/")[-1] if path else "document"


def _known_download_size(headers: Any) -> int | None:
    try:
        raw_size = headers.get("content-length")
    except Exception:
        return None
    if raw_size is None:
        return None
    try:
        size = int(raw_size)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def detect_document_extension(filename: str) -> str | None:
    """Return the validated extension (without dot) or None when unsupported."""
    for candidate in re.findall(r"\.[A-Za-z0-9]+$", filename):
        if candidate.lower() in _SUPPORTED_EXTENSIONS:
            return candidate.lower().lstrip(".")
    return None


def mime_type_from_image_id(image_id: str) -> str:
    lowered = image_id.lower()
    for suffix, mime_type in _IMAGE_MIME_TYPES.items():
        if lowered.endswith(suffix):
            return mime_type
    return "application/octet-stream"


def rewrite_image_refs(markdown: str, ref_to_url: dict[str, str]) -> str:
    """Rewrite provider image refs (`![...](img-0.jpeg)`) to uploaded URLs."""
    rewritten = markdown
    for image_ref, url in ref_to_url.items():
        rewritten = rewritten.replace(f"]({image_ref})", f"]({url})")
    return rewritten


def truncate_markdown(markdown: str, limit: int) -> tuple[str, bool]:
    """Cap the markdown length and flag truncation."""
    if limit <= 0 or len(markdown) <= limit:
        return markdown, False
    room = max(limit - len(_TRUNCATION_NOTICE), 1)
    return markdown[:room] + _TRUNCATION_NOTICE, True


async def _upload_image_to_storage(
    *, user_id: str, image_id: str, data: bytes
) -> dict[str, Any] | None:
    """Upload one extracted image beside user uploads; return None on failure."""
    from src.infra.storage.s3.service import get_or_init_storage

    content_type = mime_type_from_image_id(image_id)
    spooled = SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b")
    try:
        await run_blocking_io(spooled.write, data)
        await run_blocking_io(spooled.seek, 0)
        storage = await get_or_init_storage()
        result = await storage.upload_file(
            spooled,
            folder=f"parsed-documents/{user_id}",
            filename=image_id,
            content_type=content_type,
            skip_size_limit=True,
        )
        return {
            "key": result.key,
            "url": result.url,
            "size": getattr(result, "size", None) or len(data),
            "content_type": getattr(result, "content_type", None) or content_type,
        }
    except Exception as e:
        logger.warning(
            "[document_parse] image upload failed for %s: error_type=%s",
            image_id,
            type(e).__name__,
        )
        return None
    finally:
        await run_blocking_io(spooled.close)


@tool
async def document_parse(
    url: Annotated[
        str,
        "URL of the document to parse. Supports absolute URLs and /api upload paths from the attachment list.",
    ],
    include_images: Annotated[
        bool,
        "Extract embedded images, upload them to storage and inline them as Markdown image URLs.",
    ] = True,
    pages: Annotated[
        str | None, "Optional 0-based page range for large documents, such as '0-3' or '0,2-4'."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Parse a document (PDF, DOCX, PPTX, DOC, PPT, ODT) into Markdown via the configured
    document parsing providers (Mistral OCR, MinerU, Azure Document Intelligence, docling,
    Tika, PaddleOCR-VL, or the local MarkItDown fallback), with embedded images uploaded
    and inlined as image URLs. Use this to read user document attachments instead of
    writing ad-hoc sandbox parsing code."""

    resolved_url = _resolve_url(url, runtime)

    filename = _guess_filename(resolved_url)
    extension = detect_document_extension(filename)
    if extension is None:
        return await _json_dumps_result(
            {
                "error": (
                    f"Unsupported document type for '{filename}'. "
                    "Supported: pdf, docx, pptx, doc, ppt, odt"
                )
            }
        )

    max_download_bytes = max(
        int(getattr(settings, "DOCUMENT_PARSE_MAX_DOWNLOAD_BYTES", 0) or 0),
        1,
    )
    max_output_chars = int(getattr(settings, "DOCUMENT_PARSE_MAX_OUTPUT_CHARS", 0) or 0)
    image_limit = int(getattr(settings, "DOCUMENT_PARSE_MAX_IMAGES", 0) or 0)

    spooled = SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b")
    try:
        try:
            total_size = 0
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)
            ) as http_client:
                async with http_client.stream("GET", resolved_url) as response:
                    response.raise_for_status()
                    known_size = _known_download_size(getattr(response, "headers", {}))
                    if known_size is not None and known_size > max_download_bytes:
                        return await _json_dumps_result(
                            {"error": f"Document download exceeds {max_download_bytes} bytes"}
                        )
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        total_size += len(chunk)
                        if total_size > max_download_bytes:
                            return await _json_dumps_result(
                                {"error": (f"Document download exceeds {max_download_bytes} bytes")}
                            )
                        await run_blocking_io(spooled.write, chunk)

                await run_blocking_io(spooled.seek, 0)
                data = await run_blocking_io(spooled.read)

                started_at = time.monotonic()
                try:
                    parsed = await execute_document_parse(
                        data=data,
                        filename=filename,
                        include_images=include_images,
                        pages=pages,
                        image_limit=image_limit,
                        client=http_client,
                    )
                except DocumentParseError as exc:
                    return await _json_dumps_result({"error": str(exc)})
                except Exception as exc:
                    logger.warning("[document_parse] failed for %s: %s", resolved_url, exc)
                    return await _json_dumps_result({"error": f"Document parse failed: {exc}"})
        except Exception as exc:
            logger.warning("[document_parse] download failed for %s: %s", resolved_url, exc)
            return await _json_dumps_result({"error": f"Document download failed: {exc}"})

        markdown = str(parsed.get("markdown") or "")

        images_payload: list[dict[str, Any]] = []
        ref_to_url: dict[str, str] = {}
        provider_images = parsed.get("images") or []
        if include_images and isinstance(provider_images, list):
            user_id = get_user_id_from_runtime(runtime) or "anonymous"
            for image in provider_images:
                if image_limit > 0 and len(images_payload) >= image_limit:
                    break
                ref = str(image.get("ref") or "")
                raw = str(image.get("base64") or "")
                if not ref or not raw:
                    continue
                try:
                    image_bytes = await run_blocking_io(base64.b64decode, raw)
                except (binascii.Error, ValueError):
                    continue
                image_name = PurePosixPath(ref).name or ref
                uploaded = await _upload_image_to_storage(
                    user_id=user_id, image_id=image_name, data=image_bytes
                )
                if uploaded is None:
                    continue
                ref_to_url[ref] = str(uploaded["url"])
                images_payload.append(
                    {
                        "index": len(images_payload) + 1,
                        "id": image_name,
                        "url": uploaded["url"],
                        "mime_type": uploaded["content_type"],
                        "size": uploaded["size"],
                    }
                )

        if ref_to_url:
            markdown = rewrite_image_refs(markdown, ref_to_url)
        markdown, truncated = truncate_markdown(markdown, max_output_chars)

        result = {
            "success": True,
            "url": resolved_url,
            "filename": filename,
            "provider": parsed.get("engine"),
            "pages_processed": parsed.get("pages"),
            "markdown": markdown,
            "truncated": truncated,
            "image_count": len(images_payload),
            "images": images_payload,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
        }
        return await _json_dumps_result(result)
    finally:
        await run_blocking_io(spooled.close)


def get_document_parse_tool() -> BaseTool:
    return document_parse
