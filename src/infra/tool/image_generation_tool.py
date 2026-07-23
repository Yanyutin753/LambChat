"""OpenAI-compatible image generation tool for LambChat agents."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import mimetypes
import os
import random
import re
import sys
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any
from urllib.parse import urlparse, urlsplit

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_blocking_io
from src.infra.image_utils import compress_image_bytes_if_needed
from src.infra.logging import get_logger
from src.infra.storage.s3.service import get_or_init_storage
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_user_id_from_runtime,
)
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

try:
    from langchain.tools import ToolRuntime  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    _mod = type(sys)("langchain.tools")
    _mod.ToolRuntime = Any  # type: ignore[attr-defined]
    sys.modules.setdefault("langchain.tools", _mod)
    from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

logger = get_logger(__name__)

DEFAULT_IMAGE_GENERATION_BASE_URL = "https://api.openai.com/v1"
DEFAULT_IMAGE_GENERATION_MODEL = "gpt-image-2"
IMAGE_API_MAX_ATTEMPTS = 3
IMAGE_API_RETRY_BASE_DELAY_SECONDS = 1.0
IMAGE_API_RETRY_JITTER_SECONDS = 0.5  # 重试抖动，防惊群
IMAGE_API_RETRY_MAX_DELAY_SECONDS = 60  # 单次重试等待上限，防异常 Retry-After 长挂
_SPOOL_MAX_MEMORY_BYTES = 2 * 1024 * 1024
_BASE64_DECODE_CHUNK_CHARS = 256 * 1024
_IMAGE_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024
_UPLOAD_FILE_MARKER = "/api/upload/file/"


_DEFAULT_IMAGE_SIZE = "1024x1024"


# ---------------------------------------------------------------------------
# 复用 httpx.AsyncClient（减少 TLS 握手 / DNS / 连接建立开销，提升稳定性）
# ---------------------------------------------------------------------------
_image_api_client: httpx.AsyncClient | None = None
_download_client: httpx.AsyncClient | None = None


def _get_image_api_client() -> httpx.AsyncClient:
    """生图 API 调用复用 client（连接池预热，减少握手失败）。"""
    global _image_api_client
    if _image_api_client is None or getattr(_image_api_client, "is_closed", False):
        read_timeout = float(getattr(settings, "IMAGE_GENERATION_TIMEOUT", 120) or 120)
        _image_api_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        )
    return _image_api_client


def _get_download_client() -> httpx.AsyncClient:
    """参考图下载复用 client（follow_redirects，读超时 60s）。"""
    global _download_client
    if _download_client is None or getattr(_download_client, "is_closed", False):
        _download_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        )
    return _download_client


async def close_image_clients() -> None:
    """关闭复用的 httpx client（应用关闭时调用）。"""
    global _image_api_client, _download_client
    for client in (_image_api_client, _download_client):
        if client is not None and not getattr(client, "is_closed", False):
            try:
                await client.aclose()
            except Exception as e:
                logger.warning("关闭生图 httpx client 失败: %s", e)
    _image_api_client = None
    _download_client = None


class _BackendImageNotFoundError(ValueError):
    """Raised when a sandbox path cannot be resolved to image bytes."""


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


def _strip_data_url_prefix(value: str) -> tuple[str, str]:
    match = re.match(r"^data:([^;]+);base64,(.+)$", value, re.DOTALL)
    if not match:
        return "", value
    return match.group(1), match.group(2)


def _estimate_base64_decoded_size(value: str) -> int:
    normalized = "".join(value.split())
    stripped = normalized.rstrip("=")
    return (len(stripped) * 3) // 4


def _raise_image_too_large(size: int) -> None:
    raise ValueError(f"Image download too large: {size} bytes (max {_IMAGE_DOWNLOAD_MAX_BYTES})")


def _guess_mime(filename: str, fallback: str = "image/png") -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or fallback


def _generated_filename(mime: str, index: int) -> str:
    ext = (mimetypes.guess_extension(mime) or ".png").lstrip(".")
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    return f"generated-{timestamp}-{index + 1}.{ext}"


def _filename_from_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    name = parsed.path.rstrip("/").split("/")[-1]
    if name:
        return name
    return f"image-{index + 1}.png"


def _backend_path_from_image_reference(image_ref: str) -> str | None:
    ref = image_ref.strip()
    if not ref or ref.startswith("data:") or _UPLOAD_FILE_MARKER in ref:
        return None

    parsed = urlsplit(ref)
    scheme = (parsed.scheme or "").lower()
    if parsed.netloc:
        return None
    if scheme in {"http", "https"}:
        return None
    if scheme:
        return None
    return ref


def _resolve_backend_image_path(backend: Any, file_path: str) -> str:
    if file_path.startswith("/"):
        return file_path

    candidate = backend
    visited: set[int] = set()
    while candidate is not None and id(candidate) not in visited:
        visited.add(id(candidate))
        work_dir = getattr(candidate, "work_dir", None)
        if isinstance(work_dir, str) and work_dir:
            return f"{work_dir.rstrip('/')}/{file_path.lstrip('/')}"
        candidate = getattr(candidate, "default", None)

    return file_path


async def _download_file_from_backend(backend: Any, file_path: str) -> bytes | None:
    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses:
                response = responses[0]
                if response.content is not None:
                    return response.content
                if response.error:
                    logger.warning(
                        "[image_generate] Backend download error for %s: %s",
                        file_path,
                        response.error,
                    )
        except Exception as exc:
            logger.warning("[image_generate] adownload_files failed for %s: %s", file_path, exc)

    if hasattr(backend, "download_files"):
        try:
            responses = await run_blocking_io(backend.download_files, [file_path])
            if responses:
                response = responses[0]
                if response.content is not None:
                    return response.content
                if response.error:
                    logger.warning(
                        "[image_generate] Backend download error for %s: %s",
                        file_path,
                        response.error,
                    )
        except Exception as exc:
            logger.warning("[image_generate] download_files failed for %s: %s", file_path, exc)

    return None


def _spool_backend_image(content: bytes) -> SpooledTemporaryFile:
    if len(content) > _IMAGE_DOWNLOAD_MAX_BYTES:
        _raise_image_too_large(len(content))
    spooled = SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b")
    try:
        spooled.write(content)
        spooled.seek(0)
        return spooled
    except Exception:
        spooled.close()
        raise


def _read_spooled_image(image_file: Any) -> bytes:
    image_file.seek(0)
    return bytes(image_file.read())


def _jpeg_filename(filename: str) -> str:
    stem, _ = os.path.splitext(filename)
    return f"{stem or 'image'}.jpg"


async def _close_image_files(
    image_files: list[Any],
    *,
    suppress_errors: bool = False,
) -> None:
    first_error: BaseException | None = None
    for image_file in image_files:
        try:
            await run_blocking_io(image_file.close)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None and not suppress_errors:
        raise first_error


async def _compress_image_source_if_needed(
    image_file: SpooledTemporaryFile,
    content_type: str,
    filename: str,
) -> tuple[SpooledTemporaryFile, str, str]:
    """Compress an edit source and transfer ownership of its file handle."""
    replacement: SpooledTemporaryFile | None = None
    try:
        content = await run_blocking_io(_read_spooled_image, image_file)
        compressed, compressed_type = await run_blocking_io(
            compress_image_bytes_if_needed,
            content,
            content_type,
        )
        if compressed == content and compressed_type == content_type:
            await run_blocking_io(image_file.seek, 0)
            return image_file, content_type, filename

        replacement = await run_blocking_io(_spool_backend_image, compressed)
        await run_blocking_io(image_file.close)
        return replacement, compressed_type, _jpeg_filename(filename)
    except BaseException:
        files_to_close = [image_file]
        if replacement is not None:
            files_to_close.insert(0, replacement)
        await _close_image_files(files_to_close, suppress_errors=True)
        raise


async def _download_backend_image_source(
    file_path: str,
    runtime: ToolRuntime | None,
    *,
    index: int,
) -> tuple[SpooledTemporaryFile, str, str]:
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        raise ValueError("Backend image paths require a runtime backend")

    resolved_path = _resolve_backend_image_path(backend, file_path)
    content = await _download_file_from_backend(backend, resolved_path)
    if content is None:
        raise _BackendImageNotFoundError(f"Could not download backend image: {resolved_path}")

    image_file = await run_blocking_io(_spool_backend_image, content)
    filename = os.path.basename(file_path.rstrip("/")) or f"image-{index + 1}.png"
    return image_file, _guess_mime(filename), filename


def _resolve_base_url() -> str:
    base_url = (
        getattr(settings, "IMAGE_GENERATION_BASE_URL", "") or DEFAULT_IMAGE_GENERATION_BASE_URL
    )
    return str(base_url).rstrip("/")


def _resolve_model() -> str:
    model = getattr(settings, "IMAGE_GENERATION_MODEL", "") or DEFAULT_IMAGE_GENERATION_MODEL
    return str(model).strip() or DEFAULT_IMAGE_GENERATION_MODEL


def _normalize_image_size(size: Any) -> str:
    value = str(size).strip() if size else ""
    return value or _DEFAULT_IMAGE_SIZE


def _is_retryable_image_api_status(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return status_code == 429 or 500 <= status_code <= 599


def _image_api_retry_delay(attempt: int) -> float:
    base = IMAGE_API_RETRY_BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))
    return base + random.uniform(0, IMAGE_API_RETRY_JITTER_SECONDS)


def _parse_retry_after(value: str | None) -> float | None:
    """解析 Retry-After 头（仅支持秒数形式；HTTP-date 形式返回 None）。"""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


async def _post_image_api_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    operation: str,
    **kwargs: Any,
) -> dict[str, Any]:
    for attempt in range(1, IMAGE_API_MAX_ATTEMPTS + 1):
        try:
            response = await client.post(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if attempt >= IMAGE_API_MAX_ATTEMPTS or not _is_retryable_image_api_status(status_code):
                raise
            delay = _image_api_retry_delay(attempt)
            # 429 时尊重上游 Retry-After 头：上游告知的是恢复窗口，必须不早于
            # 它重试，故取本地退避与上游建议的较大值；再封顶防异常值长挂。
            _resp_headers = getattr(exc.response, "headers", None)
            retry_after = (
                _parse_retry_after(_resp_headers.get("Retry-After"))
                if _resp_headers is not None
                else None
            )
            if retry_after is not None:
                delay = min(max(delay, retry_after), IMAGE_API_RETRY_MAX_DELAY_SECONDS)
            logger.warning(
                "[image_generate] %s API returned retryable status %s "
                "(attempt %d/%d), retrying in %.1fs",
                operation,
                status_code,
                attempt,
                IMAGE_API_MAX_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt >= IMAGE_API_MAX_ATTEMPTS:
                raise
            delay = _image_api_retry_delay(attempt)
            logger.warning(
                "[image_generate] %s API request failed with %s (attempt %d/%d), retrying in %.1fs",
                operation,
                type(exc).__name__,
                attempt,
                IMAGE_API_MAX_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Image API retry loop exhausted")


async def _download_image_source(
    url: str,
    runtime: ToolRuntime | None,
    *,
    index: int = 0,
) -> tuple[SpooledTemporaryFile, str, str]:
    backend_path = _backend_path_from_image_reference(url)
    if backend_path is not None:
        backend = get_backend_from_runtime(runtime)
        if backend is not None:
            try:
                return await _download_backend_image_source(backend_path, runtime, index=index)
            except _BackendImageNotFoundError:
                if not backend_path.startswith("/"):
                    raise
                logger.debug(
                    "[image_generate] Falling back to root-relative URL for %s",
                    backend_path,
                )
        elif not backend_path.startswith("/"):
            raise ValueError("Backend image paths require a runtime backend")

    resolved = url
    if resolved.startswith("//"):
        base_url = get_base_url_from_runtime(runtime)
        scheme = urlsplit(base_url).scheme or "https"
        resolved = f"{scheme}:{resolved}"
    elif resolved.startswith("/"):
        base_url = get_base_url_from_runtime(runtime)
        if base_url:
            resolved = f"{base_url}{resolved}"

    if resolved.startswith("data:"):
        mime, data = _strip_data_url_prefix(resolved)
        decoded = await run_blocking_io(_decode_base64_to_spooled_file, data)
        ext = (mimetypes.guess_extension(mime) or ".png").lstrip(".")
        return decoded, mime or "image/png", f"inline-image-{index + 1}.{ext}"

    client = _get_download_client()
    spooled = SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b")
    try:
        total_size = 0
        async with client.stream("GET", resolved) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                total_size += len(chunk)
                if total_size > _IMAGE_DOWNLOAD_MAX_BYTES:
                    raise ValueError(
                        f"Image download too large: {total_size} bytes "
                        f"(max {_IMAGE_DOWNLOAD_MAX_BYTES})"
                    )
                await run_blocking_io(spooled.write, chunk)
            content_type = response.headers.get("content-type", "") or _guess_mime(resolved)
        await run_blocking_io(spooled.seek, 0)
        filename = _filename_from_url(resolved, index)
        return spooled, content_type, filename
    except Exception:
        spooled.close()
        raise


def _decode_base64_to_spooled_file(data: str) -> SpooledTemporaryFile:
    estimated_size = _estimate_base64_decoded_size(data)
    if estimated_size > _IMAGE_DOWNLOAD_MAX_BYTES:
        _raise_image_too_large(estimated_size)

    spooled = SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b")
    carry = ""
    total_size = 0
    try:
        for offset in range(0, len(data), _BASE64_DECODE_CHUNK_CHARS):
            chunk = "".join(data[offset : offset + _BASE64_DECODE_CHUNK_CHARS].split())
            if not chunk:
                continue
            pending = carry + chunk
            decode_len = (len(pending) // 4) * 4
            if decode_len == 0:
                carry = pending
                continue
            decoded = base64.b64decode(pending[:decode_len])
            total_size += len(decoded)
            if total_size > _IMAGE_DOWNLOAD_MAX_BYTES:
                _raise_image_too_large(total_size)
            spooled.write(decoded)
            carry = pending[decode_len:]

        if carry:
            decoded = base64.b64decode(carry)
            total_size += len(decoded)
            if total_size > _IMAGE_DOWNLOAD_MAX_BYTES:
                _raise_image_too_large(total_size)
            spooled.write(decoded)
        spooled.seek(0)
        return spooled
    except (binascii.Error, ValueError):
        spooled.close()
        raise


def _file_size(file_obj: Any) -> int:
    current = file_obj.tell()
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(current)
    return size


async def _upload_image_file(
    file_obj: Any,
    *,
    user_id: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    storage = await get_or_init_storage()
    size = await run_blocking_io(_file_size, file_obj)
    # 防御性冗余校验：与下载层一致的 20MB 上限。真正的流式卡口在
    # _download_image_source / _decode_base64_to_spooled_file，这里只是
    # 让已算出的 size 不再只是摆设，并兜住任何绕过下载层的异常输入。
    if size > _IMAGE_DOWNLOAD_MAX_BYTES:
        raise ValueError(
            f"Generated image too large: {size} bytes (max {_IMAGE_DOWNLOAD_MAX_BYTES})"
        )
    await run_blocking_io(file_obj.seek, 0)
    result = await storage.upload_file(
        file_obj,
        folder=f"generated-images/{user_id}",
        filename=filename,
        content_type=content_type,
        skip_size_limit=True,
    )
    return {
        "key": result.key,
        "url": result.url,
        "size": getattr(result, "size", size),
        "content_type": getattr(result, "content_type", content_type),
    }


def _extract_image_payload(data: dict[str, Any]) -> tuple[SpooledTemporaryFile | None, str]:
    if isinstance(data.get("b64_json"), str) and data["b64_json"].strip():
        raw = _decode_base64_to_spooled_file(data["b64_json"])
        return raw, "image/png"

    if isinstance(data.get("url"), str) and data["url"].strip():
        parsed = urlparse(data["url"])
        filename = parsed.path.rstrip("/").split("/")[-1] or "image.png"
        mime = _guess_mime(filename)
        return None, mime

    if isinstance(data.get("base64"), str) and data["base64"].strip():
        raw = _decode_base64_to_spooled_file(data["base64"])
        return raw, "image/png"

    if isinstance(data.get("data"), str) and data["data"].strip():
        raw = _decode_base64_to_spooled_file(data["data"])
        return raw, "image/png"

    raise ValueError("Image API response did not include a readable image payload")


async def _convert_result_item(
    item: dict[str, Any],
    *,
    user_id: str,
    runtime: ToolRuntime | None,
    index: int,
) -> dict[str, Any]:
    payload = item.get("result") if isinstance(item.get("result"), dict) else item
    if not isinstance(payload, dict):
        raise ValueError("Image API response item is not an object")

    image_file, mime = await run_blocking_io(_extract_image_payload, payload)
    if image_file is None and isinstance(payload.get("url"), str):
        image_file, source_mime, _ = await _download_image_source(payload["url"], runtime)
        mime = source_mime
    if image_file is None:
        raise ValueError("Image API response did not include image data")
    filename = _generated_filename(mime, index)

    try:
        uploaded = await _upload_image_file(
            image_file,
            user_id=user_id,
            filename=filename,
            content_type=mime,
        )
    finally:
        await run_blocking_io(image_file.close)
    base_url = get_base_url_from_runtime(runtime)
    proxy_url = (
        f"{base_url}/api/upload/file/{uploaded['key']}"
        if base_url
        else f"/api/upload/file/{uploaded['key']}"
    )
    result: dict[str, Any] = {
        "url": proxy_url,
        "key": uploaded["key"],
        "content_type": uploaded["content_type"],
    }
    if payload.get("revised_prompt"):
        result["revised_prompt"] = payload.get("revised_prompt")
    return result


async def _call_generation_api(
    *,
    prompt: str,
    background: str,
    size: str,
    quality: str,
    output_format: str,
    runtime: ToolRuntime | None,
) -> dict[str, Any]:
    api_key = getattr(settings, "IMAGE_GENERATION_API_KEY", "") or ""
    if not api_key:
        return {"error": "IMAGE_GENERATION_API_KEY is not configured"}

    base_url = _resolve_base_url()
    model = _resolve_model()
    user_id = get_user_id_from_runtime(runtime) or "anonymous"

    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "background": str(background),
        "size": _normalize_image_size(size),
        "quality": str(quality),
        "n": 1,
        "output_format": str(output_format),
    }

    client = _get_image_api_client()
    body = await _post_image_api_with_retries(
        client,
        f"{base_url}/images/generations",
        operation="generation",
        headers=headers,
        json=payload,
    )

    items = []
    if isinstance(body, dict):
        raw_items = body.get("data")
        if isinstance(raw_items, list):
            items = [item for item in raw_items if isinstance(item, dict)]
        elif isinstance(raw_items, dict):
            items = [raw_items]

    if not items:
        return {
            "error": "Image API did not return any image data",
            "raw_response": body,
        }

    images = []
    for index, item in enumerate(items):
        images.append(
            await _convert_result_item(
                item,
                user_id=user_id,
                runtime=runtime,
                index=index,
            )
        )

    return {
        "success": True,
        "images": images,
    }


async def _call_edit_api(
    *,
    prompt: str,
    input_images: list[str],
    background: str,
    input_fidelity: str,
    size: str,
    quality: str,
    output_format: str,
    runtime: ToolRuntime | None,
) -> dict[str, Any]:
    api_key = getattr(settings, "IMAGE_GENERATION_API_KEY", "") or ""
    if not api_key:
        return {"error": "IMAGE_GENERATION_API_KEY is not configured"}

    base_url = _resolve_base_url()
    model = _resolve_model()
    user_id = get_user_id_from_runtime(runtime) or "anonymous"

    source_files = []
    files: list[tuple[str, tuple[str, Any, str]]] = []
    try:
        for index, image_url in enumerate(input_images[:16]):
            image_file, content_type, filename = await _download_image_source(
                image_url,
                runtime,
                index=index,
            )
            image_file, content_type, filename = await _compress_image_source_if_needed(
                image_file,
                content_type,
                filename,
            )
            source_files.append(image_file)
            files.append(("image", (filename, image_file, content_type)))

        data: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "background": str(background),
            "input_fidelity": str(input_fidelity),
            "size": _normalize_image_size(size),
            "quality": str(quality),
            "n": 1,
            "output_format": str(output_format),
        }

        client = _get_image_api_client()
        body = await _post_image_api_with_retries(
            client,
            f"{base_url}/images/edits",
            operation="edit",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
        )
    finally:
        await _close_image_files(
            source_files,
            suppress_errors=sys.exc_info()[0] is not None,
        )

    items = []
    if isinstance(body, dict):
        raw_items = body.get("data")
        if isinstance(raw_items, list):
            items = [item for item in raw_items if isinstance(item, dict)]
        elif isinstance(raw_items, dict):
            items = [raw_items]

    if not items:
        return {
            "error": "Image API did not return any image data",
            "raw_response": body,
        }

    images = []
    for index, item in enumerate(items):
        images.append(
            await _convert_result_item(
                item,
                user_id=user_id,
                runtime=runtime,
                index=index,
            )
        )

    return {
        "success": True,
        "images": images,
    }


async def _image_generate_impl(
    *,
    prompt: str,
    input_images: list[str] | None,
    background: str,
    input_fidelity: str,
    size: str,
    quality: str,
    output_format: str,
    runtime: ToolRuntime | None,
) -> str:
    try:
        if input_images:
            result = await _call_edit_api(
                prompt=prompt,
                input_images=list(input_images),
                background=background,
                input_fidelity=input_fidelity,
                size=size,
                quality=quality,
                output_format=output_format,
                runtime=runtime,
            )
        else:
            result = await _call_generation_api(
                prompt=prompt,
                background=background,
                size=size,
                quality=quality,
                output_format=output_format,
                runtime=runtime,
            )
        return await _json_dumps_result(result)
    except Exception as exc:
        logger.warning("[image_generate] failed: %s", exc)
        return await _json_dumps_result({"error": f"Image generation failed: {exc}"})


@tool
async def image_generate(
    prompt: Annotated[str, "Describe the image you want to create or edit."],
    input_images: Annotated[
        list[str] | None,
        "Optional source image URLs or project file URLs. Provide one or more images to switch to image-to-image mode; leave empty for pure text-to-image.",
    ] = None,
    background: Annotated[
        str,
        "Background handling: auto, opaque, or transparent.",
    ] = "auto",
    input_fidelity: Annotated[
        str,
        "How strongly edits should preserve the input image: low or high.",
    ] = "low",
    size: Annotated[
        str,
        "Output image size. 1K sizes: 1024x1024, 1536x1024, 1024x1536, 1792x1024, 1024x1792. 2K sizes: 2048x2048, 3072x2048, 2048x3072, 2048x1152, 1152x2048, 2048x1536, 1536x2048. Also accepts ratio strings like auto, 1:1, 16:9, 9:16, 4:3, 3:4, etc.",
    ] = _DEFAULT_IMAGE_SIZE,
    quality: Annotated[
        str,
        "Generation quality: auto, low, medium, or high.",
    ] = "auto",
    output_format: Annotated[
        str,
        "Output file format: png, jpeg, or webp.",
    ] = "png",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Generate or edit images with an OpenAI-compatible image API.

    Use this tool for either:
    - text-to-image generation when only `prompt` is provided
    - image-to-image editing when `input_images` is provided

    IMPORTANT reference-image routing:
    - If the user uploaded or mentioned an image and asks for 图生图, 参考图,
      参考这张, 照着这张, 基于这张, 改这张, 保持风格, 同款, or image-to-image,
      pass the uploaded image URLs in `input_images`. Do not leave `input_images`
      empty for those requests.
    - For multiple images, explain each image role in the prompt, for example:
      first image is the edit target, second image is the style/reference image.
    - If no image URL is available yet, ask for or locate the uploaded image URL before
      calling this tool instead of silently doing pure text-to-image generation.

    The tool accepts a small, opinionated set of options for canvas size, edit fidelity,
    background handling, quality, and output format. Input images can be uploaded files,
    project file URLs, or other accessible image URLs.

    The response contains uploaded image URLs plus metadata such as the generated file key
    and any revised prompt returned by the image API.
    """
    return await _image_generate_impl(
        prompt=prompt,
        input_images=input_images,
        background=background,
        input_fidelity=input_fidelity,
        size=size,
        quality=quality,
        output_format=output_format,
        runtime=runtime,
    )


