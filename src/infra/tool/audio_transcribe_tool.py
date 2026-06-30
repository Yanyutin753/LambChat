"""Audio transcription tool backed by OpenAI-compatible audio/transcriptions."""

from __future__ import annotations

import inspect
import json
import sys
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import urlparse

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg
from openai import AsyncOpenAI

from src.infra.async_utils import run_blocking_io
from src.infra.extensions import PluginSettingsResolver
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_base_url_from_runtime
from src.kernel.extensions.builtin_plugins import AUDIO_TRANSCRIPTION_PLUGIN_ID

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

# Bound remote audio downloads before forwarding them to the transcription API.
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


def _settings_resolver() -> PluginSettingsResolver:
    return PluginSettingsResolver(plugin_id=AUDIO_TRANSCRIPTION_PLUGIN_ID)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


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


async def _build_client() -> AsyncOpenAI | None:
    resolver = _settings_resolver()
    api_key = await resolver.get_secret("API_KEY")
    if not api_key:
        return None

    base_url = await resolver.get_str("BASE_URL", "") or None
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    return AsyncOpenAI(**client_kwargs)


async def _close_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if close is None:
        return
    try:
        await _maybe_await(close())
    except Exception as exc:
        logger.debug("[audio_transcribe] failed to close OpenAI client: %s", exc)


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

    resolver = _settings_resolver()
    client = await _build_client()
    if client is None:
        return await _json_dumps_result({"error": "AUDIO_TRANSCRIPTION_API_KEY is not configured"})

    resolved_model = model or await resolver.get_str("MODEL", "gpt-4o-mini-transcribe")

    try:
        try:
            filename = _guess_filename(resolved_url)
            with SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b") as file_obj:
                max_download_bytes = max(
                    await resolver.get_int("MAX_DOWNLOAD_BYTES", _MAX_DOWNLOAD_BYTES),
                    1,
                )
                total_size = 0
                async with httpx.AsyncClient(follow_redirects=True, timeout=60) as http_client:
                    async with http_client.stream("GET", resolved_url) as response:
                        response.raise_for_status()
                        known_size = _known_download_size(getattr(response, "headers", {}))
                        if known_size is not None and known_size > max_download_bytes:
                            return await _json_dumps_result(
                                {"error": f"Audio download exceeds {max_download_bytes} bytes"}
                            )
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            total_size += len(chunk)
                            if total_size > max_download_bytes:
                                return await _json_dumps_result(
                                    {
                                        "error": (
                                            f"Audio download exceeds {max_download_bytes} bytes"
                                        )
                                    }
                                )
                            await run_blocking_io(file_obj.write, chunk)
                await run_blocking_io(file_obj.seek, 0)

                request: dict[str, Any] = {
                    "file": (filename, file_obj),
                    "model": resolved_model,
                }
                if language:
                    request["language"] = language
                if prompt:
                    request["prompt"] = prompt

                result = await client.audio.transcriptions.create(**request)
        except Exception as exc:
            logger.warning("[audio_transcribe] transcription failed for %s: %s", resolved_url, exc)
            return await _json_dumps_result({"error": f"Audio transcription failed: {exc}"})

        text = getattr(result, "text", None)
        if text is None and isinstance(result, str):
            text = result

        payload = {
            "success": True,
            "text": text or "",
            "url": resolved_url,
            "filename": filename,
            "model": resolved_model,
        }
        response_language = getattr(result, "language", None)
        if response_language:
            payload["language"] = response_language
        response_duration = getattr(result, "duration", None)
        if response_duration is not None:
            payload["duration"] = response_duration

        return await _json_dumps_result(payload)
    finally:
        await _close_client(client)


def get_audio_transcribe_tool() -> BaseTool:
    return audio_transcribe
