"""Internal data and parsing helpers for artifact delivery."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

from langchain_core.messages import ToolMessage

from src.infra.async_utils import run_blocking_io

RevealTool = Callable[..., Awaitable[str]]

_EXECUTE_SNAPSHOT_MAX_CHANGED_FILES = 20
_ARTIFACT_DELIVERY_CONCURRENCY = 4
_FILE_URL_PATTERN = re.compile(r"https?://[^\s<>\]\"']+", re.IGNORECASE)
_AUTO_DELIVERABLE_URL_EXTENSIONS = frozenset(
    {
        ".avif",
        ".bmp",
        ".csv",
        ".doc",
        ".docx",
        ".gif",
        ".gz",
        ".htm",
        ".html",
        ".jpeg",
        ".jpg",
        ".json",
        ".md",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".svg",
        ".tar",
        ".txt",
        ".wav",
        ".webm",
        ".webp",
        ".xls",
        ".xlsx",
        ".zip",
    }
)
_IGNORED_PATH_PARTS = frozenset(
    {
        ".cache",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
_SENSITIVE_FILENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)


@dataclass
class StagedArtifact:
    path: str
    kind: str = "file"
    name: str | None = None
    description: str = ""
    priority: str = "final"
    revealed: bool = False


@dataclass
class _ArtifactRunState:
    artifacts: dict[str, StagedArtifact] = field(default_factory=dict)
    background_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    delivery_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    artifact_generations: dict[str, int] = field(default_factory=dict)
    suppressed_paths: dict[str, int] = field(default_factory=dict)
    delivery_semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(_ARTIFACT_DELIVERY_CONCURRENCY)
    )
    accepting_tasks: bool = True
    emission_open: bool = True
    snapshot_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    baseline_snapshot_task: asyncio.Task[Any] | None = None
    last_snapshot: dict[str, tuple[int | None, str | None]] | None = None


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_blocking_io(json.dumps, data, ensure_ascii=False)


def _normalize_path(path: str) -> str:
    parsed = urlparse(path.strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return path.strip()
    return path.strip().replace("\\", "/").replace("//", "/").rstrip("/")


def _parse_jsonish(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _file_info_value(info: Any, key: str) -> Any:
    if isinstance(info, dict):
        return info.get(key)
    return getattr(info, key, None)


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _should_skip_auto_artifact(path: str) -> bool:
    parsed = urlparse(path.strip())
    normalized = unquote(parsed.path if parsed.scheme in {"http", "https"} else path)
    normalized = normalized.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if any(part in _IGNORED_PATH_PARTS for part in parts):
        return True
    filename = os.path.basename(normalized).lower()
    if filename in _SENSITIVE_FILENAMES:
        return True
    return filename.endswith((".log", ".tmp", ".temp", ".pyc", ".map"))


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                item_text = item.get("text") or item.get("content")
                if isinstance(item_text, str):
                    text_parts.append(item_text)
        return "\n".join(text_parts)
    return ""


def _is_auto_deliverable_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    clean_path = unquote(parsed.path)
    extension = os.path.splitext(clean_path)[1].lower()
    return extension in _AUTO_DELIVERABLE_URL_EXTENSIONS


def _extract_file_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _FILE_URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(".,;:!?)]}")
        if not _is_auto_deliverable_url(url) or _should_skip_auto_artifact(url):
            continue
        normalized = _normalize_path(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(url)
    return urls


async def _list_backend_files(backend: Any, workspace: str) -> list[Any]:
    result = await backend.aglob("**/*", path=workspace)
    if result.error:
        raise RuntimeError(f"Artifact workspace glob failed for {workspace}: {result.error}")
    return result.matches or []


def _path_from_reveal_result(result: ToolMessage, args: dict[str, Any]) -> str | None:
    parsed = _parse_jsonish(result.content)
    if parsed:
        meta = parsed.get("_meta") if isinstance(parsed.get("_meta"), dict) else None
        path = meta.get("path") if meta else None
        if isinstance(path, str) and path:
            return path

        if parsed.get("type") == "file_reveal" and isinstance(parsed.get("file"), dict):
            file_path = parsed["file"].get("path")
            if isinstance(file_path, str) and file_path:
                return file_path

        project_path = parsed.get("path") or parsed.get("project_path")
        if isinstance(project_path, str) and project_path:
            return project_path

    fallback = args.get("file_path") or args.get("project_path") or args.get("path")
    return fallback if isinstance(fallback, str) and fallback else None


def _reveal_error(parsed: dict[str, Any] | None) -> str | None:
    if not parsed:
        return None
    error = parsed.get("error")
    if isinstance(error, str) and error:
        return error
    message = parsed.get("message")
    if isinstance(message, str) and parsed.get("error"):
        return message
    file = parsed.get("file")
    if isinstance(file, dict):
        file_error = file.get("error")
        if isinstance(file_error, str) and file_error:
            return file_error
    return None
