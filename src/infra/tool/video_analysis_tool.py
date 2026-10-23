"""Analyze bounded video bytes using the configured model's native video protocol."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
from contextlib import aclosing
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

from langchain_core.tools import BaseTool, InjectedToolArg

from src.agents.core.node_utils import build_human_message
from src.infra.async_utils import run_long_blocking_io
from src.infra.llm.quota import is_quota_error
from src.infra.llm.retry import is_retryable_model_error
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_session_id_from_runtime,
    get_user_id_from_runtime,
)
from src.kernel.config import settings
from src.kernel.errors import AppError

try:
    from langchain.tools import ToolRuntime  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    import sys
    import types

    _mod = types.ModuleType("langchain.tools")
    _mod.ToolRuntime = Any  # type: ignore[attr-defined]
    sys.modules.setdefault("langchain.tools", _mod)
    from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

logger = get_logger(__name__)

DEFAULT_VIDEO_ANALYSIS_PROMPT = "Describe the video content clearly and objectively."
DEFAULT_VIDEO_ANALYSIS_MAX_BYTES = 50 * 1024 * 1024
VIDEO_ANALYSIS_INTERNAL_RUN_CONFIG = {
    "metadata": {"lc_source": "video_analysis_tool", "internal_tool_call": True},
    "tags": ["internal_tool_call", "video_analysis_tool"],
}
_UPLOAD_FILE_MARKER = "/api/upload/file/"
_MODEL_TIMEOUT_SECONDS = 180
_DOWNLOAD_TIMEOUT_SECONDS = 60


def get_video_analysis_max_bytes() -> int:
    raw = getattr(settings, "VIDEO_ANALYSIS_MAX_BYTES", 0) or 0
    return raw if raw > 0 else DEFAULT_VIDEO_ANALYSIS_MAX_BYTES


def _guess_video_mime_type(file_path: str, content: bytes) -> str | None:
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and mime_type.startswith("video/"):
        return mime_type

    # 魔数兜底：mp4/mov 的 ftyp box、webm/mkv 的 EBML 头
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand.startswith(b"qt"):
            return "video/quicktime"
        return "video/mp4"
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        # EBML 容器：webm 优先报告（浏览器通配），mk4/mkv 同容器
        return "video/webm"
    return None


def _backend_path_from_video_reference(video_ref: str) -> str | None:
    ref = video_ref.strip()
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


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_long_blocking_io(json.dumps, data, ensure_ascii=False)


async def _download_uploaded_video(ref: str, runtime: Any, max_bytes: int) -> bytes | None:
    from src.infra.revealed_file.storage import get_revealed_file_storage
    from src.infra.storage.s3.service import get_or_init_storage
    from src.infra.upload.file_record import get_file_record_storage

    parsed = urlsplit(ref)
    base = urlsplit(get_base_url_from_runtime(runtime))
    if parsed.netloc and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.path.startswith(_UPLOAD_FILE_MARKER):
        return None
    key = unquote(parsed.path[len(_UPLOAD_FILE_MARKER) :])
    if "\\" in key or any(part in {"", ".", ".."} for part in key.split("/")):
        return None
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return None
    records = get_file_record_storage()
    if await records.is_private_key(key):
        await records.require_private_access(key, user_id, get_session_id_from_runtime(runtime))
    else:
        record = await records.find_by_key(key, user_id)
        if record and record.get("deleting_at"):
            return None
        if not record and not await get_revealed_file_storage().find_by_file_key(user_id, key):
            return None

    storage = await get_or_init_storage()
    content = bytearray()
    async with aclosing(storage.download_stream(key)) as stream:
        async for chunk in stream:
            if len(content) + len(chunk) > max_bytes:
                raise ValueError("video_too_large")
            content.extend(chunk)
    return bytes(content)


async def _call_with_retries(llm: Any, messages: list[Any]) -> Any:
    # One deadline covers all attempts and backoff, including SDK/network stalls.
    async with asyncio.timeout(_MODEL_TIMEOUT_SECONDS):
        return await _invoke_with_retries(llm, messages)


async def _invoke_with_retries(llm: Any, messages: list[Any]) -> Any:
    """与 image_analysis_tool 同款退避重试，但读视频工具自己的
    VIDEO_ANALYSIS_MAX_ATTEMPTS / VIDEO_ANALYSIS_RETRY_DELAY（一工具一套）。"""
    max_attempts = max(1, int(getattr(settings, "VIDEO_ANALYSIS_MAX_ATTEMPTS", 3) or 3))
    base_delay = float(getattr(settings, "VIDEO_ANALYSIS_RETRY_DELAY", 1.0) or 0)

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await llm.ainvoke(messages, config=VIDEO_ANALYSIS_INTERNAL_RUN_CONFIG)
        except Exception as exc:
            if is_quota_error(exc):
                raise
            last_exc = exc
            if attempt >= max_attempts or not is_retryable_model_error(exc):
                break
            delay = base_delay * (2 ** max(0, attempt - 1))
            logger.warning(
                "[video_analyze] model call failed with %s (attempt %d/%d), retrying in %.1fs",
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
async def video_analyze(
    video_urls: Annotated[
        list[str],
        "Sandbox video paths or your own LambChat /api/upload/file/ URLs (mp4/webm/mov). "
        "Webpage/share URLs are unsupported; download the actual video into the sandbox first.",
    ],
    prompt: Annotated[
        str,
        "Question or instruction for the vision model, such as what to describe in the video.",
    ] = DEFAULT_VIDEO_ANALYSIS_PROMPT,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None,
) -> str:
    """Analyze one or more videos with the configured vision-language model.
    Returns JSON {success, analysis, model_id, videos, errors?}."""
    from src.infra.llm.client import LLMClient, _resolve_use_responses
    from src.infra.llm.providers import _parse_provider, _resolve_protocol
    from src.infra.tool.image_analysis_tool import (
        _content_to_text,
        _download_file_from_backend,
        _resolve_model_config,
    )

    try:
        # 视频专用模型优先；未配置回落图片分析的 VLM（同一能力族）
        model_reference = str(getattr(settings, "VIDEO_ANALYSIS_MODEL_ID", "") or "").strip()
        fallback_reference = str(getattr(settings, "IMAGE_ANALYSIS_MODEL_ID", "") or "").strip()
        effective_reference = model_reference or fallback_reference
        configured_key = "VIDEO_ANALYSIS_MODEL_ID" if model_reference else "IMAGE_ANALYSIS_MODEL_ID"
        if not effective_reference:
            return await _json_dumps_result(
                {
                    "error": "Neither VIDEO_ANALYSIS_MODEL_ID nor IMAGE_ANALYSIS_MODEL_ID is configured"
                }
            )
        model_config = await _resolve_model_config(effective_reference)
        if not model_config:
            return await _json_dumps_result({"error": f"Configured {configured_key} not found"})
        if not model_config.profile or not model_config.profile.supports_vision:
            return await _json_dumps_result(
                {"error": f"Configured {configured_key} does not support vision"},
            )

        provider, _ = _parse_provider(model_config.value)
        protocol = _resolve_protocol(model_config.provider or provider)
        if protocol not in {"google", "openai"} or _resolve_use_responses(
            protocol, model_config.api_format
        ):
            return await _json_dumps_result(
                {
                    "success": False,
                    "error": "video_model_protocol_unsupported",
                    "message": "Configure VIDEO_ANALYSIS_MODEL_ID with a native video model "
                    "using Google or video-capable OpenAI Chat Completions. "
                    "Image vision support alone does not imply video support.",
                }
            )

        refs = [str(u).strip() for u in (video_urls or []) if str(u).strip()]
        if not refs:
            return await _json_dumps_result({"error": "video_urls must include at least one video"})

        backend = get_backend_from_runtime(runtime)
        max_bytes = get_video_analysis_max_bytes()
        attachments: list[dict[str, Any]] = []
        videos_meta: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for index, ref in enumerate(refs):
            backend_path = _backend_path_from_video_reference(ref)
            try:
                async with asyncio.timeout(_DOWNLOAD_TIMEOUT_SECONDS):
                    content = (
                        await _download_file_from_backend(backend, backend_path)
                        if backend is not None and backend_path is not None
                        else await _download_uploaded_video(ref, runtime, max_bytes)
                    )
            except AppError:
                errors.append({"url": ref, "error": "video_not_accessible"})
                continue
            except TimeoutError:
                errors.append({"url": ref, "error": "video_download_timeout"})
                continue
            except ValueError as exc:
                if str(exc) != "video_too_large":
                    raise
                errors.append({"url": ref, "error": "video_too_large", "max_bytes": max_bytes})
                continue
            if content is None:
                errors.append({"url": ref, "error": "video_not_accessible"})
                continue
            backend_path = backend_path or unquote(urlsplit(ref).path)
            if len(content) > max_bytes:
                logger.warning(
                    "[video_analyze] refusing oversized video: %s size=%s max=%s",
                    backend_path,
                    len(content),
                    max_bytes,
                )
                errors.append(
                    {
                        "url": ref,
                        "error": "video_too_large",
                        "size_bytes": len(content),
                        "max_bytes": max_bytes,
                    }
                )
                continue
            mime_type = _guess_video_mime_type(backend_path, content)
            if not mime_type:
                errors.append({"url": ref, "error": "unsupported_video_format"})
                continue

            encoded = await run_long_blocking_io(base64.b64encode, content)
            data_url = f"data:{mime_type};base64,{encoded.decode('ascii')}"
            attachments.append(
                {
                    "id": f"video-{index + 1}",
                    "name": os.path.basename(backend_path.rstrip("/")) or f"video-{index + 1}",
                    "type": "video",
                    "mime_type": mime_type,
                    "url": None,
                    "data_url": data_url,
                    "size": len(content),
                }
            )
            videos_meta.append({"url": ref, "mime_type": mime_type, "size_bytes": len(content)})

        if not attachments:
            return await _json_dumps_result({"success": False, "errors": errors})

        message = build_human_message(
            prompt or DEFAULT_VIDEO_ANALYSIS_PROMPT, attachments, supports_vision=True
        )
        if isinstance(message.content, str):
            return await _json_dumps_result({"success": False, "errors": errors})

        if protocol == "google":
            message.content = [
                {
                    "type": "video",
                    "mime_type": item["mime_type"],
                    "base64": item["data_url"].split(",", 1)[1],
                }
                if isinstance(part, dict) and part.get("type") == "video_url"
                else part
                for part, item in zip(message.content, [{}, *attachments], strict=True)
            ]

        llm = await LLMClient.get_model(model_config=model_config)
        response = await _call_with_retries(llm, [message])
        analysis = _content_to_text(getattr(response, "content", response))
        if not analysis.strip():
            return await _json_dumps_result({"success": False, "error": "empty_video_analysis"})
        return await _json_dumps_result(
            {
                "success": True,
                "analysis": analysis,
                "model_id": model_config.id or effective_reference,
                "videos": videos_meta,
                **({"errors": errors} if errors else {}),
            },
        )
    except TimeoutError:
        return await _json_dumps_result(
            {
                "success": False,
                "error": "video_analysis_timeout",
                "timeout_seconds": _MODEL_TIMEOUT_SECONDS,
            }
        )
    except Exception as exc:
        # 只记异常类型不记正文（对齐 image_analyze：请求体内嵌视频 data URL）
        if is_quota_error(exc):
            raise
        logger.warning("[video_analyze] failed: error_type=%s", type(exc).__name__)
        return await _json_dumps_result({"success": False, "error": "Video analysis failed"})


def get_video_analysis_tool() -> BaseTool:
    return video_analyze
