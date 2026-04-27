"""Audio transcription tool backed by OpenAI-compatible audio/transcriptions."""

from __future__ import annotations

import inspect
import io
import json
import sys
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg
from openai import AsyncOpenAI

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_base_url_from_runtime
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


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _resolve_url(url: str, runtime: ToolRuntime | None) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        base_url = get_base_url_from_runtime(runtime)
        if base_url:
            return f"{base_url}{url}"
    return url


def _guess_filename(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] if path else "audio"


def _build_client() -> AsyncOpenAI | None:
    api_key = getattr(settings, "AUDIO_TRANSCRIPTION_API_KEY", "") or ""
    if not api_key:
        return None

    base_url = getattr(settings, "AUDIO_TRANSCRIPTION_BASE_URL", "") or None
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    return AsyncOpenAI(**client_kwargs)


@tool
async def audio_transcribe(
    url: Annotated[
        str, "URL of the audio file to transcribe. Supports absolute URLs and /api paths."
    ],
    model: Annotated[
        str | None,
        "Optional transcription model override, such as gpt-4o-mini-transcribe or FunAudioLLM/SenseVoiceSmall.",
    ] = None,
    language: Annotated[str | None, "Optional language hint, such as en or zh."] = None,
    prompt: Annotated[str | None, "Optional transcription prompt to improve recognition."] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Download one audio file by URL and transcribe it into text."""

    resolved_url = _resolve_url(url, runtime)

    client = _build_client()
    if client is None:
        return _json({"error": "AUDIO_TRANSCRIPTION_API_KEY is not configured"})

    resolved_model = (
        model or getattr(settings, "AUDIO_TRANSCRIPTION_MODEL", "") or "gpt-4o-mini-transcribe"
    )

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as http_client:
            response = await _maybe_await(http_client.get(resolved_url))
            response.raise_for_status()
        file_bytes = response.content

        file_obj = io.BytesIO(file_bytes)
        file_obj.name = _guess_filename(resolved_url)  # type: ignore[attr-defined]

        request: dict[str, Any] = {
            "file": file_obj,
            "model": resolved_model,
        }
        if language:
            request["language"] = language
        if prompt:
            request["prompt"] = prompt

        result = await client.audio.transcriptions.create(**request)
    except Exception as exc:
        logger.warning("[audio_transcribe] transcription failed for %s: %s", resolved_url, exc)
        return _json({"error": f"Audio transcription failed: {exc}"})

    text = getattr(result, "text", None)
    if text is None and isinstance(result, str):
        text = result

    payload = {
        "success": True,
        "text": text or "",
        "url": resolved_url,
        "filename": file_obj.name,
        "model": resolved_model,
    }
    response_language = getattr(result, "language", None)
    if response_language:
        payload["language"] = response_language
    response_duration = getattr(result, "duration", None)
    if response_duration is not None:
        payload["duration"] = response_duration

    return _json(payload)


def get_audio_transcribe_tool() -> BaseTool:
    return audio_transcribe
