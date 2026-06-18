"""OpenAI-compatible image generation tool for LambChat agents."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import mimetypes
import re
import sys
from enum import Enum
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_blocking_io
from src.infra.extensions import PluginSettingsResolver
from src.infra.logging import get_logger
from src.infra.storage.s3.service import get_or_init_storage
from src.infra.tool.backend_utils import (
    get_base_url_from_runtime,
    get_user_id_from_runtime,
)
from src.infra.utils.datetime import utc_now
from src.kernel.extensions.builtin_plugins import IMAGE_GENERATION_PLUGIN_ID

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
_SPOOL_MAX_MEMORY_BYTES = 2 * 1024 * 1024
_BASE64_DECODE_CHUNK_CHARS = 256 * 1024
_IMAGE_DOWNLOAD_MAX_BYTES = 20 * 1024 * 1024


class ImageBackground(str, Enum):
    AUTO = "auto"
    OPAQUE = "opaque"
    TRANSPARENT = "transparent"


class ImageInputFidelity(str, Enum):
    LOW = "low"
    HIGH = "high"


class ImageSize(str, Enum):
    SQUARE = "1024x1024"
    PORTRAIT = "1024x1536"
    LANDSCAPE = "1536x1024"


class ImageQuality(str, Enum):
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImageOutputFormat(str, Enum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


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


def _settings_resolver() -> PluginSettingsResolver:
    return PluginSettingsResolver(plugin_id=IMAGE_GENERATION_PLUGIN_ID)


async def _resolve_base_url() -> str:
    base_url = await _settings_resolver().get_str(
        "BASE_URL",
        DEFAULT_IMAGE_GENERATION_BASE_URL,
    )
    return str(base_url).rstrip("/")


async def _resolve_model() -> str:
    model = await _settings_resolver().get_str("MODEL", DEFAULT_IMAGE_GENERATION_MODEL)
    return str(model).strip() or DEFAULT_IMAGE_GENERATION_MODEL


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _normalize_image_size(size: Any) -> str:
    value = _enum_value(size).strip()
    if not value:
        return "1024x1024"
    if value in {item.value for item in ImageSize}:
        return value

    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if not match:
        return value

    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return "1024x1024"

    ratio = width / height
    supported = {
        "1024x1024": 1.0,
        "1024x1536": 1024 / 1536,
        "1536x1024": 1536 / 1024,
    }
    return min(supported, key=lambda candidate: abs(supported[candidate] - ratio))


def _is_retryable_image_api_status(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return status_code == 429 or 500 <= status_code <= 599


def _image_api_retry_delay(attempt: int) -> float:
    return IMAGE_API_RETRY_BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))


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
    resolved = url
    if resolved.startswith("/"):
        base_url = get_base_url_from_runtime(runtime)
        if base_url:
            resolved = f"{base_url}{resolved}"

    if resolved.startswith("data:"):
        mime, data = _strip_data_url_prefix(resolved)
        decoded = await run_blocking_io(_decode_base64_to_spooled_file, data)
        ext = (mimetypes.guess_extension(mime) or ".png").lstrip(".")
        return decoded, mime or "image/png", f"inline-image-{index + 1}.{ext}"

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
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
    await run_blocking_io(file_obj.seek, 0)
    result = await storage.upload_file(
        file_obj,
        folder=f"generated-images/{user_id}",
        filename=filename,
        content_type=content_type,
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
        image_file.close()
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
    n: int,
    output_format: str,
    runtime: ToolRuntime | None,
) -> dict[str, Any]:
    resolver = _settings_resolver()
    api_key = await resolver.get_secret("API_KEY")
    if not api_key:
        return {"error": "IMAGE_GENERATION_API_KEY is not configured"}

    base_url = await _resolve_base_url()
    model = await _resolve_model()
    timeout = await resolver.get_int("TIMEOUT", 120)
    user_id = get_user_id_from_runtime(runtime) or "anonymous"

    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "background": _enum_value(background),
        "size": _normalize_image_size(size),
        "quality": _enum_value(quality),
        "n": max(1, min(int(n), 10)),
        "output_format": _enum_value(output_format),
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
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
    n: int,
    output_format: str,
    runtime: ToolRuntime | None,
) -> dict[str, Any]:
    resolver = _settings_resolver()
    api_key = await resolver.get_secret("API_KEY")
    if not api_key:
        return {"error": "IMAGE_GENERATION_API_KEY is not configured"}

    base_url = await _resolve_base_url()
    model = await _resolve_model()
    timeout = await resolver.get_int("TIMEOUT", 120)
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
            source_files.append(image_file)
            files.append(("image", (filename, image_file, content_type)))

        data: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "background": _enum_value(background),
            "input_fidelity": _enum_value(input_fidelity),
            "size": _normalize_image_size(size),
            "quality": _enum_value(quality),
            "n": max(1, min(int(n), 10)),
            "output_format": _enum_value(output_format),
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            body = await _post_image_api_with_retries(
                client,
                f"{base_url}/images/edits",
                operation="edit",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=files,
            )
    finally:
        for image_file in source_files:
            image_file.close()

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
    background: ImageBackground,
    input_fidelity: ImageInputFidelity,
    size: ImageSize,
    quality: ImageQuality,
    n: int,
    output_format: ImageOutputFormat,
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
                n=n,
                output_format=output_format,
                runtime=runtime,
            )
        else:
            result = await _call_generation_api(
                prompt=prompt,
                background=background,
                size=size,
                quality=quality,
                n=n,
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
        ImageBackground,
        "Background handling for the generated image. Choose auto, opaque, or transparent.",
    ] = ImageBackground.AUTO,
    input_fidelity: Annotated[
        ImageInputFidelity,
        "How strongly edits should preserve the input image. Choose low or high.",
    ] = ImageInputFidelity.LOW,
    size: Annotated[
        ImageSize,
        "Canvas size for the result. Choose square, portrait, or landscape.",
    ] = ImageSize.SQUARE,
    quality: Annotated[
        ImageQuality,
        "Generation quality. Choose auto, low, medium, or high.",
    ] = ImageQuality.AUTO,
    n: Annotated[
        int,
        "Number of images to generate. Values outside 1-10 are clamped.",
    ] = 1,
    output_format: Annotated[
        ImageOutputFormat,
        "Output file format. Choose png, jpeg, or webp.",
    ] = ImageOutputFormat.PNG,
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
        n=n,
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
        ImageBackground,
        "Background handling for the generated image. Choose auto, opaque, or transparent.",
    ] = ImageBackground.AUTO,
    input_fidelity: Annotated[
        ImageInputFidelity,
        "How strongly edits should preserve the input image. Choose high when preserving a person, product, composition, or exact reference matters.",
    ] = ImageInputFidelity.HIGH,
    size: Annotated[
        ImageSize,
        "Canvas size for the result. Choose square, portrait, or landscape.",
    ] = ImageSize.SQUARE,
    quality: Annotated[
        ImageQuality,
        "Generation quality. Choose auto, low, medium, or high.",
    ] = ImageQuality.AUTO,
    n: Annotated[
        int,
        "Number of images to generate. Values outside 1-10 are clamped.",
    ] = 1,
    output_format: Annotated[
        ImageOutputFormat,
        "Output file format. Choose png, jpeg, or webp.",
    ] = ImageOutputFormat.PNG,
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
        n=n,
        output_format=output_format,
        runtime=runtime,
    )


def get_image_generation_tool() -> BaseTool:
    return image_generate


def get_reference_image_generation_tool() -> BaseTool:
    return image_edit_with_references