@tool
async def image_edit_with_references(
    prompt: Annotated[
        str,
        "Describe how to edit or regenerate the image, including each input image role.",
    ],
    input_images: Annotated[
        list[str],
        "Required source/reference image URLs. Use uploaded image URLs here for 图生图, 参考图, 照着这张, 基于这张, 改这张, 保持风格, 同款, or image-to-image requests.",
    ],
    background: Annotated[
        str,
        "Background handling: auto, opaque, or transparent.",
    ] = "auto",
    input_fidelity: Annotated[
        str,
        "How strongly edits should preserve the input image: low or high.",
    ] = "high",
    size: Annotated[
        str,
        "Output image size. 1K sizes: 1024x1024, 1536x1024, 1024x1536, 1792x1024, 1024x1792. 2K sizes: 2048x2048, 3072x2048, 2048x3072, 2048x1152, 1152x2048, 2048x1536, 1536x2048. Also accepts ratio strings like auto, 1:1, 16:9, 9:16, 4:3, 3:4, etc.",
    ] = _DEFAULT_IMAGE_SIZE,
    quality: Annotated[
        str,
        "Generation quality: auto, low, medium, or high.",
    ] = "auto",
    output_format: Annotated[
        str,
        "Output file format: png, jpeg, or webp.",
    ] = "png",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Edit or regenerate images from required reference images.

    Use this tool instead of pure text-to-image when the user provides image attachments
    or says 图生图, 参考图, 参考这张图生成, 照着这张, 基于这张, 改这张, 把这张改成,
    保持人物/产品/构图/风格, 同款, style reference, composition reference, or
    image-to-image.

    Always put the uploaded image URLs in `input_images`. If there are multiple images,
    state their roles in `prompt`, such as: Image 1 is the edit target; Image 2 is the
    style/reference image; preserve Image 1's subject while applying Image 2's style.
    This wrapper requires `input_images` so reference-image requests are not accidentally
    handled as text-only generation.
    """
    if not input_images:
        return await _json_dumps_result(
            {
                "error": (
                    "input_images is required for reference-image editing. "
                    "Use the uploaded image URL(s) as input_images and retry."
                )
            }
        )

    return await _image_generate_impl(
        prompt=prompt,
        input_images=input_images,
        background=background,
        input_fidelity=input_fidelity,
        size=size,
        quality=quality,
        output_format=output_format,
        runtime=runtime,
    )


def get_image_generation_tool() -> BaseTool:
    return image_generate


def get_reference_image_generation_tool() -> BaseTool:
    return image_edit_with_references
