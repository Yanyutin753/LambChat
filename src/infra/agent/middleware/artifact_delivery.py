"""Artifact delivery middleware — auto-deliver generated files without tool chrome."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import unquote, urlparse

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from src.infra.async_utils import run_blocking_io

RevealTool = Callable[..., Awaitable[str]]

logger = logging.getLogger(__name__)
_EXECUTE_SNAPSHOT_MAX_CHANGED_FILES = 20
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
    if hasattr(backend, "aglob_info"):
        return await backend.aglob_info("**/*", path=workspace)
    if hasattr(backend, "aglob"):
        result = await backend.aglob("**/*", path=workspace)
        return getattr(result, "matches", result) or []
    if hasattr(backend, "glob_info"):
        return await run_blocking_io(backend.glob_info, "**/*", workspace)
    if hasattr(backend, "glob"):
        result = await run_blocking_io(backend.glob, "**/*", workspace)
        return getattr(result, "matches", result) or []
    return []


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


class ArtifactDeliveryMiddleware(AgentMiddleware):
    """Detect sandbox artifacts, index them, and emit artifact result events."""

    def __init__(
        self,
        *,
        reveal_file: RevealTool | None = None,
        reveal_project: RevealTool | None = None,
        workspace_path: str | None = None,
    ) -> None:
        super().__init__()
        self._artifacts: dict[str, StagedArtifact] = {}
        self._reveal_file = reveal_file
        self._reveal_project = reveal_project
        self._workspace_path = workspace_path.rstrip("/") if workspace_path else None

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        before_snapshot = None
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        if tool_name == "execute":
            before_snapshot = await self._snapshot_workspace(request.runtime)

        result = await handler(request)
        if not isinstance(result, ToolMessage):
            return result

        if tool_name == "execute":
            staged = await self._auto_stage_execute_changes(
                request.runtime,
                before_snapshot,
                result,
            )
            await self._deliver_staged_artifacts(staged, request.runtime)
            return result

        if tool_name in {"reveal_file", "reveal_project"}:
            self._mark_revealed(result, tool_args)
            return result

        staged = self._auto_stage_from_tool_result(tool_name, tool_args, result)
        await self._deliver_staged_artifacts(staged, request.runtime)
        return result

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._auto_stage_external_urls_from_state(state)
        pending = [artifact for artifact in self._artifacts.values() if not artifact.revealed]
        if not pending:
            return None

        for artifact in pending:
            delivered = await self._deliver_artifact(artifact, runtime)
            if delivered:
                artifact.revealed = True

        return {"messages": []}

    def _auto_stage_external_urls_from_state(self, state: Any) -> None:
        messages = state.get("messages") if isinstance(state, dict) else None
        if not isinstance(messages, list):
            return

        for message in messages:
            if getattr(message, "type", None) not in {"ai", "assistant"}:
                continue
            content = _content_to_text(getattr(message, "content", ""))
            if not content:
                continue
            for url in _extract_file_urls_from_text(content):
                self._stage_path(
                    url,
                    kind="file",
                    description="External file linked by the agent",
                    priority="intermediate",
                )

    def _mark_revealed(self, result: ToolMessage, args: dict[str, Any]) -> None:
        path = _path_from_reveal_result(result, args)
        if not path:
            return

        normalized_path = _normalize_path(path)
        existing = self._artifacts.get(normalized_path)
        if existing is None:
            self._artifacts[normalized_path] = StagedArtifact(
                path=path,
                kind="project" if result.name == "reveal_project" else "file",
                revealed=True,
            )
            return
        existing.revealed = True

    def _auto_stage_from_tool_result(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: ToolMessage,
    ) -> list[StagedArtifact]:
        if getattr(result, "status", None) == "error":
            return []

        parsed = _parse_jsonish(result.content)
        if isinstance(parsed, dict) and (
            parsed.get("success") is False or parsed.get("error") is not None
        ):
            return []

        path = self._artifact_path_from_tool(tool_name, args, parsed)
        if not path:
            return []

        artifact = self._stage_path(
            path,
            kind="file",
            description=self._description_from_auto_stage(tool_name),
            priority="intermediate",
        )
        return [artifact] if artifact is not None else []

    @staticmethod
    def _artifact_path_from_tool(
        tool_name: str,
        args: dict[str, Any],
        parsed: dict[str, Any] | None,
    ) -> str | None:
        if tool_name == "upload_url_to_sandbox":
            result_path = parsed.get("path") if parsed else None
            if isinstance(result_path, str) and result_path:
                return result_path

        if tool_name in {"write_file", "edit_file"}:
            for key in ("file_path", "path"):
                path = args.get(key)
                if isinstance(path, str) and path:
                    return path

        return None

    @staticmethod
    def _description_from_auto_stage(tool_name: str) -> str:
        match tool_name:
            case "write_file":
                return "File created by the agent"
            case "edit_file":
                return "File modified by the agent"
            case "upload_url_to_sandbox":
                return "File downloaded into the sandbox"
            case _:
                return ""

    def _stage_path(
        self,
        path: str,
        *,
        kind: str,
        name: str | None = None,
        description: str = "",
        priority: str = "final",
    ) -> StagedArtifact | None:
        normalized_path = _normalize_path(path)
        if kind == "file" and _should_skip_auto_artifact(normalized_path):
            return None
        artifact = StagedArtifact(
            path=path,
            kind=kind,
            name=name,
            description=description,
            priority=priority,
        )
        self._artifacts[normalized_path] = artifact
        return artifact

    async def _auto_stage_execute_changes(
        self,
        runtime: Any,
        before_snapshot: dict[str, tuple[int | None, str | None]] | None,
        result: ToolMessage,
    ) -> list[StagedArtifact]:
        if before_snapshot is None or getattr(result, "status", None) == "error":
            return []
        parsed = _parse_jsonish(result.content)
        if isinstance(parsed, dict) and (
            parsed.get("success") is False or parsed.get("error") is not None
        ):
            return []

        after_snapshot = await self._snapshot_workspace(runtime)
        if after_snapshot is None:
            return []

        changed_paths: list[str] = []
        for path, signature in after_snapshot.items():
            if before_snapshot.get(path) != signature and not _should_skip_auto_artifact(path):
                changed_paths.append(path)
            if len(changed_paths) >= _EXECUTE_SNAPSHOT_MAX_CHANGED_FILES:
                break

        staged: list[StagedArtifact] = []
        for path in changed_paths:
            artifact = self._stage_path(
                path,
                kind="file",
                description="File created or modified by a shell command",
                priority="intermediate",
            )
            if artifact is not None:
                staged.append(artifact)
        return staged

    async def _snapshot_workspace(
        self, runtime: Any
    ) -> dict[str, tuple[int | None, str | None]] | None:
        workspace = self._workspace_path or self._workspace_from_runtime(runtime)
        if not workspace:
            return None
        backend = self._backend_from_runtime(runtime)
        if backend is None:
            return None

        try:
            infos = await _list_backend_files(backend, workspace)
        except Exception as exc:
            logger.debug("Artifact workspace snapshot failed for %s: %s", workspace, exc)
            return None

        snapshot: dict[str, tuple[int | None, str | None]] = {}
        for info in infos:
            path = _file_info_value(info, "path")
            if not isinstance(path, str) or not path or _file_info_value(info, "is_dir"):
                continue
            snapshot[path] = (
                _coerce_int(_file_info_value(info, "size")),
                _coerce_str(_file_info_value(info, "modified_at")),
            )
        return snapshot

    @staticmethod
    def _workspace_from_runtime(runtime: Any) -> str | None:
        backend = ArtifactDeliveryMiddleware._backend_from_runtime(runtime)
        work_dir = getattr(backend, "work_dir", None)
        if isinstance(work_dir, str) and work_dir:
            return work_dir.rstrip("/")
        workspace_path = getattr(backend, "workspace_path", None)
        if isinstance(workspace_path, str) and workspace_path:
            return workspace_path.rstrip("/")

        config = getattr(runtime, "config", None)
        configurable = config.get("configurable") if isinstance(config, dict) else None
        if isinstance(configurable, dict):
            for key in ("work_dir", "workspace_path"):
                value = configurable.get(key)
                if isinstance(value, str) and value:
                    return value.rstrip("/")
        return None

    @staticmethod
    def _backend_from_runtime(runtime: Any) -> Any | None:
        try:
            from src.infra.tool.backend_utils import get_backend_from_runtime

            return get_backend_from_runtime(runtime)
        except Exception:
            return None

    async def _deliver_artifact(self, artifact: StagedArtifact, runtime: Any) -> bool:
        is_project = artifact.kind in {"project", "folder"}
        tool_name = "reveal_project" if is_project else "reveal_file"
        args: dict[str, Any]
        if is_project:
            args = {
                "project_path": artifact.path,
                "name": artifact.name or artifact.path.rstrip("/").rsplit("/", 1)[-1],
            }
            if artifact.description:
                args["description"] = artifact.description
        else:
            args = {
                "file_path": artifact.path,
                "description": artifact.description,
            }

        try:
            content = await self._call_reveal_tool(tool_name, args, runtime)
            parsed = _parse_jsonish(content)
            error = _reveal_error(parsed)
            if error:
                delivered = self._failed_artifact_payload(artifact, error)
                status = "error"
            else:
                delivered = self._artifact_payload_from_reveal_content(artifact, content, args)
                status = "success"
        except Exception as exc:
            logger.warning("Artifact reveal failed for %s: %s", artifact.path, exc)
            content = await _json_dumps_result(
                {
                    "type": "artifact_reveal_failed",
                    "path": artifact.path,
                    "kind": artifact.kind,
                    "error": str(exc),
                }
            )
            delivered = self._failed_artifact_payload(artifact, str(exc))
            status = "error"
            error = str(exc)

        return await self._emit_artifact_result(runtime, delivered, status=status, error=error)

    async def _deliver_staged_artifacts(
        self,
        artifacts: list[StagedArtifact],
        runtime: Any,
    ) -> None:
        if self._get_presenter(runtime) is None:
            return
        for artifact in artifacts:
            if artifact.revealed:
                continue
            delivered = await self._deliver_artifact(artifact, runtime)
            if delivered:
                artifact.revealed = True

    async def _call_reveal_tool(self, tool_name: str, args: dict[str, Any], runtime: Any) -> str:
        delivery_runtime = self._runtime_with_delivery_source(runtime, "artifact_auto")
        if tool_name == "reveal_project":
            reveal_project = self._reveal_project
            if reveal_project is None:
                from src.infra.tool.reveal_project_tool import reveal_project as reveal_project_tool

                reveal_project = cast(RevealTool, getattr(reveal_project_tool, "coroutine"))

            return await reveal_project(**args, runtime=delivery_runtime)

        reveal_file = self._reveal_file
        if reveal_file is None:
            from src.infra.tool.reveal_file_tool import reveal_file as reveal_file_tool

            reveal_file = cast(RevealTool, getattr(reveal_file_tool, "coroutine"))

        return await reveal_file(**args, runtime=delivery_runtime)

    @staticmethod
    def _runtime_with_delivery_source(runtime: Any, delivery_source: str) -> Any:
        config = getattr(runtime, "config", None)
        if not isinstance(config, dict):
            return SimpleNamespace(config={"configurable": {"delivery_source": delivery_source}})

        next_config = dict(config)
        configurable = next_config.get("configurable")
        if isinstance(configurable, dict):
            next_config["configurable"] = {
                **configurable,
                "delivery_source": delivery_source,
            }
        else:
            next_config["configurable"] = {"delivery_source": delivery_source}
        return SimpleNamespace(config=next_config)

    @staticmethod
    def _get_presenter(runtime: Any) -> Any | None:
        config = getattr(runtime, "config", None)
        if not isinstance(config, dict):
            return None
        configurable = config.get("configurable")
        if not isinstance(configurable, dict):
            return None
        return configurable.get("presenter")

    async def _emit_artifact_result(
        self,
        runtime: Any,
        artifact: dict[str, Any],
        *,
        status: str,
        error: str | None,
    ) -> bool:
        presenter = self._get_presenter(runtime)
        if presenter is None or not hasattr(presenter, "present_artifact_result"):
            return False

        event = presenter.present_artifact_result(
            artifact,
            success=status != "error",
            error=error,
        )
        emit = getattr(presenter, "emit", None)
        if callable(emit):
            await emit(event)
            return True
        return False

    def _artifact_payload_from_reveal_content(
        self,
        artifact: StagedArtifact,
        content: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        parsed = _parse_jsonish(content) or {}
        if artifact.kind in {"project", "folder"}:
            return self._project_artifact_payload(artifact, parsed, args)
        return self._file_artifact_payload(artifact, parsed)

    @staticmethod
    def _file_artifact_payload(artifact: StagedArtifact, parsed: dict[str, Any]) -> dict[str, Any]:
        raw_meta = parsed.get("_meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        meta_path = meta.get("path")
        file_path = meta_path if isinstance(meta_path, str) and meta_path else artifact.path
        s3_key = parsed.get("key") if isinstance(parsed.get("key"), str) else None
        s3_url = parsed.get("url") if isinstance(parsed.get("url"), str) else None
        name = parsed.get("name") if isinstance(parsed.get("name"), str) else None
        file_size = parsed.get("size") if isinstance(parsed.get("size"), int) else None
        preview_key = s3_key or s3_url or file_path
        meta_description = meta.get("description")
        description = (
            meta_description if isinstance(meta_description, str) else artifact.description
        )

        return {
            "kind": "file",
            "id": f"file:{preview_key}",
            "name": name or file_path.rstrip("/").rsplit("/", 1)[-1] or file_path,
            "path": file_path,
            "description": description,
            "fileSize": file_size,
            "preview": {
                "kind": "file",
                "previewKey": preview_key,
                "filePath": file_path,
                "s3Key": s3_key,
                "signedUrl": s3_url,
                "fileSize": file_size,
            },
        }

    @staticmethod
    def _project_artifact_payload(
        artifact: StagedArtifact,
        parsed: dict[str, Any],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        parsed_path = parsed.get("path")
        args_project_path = args.get("project_path")
        project_path = (
            parsed_path
            if isinstance(parsed_path, str) and parsed_path
            else args_project_path
            if isinstance(args_project_path, str) and args_project_path
            else artifact.path
        )
        parsed_name = parsed.get("name")
        args_name = args.get("name")
        project_name = (
            parsed_name
            if isinstance(parsed_name, str) and parsed_name
            else args_name
            if isinstance(args_name, str) and args_name
            else artifact.name or project_path.rstrip("/").rsplit("/", 1)[-1]
        )
        mode = parsed.get("mode") if parsed.get("mode") in {"project", "folder"} else "folder"
        template = parsed.get("template") if isinstance(parsed.get("template"), str) else "static"
        file_count = parsed.get("file_count") if isinstance(parsed.get("file_count"), int) else 0
        preview_key = project_path or project_name

        return {
            "kind": "project",
            "id": f"project:{preview_key}",
            "name": project_name,
            "mode": mode,
            "fileCount": file_count,
            "template": template,
            "preview": {
                "kind": "project",
                "previewKey": preview_key,
                "project": parsed,
            },
        }

    @staticmethod
    def _failed_artifact_payload(artifact: StagedArtifact, error: str) -> dict[str, Any]:
        return {
            "kind": artifact.kind,
            "id": f"failed:{artifact.path}",
            "name": artifact.name or artifact.path.rstrip("/").rsplit("/", 1)[-1],
            "path": artifact.path,
            "description": artifact.description,
            "error": error,
        }
