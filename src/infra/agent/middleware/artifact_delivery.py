"""Artifact delivery middleware — auto-deliver generated files without tool chrome."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Coroutine
from types import SimpleNamespace
from typing import Any, cast

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from src.infra.agent.middleware._artifact_delivery_support import (
    _ARTIFACT_DELIVERY_CONCURRENCY as _ARTIFACT_DELIVERY_CONCURRENCY,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _AUTO_DELIVERABLE_URL_EXTENSIONS as _AUTO_DELIVERABLE_URL_EXTENSIONS,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _EXECUTE_SNAPSHOT_MAX_CHANGED_FILES,
    RevealTool,
    StagedArtifact,
    _ArtifactRunState,
    _coerce_int,
    _coerce_str,
    _content_to_text,
    _extract_file_urls_from_text,
    _file_info_value,
    _json_dumps_result,
    _list_backend_files,
    _normalize_path,
    _parse_jsonish,
    _path_from_reveal_result,
    _reveal_error,
    _should_skip_auto_artifact,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _FILE_URL_PATTERN as _FILE_URL_PATTERN,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _IGNORED_PATH_PARTS as _IGNORED_PATH_PARTS,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _SENSITIVE_FILENAMES as _SENSITIVE_FILENAMES,
)
from src.infra.agent.middleware._artifact_delivery_support import (
    _is_auto_deliverable_url as _is_auto_deliverable_url,
)

logger = logging.getLogger(__name__)
_ARTIFACT_BACKGROUND_DRAIN_TIMEOUT = 3.0
_ARTIFACT_BACKGROUND_CANCEL_GRACE = 0.05


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
        self._reveal_file = reveal_file
        self._reveal_project = reveal_project
        self._workspace_path = workspace_path.rstrip("/") if workspace_path else None
        self._runs: dict[object, _ArtifactRunState] = {}
        self._fallback_run_key = object()

    def _run_key(self, runtime: Any) -> object:
        stream_writer = getattr(runtime, "stream_writer", None)
        if stream_writer is None:
            config = getattr(runtime, "config", None)
            configurable = config.get("configurable") if isinstance(config, dict) else None
            pregel_runtime = (
                configurable.get("__pregel_runtime") if isinstance(configurable, dict) else None
            )
            stream_writer = getattr(pregel_runtime, "stream_writer", None)
        return stream_writer if stream_writer is not None else self._fallback_run_key

    def _run_state(self, runtime: Any) -> tuple[object, _ArtifactRunState]:
        key = self._run_key(runtime)
        run = self._runs.get(key)
        if run is None:
            run = _ArtifactRunState()
            self._runs[key] = run
        return key, run

    async def abefore_agent(self, state: Any, runtime: Any) -> None:
        del state
        _, run = self._run_state(runtime)
        if run.baseline_snapshot_task is None:
            run.baseline_snapshot_task = self._schedule_workspace_snapshot(
                run,
                runtime,
                name="initial-snapshot",
            )

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        _, run = self._run_state(request.runtime)
        before_snapshot_task = None
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        if tool_name == "execute":
            before_snapshot_task = self._schedule_workspace_snapshot(
                run,
                request.runtime,
                name="before-execute-snapshot",
            )

        explicit_path = None
        if tool_name in {"reveal_file", "reveal_project"}:
            explicit_path = self._suppress_auto_delivery(run, tool_args)

        try:
            result = await handler(request)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._resume_auto_delivery(run, explicit_path, request.runtime)
            raise
        if not isinstance(result, ToolMessage):
            self._resume_auto_delivery(run, explicit_path, request.runtime)
            return result

        if tool_name == "execute":
            self._track_background_task(
                run,
                self._process_execute_changes(
                    run,
                    request.runtime,
                    before_snapshot_task,
                    result,
                ),
                name="execute-changes",
            )
            return result

        if tool_name in {"reveal_file", "reveal_project"}:
            if self._mark_revealed(run, result, tool_args):
                if explicit_path is not None:
                    existing = run.artifacts.get(explicit_path)
                    if existing is not None:
                        existing.revealed = True
                self._release_auto_suppression(run, explicit_path)
            else:
                self._resume_auto_delivery(run, explicit_path, request.runtime)
            return result

        staged = self._auto_stage_from_tool_result(run, tool_name, tool_args, result)
        self._deliver_staged_artifacts(run, staged, request.runtime)
        return result

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        key, run = self._run_state(runtime)
        try:
            self._auto_stage_external_urls_from_state(run, state)
            artifact_count_before_drain = len(run.artifacts)
            had_pending_artifacts = False
            for artifact in run.artifacts.values():
                if not artifact.revealed:
                    had_pending_artifacts = True
                    self._schedule_artifact_delivery(
                        run,
                        artifact,
                        runtime,
                        allow_without_presenter=True,
                    )
            await self._drain_background_tasks(run)
            found_artifacts_during_drain = len(run.artifacts) > artifact_count_before_drain
            if had_pending_artifacts or found_artifacts_during_drain:
                return {"messages": []}
            return None
        finally:
            if self._runs.get(key) is run:
                self._runs.pop(key, None)

    def _auto_stage_external_urls_from_state(
        self,
        run: _ArtifactRunState,
        state: Any,
    ) -> None:
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
                    run,
                    url,
                    kind="file",
                    description="External file linked by the agent",
                    priority="intermediate",
                )

    @staticmethod
    def _explicit_path(args: dict[str, Any]) -> str | None:
        path = args.get("file_path") or args.get("project_path") or args.get("path")
        return _normalize_path(path) if isinstance(path, str) and path else None

    def _suppress_auto_delivery(
        self,
        run: _ArtifactRunState,
        args: dict[str, Any],
    ) -> str | None:
        normalized_path = self._explicit_path(args)
        if normalized_path is None:
            return None
        run.suppressed_paths[normalized_path] = run.suppressed_paths.get(normalized_path, 0) + 1
        run.artifact_generations[normalized_path] = (
            run.artifact_generations.get(normalized_path, 0) + 1
        )
        delivery_task = run.delivery_tasks.get(normalized_path)
        if delivery_task is not None and not delivery_task.done():
            delivery_task.cancel()
        return normalized_path

    @staticmethod
    def _release_auto_suppression(
        run: _ArtifactRunState,
        normalized_path: str | None,
    ) -> bool:
        if normalized_path is None:
            return False
        count = run.suppressed_paths.get(normalized_path, 0)
        if count > 1:
            run.suppressed_paths[normalized_path] = count - 1
            return False
        run.suppressed_paths.pop(normalized_path, None)
        return count == 1

    def _resume_auto_delivery(
        self,
        run: _ArtifactRunState,
        normalized_path: str | None,
        runtime: Any,
    ) -> None:
        if normalized_path is None:
            return
        if not self._release_auto_suppression(run, normalized_path):
            return
        self._schedule_resumed_auto_delivery(run, normalized_path, runtime)

    def _schedule_resumed_auto_delivery(
        self,
        run: _ArtifactRunState,
        normalized_path: str,
        runtime: Any,
    ) -> None:
        artifact = run.artifacts.get(normalized_path)
        if artifact is None or artifact.revealed or not run.accepting_tasks:
            return

        active = run.delivery_tasks.get(normalized_path)
        if active is not None and not active.done():

            def resume_after_active(_done_task: asyncio.Task[Any]) -> None:
                self._schedule_resumed_auto_delivery(run, normalized_path, runtime)

            active.add_done_callback(resume_after_active)
            return
        self._schedule_artifact_delivery(run, artifact, runtime)

    def _mark_revealed(
        self,
        run: _ArtifactRunState,
        result: ToolMessage,
        args: dict[str, Any],
    ) -> bool:
        parsed = _parse_jsonish(result.content)
        if (
            getattr(result, "status", None) == "error"
            or (isinstance(parsed, dict) and parsed.get("success") is False)
            or _reveal_error(parsed) is not None
        ):
            return False
        path = _path_from_reveal_result(result, args)
        if not path:
            return False

        normalized_path = _normalize_path(path)
        run.artifact_generations[normalized_path] = (
            run.artifact_generations.get(normalized_path, 0) + 1
        )
        delivery_task = run.delivery_tasks.get(normalized_path)
        if delivery_task is not None and not delivery_task.done():
            delivery_task.cancel()
        existing = run.artifacts.get(normalized_path)
        if existing is None:
            run.artifacts[normalized_path] = StagedArtifact(
                path=path,
                kind="project" if result.name == "reveal_project" else "file",
                revealed=True,
            )
            return True
        existing.revealed = True
        return True

    def _auto_stage_from_tool_result(
        self,
        run: _ArtifactRunState,
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
            run,
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
        run: _ArtifactRunState,
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
        run.artifacts[normalized_path] = artifact
        run.artifact_generations[normalized_path] = (
            run.artifact_generations.get(normalized_path, 0) + 1
        )
        return artifact

    async def _process_execute_changes(
        self,
        run: _ArtifactRunState,
        runtime: Any,
        before_task: asyncio.Task[Any] | None,
        result: ToolMessage,
    ) -> None:
        if getattr(result, "status", None) == "error":
            return
        parsed = _parse_jsonish(result.content)
        if isinstance(parsed, dict) and (
            parsed.get("success") is False or parsed.get("error") is not None
        ):
            return

        before_snapshot = None
        if before_task is not None:
            with contextlib.suppress(Exception):
                before_snapshot = await before_task
        if before_snapshot is None and run.baseline_snapshot_task is not None:
            with contextlib.suppress(Exception):
                before_snapshot = await run.baseline_snapshot_task
        if before_snapshot is None:
            before_snapshot = run.last_snapshot

        after_snapshot = await self._take_workspace_snapshot(run, runtime)
        if before_snapshot is None or after_snapshot is None:
            return

        staged = self._stage_snapshot_changes(run, before_snapshot, after_snapshot)
        self._deliver_staged_artifacts(
            run,
            staged,
            runtime,
            allow_without_presenter=True,
        )

    def _stage_snapshot_changes(
        self,
        run: _ArtifactRunState,
        before_snapshot: dict[str, tuple[int | None, str | None]],
        after_snapshot: dict[str, tuple[int | None, str | None]],
    ) -> list[StagedArtifact]:
        changed_paths: list[str] = []
        for path, signature in after_snapshot.items():
            if before_snapshot.get(path) != signature and not _should_skip_auto_artifact(path):
                changed_paths.append(path)
            if len(changed_paths) >= _EXECUTE_SNAPSHOT_MAX_CHANGED_FILES:
                break

        staged: list[StagedArtifact] = []
        for path in changed_paths:
            artifact = self._stage_path(
                run,
                path,
                kind="file",
                description="File created or modified by a shell command",
                priority="intermediate",
            )
            if artifact is not None:
                staged.append(artifact)
        return staged

    async def _take_workspace_snapshot(
        self,
        run: _ArtifactRunState,
        runtime: Any,
    ) -> dict[str, tuple[int | None, str | None]] | None:
        async with run.snapshot_lock:
            snapshot = await self._snapshot_workspace(runtime)
            if snapshot is not None:
                run.last_snapshot = snapshot
            return snapshot

    def _schedule_workspace_snapshot(
        self,
        run: _ArtifactRunState,
        runtime: Any,
        *,
        name: str,
    ) -> asyncio.Task[Any] | None:
        return self._track_background_task(
            run,
            self._take_workspace_snapshot(run, runtime),
            name=name,
        )

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

    def _track_background_task(
        self,
        run: _ArtifactRunState,
        awaitable: Coroutine[Any, Any, Any],
        *,
        name: str,
    ) -> asyncio.Task[Any] | None:
        if not run.accepting_tasks:
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            return None

        task = asyncio.create_task(awaitable, name=f"artifact:{name}")
        run.background_tasks.add(task)

        def on_done(done_task: asyncio.Task[Any]) -> None:
            run.background_tasks.discard(done_task)
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception:
                logger.warning("Artifact background task failed: %s", name, exc_info=True)

        task.add_done_callback(on_done)
        return task

    def _schedule_artifact_delivery(
        self,
        run: _ArtifactRunState,
        artifact: StagedArtifact,
        runtime: Any,
        *,
        allow_without_presenter: bool = False,
    ) -> None:
        if self._get_presenter(runtime) is None and not allow_without_presenter:
            return
        normalized = _normalize_path(artifact.path)
        if normalized in run.suppressed_paths:
            return
        active = run.delivery_tasks.get(normalized)
        if active is not None and not active.done():
            return
        task = self._track_background_task(
            run,
            self._deliver_latest_artifact(run, normalized, runtime),
            name=f"deliver:{normalized}",
        )
        if task is not None:
            run.delivery_tasks[normalized] = task

    async def _deliver_latest_artifact(
        self,
        run: _ArtifactRunState,
        normalized: str,
        runtime: Any,
    ) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                artifact = run.artifacts.get(normalized)
                if artifact is None or artifact.revealed or normalized in run.suppressed_paths:
                    return
                generation = run.artifact_generations.get(normalized, 0)
                async with run.delivery_semaphore:
                    delivered = await self._deliver_artifact(
                        run,
                        artifact,
                        runtime,
                        normalized=normalized,
                        generation=generation,
                    )
                if generation != run.artifact_generations.get(normalized, 0):
                    continue
                if delivered:
                    artifact.revealed = True
                return
        finally:
            if run.delivery_tasks.get(normalized) is current_task:
                run.delivery_tasks.pop(normalized, None)

    async def _drain_background_tasks(self, run: _ArtifactRunState) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _ARTIFACT_BACKGROUND_DRAIN_TIMEOUT
        timed_out = False
        try:
            while run.background_tasks:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    timed_out = True
                    break
                done, _ = await asyncio.wait(
                    list(run.background_tasks),
                    timeout=remaining,
                )
                run.background_tasks.difference_update(done)
        finally:
            run.accepting_tasks = False
            run.emission_open = False
            pending = list(run.background_tasks)
            for task in pending:
                task.cancel()
            if pending:
                if timed_out:
                    logger.warning(
                        "Cancelling %s artifact background task(s) after %.1fs drain timeout",
                        len(pending),
                        _ARTIFACT_BACKGROUND_DRAIN_TIMEOUT,
                    )
                await asyncio.wait(pending, timeout=_ARTIFACT_BACKGROUND_CANCEL_GRACE)

    async def _deliver_artifact(
        self,
        run: _ArtifactRunState,
        artifact: StagedArtifact,
        runtime: Any,
        *,
        normalized: str,
        generation: int,
    ) -> bool:
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

        return await self._emit_artifact_result(
            run,
            runtime,
            artifact,
            delivered,
            normalized=normalized,
            generation=generation,
            status=status,
            error=error,
        )

    def _deliver_staged_artifacts(
        self,
        run: _ArtifactRunState,
        artifacts: list[StagedArtifact],
        runtime: Any,
        *,
        allow_without_presenter: bool = False,
    ) -> None:
        for artifact in artifacts:
            if artifact.revealed:
                continue
            self._schedule_artifact_delivery(
                run,
                artifact,
                runtime,
                allow_without_presenter=allow_without_presenter,
            )

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
        run: _ArtifactRunState,
        runtime: Any,
        staged: StagedArtifact,
        artifact: dict[str, Any],
        *,
        normalized: str,
        generation: int,
        status: str,
        error: str | None,
    ) -> bool:
        if (
            not run.emission_open
            or staged.revealed
            or generation != run.artifact_generations.get(normalized, 0)
        ):
            return False
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
            if (
                not run.emission_open
                or staged.revealed
                or generation != run.artifact_generations.get(normalized, 0)
            ):
                return False
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
