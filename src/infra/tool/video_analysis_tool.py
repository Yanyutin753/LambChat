"""Vision model video analysis tool for LambChat agents（对齐 image_analysis_tool）.

复用 IMAGE_ANALYSIS_MODEL_ID 的 VLM：支持视觉的模型按 provider 约定同样
接受 ``video_url`` 块（GLM-4V 系等 OpenAI 兼容形态）。视频不压缩（无服务端
转码设施），以 ``VIDEO_ANALYSIS_MAX_BYTES`` 硬限制体量——base64 膨胀 ×4/3，
超限整文件拒绝并回报上限，避免把上下文/请求体打爆。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

from langchain_core.tools import BaseTool, InjectedToolArg

from src.agents.core.node_utils import build_human_message
from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime
from src.kernel.config import settings

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
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


@tool
async def video_analyze(
    video_urls: Annotated[
        list[str],
        "Video URLs or project file URLs to inspect (mp4/webm/mov). Provide one or more videos.",
    ],
    prompt: Annotated[
        str,
        "Question or instruction for the vision model, such as what to describe in the video.",
    ] = DEFAULT_VIDEO_ANALYSIS_PROMPT,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None,
) -> str:
    """Analyze one or more videos with the configured vision-language model."""
    from src.infra.llm.client import LLMClient
    from src.infra.tool.image_analysis_tool import (
        _call_with_retries,
        _content_to_text,
        _download_file_from_backend,
        _resolve_model_config,
    )

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
                {"error": "Configured IMAGE_ANALYSIS_MODEL_ID does not support vision"},
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
            if backend is None or backend_path is None:
                # 非 backend 可解析引用（http/data 等）没有字节来源，无法
                # 内联为 video_url 块——VLM 视频必须内联字节
                errors.append({"url": ref, "error": "video_not_accessible"})
                continue

            content = await _download_file_from_backend(backend, backend_path)
            if content is None:
                errors.append({"url": ref, "error": "video_download_failed"})
                continue
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

            encoded = await run_blocking_io(base64.b64encode, content)
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

        llm = await LLMClient.get_model(model_config=model_config)
        response = await _call_with_retries(llm, [message])
        analysis = _content_to_text(getattr(response, "content", response))
        return await _json_dumps_result(
            {
                "success": True,
                "analysis": analysis,
                "model_id": model_config.id or model_reference,
                "videos": videos_meta,
                **({"errors": errors} if errors else {}),
            },
        )
    except Exception as exc:
        # 只记异常类型不记正文（对齐 image_analyze：请求体内嵌视频 data URL）
        logger.warning("[video_analyze] failed: error_type=%s", type(exc).__name__)
        return await _json_dumps_result({"error": "Video analysis failed"})


def get_video_analysis_tool() -> BaseTool:
    return video_analyze
