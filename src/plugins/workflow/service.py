"""Business service for the workflow plugin."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from arq.connections import create_pool
from langchain_core.tools import BaseTool

from src.infra.task.arq_settings import build_arq_redis_settings
from src.kernel.config import settings
from src.kernel.schemas.user import TokenPayload
from src.plugins.workflow.contracts import schema_value_mismatches
from src.plugins.workflow.executor import (
    CredentialSecretResolver,
    HttpInvoker,
    KnowledgeRetriever,
    LlmInvoker,
    MinimalWorkflowExecutor,
    SubWorkflowInvoker,
    WorkflowExecutionError,
    WorkflowExecutionPaused,
)
from src.plugins.workflow.parser import parse_workflow
from src.plugins.workflow.policy import HttpRequestPolicy, resolve_http_request_policy
from src.plugins.workflow.storage import WorkflowPluginStorage

AsyncRunDispatcher = Callable[[str, str, list[str]], Awaitable[None]]
MAX_SUB_WORKFLOW_DEPTH = 5
RUN_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class WorkflowPluginService:
    def __init__(
        self,
        storage: WorkflowPluginStorage | None = None,
        executor: MinimalWorkflowExecutor | None = None,
        http_policy: HttpRequestPolicy | None = None,
        http_invoker: HttpInvoker | None = None,
        llm_invoker: LlmInvoker | None = None,
        knowledge_retriever: KnowledgeRetriever | None = None,
        async_run_dispatcher: AsyncRunDispatcher | None = None,
        sub_workflow_depth: int = 0,
        sub_workflow_stack: tuple[str, ...] | None = None,
    ) -> None:
        self.storage = storage or WorkflowPluginStorage()
        self.executor = executor or MinimalWorkflowExecutor()
        self.http_policy = http_policy
        self.http_invoker = http_invoker
        self.llm_invoker = llm_invoker
        self.knowledge_retriever = knowledge_retriever
        self.async_run_dispatcher = async_run_dispatcher
        self.sub_workflow_depth = sub_workflow_depth
        self.sub_workflow_stack = sub_workflow_stack or ()

    @staticmethod
    def build_import_report(
        *,
        name: str,
        source_payload: dict[str, Any] | None = None,
        source_content: str | None = None,
        source_format: str = "json",
        user: TokenPayload,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        del user
        payload = resolve_workflow_source_payload(
            source_format=source_format,
            source_payload=source_payload,
            source_content=source_content,
        )
        report = parse_workflow(payload, name=name).report
        return {**report, "workflow_id": workflow_id}

    async def list_workflows(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
        query: str | None = None,
        status_filter: str | None = None,
    ):
        return await self.storage.list_workflows(
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
            query=query,
            status_filter=status_filter,
        )

    async def get_workflow(self, workflow_id: str, *, owner_user_id: str):
        return await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)

    async def get_workflow_detail(self, workflow_id: str, *, owner_user_id: str):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            return None, None
        latest_version = await self.storage.get_latest_version(
            workflow_id,
            owner_user_id=owner_user_id,
        )
        return definition, latest_version

    async def get_workflow_input_schema(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            raise LookupError("workflow_not_found")
        version = None
        resolved_version_id = (
            version_id or definition.published_version_id or definition.latest_version_id
        )
        if resolved_version_id:
            version = await self.storage.get_version(
                resolved_version_id, owner_user_id=owner_user_id
            )
        if version is None:
            version = await self.storage.get_latest_version(
                workflow_id, owner_user_id=owner_user_id
            )
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")
        from src.plugins.workflow.tools import infer_workflow_input_schema_payload

        return infer_workflow_input_schema_payload(
            workflow_id=workflow_id,
            status=definition.status,
            version_id=version.version_id,
            version_number=version.version_number,
            internal_model=version.internal_model,
        )

    async def get_workflow_io_contract(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            raise LookupError("workflow_not_found")
        version = None
        resolved_version_id = (
            version_id or definition.published_version_id or definition.latest_version_id
        )
        if resolved_version_id:
            version = await self.storage.get_version(
                resolved_version_id, owner_user_id=owner_user_id
            )
        if version is None:
            version = await self.storage.get_latest_version(
                workflow_id, owner_user_id=owner_user_id
            )
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")
        from src.plugins.workflow.tools import infer_workflow_io_contract_payload

        return infer_workflow_io_contract_payload(
            workflow_id=workflow_id,
            status=definition.status,
            version_id=version.version_id,
            version_number=version.version_number,
            internal_model=version.internal_model,
        )

    async def list_versions(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            raise LookupError("workflow_not_found")
        return await self.storage.list_versions(
            workflow_id,
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
        )

    async def list_runs(
        self,
        workflow_id: str,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=owner_user_id)
        if definition is None:
            raise LookupError("workflow_not_found")
        return await self.storage.list_runs(
            workflow_id,
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
        )

    async def list_pending_approvals(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 50,
    ):
        return await self.storage.list_pending_approval_runs(
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
        )

    async def list_run_events(
        self,
        *,
        workflow_id: str,
        run_id: str,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 200,
    ):
        run = await self.storage.get_run(run_id, owner_user_id=owner_user_id)
        if run is None or run.workflow_id != workflow_id:
            raise LookupError("workflow_run_not_found")
        events = await self.storage.list_run_events(
            run_id,
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
        )
        return run, events

    async def cancel_run(
        self,
        *,
        workflow_id: str,
        run_id: str,
        user: TokenPayload,
    ):
        run = await self.storage.get_run(run_id, owner_user_id=user.sub)
        if run is None or run.workflow_id != workflow_id:
            raise LookupError("workflow_run_not_found")
        try:
            return await self.storage.cancel_run(run_id=run_id, owner_user_id=user.sub)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    async def resume_run(
        self,
        *,
        workflow_id: str,
        run_id: str,
        approval_response: dict[str, Any],
        user: TokenPayload,
    ):
        run = await self.storage.get_run(run_id, owner_user_id=user.sub)
        if run is None or run.workflow_id != workflow_id:
            raise LookupError("workflow_run_not_found")
        if run.status != "paused":
            raise ValueError(f"workflow_run_not_paused:{run.status}")
        pause = run.pause if isinstance(run.pause, dict) else {}
        resume_state = (
            pause.get("resume_state") if isinstance(pause.get("resume_state"), dict) else None
        )
        if resume_state is None:
            raise ValueError("workflow_run_resume_state_missing")
        version = await self.storage.get_version(run.version_id, owner_user_id=user.sub)
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")
        try:
            execution = await self.executor.resume_async(
                version.internal_model,
                resume_state=resume_state,
                approval_response=approval_response,
                tool_invoker=await self._build_tool_invoker_if_needed(
                    version.internal_model,
                    user=user,
                    validate_only=False,
                ),
                http_policy=await self._http_policy_if_needed(version.internal_model),
                http_invoker=self.http_invoker,
                credential_secret_resolver=self._build_credential_secret_resolver_if_needed(
                    version.internal_model,
                    user=user,
                ),
                llm_invoker=await self._build_llm_invoker_if_needed(version.internal_model),
                knowledge_retriever=await self._build_knowledge_retriever_if_needed(
                    version.internal_model,
                    user=user,
                ),
                sub_workflow_invoker=await self._build_sub_workflow_invoker_if_needed(
                    version.internal_model,
                    user=user,
                    current_workflow_id=run.workflow_id,
                ),
                cancel_checker=self._build_run_cancel_checker(run=run, user=user),
                default_node_timeout_seconds=await self._default_node_timeout_seconds(),
            )
        except WorkflowExecutionPaused as exc:
            return await self._pause_run(run=run, user=user, pause=exc, include_run_started=False)
        except WorkflowExecutionError as exc:
            return await self._finish_run_failed(
                run=run,
                user=user,
                error=str(exc),
                events=getattr(exc, "events", []),
                include_run_started=False,
            )
        except Exception as exc:
            return await self._finish_run_failed(
                run=run,
                user=user,
                error=f"workflow_run_unexpected_error:{exc}",
                events=[],
                include_run_started=False,
            )

        terminal_result = await self._terminal_result_if_needed(run=run, user=user)
        if terminal_result is not None:
            return terminal_result

        events = await self.storage.append_run_events(
            run=run,
            events=[*execution.events, _run_succeeded_event(execution.output)],
        )
        run = await self.storage.finish_run(
            run_id=run.run_id,
            owner_user_id=user.sub,
            status="succeeded",
            output=execution.output,
        )
        return run, events

    async def import_workflow(
        self,
        *,
        name: str,
        source_format: Literal["json", "yaml"],
        source_payload: dict[str, Any] | None = None,
        source_content: str | None = None,
        dry_run: bool,
        user: TokenPayload,
    ):
        source_payload = resolve_workflow_source_payload(
            source_format=source_format,
            source_payload=source_payload,
            source_content=source_content,
        )
        parse_result = parse_workflow(source_payload, name=name)
        report = await self._with_credential_resolution(
            parse_result.report,
            owner_user_id=user.sub,
        )
        if dry_run:
            return None, None, report

        definition, version = await self.storage.create_imported_workflow(
            owner_user_id=user.sub,
            created_by=user.sub,
            name=name,
            source_format=source_format,
            source_payload=source_payload,
            internal_model=parse_result.internal_model,
            compatibility_report=report,
        )
        report = {**report, "workflow_id": definition.workflow_id}
        return definition, version, report

    async def create_workflow_version(
        self,
        *,
        workflow_id: str,
        name: str | None,
        source_format: Literal["json", "yaml"],
        source_payload: dict[str, Any] | None = None,
        source_content: str | None = None,
        user: TokenPayload,
    ):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")
        parse_name = name or definition.name
        source_payload = resolve_workflow_source_payload(
            source_format=source_format,
            source_payload=source_payload,
            source_content=source_content,
        )
        parse_result = parse_workflow(source_payload, name=parse_name)
        report = await self._with_credential_resolution(
            parse_result.report,
            owner_user_id=user.sub,
        )
        definition, version = await self.storage.create_workflow_version(
            workflow_id=workflow_id,
            owner_user_id=user.sub,
            created_by=user.sub,
            name=name,
            source_format=source_format,
            source_payload=source_payload,
            internal_model=parse_result.internal_model,
            compatibility_report=report,
        )
        report = {**report, "workflow_id": workflow_id}
        return definition, version, report

    async def publish_workflow(
        self,
        *,
        workflow_id: str,
        version_id: str | None,
        user: TokenPayload,
    ):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")
        version = (
            await self.storage.get_version(version_id, owner_user_id=user.sub)
            if version_id
            else await self.storage.get_latest_version(workflow_id, owner_user_id=user.sub)
        )
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")
        await self._assert_version_publishable_for_user(
            workflow_id=workflow_id,
            internal_model=version.internal_model,
            compatibility_report=version.compatibility_report,
            user=user,
        )
        return await self.storage.publish_workflow(
            workflow_id=workflow_id,
            owner_user_id=user.sub,
            version_id=version.version_id,
        )

    async def validate_workflow_version(
        self,
        *,
        workflow_id: str,
        version_id: str | None,
        user: TokenPayload,
    ) -> dict[str, Any]:
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")
        version = (
            await self.storage.get_version(version_id, owner_user_id=user.sub)
            if version_id
            else await self.storage.get_latest_version(workflow_id, owner_user_id=user.sub)
        )
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")

        errors: list[str] = []
        reachable_node_ids: set[str] = set()
        credential_resolution = await self._credential_resolution_payload(
            version.compatibility_report,
            owner_user_id=user.sub,
        )
        try:
            self._assert_import_publishable(version.internal_model, version.compatibility_report)
            available_tool_names = await self._available_tool_names_if_needed(
                version.internal_model,
                user=user,
            )
            available_sub_workflow_refs = await self._available_sub_workflow_refs_if_needed(
                version.internal_model,
                user=user,
                current_workflow_id=workflow_id,
            )
            result = self.executor.validate_static(
                version.internal_model,
                available_tool_names=available_tool_names,
                http_policy=await self._http_policy_if_needed(version.internal_model),
                llm_available=await self._llm_available_if_needed(version.internal_model),
                knowledge_available=await self._knowledge_available_if_needed(
                    version.internal_model
                ),
                available_sub_workflow_refs=available_sub_workflow_refs,
            )
            errors.extend(result.errors)
            reachable_node_ids = result.reachable_node_ids
        except ValueError as exc:
            errors.append(str(exc))

        return {
            "workflow_id": workflow_id,
            "version_id": version.version_id,
            "version_number": version.version_number,
            "runnable": not errors,
            "errors": errors,
            "reachable_node_ids": sorted(reachable_node_ids),
            **credential_resolution,
        }

    async def unpublish_workflow(self, *, workflow_id: str, user: TokenPayload):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")
        return await self.storage.unpublish_workflow(
            workflow_id=workflow_id,
            owner_user_id=user.sub,
        )

    async def delete_workflow(self, *, workflow_id: str, user: TokenPayload):
        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")
        return await self.storage.archive_workflow(
            workflow_id=workflow_id,
            owner_user_id=user.sub,
        )

    async def list_credentials(self, *, user: TokenPayload, skip: int = 0, limit: int = 50):
        return await self.storage.list_credentials(
            owner_user_id=user.sub,
            skip=skip,
            limit=limit,
        )

    async def upsert_credential(
        self,
        *,
        user: TokenPayload,
        ref: str,
        credential_type: str,
        label: str = "",
        description: str = "",
        secret: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        normalized_ref = str(ref or "").strip()
        if not normalized_ref:
            raise ValueError("workflow_credential_ref_required")
        normalized_type = str(credential_type or "credential_ref").strip() or "credential_ref"
        return await self.storage.upsert_credential(
            owner_user_id=user.sub,
            ref=normalized_ref,
            credential_type=normalized_type,
            label=str(label or "").strip(),
            description=str(description or "").strip(),
            secret=secret,
            metadata=metadata or {},
        )

    async def delete_credential(self, *, user: TokenPayload, credential_id: str) -> bool:
        return await self.storage.delete_credential(
            owner_user_id=user.sub,
            credential_id=credential_id,
        )

    async def run_workflow(
        self,
        *,
        workflow_id: str,
        version_id: str | None,
        workflow_input: dict[str, Any],
        mode: Literal["sync", "async", "stream"],
        user: TokenPayload,
    ):
        if mode not in {"sync", "async", "stream"}:
            raise ValueError("workflow_run_mode_not_supported")

        definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
        if definition is None:
            raise LookupError("workflow_not_found")

        resolved_version_id = version_id or definition.published_version_id
        version = (
            await self.storage.get_version(resolved_version_id, owner_user_id=user.sub)
            if resolved_version_id
            else await self.storage.get_latest_version(workflow_id, owner_user_id=user.sub)
        )
        if version is None or version.workflow_id != workflow_id:
            raise LookupError("workflow_version_not_found")

        _assert_workflow_input_contract(
            workflow_id=workflow_id,
            status=definition.status,
            version=version,
            workflow_input=workflow_input,
        )

        run = await self.storage.create_run(
            workflow_id=workflow_id,
            version_id=version.version_id,
            owner_user_id=user.sub,
            mode=mode,
            workflow_input=workflow_input,
        )
        if mode in {"async", "stream"}:
            run_started_events = await self.storage.append_run_events(
                run=run,
                events=[{"event_type": "run_queued", "payload": {"mode": mode}}],
            )
            try:
                await self._dispatch_async_run(
                    run=run,
                    internal_model=version.internal_model,
                    workflow_input=workflow_input,
                    user=user,
                )
            except Exception as exc:
                failed_run, failed_events = await self._finish_run_failed(
                    run=run,
                    user=user,
                    error=f"workflow_run_dispatch_failed:{exc}",
                    events=[],
                    include_run_started=False,
                )
                return failed_run, [*run_started_events, *failed_events]
            return run, run_started_events

        return await self._execute_run_to_completion(
            run=run,
            internal_model=version.internal_model,
            workflow_input=workflow_input,
            user=user,
        )

    async def execute_existing_run(
        self,
        *,
        run_id: str,
        owner_user_id: str,
        user_roles: list[str] | None = None,
    ):
        run = await self.storage.get_run(run_id, owner_user_id=owner_user_id)
        if run is None:
            raise LookupError("workflow_run_not_found")
        if run.status not in {"queued", "running"}:
            events = await self.storage.list_run_events(run_id, owner_user_id=owner_user_id)
            return run, events

        user = TokenPayload(
            sub=owner_user_id,
            username=owner_user_id,
            roles=user_roles or [],
            permissions=["workflow:run", "workflow:read"],
        )
        version = await self.storage.get_version(run.version_id, owner_user_id=owner_user_id)
        if version is None or version.workflow_id != run.workflow_id:
            return await self._finish_run_failed(
                run=run,
                user=user,
                error="workflow_version_not_found",
                events=[],
            )
        return await self._execute_run_to_completion(
            run=run,
            internal_model=version.internal_model,
            workflow_input=run.input,
            user=user,
        )

    async def _dispatch_async_run(
        self,
        *,
        run,
        internal_model: dict[str, Any],
        workflow_input: dict[str, Any],
        user: TokenPayload,
    ) -> None:
        if self.async_run_dispatcher is not None:
            await self.async_run_dispatcher(run.run_id, user.sub, list(user.roles or []))
            return

        if settings.TASK_BACKEND == "arq":
            await dispatch_workflow_run_to_arq(
                run_id=run.run_id,
                owner_user_id=user.sub,
                user_roles=list(user.roles or []),
            )
            return

        asyncio.create_task(
            self._execute_run_to_completion(
                run=run,
                internal_model=internal_model,
                workflow_input=workflow_input,
                user=user,
            )
        )

    async def _execute_run_to_completion(
        self,
        *,
        run,
        internal_model: dict[str, Any],
        workflow_input: dict[str, Any],
        user: TokenPayload,
    ):
        try:
            execution = await self.executor.execute_async(
                internal_model,
                workflow_input=workflow_input,
                tool_invoker=await self._build_tool_invoker_if_needed(
                    internal_model,
                    user=user,
                    validate_only=False,
                ),
                http_policy=await self._http_policy_if_needed(internal_model),
                http_invoker=self.http_invoker,
                credential_secret_resolver=self._build_credential_secret_resolver_if_needed(
                    internal_model,
                    user=user,
                ),
                llm_invoker=await self._build_llm_invoker_if_needed(internal_model),
                knowledge_retriever=await self._build_knowledge_retriever_if_needed(
                    internal_model,
                    user=user,
                ),
                sub_workflow_invoker=await self._build_sub_workflow_invoker_if_needed(
                    internal_model,
                    user=user,
                    current_workflow_id=run.workflow_id,
                ),
                cancel_checker=self._build_run_cancel_checker(run=run, user=user),
                default_node_timeout_seconds=await self._default_node_timeout_seconds(),
            )
        except WorkflowExecutionPaused as exc:
            return await self._pause_run(run=run, user=user, pause=exc)
        except WorkflowExecutionError as exc:
            return await self._finish_run_failed(
                run=run,
                user=user,
                error=str(exc),
                events=getattr(exc, "events", []),
            )
        except Exception as exc:
            return await self._finish_run_failed(
                run=run,
                user=user,
                error=f"workflow_run_unexpected_error:{exc}",
                events=[],
            )

        terminal_result = await self._terminal_result_if_needed(run=run, user=user)
        if terminal_result is not None:
            return terminal_result

        events = await self.storage.append_run_events(
            run=run,
            events=_events_with_run_started(
                run=run,
                events=[*execution.events, _run_succeeded_event(execution.output)],
            ),
        )
        run = await self.storage.finish_run(
            run_id=run.run_id,
            owner_user_id=user.sub,
            status="succeeded",
            output=execution.output,
        )
        return run, events

    async def _pause_run(
        self,
        *,
        run,
        user: TokenPayload,
        pause: WorkflowExecutionPaused,
        include_run_started: bool = True,
    ):
        terminal_result = await self._terminal_result_if_needed(run=run, user=user)
        if terminal_result is not None:
            return terminal_result

        paused_events = [
            *pause.events,
            {
                "event_type": "run_paused",
                "payload": {
                    "error": str(pause),
                    "pending_approval": pause.pending_approval,
                },
            },
        ]
        if include_run_started:
            paused_events = _events_with_run_started(run=run, events=paused_events)
        persisted_events = await self.storage.append_run_events(run=run, events=paused_events)
        run = await self.storage.pause_run(
            run_id=run.run_id,
            owner_user_id=user.sub,
            output=pause.output,
            error=str(pause),
            pause={
                "kind": "human_approval",
                "resume_state": pause.pause_state,
                "pending_approval": pause.pending_approval,
            },
        )
        return run, persisted_events

    async def _finish_run_failed(
        self,
        *,
        run,
        user: TokenPayload,
        error: str,
        events: list[dict[str, Any]],
        include_run_started: bool = True,
    ):
        terminal_result = await self._terminal_result_if_needed(run=run, user=user)
        if terminal_result is not None:
            return terminal_result

        failed_events = [
            *events,
            {
                "event_type": "run_failed",
                "payload": {"error": error},
            },
        ]
        if include_run_started:
            failed_events = _events_with_run_started(run=run, events=failed_events)
        persisted_events = await self.storage.append_run_events(
            run=run,
            events=failed_events,
        )
        run = await self.storage.finish_run(
            run_id=run.run_id,
            owner_user_id=user.sub,
            status="failed",
            error=error,
        )
        return run, persisted_events

    def _build_run_cancel_checker(self, *, run, user: TokenPayload):
        async def is_cancelled() -> bool:
            current_run = await self.storage.get_run(run.run_id, owner_user_id=user.sub)
            return current_run is not None and current_run.status == "cancelled"

        return is_cancelled

    async def _terminal_result_if_needed(self, *, run, user: TokenPayload):
        current_run = await self.storage.get_run(run.run_id, owner_user_id=user.sub)
        if current_run is None or current_run.status not in RUN_TERMINAL_STATUSES:
            return None
        events = await self.storage.list_run_events(run.run_id, owner_user_id=user.sub)
        return current_run, events

    async def _assert_version_publishable_for_user(
        self,
        *,
        workflow_id: str,
        internal_model: dict[str, Any],
        compatibility_report: dict[str, Any],
        user: TokenPayload,
    ) -> None:
        self._assert_import_publishable(internal_model, compatibility_report)
        available_tool_names = await self._available_tool_names_if_needed(internal_model, user=user)
        available_sub_workflow_refs = await self._available_sub_workflow_refs_if_needed(
            internal_model,
            user=user,
            current_workflow_id=workflow_id,
        )
        result = self.executor.validate_static(
            internal_model,
            available_tool_names=available_tool_names,
            http_policy=await self._http_policy_if_needed(internal_model),
            llm_available=await self._llm_available_if_needed(internal_model),
            knowledge_available=await self._knowledge_available_if_needed(internal_model),
            available_sub_workflow_refs=available_sub_workflow_refs,
        )
        try:
            result.raise_for_errors()
        except WorkflowExecutionError as exc:
            raise ValueError(f"workflow_version_not_publishable:{exc}") from exc

    async def _with_credential_resolution(
        self,
        report: dict[str, Any],
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            **report,
            **await self._credential_resolution_payload(report, owner_user_id=owner_user_id),
        }

    async def _credential_resolution_payload(
        self,
        report: dict[str, Any],
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        required = _credential_refs_required(report)
        mappings = await _resolve_credential_ref_mappings()
        mappings.update(
            await self._credential_vault_mappings(required, owner_user_id=owner_user_id)
        )
        return _credential_resolution_payload(required, mappings)

    async def _credential_vault_mappings(
        self,
        required_refs: list[str],
        *,
        owner_user_id: str | None,
    ) -> dict[str, dict[str, str]]:
        if owner_user_id is None or not required_refs:
            return {}
        list_refs = getattr(self.storage, "list_credential_refs", None)
        if not callable(list_refs):
            return {}
        try:
            credentials = await list_refs(owner_user_id=owner_user_id)
        except Exception:
            return {}
        resolved: dict[str, dict[str, str]] = {}
        for ref in required_refs:
            credential = credentials.get(ref) if isinstance(credentials, dict) else None
            if credential is None:
                continue
            target = f"credential:{credential.credential_id}"
            entry = {
                "ref": credential.ref,
                "type": credential.type,
                "target": target,
            }
            if credential.label:
                entry["label"] = credential.label
            if credential.description:
                entry["description"] = credential.description
            resolved[ref] = entry
        return resolved

    async def _build_tool_invoker_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
        validate_only: bool,
    ):
        if not _model_contains_node_type(internal_model, "tool_call"):
            return None
        return await self._build_tool_invoker(user=user, validate_only=validate_only)

    async def _available_tool_names_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
    ) -> set[str] | None:
        if not _model_contains_node_type(internal_model, "tool_call"):
            return None
        tools = await self._list_internal_tools_for_user(user=user)
        return {tool.name for tool in tools}

    async def _http_policy_if_needed(
        self,
        internal_model: dict[str, Any],
    ) -> HttpRequestPolicy | None:
        if not _model_contains_node_type(internal_model, "http_request"):
            return None
        if self.http_policy is not None:
            return self.http_policy
        return await resolve_http_request_policy()

    def _build_credential_secret_resolver_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
    ) -> CredentialSecretResolver | None:
        if not _model_contains_any_node_type(
            internal_model,
            {"http_request", "llm", "parameter_extractor", "question_classifier"},
        ):
            return None
        get_secret = getattr(self.storage, "get_credential_secret_by_ref", None)
        if not callable(get_secret):
            return None

        async def resolve(ref: str) -> str | None:
            normalized_ref = str(ref or "").strip()
            if not normalized_ref:
                return None
            return await get_secret(owner_user_id=user.sub, ref=normalized_ref)

        return resolve

    async def _default_node_timeout_seconds(self) -> float:
        try:
            from pathlib import Path

            from src.infra.extensions.plugin_settings import PluginSettingsResolver
            from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

            manifest = build_workflow_plugin_manifest()
            manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / "workflow")
            resolver = PluginSettingsResolver(plugin_id="workflow", manifests=(manifest,))
            timeout_seconds = await resolver.get_int("DEFAULT_TIMEOUT_SECONDS", 120)
        except Exception:
            timeout_seconds = 120
        return max(min(float(timeout_seconds), 3600.0), 1.0)

    async def _llm_available_if_needed(self, internal_model: dict[str, Any]) -> bool:
        if not _model_contains_any_node_type(
            internal_model,
            {"llm", "parameter_extractor", "question_classifier"},
        ):
            return False
        return True

    async def _knowledge_available_if_needed(self, internal_model: dict[str, Any]) -> bool:
        if not _model_contains_node_type(internal_model, "knowledge_retrieval"):
            return False
        if self.knowledge_retriever is not None:
            return True
        try:
            from src.kernel.config import settings as app_settings

            return bool(getattr(app_settings, "ENABLE_MEMORY", False))
        except Exception:
            return False

    async def _build_knowledge_retriever_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
    ) -> KnowledgeRetriever | None:
        if not _model_contains_node_type(internal_model, "knowledge_retrieval"):
            return None
        if self.knowledge_retriever is not None:
            return self.knowledge_retriever
        return self._build_memory_knowledge_retriever(user=user)

    def _build_memory_knowledge_retriever(self, *, user: TokenPayload) -> KnowledgeRetriever:
        async def retrieve(request: dict[str, Any]) -> dict[str, Any]:
            from src.infra.memory import tools as memory_tools

            backend = await memory_tools._get_backend()
            if backend is None:
                raise WorkflowExecutionError("workflow_knowledge_retriever_unavailable")
            query = str(request.get("query") or "")
            max_results = _int_or_none(request.get("top_k")) or 5
            dataset_ids = [str(item) for item in request.get("dataset_ids") or [] if item]
            dataset_mapping = await _resolve_knowledge_dataset_mappings()
            mapped = _memory_types_for_dataset_ids(dataset_ids, dataset_mapping)
            memory_types = mapped["memory_types"] or None
            result = await backend.recall(user.sub, query, max_results, memory_types)
            if isinstance(result, dict):
                return {
                    **result,
                    "dataset_ids": dataset_ids,
                    "resolved_dataset_ids": mapped["resolved_dataset_ids"],
                    "unresolved_dataset_ids": mapped["unresolved_dataset_ids"],
                    "memory_types": memory_types or [],
                    "query": query,
                }
            return {
                "success": True,
                "items": result,
                "dataset_ids": dataset_ids,
                "resolved_dataset_ids": mapped["resolved_dataset_ids"],
                "unresolved_dataset_ids": mapped["unresolved_dataset_ids"],
                "memory_types": memory_types or [],
                "query": query,
            }

        return retrieve

    async def _build_sub_workflow_invoker_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
        current_workflow_id: str,
    ) -> SubWorkflowInvoker | None:
        if not _model_contains_node_type(internal_model, "sub_workflow"):
            return None
        if self.sub_workflow_depth >= MAX_SUB_WORKFLOW_DEPTH:
            raise WorkflowExecutionError("workflow_sub_workflow_depth_exceeded")

        async def invoke(request: dict[str, Any]) -> dict[str, Any]:
            workflow_id = str(request.get("workflow_id") or "").strip()
            if not workflow_id:
                raise WorkflowExecutionError("workflow_sub_workflow_id_missing")
            if workflow_id == current_workflow_id or workflow_id in self.sub_workflow_stack:
                raise WorkflowExecutionError(f"workflow_sub_workflow_cycle_detected:{workflow_id}")
            version_id = request.get("version_id")
            definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
            if definition is None:
                raise WorkflowExecutionError(f"workflow_sub_workflow_not_available:{workflow_id}")
            if not version_id and not getattr(definition, "published_version_id", None):
                raise WorkflowExecutionError(f"workflow_sub_workflow_not_published:{workflow_id}")
            next_stack = _append_sub_workflow_stack(
                self.sub_workflow_stack,
                current_workflow_id,
                workflow_id,
            )
            child_service = WorkflowPluginService(
                storage=self.storage,
                executor=self.executor,
                http_policy=self.http_policy,
                http_invoker=self.http_invoker,
                llm_invoker=self.llm_invoker,
                knowledge_retriever=self.knowledge_retriever,
                async_run_dispatcher=self.async_run_dispatcher,
                sub_workflow_depth=self.sub_workflow_depth + 1,
                sub_workflow_stack=next_stack,
            )
            raw_workflow_input = request.get("input")
            workflow_input = raw_workflow_input if isinstance(raw_workflow_input, dict) else {}
            run, events = await child_service.run_workflow(
                workflow_id=workflow_id,
                version_id=str(version_id) if version_id else None,
                workflow_input=workflow_input,
                mode="sync",
                user=user,
            )
            if run.status != "succeeded":
                raise WorkflowExecutionError(
                    run.error or f"workflow_sub_workflow_failed:{workflow_id}"
                )
            return {
                "workflow_id": run.workflow_id,
                "version_id": run.version_id,
                "run_id": run.run_id,
                "status": run.status,
                "output": run.output,
                "events": [event.model_dump(mode="json") for event in events],
            }

        return invoke

    async def _available_sub_workflow_refs_if_needed(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
        current_workflow_id: Any = None,
    ) -> set[str] | None:
        if not _model_contains_node_type(internal_model, "sub_workflow"):
            return None
        refs: set[str] = set()
        visited: set[str] = set()
        root_workflow_id = str(current_workflow_id or "").strip()
        ancestry = (root_workflow_id,) if root_workflow_id else self.sub_workflow_stack
        await self._collect_available_sub_workflow_refs(
            internal_model,
            user=user,
            ancestry=ancestry,
            refs=refs,
            visited=visited,
        )
        return refs

    async def _collect_available_sub_workflow_refs(
        self,
        internal_model: dict[str, Any],
        *,
        user: TokenPayload,
        ancestry: tuple[str, ...],
        refs: set[str],
        visited: set[str],
    ) -> None:
        for dependency in _sub_workflow_dependencies(internal_model):
            workflow_id = dependency["workflow_id"]
            version_id = dependency.get("version_id")
            if not workflow_id:
                continue
            if workflow_id in ancestry:
                raise ValueError(f"workflow_sub_workflow_cycle_detected:{workflow_id}")
            definition = await self.storage.get_workflow(workflow_id, owner_user_id=user.sub)
            if definition is None:
                raise ValueError(f"workflow_sub_workflow_not_available:{workflow_id}")
            resolved_version_id = version_id or getattr(definition, "published_version_id", None)
            if not resolved_version_id:
                raise ValueError(f"workflow_sub_workflow_not_published:{workflow_id}")
            version = (
                await self.storage.get_version(str(resolved_version_id), owner_user_id=user.sub)
                if resolved_version_id
                else None
            )
            if version is None or version.workflow_id != workflow_id:
                raise ValueError(f"workflow_sub_workflow_not_available:{workflow_id}")
            ref_key = _sub_workflow_ref_key(workflow_id, version_id)
            refs.add(ref_key)
            resolved_ref_key = _sub_workflow_ref_key(workflow_id, str(resolved_version_id))
            if resolved_ref_key in visited:
                continue
            visited.add(resolved_ref_key)
            child_ancestry = _append_sub_workflow_stack(ancestry, workflow_id, "")
            try:
                self._assert_import_publishable(
                    version.internal_model, version.compatibility_report
                )
            except ValueError as exc:
                raise ValueError(
                    f"workflow_sub_workflow_not_publishable:{workflow_id}:{exc}"
                ) from exc
            await self._collect_available_sub_workflow_refs(
                version.internal_model,
                user=user,
                ancestry=child_ancestry,
                refs=refs,
                visited=visited,
            )
            child_result = self.executor.validate_static(
                version.internal_model,
                available_tool_names=await self._available_tool_names_if_needed(
                    version.internal_model, user=user
                ),
                http_policy=await self._http_policy_if_needed(version.internal_model),
                llm_available=await self._llm_available_if_needed(version.internal_model),
                knowledge_available=await self._knowledge_available_if_needed(
                    version.internal_model
                ),
                available_sub_workflow_refs=refs,
            )
            try:
                child_result.raise_for_errors()
            except WorkflowExecutionError as exc:
                raise ValueError(
                    f"workflow_sub_workflow_not_publishable:{workflow_id}:{exc}"
                ) from exc

    async def _build_llm_invoker_if_needed(
        self, internal_model: dict[str, Any]
    ) -> LlmInvoker | None:
        if not _model_contains_any_node_type(
            internal_model,
            {"llm", "parameter_extractor", "question_classifier"},
        ):
            return None
        if self.llm_invoker is not None:
            return self.llm_invoker
        return self._build_llm_invoker()

    def _build_llm_invoker(self) -> LlmInvoker:
        async def invoke(request: dict[str, Any]) -> dict[str, Any]:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            from src.infra.llm.client import LLMClient
            from src.infra.llm.models_service import resolve_model_reference

            model_id = request.get("model_id")
            model = request.get("model")
            if not model_id:
                resolved_model_id, resolved_model = await resolve_model_reference(
                    str(model or "") or None
                )
                model_id = resolved_model_id
                model = resolved_model or model
            model_kwargs: dict[str, Any] = {
                "model": str(model) if model else None,
                "model_id": str(model_id) if model_id else None,
                "temperature": _float_or_default(request.get("temperature"), 0.7),
                "max_tokens": _int_or_none(request.get("max_tokens")),
                "api_key": str(request.get("api_key")) if request.get("api_key") else None,
                "api_base": str(request.get("api_base")) if request.get("api_base") else None,
            }
            llm = await LLMClient.get_model(**model_kwargs, streaming=False)
            messages = _langchain_messages_from_request(
                request,
                ai_message_cls=AIMessage,
                human_message_cls=HumanMessage,
                system_message_cls=SystemMessage,
            )
            try:
                response = await llm.ainvoke(messages)
            except Exception as exc:
                if not _should_retry_llm_without_streaming(exc):
                    raise
                direct_result = await _invoke_openai_compatible_without_streaming(
                    model_kwargs=model_kwargs,
                    messages=messages,
                )
                return {
                    "text": direct_result["text"],
                    "model": str(model or model_id or direct_result.get("model") or ""),
                    "usage": direct_result.get("usage") or {},
                }
            return {
                "text": _message_content_text(response),
                "model": str(model or model_id or ""),
                "usage": _message_usage(response),
            }

        return invoke

    async def _build_tool_invoker(
        self,
        *,
        user: TokenPayload,
        validate_only: bool,
    ):
        tools = await self._list_internal_tools_for_user(user=user)
        tools_by_name: dict[str, BaseTool] = {tool.name: tool for tool in tools}

        async def invoke(tool_name: str, arguments: dict[str, Any]) -> Any:
            tool = tools_by_name.get(tool_name)
            if tool is None:
                raise WorkflowExecutionError(f"workflow_tool_not_available:{tool_name}")
            if validate_only:
                return {"validated": True, "tool_name": tool_name}
            return await tool.ainvoke(arguments)

        return invoke

    async def _list_internal_tools_for_user(self, *, user: TokenPayload) -> list[BaseTool]:
        from src.infra.tool.internal_registry import get_internal_tools_for_user

        return await get_internal_tools_for_user(
            user_id=user.sub,
            user_roles=user.roles,
            is_admin="admin" in user.roles,
        )

    @staticmethod
    def _assert_import_publishable(
        internal_model: dict[str, Any],
        compatibility_report: dict[str, Any],
    ) -> None:
        blocked_errors = _blocked_import_errors(compatibility_report)
        if blocked_errors:
            raise ValueError("workflow_version_not_publishable:" + ";".join(blocked_errors))
        validation = internal_model.get("validation") if isinstance(internal_model, dict) else None
        if isinstance(validation, dict) and validation.get("runnable") is False:
            raise ValueError("workflow_version_not_publishable:import_validation_failed")
        if compatibility_report.get("errors"):
            raise ValueError("workflow_version_not_publishable:import_errors")


async def create_workflow_service() -> WorkflowPluginService:
    from src.plugins.workflow.lifecycle import create_workflow_storage

    return WorkflowPluginService(storage=await create_workflow_storage())


async def get_workflow_service() -> WorkflowPluginService:
    return await create_workflow_service()


def _run_started_event(*, mode: str, workflow_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "run_started",
        "payload": {
            "status": "running",
            "mode": mode,
            "input_keys": sorted(str(key) for key in workflow_input),
        },
    }


def _assert_workflow_input_contract(
    *,
    workflow_id: str,
    status: str,
    version: Any,
    workflow_input: dict[str, Any],
) -> None:
    schema = _workflow_input_schema_for_version(
        workflow_id=workflow_id,
        status=status,
        version=version,
    )
    missing = _missing_required_workflow_inputs(schema=schema, workflow_input=workflow_input)
    if missing:
        raise ValueError(f"workflow_input_required_missing:{','.join(missing)}")
    type_or_enum_error = _workflow_input_type_or_enum_error(
        schema=schema,
        workflow_input=workflow_input,
    )
    if type_or_enum_error:
        raise ValueError(type_or_enum_error)


def _workflow_input_schema_for_version(
    *,
    workflow_id: str,
    status: str,
    version: Any,
) -> dict[str, Any]:
    from src.plugins.workflow.tools import infer_workflow_input_schema_payload

    payload = infer_workflow_input_schema_payload(
        workflow_id=workflow_id,
        status=status,
        version_id=str(getattr(version, "version_id", "")),
        version_number=int(getattr(version, "version_number", 0) or 0),
        internal_model=getattr(version, "internal_model", {}) or {},
    )
    schema = payload.get("input_schema") if isinstance(payload, dict) else None
    if not isinstance(schema, dict):
        return {}
    return schema


def _missing_required_workflow_inputs(
    *,
    schema: dict[str, Any],
    workflow_input: dict[str, Any],
) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    missing: list[str] = []
    for raw_field in schema.get("required") or []:
        field = str(raw_field).strip()
        if not field:
            continue
        raw_field_schema = properties.get(field)
        field_schema: dict[str, Any] = (
            raw_field_schema if isinstance(raw_field_schema, dict) else {}
        )
        if "default" in field_schema:
            continue
        if _workflow_input_value(workflow_input, field) in (None, "", [], {}):
            missing.append(field)
    return sorted(set(missing))


def _workflow_input_type_or_enum_error(
    *,
    schema: dict[str, Any],
    workflow_input: dict[str, Any],
) -> str | None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    for field, raw_field_schema in properties.items():
        field_name = str(field).strip()
        if not field_name:
            continue
        value = _workflow_input_value(workflow_input, field_name)
        if value in (None, ""):
            continue
        field_schema = raw_field_schema if isinstance(raw_field_schema, dict) else {}
        for mismatch in schema_value_mismatches(
            value,
            field_schema,
            field_name,
            ignore_required_defaults=True,
        ):
            error = _workflow_input_schema_mismatch_error(mismatch)
            if error:
                return error
        constraint_error = _workflow_input_constraint_error(field_name, value, field_schema)
        if constraint_error:
            return constraint_error
    return None


def _workflow_input_schema_mismatch_error(mismatch: dict[str, Any]) -> str | None:
    field_name = str(mismatch.get("field") or "").strip()
    if not field_name:
        return None
    expected = mismatch.get("expected")
    actual = mismatch.get("actual")
    if expected == "required" and actual == "missing":
        return f"workflow_input_required_missing:{field_name}"
    if isinstance(expected, dict) and isinstance(expected.get("enum"), list):
        return f"workflow_input_enum_mismatch:{field_name}"
    expected_types = _workflow_input_expected_types(expected)
    if expected_types:
        return f"workflow_input_type_mismatch:{field_name}:{'|'.join(expected_types)}"
    return None


def _workflow_input_expected_types(raw_type: Any) -> list[str]:
    aliases = {
        "str": "string",
        "string": "string",
        "text": "string",
        "paragraph": "string",
        "select": "string",
        "email": "string",
        "url": "string",
        "uri": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "double": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
        "dict": "object",
        "map": "object",
    }
    normalized: list[str] = []
    raw_types = raw_type if isinstance(raw_type, list) else [raw_type]
    for item in raw_types:
        expected = aliases.get(str(item or "").strip().lower())
        if expected and expected not in normalized:
            normalized.append(expected)
    return normalized


def _workflow_input_matches_type(value: Any, expected_types: list[str]) -> bool:
    for expected_type in expected_types:
        if expected_type == "string" and isinstance(value, str):
            return True
        if expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if (
            expected_type == "number"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            return True
        if expected_type == "boolean" and isinstance(value, bool):
            return True
        if expected_type == "array" and isinstance(value, list):
            return True
        if expected_type == "object" and isinstance(value, dict):
            return True
    return False


def _workflow_input_constraint_error(
    field_name: str,
    value: Any,
    field_schema: dict[str, Any],
) -> str | None:
    min_length = _optional_int(field_schema.get("minLength"))
    if min_length is not None and (not isinstance(value, str) or len(value) < min_length):
        return f"workflow_input_constraint_violation:{field_name}:minLength"
    max_length = _optional_int(field_schema.get("maxLength"))
    if max_length is not None and (not isinstance(value, str) or len(value) > max_length):
        return f"workflow_input_constraint_violation:{field_name}:maxLength"

    min_items = _optional_int(field_schema.get("minItems"))
    if min_items is not None and (not isinstance(value, list) or len(value) < min_items):
        return f"workflow_input_constraint_violation:{field_name}:minItems"
    max_items = _optional_int(field_schema.get("maxItems"))
    if max_items is not None and (not isinstance(value, list) or len(value) > max_items):
        return f"workflow_input_constraint_violation:{field_name}:maxItems"

    numeric_value = _workflow_input_numeric_value(value)
    minimum = _optional_float(field_schema.get("minimum"))
    if minimum is not None and (numeric_value is None or numeric_value < minimum):
        return f"workflow_input_constraint_violation:{field_name}:minimum"
    maximum = _optional_float(field_schema.get("maximum"))
    if maximum is not None and (numeric_value is None or numeric_value > maximum):
        return f"workflow_input_constraint_violation:{field_name}:maximum"
    exclusive_minimum = _optional_float(field_schema.get("exclusiveMinimum"))
    if exclusive_minimum is not None and (
        numeric_value is None or numeric_value <= exclusive_minimum
    ):
        return f"workflow_input_constraint_violation:{field_name}:exclusiveMinimum"
    exclusive_maximum = _optional_float(field_schema.get("exclusiveMaximum"))
    if exclusive_maximum is not None and (
        numeric_value is None or numeric_value >= exclusive_maximum
    ):
        return f"workflow_input_constraint_violation:{field_name}:exclusiveMaximum"

    expected_format = str(field_schema.get("format") or "").strip().lower()
    if expected_format in {"email", "url", "uri"} and not _workflow_input_matches_format(
        value,
        expected_format,
    ):
        return f"workflow_input_constraint_violation:{field_name}:format"
    return None


def _workflow_input_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _workflow_input_matches_format(value: Any, expected_format: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    if expected_format == "email":
        local, separator, domain = candidate.partition("@")
        return bool(local and separator and "." in domain and not domain.endswith("."))
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _workflow_input_value(workflow_input: dict[str, Any], field: str) -> Any:
    current: Any = workflow_input
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _events_with_run_started(*, run: Any, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if events and str(events[0].get("event_type") or "") == "run_started":
        return events
    return [
        _run_started_event(
            mode=str(run.mode), workflow_input=dict(getattr(run, "input", {}) or {})
        ),
        *events,
    ]


def _run_succeeded_event(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "run_succeeded",
        "payload": {
            "status": "succeeded",
            "output_keys": sorted(str(key) for key in output),
        },
    }


async def dispatch_workflow_run_to_arq(
    *,
    run_id: str,
    owner_user_id: str,
    user_roles: list[str],
) -> None:
    arq_pool = await create_pool(
        build_arq_redis_settings(settings),
        default_queue_name=settings.ARQ_QUEUE_NAME,
    )
    try:
        await arq_pool.enqueue_job(
            "run_workflow_task",
            run_id,
            owner_user_id,
            user_roles,
            _job_id=run_id,
        )
    finally:
        close = getattr(arq_pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
        wait_closed = getattr(arq_pool, "wait_closed", None)
        if wait_closed is not None:
            result = wait_closed()
            if inspect.isawaitable(result):
                await result


def _model_contains_node_type(internal_model: dict[str, Any], node_type: str) -> bool:
    return _model_contains_any_node_type(internal_model, {node_type})


def _sub_workflow_dependencies(internal_model: dict[str, Any]) -> list[dict[str, str | None]]:
    graph = internal_model.get("graph") if isinstance(internal_model, dict) else None
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    dependencies: list[dict[str, str | None]] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "sub_workflow":
            continue
        raw_data = node.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        workflow_id = _sub_workflow_id_from_data(data)
        if not workflow_id:
            continue
        dependencies.append(
            {
                "workflow_id": workflow_id,
                "version_id": _sub_workflow_version_id_from_data(data),
            }
        )
    return dependencies


def _sub_workflow_id_from_data(data: dict[str, Any]) -> str:
    value = (
        data.get("workflow_id")
        or data.get("workflowId")
        or data.get("target_workflow_id")
        or data.get("targetWorkflowId")
        or data.get("app_id")
        or data.get("appId")
    )
    return str(value or "").strip()


def _sub_workflow_version_id_from_data(data: dict[str, Any]) -> str | None:
    value = (
        data.get("version_id")
        or data.get("versionId")
        or data.get("workflow_version_id")
        or data.get("workflowVersionId")
    )
    text = str(value or "").strip()
    return text or None


def _sub_workflow_ref_key(workflow_id: str, version_id: str | None = None) -> str:
    return f"{workflow_id}@{version_id or 'published'}"


def _append_sub_workflow_stack(
    stack: tuple[str, ...],
    current_workflow_id: str,
    child_workflow_id: str,
) -> tuple[str, ...]:
    ordered = [*stack, current_workflow_id, child_workflow_id]
    deduped: list[str] = []
    for workflow_id in ordered:
        if workflow_id and workflow_id not in deduped:
            deduped.append(workflow_id)
    return tuple(deduped)


def _blocked_import_errors(compatibility_report: dict[str, Any]) -> list[str]:
    unsupported_nodes = compatibility_report.get("unsupported_nodes")
    if not isinstance(unsupported_nodes, list):
        return []
    errors: list[str] = []
    for raw_node in unsupported_nodes:
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id") or "")
        source_type = str(raw_node.get("type") or "").strip().lower()
        reason = str(raw_node.get("reason") or "unsupported_node_type")
        if source_type == "code" and reason == "blocked_by_policy":
            errors.append(f"workflow_code_node_blocked_by_policy:{node_id}")
        elif source_type in {"sub-workflow", "sub_workflow"} and reason == "blocked_by_policy":
            errors.append(f"workflow_sub_workflow_node_blocked_by_policy:{node_id}")
        elif source_type in {"human-approval", "human_approval"} and reason == "blocked_by_policy":
            errors.append(f"workflow_human_approval_node_blocked_by_policy:{node_id}")
        elif reason == "blocked_by_policy":
            errors.append(f"workflow_node_blocked_by_policy:{node_id}:{source_type or 'unknown'}")
    return errors


async def _resolve_credential_ref_mappings() -> dict[str, dict[str, str]]:
    try:
        from pathlib import Path

        from src.infra.extensions.plugin_settings import PluginSettingsResolver
        from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

        manifest = build_workflow_plugin_manifest()
        manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / "workflow")
        resolver = PluginSettingsResolver(plugin_id="workflow", manifests=(manifest,))
        raw = await resolver.get("CREDENTIAL_REF_MAPPINGS", {})
    except Exception:
        raw = {}
    return _normalize_credential_ref_mappings(raw)


def _normalize_credential_ref_mappings(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for raw_ref, raw_mapping in raw.items():
        ref = str(raw_ref or "").strip()
        if not ref:
            continue
        if isinstance(raw_mapping, str):
            target = raw_mapping.strip()
            mapping_type = "credential_ref"
            label = ""
            description = ""
        elif isinstance(raw_mapping, dict):
            target = str(
                raw_mapping.get("target")
                or raw_mapping.get("target_ref")
                or raw_mapping.get("credential_ref")
                or raw_mapping.get("credential_id")
                or raw_mapping.get("model_id")
                or ""
            ).strip()
            mapping_type = str(
                raw_mapping.get("type") or raw_mapping.get("kind") or "credential_ref"
            ).strip()
            label = str(raw_mapping.get("label") or raw_mapping.get("name") or "").strip()
            description = str(raw_mapping.get("description") or "").strip()
        else:
            continue
        if not target:
            continue
        entry = {"ref": ref, "type": mapping_type or "credential_ref", "target": target}
        if label:
            entry["label"] = label
        if description:
            entry["description"] = description
        normalized[ref] = entry
    return normalized


def _credential_refs_required(report: dict[str, Any]) -> list[str]:
    refs = report.get("credential_refs_required") if isinstance(report, dict) else None
    if not isinstance(refs, list):
        return []
    return sorted({str(ref).strip() for ref in refs if str(ref).strip()})


def _credential_resolution_payload(
    required_refs: list[str],
    mappings: dict[str, dict[str, str]],
) -> dict[str, Any]:
    resolved = [mappings[ref] for ref in required_refs if ref in mappings]
    unresolved = [ref for ref in required_refs if ref not in mappings]
    return {
        "credential_refs_required": required_refs,
        "credential_refs_resolved": resolved,
        "credential_refs_unresolved": unresolved,
    }


async def _resolve_knowledge_dataset_mappings() -> dict[str, list[str]]:
    try:
        from pathlib import Path

        from src.infra.extensions.plugin_settings import PluginSettingsResolver
        from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

        manifest = build_workflow_plugin_manifest()
        manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / "workflow")
        resolver = PluginSettingsResolver(plugin_id="workflow", manifests=(manifest,))
        raw = await resolver.get("KNOWLEDGE_DATASET_MAPPINGS", {})
    except Exception:
        raw = {}
    return _normalize_knowledge_dataset_mappings(raw)


def _normalize_knowledge_dataset_mappings(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in raw.items():
        dataset_id = str(key or "").strip()
        if not dataset_id:
            continue
        if isinstance(value, dict):
            memory_types = (
                value.get("memory_types") or value.get("memoryTypes") or value.get("types")
            )
        else:
            memory_types = value
        if isinstance(memory_types, str):
            items = [item.strip() for item in memory_types.split(",")]
        elif isinstance(memory_types, list | tuple | set):
            items = [str(item).strip() for item in memory_types]
        else:
            items = []
        normalized[dataset_id] = sorted({item for item in items if item})
    return normalized


def _memory_types_for_dataset_ids(
    dataset_ids: list[str],
    mapping: dict[str, list[str]],
) -> dict[str, list[str]]:
    resolved: list[str] = []
    unresolved: list[str] = []
    memory_types: list[str] = []
    for dataset_id in dataset_ids:
        mapped_types = mapping.get(dataset_id)
        if mapped_types:
            resolved.append(dataset_id)
            memory_types.extend(mapped_types)
        else:
            unresolved.append(dataset_id)
    return {
        "resolved_dataset_ids": resolved,
        "unresolved_dataset_ids": unresolved,
        "memory_types": sorted(set(memory_types)),
    }


def _model_contains_any_node_type(internal_model: dict[str, Any], node_types: set[str]) -> bool:
    graph = internal_model.get("graph") if isinstance(internal_model, dict) else None
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    return any(isinstance(node, dict) and node.get("type") in node_types for node in nodes)


def _langchain_messages_from_request(
    request: dict[str, Any],
    *,
    ai_message_cls,
    human_message_cls,
    system_message_cls,
):
    messages = []
    system_prompt = request.get("system_prompt")
    if system_prompt:
        messages.append(system_message_cls(content=str(system_prompt)))
    for item in request.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").lower()
        content = str(item.get("content") or "")
        if not content:
            continue
        if role == "system":
            messages.append(system_message_cls(content=content))
        elif role == "assistant":
            messages.append(ai_message_cls(content=content))
        else:
            messages.append(human_message_cls(content=content))
    prompt = request.get("prompt")
    if prompt:
        messages.append(human_message_cls(content=str(prompt)))
    return messages


async def _invoke_openai_compatible_without_streaming(
    *,
    model_kwargs: dict[str, Any],
    messages: list[Any],
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    resolved = await _resolve_llm_direct_model_kwargs(model_kwargs)
    api_key = resolved.get("api_key") or "sk-placeholder"
    api_base = resolved.get("api_base") or None
    model = resolved.get("model")
    payload: dict[str, Any] = {
        "model": str(model or ""),
        "messages": [_openai_message_payload(message) for message in messages],
        "temperature": resolved.get("temperature"),
        "stream": False,
    }
    max_tokens = resolved.get("max_tokens")
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    client = AsyncOpenAI(api_key=str(api_key), base_url=str(api_base) if api_base else None)
    response = await client.chat.completions.create(**payload)
    return _normalize_openai_compatible_response(response)


async def _resolve_llm_direct_model_kwargs(model_kwargs: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(model_kwargs)
    model = str(resolved.get("model") or "").strip()
    model_id = str(resolved.get("model_id") or "").strip()
    stored_model = None

    try:
        from src.infra.agent.model_storage import get_model_storage
        from src.infra.llm.models_service import get_default_model, get_default_model_id

        storage = get_model_storage()
        if model_id:
            stored_model = await storage.get(model_id)
        elif model:
            get_by_value = getattr(storage, "get_by_value", None)
            if get_by_value is not None:
                stored_model = await get_by_value(model)
        else:
            default_model_id = await get_default_model_id()
            if default_model_id:
                stored_model = await storage.get(default_model_id)
            if stored_model is None:
                model = await get_default_model()
    except Exception:
        stored_model = None

    if stored_model is None and not model:
        from src.infra.llm.models_service import get_default_model

        model = await get_default_model()

    if stored_model is not None:
        resolved["model"] = getattr(stored_model, "value", None) or resolved.get("model")
        resolved["model_id"] = getattr(stored_model, "id", None) or resolved.get("model_id")
        resolved["provider"] = getattr(stored_model, "provider", None) or resolved.get("provider")
        resolved["api_key"] = resolved.get("api_key") or getattr(stored_model, "api_key", None)
        resolved["api_base"] = resolved.get("api_base") or getattr(stored_model, "api_base", None)
        if getattr(stored_model, "temperature", None) is not None:
            resolved["temperature"] = getattr(stored_model, "temperature")
        if (
            resolved.get("max_tokens") is None
            and getattr(stored_model, "max_tokens", None) is not None
        ):
            resolved["max_tokens"] = getattr(stored_model, "max_tokens")
    elif model and not resolved.get("model"):
        resolved["model"] = model

    model_value = str(resolved.get("model") or "").strip()
    if model_value:
        from src.infra.llm.client import _parse_provider, _resolve_protocol
        from src.infra.llm.models_service import get_cached_api_key

        parsed_provider, model_name = _parse_provider(model_value)
        provider = str(resolved.get("provider") or parsed_provider)
        if _resolve_protocol(provider) != "openai":
            raise ValueError(f"workflow_llm_non_streaming_fallback_unsupported_provider:{provider}")
        resolved["model"] = model_name
        if not resolved.get("api_key"):
            resolved["api_key"] = get_cached_api_key(model_value)
    return resolved


def _should_retry_llm_without_streaming(exc: Exception) -> bool:
    message = str(exc)
    return "No generations found in stream" in message or "model_dump" in message


def _openai_message_payload(message: Any) -> dict[str, str]:
    role = getattr(message, "type", None) or getattr(message, "role", None) or "user"
    if role == "human":
        role = "user"
    elif role == "ai":
        role = "assistant"
    elif role not in {"system", "assistant", "user", "tool"}:
        role = "user"
    return {"role": str(role), "content": _message_content_text(message)}


def _normalize_openai_compatible_response(response: Any) -> dict[str, Any]:
    if isinstance(response, str):
        return {"text": response, "usage": {}, "model": None}
    data = response if isinstance(response, dict) else response.model_dump()
    if isinstance(data, str):
        return {"text": data, "usage": {}, "model": None}
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise ValueError(f"workflow_llm_non_streaming_response_missing_choices:{data}")
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        text = "".join(
            str(item.get("text") or item) if isinstance(item, dict) else str(item)
            for item in content
        )
    else:
        text = "" if content is None else str(content)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {"text": text, "usage": usage, "model": data.get("model")}


def _message_content_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)
    return "" if content is None else str(content)


def _message_usage(message: Any) -> dict[str, Any]:
    usage = getattr(message, "usage_metadata", None) or getattr(message, "response_metadata", None)
    return usage if isinstance(usage, dict) else {}


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_workflow_source_payload(
    *,
    source_format: str,
    source_payload: dict[str, Any] | None = None,
    source_content: str | None = None,
) -> dict[str, Any]:
    if source_content is None or not source_content.strip():
        return source_payload or {}

    normalized_format = source_format.strip().lower()
    try:
        if normalized_format == "json":
            parsed = json.loads(source_content)
        elif normalized_format == "yaml":
            parsed = yaml.safe_load(source_content)
        else:
            raise ValueError(f"workflow_source_format_not_supported:{source_format}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"workflow_source_parse_failed:{normalized_format}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("workflow_source_must_be_mapping")
    return parsed
