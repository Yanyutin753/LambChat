"""Vision model image analysis tool for LambChat agents."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import sys
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

from langchain_core.tools import BaseTool, InjectedToolArg

from src.agents.core.node_utils import (
    IMAGE_DATA_URL_INLINE_MAX_BYTES,
    build_human_message,
    inline_image_attachments_as_data_urls,
)
from src.infra.async_utils import run_blocking_io
from src.infra.llm.client import LLMClient
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime, get_base_url_from_runtime
from src.kernel.config import settings
from src.kernel.schemas.model import ModelConfig

try:
    from langchain.tools import ToolRuntime  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    _mod = type(sys)("langchain.tools")
    _mod.ToolRuntime = Any  # type: ignore[attr-defined]
    sys.modules.setdefault("langchain.tools", _mod)
    from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

logger = get_logger(__name__)

DEFAULT_IMAGE_ANALYSIS_PROMPT = "Describe the image clearly and objectively."
IMAGE_ANALYSIS_INTERNAL_RUN_CONFIG = {
    "metadata": {"lc_source": "image_analysis_tool", "internal_tool_call": True},
    "tags": ["internal_tool_call", "image_analysis_tool"],
}
_UPLOAD_FILE_MARKER = "/api/upload/file/"


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


async def _resolve_model_config(reference: str) -> ModelConfig | None:
    value = reference.strip()
    if not value:
        return None

    from src.infra.agent.model_storage import get_model_storage

    storage = get_model_storage()
    model = await storage.get(value)
    if model:
        return model
    return await storage.get_by_value(value)


def _image_attachments_from_urls(image_urls: list[str]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for index, image_url in enumerate(image_urls):
        url = str(image_url).strip()
        if not url:
            continue
        attachments.append(
            {
                "id": f"image-{index + 1}",
                "name": f"image-{index + 1}",
                "type": "image",
                "mime_type": "image/jpeg",
                "url": url,
            }
        )
    return attachments


def _backend_path_from_image_reference(image_ref: str) -> str | None:
    ref = image_ref.strip()
    if not ref or ref.startswith("data:") or _UPLOAD_FILE_MARKER in ref:
        return None

    parsed = urlsplit(ref)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"http", "https"}:
        return None
    if scheme == "file":
        return unquote(parsed.path or "")
    if scheme:
        return None
    return ref


def _guess_image_mime_type(file_path: str, content: bytes) -> str | None:
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and mime_type.startswith("image/"):
        return mime_type

    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"RIFF", "image/webp"),
        (b"BM", "image/bmp"),
    )
    for prefix, detected_mime_type in signatures:
        if content.startswith(prefix):
            return detected_mime_type
    if content.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    return None


async def _download_file_from_backend(backend: Any, file_path: str) -> bytes | None:
    if hasattr(backend, "adownload_files"):
        try:
            responses = await backend.adownload_files([file_path])
            if responses:
                resp = responses[0]
                if resp.content:
                    return resp.content
                if resp.error:
                    logger.warning(
                        "[image_analyze] Download error for %s: %s", file_path, resp.error
                    )
        except Exception as e:
            logger.warning("[image_analyze] adownload_files failed for %s: %s", file_path, e)

    if hasattr(backend, "download_files"):
        try:
            responses = await run_blocking_io(backend.download_files, [file_path])
            if responses:
                resp = responses[0]
                if resp.content:
                    return resp.content
                if resp.error:
                    logger.warning(
                        "[image_analyze] Download error for %s: %s", file_path, resp.error
                    )
        except Exception as e:
            logger.warning("[image_analyze] download_files failed for %s: %s", file_path, e)

    return None


async def _inline_backend_image_paths(
    attachments: list[dict[str, Any]],
    runtime: ToolRuntime | None,
) -> list[dict[str, Any]]:
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return attachments

    resolved: list[dict[str, Any]] = []
    for attachment in attachments:
        url = str(attachment.get("url") or "")
        backend_path = _backend_path_from_image_reference(url)
        if backend_path is None:
            resolved.append(attachment)
            continue

        content = await _download_file_from_backend(backend, backend_path)
        if content is None:
            resolved.append(attachment)
            continue
        if len(content) > IMAGE_DATA_URL_INLINE_MAX_BYTES:
            logger.warning(
                "[image_analyze] Refusing oversized backend image: %s size=%s max=%s",
                backend_path,
                len(content),
                IMAGE_DATA_URL_INLINE_MAX_BYTES,
            )
            resolved.append(attachment)
            continue

        mime_type = _guess_image_mime_type(backend_path, content)
        if not mime_type:
            logger.warning(
                "[image_analyze] Backend file is not a recognized image: %s", backend_path
            )
            resolved.append(attachment)
            continue

        encoded = await run_blocking_io(base64.b64encode, content)
        data_url = f"data:{mime_type};base64,{encoded.decode('ascii')}"
        resolved.append(
            {
                **attachment,
                "name": os.path.basename(backend_path.rstrip("/")) or attachment.get("name"),
                "mime_type": mime_type,
                "url": None,
                "data_url": data_url,
                "size": len(content),
            }
        )

    return resolved


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    return str(content)


async def _call_with_retries(llm: Any, messages: list[Any]) -> Any:
    max_attempts = max(1, int(getattr(settings, "IMAGE_ANALYSIS_MAX_ATTEMPTS", 3) or 3))
    base_delay = float(getattr(settings, "IMAGE_ANALYSIS_RETRY_DELAY", 1.0) or 0)

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await llm.ainvoke(messages, config=IMAGE_ANALYSIS_INTERNAL_RUN_CONFIG)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = base_delay * (2 ** max(0, attempt - 1))
            logger.warning(
                "[image_analyze] model call failed with %s (attempt %d/%d), retrying in %.1fs",
                type(exc).__name__,
                attempt,
                max_attempts,
                delay,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


@tool
async def image_analyze(
    image_urls: Annotated[
        list[str],
        "Image URLs or project file URLs to inspect. Provide one or more images.",
    ],
    prompt: Annotated[
        str,
        "Question or instruction for the vision model, such as what to describe or compare.",
    ] = DEFAULT_IMAGE_ANALYSIS_PROMPT,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None,
) -> str:
    """Analyze one or more images with the configured vision-language model."""
    try:
        model_reference = str(getattr(settings, "IMAGE_ANALYSIS_MODEL_ID", "") or "").strip()
        if not model_reference:
            return await _json_dumps_result({"error": "IMAGE_ANALYSIS_MODEL_ID is not configured"})

        model_config = await _resolve_model_config(model_reference)
        if not model_config:
            return await _json_dumps_result(
                {"error": "Configured IMAGE_ANALYSIS_MODEL_ID not found"}
            )
        if not model_config.profile or not model_config.profile.supports_vision:
            return await _json_dumps_result(
                {"error": "Configured IMAGE_ANALYSIS_MODEL_ID does not support vision"}
            )

        attachments = _image_attachments_from_urls(image_urls)
        if not attachments:
            return await _json_dumps_result({"error": "image_urls must include at least one image"})

        attachments = await _inline_backend_image_paths(attachments, runtime)
        force_data_url = bool(model_config.profile.image_url_to_base64)
        attachments = await inline_image_attachments_as_data_urls(
            attachments,
            base_url=get_base_url_from_runtime(runtime),
            force_data_url=force_data_url,
        )
        message = build_human_message(
            prompt or DEFAULT_IMAGE_ANALYSIS_PROMPT, attachments, supports_vision=True
        )
        if isinstance(message.content, str):
            return await _json_dumps_result({"error": "No readable image URLs were provided"})

        llm = await LLMClient.get_model(model_config=model_config)
        response = await _call_with_retries(llm, [message])
        analysis = _content_to_text(getattr(response, "content", response))
        return await _json_dumps_result(
            {
                "success": True,
                "analysis": analysis,
                "model_id": model_config.id or model_reference,
            }
        )
    except Exception as exc:
        logger.warning("[image_analyze] failed: %s", exc)
        return await _json_dumps_result({"error": f"Image analysis failed: {exc}"})


def get_image_analysis_tool() -> BaseTool:
    return image_analyze
