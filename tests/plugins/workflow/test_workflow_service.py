from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.user import TokenPayload
from src.plugins.workflow.models import (
    WorkflowCredential,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowVersion,
)
from src.plugins.workflow.policy import build_http_request_policy
from src.plugins.workflow.service import (
    WorkflowPluginService,
    _memory_types_for_dataset_ids,
    _normalize_credential_ref_mappings,
    _normalize_knowledge_dataset_mappings,
    dispatch_workflow_run_to_arq,
    resolve_workflow_source_payload,
)
from src.plugins.workflow.tools import (
    infer_workflow_input_schema_payload,
    infer_workflow_output_schema_payload,
)


def _user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["workflow:read", "workflow:write"],
    )


class _FakeStorage:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.created_versions: list[dict] = []
        self.created_runs: list[dict] = []
        self.published: list[dict] = []
        self.unpublished: list[dict] = []
        self.run_events: list[dict] = []
        self.finished: list[dict] = []
        self.list_versions_calls: list[dict] = []
        self.list_runs_calls: list[dict] = []
        self.list_pending_approval_runs_calls: list[dict] = []
        self.list_run_events_calls: list[dict] = []
        self.version_node_type = "answer"
        self.credential_refs_required: list[str] = []
        self.credentials_by_ref: dict[str, WorkflowCredential] = {}
        self.credential_secrets_by_ref: dict[str, str] = {}
        self.current_run_status = "running"
        self.current_run_error: str | None = None
        self.current_run_output: dict[str, Any] = {}
        self.workflow_status = "draft"
        self.published_version_id: str | None = None
        self.latest_internal_model: dict[str, Any] | None = None
        self.child_published_version_id: str | None = "wfv-child"
        self.child_version_node_type = "child_answer"
        self.paused_run: WorkflowRun | None = None

    async def create_imported_workflow(self, **kwargs):
        self.created.append(kwargs)
        self.latest_internal_model = kwargs.get("internal_model") or None
        definition = type("Definition", (), {"workflow_id": "wf-created"})()
        version = type("Version", (), {"version_id": "wfv-created"})()
        return definition, version

    async def list_credential_refs(self, **kwargs):
        return self.credentials_by_ref

    async def list_credentials(self, **kwargs):
        return list(self.credentials_by_ref.values())

    async def get_credential_secret_by_ref(self, **kwargs):
        return self.credential_secrets_by_ref.get(kwargs["ref"])

    async def upsert_credential(self, **kwargs):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        credential = WorkflowCredential(
            credential_id="wfc-created",
            owner_user_id=kwargs["owner_user_id"],
            ref=kwargs["ref"],
            type=kwargs["credential_type"],
            label=kwargs.get("label") or "",
            description=kwargs.get("description") or "",
            has_secret=kwargs.get("secret") is not None,
            metadata=kwargs.get("metadata") or {},
            created_at=now,
            updated_at=now,
        )
        self.credentials_by_ref[credential.ref] = credential
        return credential

    async def delete_credential(self, **kwargs):
        for ref, credential in list(self.credentials_by_ref.items()):
            if credential.credential_id == kwargs["credential_id"]:
                del self.credentials_by_ref[ref]
                return True
        return False

    async def get_workflow(self, workflow_id: str, **kwargs):
        if workflow_id == "wf-child":
            return type(
                "Definition",
                (),
                {
                    "workflow_id": workflow_id,
                    "name": "Child",
                    "status": "published",
                    "latest_version_id": "wfv-child",
                    "published_version_id": self.child_published_version_id,
                    "version_count": 1,
                },
            )()
        if workflow_id != "wf-created":
            return None
        return type(
            "Definition",
            (),
            {
                "workflow_id": workflow_id,
                "name": "Persisted",
                "status": self.workflow_status,
                "latest_version_id": "wfv-created",
                "published_version_id": self.published_version_id,
                "version_count": 1,
            },
        )()

    async def get_version(self, version_id: str, **kwargs):
        if version_id == "wfv-child":
            return self._version(
                version_id="wfv-child",
                workflow_id="wf-child",
                node_type=self.child_version_node_type,
            )
        if version_id == "wfv-explicit":
            return self._version(
                version_id="wfv-explicit",
                version_number=7,
                node_type="schema_explicit_inputs",
            )
        if version_id != "wfv-created":
            return None
        return self._version()

    async def get_latest_version(self, workflow_id: str, **kwargs):
        return self._version() if workflow_id == "wf-created" else None

    async def list_versions(self, workflow_id: str, **kwargs):
        self.list_versions_calls.append({"workflow_id": workflow_id, **kwargs})
        return [self._version()]

    async def create_workflow_version(self, **kwargs):
        self.created_versions.append(kwargs)
        self.latest_internal_model = kwargs.get("internal_model") or None
        definition = type(
            "Definition",
            (),
            {
                "workflow_id": kwargs["workflow_id"],
                "name": kwargs.get("name") or "Persisted",
                "latest_version_id": "wfv-2",
                "published_version_id": None,
                "version_count": 2,
            },
        )()
        version = self._version(version_id="wfv-2", version_number=2)
        return definition, version

    async def publish_workflow(self, **kwargs):
        self.published.append(kwargs)
        self.workflow_status = "published"
        self.published_version_id = kwargs["version_id"]
        return type(
            "Definition",
            (),
            {
                "workflow_id": kwargs["workflow_id"],
                "name": "Persisted",
                "status": "published",
                "latest_version_id": "wfv-created",
                "published_version_id": kwargs["version_id"],
            },
        )()

    async def unpublish_workflow(self, **kwargs):
        self.unpublished.append(kwargs)
        self.workflow_status = "draft"
        self.published_version_id = None
        return type(
            "Definition",
            (),
            {
                "workflow_id": kwargs["workflow_id"],
                "name": "Persisted",
                "status": "draft",
                "latest_version_id": "wfv-created",
                "published_version_id": None,
            },
        )()

    async def get_run(self, run_id: str, **kwargs):
        if run_id != "wfr-created":
            return None
        if self.paused_run is not None:
            return self.paused_run
        return WorkflowRun(
            run_id="wfr-created",
            workflow_id="wf-created",
            version_id="wfv-created",
            owner_user_id="user-1",
            status=self.current_run_status,
            mode="sync",
            input={"name": "LambChat"},
            output=self.current_run_output,
            error=self.current_run_error,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
            if self.current_run_status in {"succeeded", "failed", "cancelled"}
            else None,
        )

    async def list_runs(self, workflow_id: str, **kwargs):
        self.list_runs_calls.append({"workflow_id": workflow_id, **kwargs})
        return [
            WorkflowRun(
                run_id="wfr-created",
                workflow_id=workflow_id,
                version_id="wfv-created",
                owner_user_id="user-1",
                status="succeeded",
                mode="sync",
                input={"name": "LambChat"},
                output={"answer": "Hi LambChat"},
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    async def list_pending_approval_runs(self, **kwargs):
        self.list_pending_approval_runs_calls.append(kwargs)
        return [
            WorkflowRun(
                run_id="wfr-paused",
                workflow_id="wf-created",
                version_id="wfv-created",
                owner_user_id="user-1",
                status="paused",
                mode="async",
                input={"name": "LambChat"},
                output={},
                error="workflow_human_approval_paused:approval",
                pause={
                    "kind": "human_approval",
                    "pending_approval": {"node_id": "approval", "instructions": "Approve LambChat"},
                },
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                finished_at=None,
            )
        ]

    async def list_run_events(self, run_id: str, **kwargs):
        self.list_run_events_calls.append({"run_id": run_id, **kwargs})
        return [
            WorkflowRunEvent(
                event_id="wfe-created",
                run_id=run_id,
                workflow_id="wf-created",
                version_id="wfv-created",
                owner_user_id="user-1",
                sequence=1,
                event_type="node_started",
                node_id="start",
                node_type="start",
                payload={"title": "Start"},
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    async def create_run(self, **kwargs):
        self.created_runs.append(kwargs)
        run_id = "wfr-child" if kwargs["workflow_id"] == "wf-child" else "wfr-created"
        return WorkflowRun(
            run_id=run_id,
            workflow_id=kwargs["workflow_id"],
            version_id=kwargs["version_id"],
            owner_user_id=kwargs["owner_user_id"],
            status="running",
            mode=kwargs["mode"],
            input=kwargs["workflow_input"],
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    async def append_run_events(self, **kwargs):
        self.run_events.extend(kwargs["events"])
        run = kwargs["run"]
        return [
            WorkflowRunEvent(
                event_id=f"wfe-{index}",
                run_id=run.run_id,
                workflow_id=run.workflow_id,
                version_id=run.version_id,
                owner_user_id=run.owner_user_id,
                sequence=index,
                event_type=event["event_type"],
                node_id=event.get("node_id"),
                node_type=event.get("node_type"),
                payload=event.get("payload", {}),
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            for index, event in enumerate(kwargs["events"], start=1)
        ]

    async def finish_run(self, **kwargs):
        self.finished.append(kwargs)
        if kwargs["run_id"] == "wfr-created":
            self.paused_run = None
            self.current_run_status = kwargs["status"]
            self.current_run_output = kwargs.get("output") or {}
            self.current_run_error = kwargs.get("error")
        workflow_id = "wf-child" if kwargs["run_id"] == "wfr-child" else "wf-created"
        version_id = "wfv-child" if kwargs["run_id"] == "wfr-child" else "wfv-created"
        return WorkflowRun(
            run_id=kwargs["run_id"],
            workflow_id=workflow_id,
            version_id=version_id,
            owner_user_id=kwargs["owner_user_id"],
            status=kwargs["status"],
            mode="sync",
            input={"name": "LambChat"},
            output=kwargs.get("output") or {},
            error=kwargs.get("error"),
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    async def pause_run(self, **kwargs):
        self.finished.append({**kwargs, "status": "paused"})
        self.current_run_status = "paused"
        self.current_run_output = kwargs.get("output") or {}
        self.current_run_error = kwargs.get("error")
        self.paused_run = WorkflowRun(
            run_id=kwargs["run_id"],
            workflow_id="wf-created",
            version_id="wfv-created",
            owner_user_id=kwargs["owner_user_id"],
            status="paused",
            mode="sync",
            input={"name": "LambChat"},
            output=kwargs.get("output") or {},
            error=kwargs.get("error"),
            pause=kwargs.get("pause") or {},
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=None,
        )
        return self.paused_run

    async def cancel_run(self, **kwargs):
        self.finished.append({**kwargs, "status": "cancelled"})
        self.current_run_status = "cancelled"
        self.current_run_output = {}
        self.current_run_error = "workflow_run_cancelled_by_user"
        run = WorkflowRun(
            run_id=kwargs["run_id"],
            workflow_id="wf-created",
            version_id="wfv-created",
            owner_user_id=kwargs["owner_user_id"],
            status="cancelled",
            mode="async",
            input={"name": "LambChat"},
            output={},
            error="workflow_run_cancelled_by_user",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        events = await self.append_run_events(
            run=run,
            events=[
                {
                    "event_type": "run_cancelled",
                    "payload": {
                        "error": "workflow_run_cancelled_by_user",
                        "cancelled_by": kwargs["owner_user_id"],
                    },
                }
            ],
        )
        return run, events

    def _version(
        self,
        *,
        version_id: str = "wfv-created",
        version_number: int = 1,
        workflow_id: str = "wf-created",
        node_type: str | None = None,
    ) -> WorkflowVersion:
        node_type = node_type or self.version_node_type
        if self.latest_internal_model and workflow_id == "wf-created":
            return WorkflowVersion(
                version_id=version_id,
                workflow_id=workflow_id,
                owner_user_id="user-1",
                version_number=version_number,
                source="workflow",
                source_format="json",
                internal_model=self.latest_internal_model,
                source_payload={},
                compatibility_report={"lossless": True},
                created_by="user-1",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        nodes = [
            {"id": "start", "type": "start", "supported": True, "data": {}},
            {
                "id": node_type,
                "type": node_type,
                "supported": True,
                "data": {"answer": "Hi {{name}}"},
            },
        ]
        edges = [{"id": "e1", "source": "start", "target": node_type, "valid": True}]
        if node_type == "condition":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "condition",
                    "type": "condition",
                    "supported": True,
                    "data": {"conditions": [{"variable": "name", "operator": "not_empty"}]},
                },
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "Hi"}},
                {"id": "fallback", "type": "answer", "supported": True, "data": {"answer": "Fallback"}},
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "condition", "valid": True},
                {
                    "id": "e2",
                    "source": "condition",
                    "target": "answer",
                    "source_handle": "true",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "condition",
                    "target": "fallback",
                    "source_handle": "false",
                    "valid": True,
                },
            ]
        if node_type == "boundary_edges":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "Hi"}},
                {"id": "end", "type": "end", "supported": True, "data": {}},
            ]
            edges = [
                {"id": "valid", "source": "start", "target": "answer", "valid": True},
                {"id": "to-start", "source": "answer", "target": "start", "valid": False},
                {"id": "from-exit", "source": "end", "target": "answer", "valid": False},
            ]
        if node_type == "tool_call":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool_call",
                    "type": "tool_call",
                    "supported": True,
                    "data": {
                        "tool_name": "echo_tool",
                        "arguments": {"text": "Hi {{name}}"},
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{tool_result.text}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "tool_call", "valid": True},
                {"id": "e2", "source": "tool_call", "target": "answer", "valid": True},
            ]
        if node_type == "http_request":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {"method": "GET", "url": "https://api.example.com/status/{{name}}"},
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{http.body}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "http", "valid": True},
                {"id": "e2", "source": "http", "target": "answer", "valid": True},
            ]
        if node_type == "http_request_auth":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "http",
                    "type": "http_request",
                    "supported": True,
                    "data": {
                        "method": "GET",
                        "url": "https://api.example.com/status/{{name}}",
                        "authorization": {"type": "bearer"},
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{http.body}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "http", "valid": True},
                {"id": "e2", "source": "http", "target": "answer", "valid": True},
            ]
        if node_type == "human_approval":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "approval",
                    "type": "human_approval",
                    "supported": True,
                    "title": "Manager approval",
                    "data": {
                        "instructions": "Approve {{name}}",
                        "assignee": "manager",
                        "output_key": "approval",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Approved {{approval.comment}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "approval", "valid": True},
                {"id": "e2", "source": "approval", "target": "answer", "valid": True},
            ]
        if node_type == "knowledge_retrieval":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "knowledge",
                    "type": "knowledge_retrieval",
                    "supported": True,
                    "data": {
                        "query_variable_selector": ["name"],
                        "dataset_ids": ["dataset-1"],
                        "output_key": "knowledge",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{knowledge.text}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "knowledge", "valid": True},
                {"id": "e2", "source": "knowledge", "target": "answer", "valid": True},
            ]
        if node_type == "llm_prompt":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "llm",
                    "type": "llm",
                    "supported": True,
                    "data": {
                        "model": {"provider": "openai", "name": "gpt-4o-mini"},
                        "prompt_template": "Say hi to {{name}}",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{llm.text}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "llm", "valid": True},
                {"id": "e2", "source": "llm", "target": "answer", "valid": True},
            ]
        if node_type == "parameter_extractor":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "extract",
                    "type": "parameter_extractor",
                    "supported": True,
                    "data": {
                        "query": "{{name}} wants workflow help",
                        "parameters": [{"name": "topic", "type": "string"}],
                        "output_key": "extracted",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{extracted.topic}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "extract", "valid": True},
                {"id": "e2", "source": "extract", "target": "answer", "valid": True},
            ]
        if node_type == "question_classifier":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "classify",
                    "type": "question_classifier",
                    "supported": True,
                    "data": {
                        "query": "{{name}} needs help",
                        "classes": [
                            {"id": "billing", "name": "Billing"},
                            {"id": "general", "name": "General"},
                        ],
                        "output_key": "question_class",
                    },
                },
                {"id": "billing", "type": "answer", "supported": True, "data": {"answer": "Billing"}},
                {"id": "general", "type": "answer", "supported": True, "data": {"answer": "General"}},
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "classify", "valid": True},
                {
                    "id": "e2",
                    "source": "classify",
                    "target": "billing",
                    "source_handle": "billing",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "classify",
                    "target": "general",
                    "source_handle": "default",
                    "valid": True,
                },
            ]
        if node_type == "data_transform":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "template",
                    "type": "template_transform",
                    "supported": True,
                    "data": {"template": "Hello {{name}}", "output_key": "rendered"},
                },
                {
                    "id": "aggregate",
                    "type": "variable_aggregator",
                    "supported": True,
                    "data": {
                        "output_key": "picked",
                        "variables": [
                            {"variable_selector": ["fallback"]},
                            {"variable_selector": ["rendered"]},
                        ],
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{picked}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "template", "valid": True},
                {"id": "e2", "source": "template", "target": "aggregate", "valid": True},
                {"id": "e3", "source": "aggregate", "target": "answer", "valid": True},
            ]
        if node_type == "schema_inputs":
            nodes = [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {
                                "name": "name",
                                "type": "string",
                                "required": True,
                                "description": "Display name",
                                "default": "Visitor",
                                "minLength": 2,
                                "maxLength": 40,
                            },
                            {
                                "name": "tone",
                                "type": "select",
                                "required": False,
                                "defaultValue": "warm",
                                "options": [
                                    {"label": "Warm", "value": "warm"},
                                    {"label": "Formal", "value": "formal"},
                                ],
                            },
                            {
                                "name": "count",
                                "inputType": "int",
                                "minimum": 1,
                                "maximum": 5,
                                "value": 2,
                            },
                            {
                                "name": "contact",
                                "type": "email",
                            },
                            {
                                "name": "links",
                                "type": "list",
                                "minItems": 1,
                                "maxItems": 3,
                            },
                            {
                                "name": "attachment",
                                "type": "file",
                                "description": "Uploaded file metadata",
                            }
                        ]
                    },
                },
                {
                    "id": "template",
                    "type": "template_transform",
                    "supported": True,
                    "data": {"template": "Hello {{name}}", "output_key": "rendered"},
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{rendered}} {{#sys.query#}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "template", "valid": True},
                {"id": "e2", "source": "template", "target": "answer", "valid": True},
            ]
        if node_type == "schema_explicit_inputs":
            nodes = [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "variables": [
                            {"name": "explicit_message", "type": "string", "required": True},
                        ]
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{explicit_message}}"},
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "answer", "valid": True}]
        if node_type == "schema_outputs":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "end",
                    "type": "end",
                    "supported": True,
                    "data": {
                        "outputs": [
                            {"name": "summary", "type": "string", "description": "Rendered summary"},
                            {"name": "count", "type": "integer"},
                        ]
                    },
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "end", "valid": True}]
        if node_type == "sub_workflow":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "subflow",
                    "type": "sub_workflow",
                    "supported": True,
                    "data": {
                        "workflow_id": "wf-child",
                        "inputs": {"name": "{{name}}"},
                        "output_key": "child",
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "{{child.answer}}"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "subflow", "valid": True},
                {"id": "e2", "source": "subflow", "target": "answer", "valid": True},
            ]
        if node_type == "self_sub_workflow":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "subflow",
                    "type": "sub_workflow",
                    "supported": True,
                    "data": {"workflow_id": "wf-created"},
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "subflow", "valid": True}]
        if node_type == "child_answer":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "Child {{name}}"},
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "answer", "valid": True}]
        if node_type == "child_calls_parent":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "subflow",
                    "type": "sub_workflow",
                    "supported": True,
                    "data": {"workflow_id": "wf-created"},
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "subflow", "valid": True}]
        if node_type == "blocked_code":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "code",
                    "type": "unsupported",
                    "source_type": "code",
                    "supported": False,
                    "data": {"language": "python3", "code": "return inputs"},
                    "metadata": {
                        "unsupported_reason": "blocked_by_policy",
                        "policy": "code_execution_disabled",
                    },
                },
            ]
            edges = [{"id": "e1", "source": "start", "target": "code", "valid": True}]
        if node_type == "hidden_llm_branch":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "condition", "type": "condition", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "llm", "type": "llm", "supported": True, "data": {}},
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "condition", "valid": True},
                {
                    "id": "e2",
                    "source": "condition",
                    "target": "answer",
                    "source_handle": "false",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "condition",
                    "target": "llm",
                    "source_handle": "true",
                    "valid": True,
                },
            ]
        if node_type == "unreachable_llm":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "ok"}},
                {"id": "orphan_llm", "type": "llm", "supported": True, "data": {"prompt": "hidden"}},
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "answer", "valid": True},
            ]
        if node_type == "hidden_missing_tool_branch":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {"id": "condition", "type": "condition", "supported": True, "data": {}},
                {
                    "id": "echo",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "echo_tool"},
                },
                {
                    "id": "missing",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "missing_tool"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "condition", "valid": True},
                {
                    "id": "e2",
                    "source": "condition",
                    "target": "echo",
                    "source_handle": "false",
                    "valid": True,
                },
                {
                    "id": "e3",
                    "source": "condition",
                    "target": "missing",
                    "source_handle": "true",
                    "valid": True,
                },
            ]
        if node_type == "missing_tool_runtime":
            nodes = [
                {"id": "start", "type": "start", "supported": True, "data": {}},
                {
                    "id": "tool",
                    "type": "tool_call",
                    "supported": True,
                    "data": {"tool_name": "missing_tool"},
                },
            ]
            edges = [
                {"id": "e1", "source": "start", "target": "tool", "valid": True},
            ]
        return WorkflowVersion(
            version_id=version_id,
            workflow_id=workflow_id,
            owner_user_id="user-1",
            version_number=version_number,
            source_format="json",
            source_payload={},
            internal_model={
                "graph": {
                    "nodes": nodes,
                    "edges": edges,
                }
            },
            compatibility_report={"credential_refs_required": self.credential_refs_required},
            created_by="user-1",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


class _EchoTool(BaseTool):
    name: str = "echo_tool"
    description: str = "Echo test tool"

    def _run(self, *args, **kwargs):
        return {"text": kwargs.get("text") or args[0].get("text")}

    async def _arun(self, *args, **kwargs):
        return {"text": kwargs.get("text") or args[0].get("text")}


@pytest.mark.asyncio
async def test_import_workflow_dry_run_does_not_write_storage() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    definition, version, report = await service.import_workflow(
        name="Dry Run",
        source_format="json",
        source_payload={"version": "0.3.0", "workflow": {"nodes": [{"id": "start"}]}},
        dry_run=True,
        user=_user(),
    )

    assert definition is None
    assert version is None
    assert storage.created == []
    assert report["source"] == "workflow"
    assert report["source_version"] == "0.3.0"
    assert report["metadata"]["detected_node_count"] == 1


@pytest.mark.asyncio
async def test_import_workflow_dry_run_reports_boundary_edge_errors() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    _definition, _version, report = await service.import_workflow(
        name="Boundary",
        source_format="json",
        source_payload={
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "answer", "type": "answer"},
                ],
                "edges": [
                    {"id": "answer-to-start", "source": "answer", "target": "start"}
                ],
            },
        },
        dry_run=True,
        user=_user(),
    )

    assert storage.created == []
    assert report["errors"] == [
        "boundary_edge_targets_entry:answer-to-start:answer->start"
    ]
    assert report["lossless"] is False


@pytest.mark.asyncio
async def test_import_workflow_persists_source_snapshot_and_internal_model() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    source_payload = {"version": "0.3.0", "app": {"name": "Demo"}}

    definition, version, report = await service.import_workflow(
        name="Persisted",
        source_format="json",
        source_payload=source_payload,
        dry_run=False,
        user=_user(),
    )

    assert definition.workflow_id == "wf-created"
    assert version.version_id == "wfv-created"
    assert report["workflow_id"] == "wf-created"
    created = storage.created[0]
    assert created["owner_user_id"] == "user-1"
    assert created["created_by"] == "user-1"
    assert created["name"] == "Persisted"
    assert created["source_payload"] == source_payload
    assert created["internal_model"]["format"] == "lambchat.workflow.v1"
    assert created["internal_model"]["source"] == "workflow"


@pytest.mark.asyncio
async def test_imported_blank_workflow_io_contract_is_declared_end_to_end() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    source_payload = {
        "version": "0.3.0",
        "app": {"name": "Blank Contract", "mode": "workflow"},
        "workflow": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "data": {
                        "title": "Start",
                        "variables": [
                            {
                                "name": "message",
                                "type": "string",
                                "required": True,
                                "description": "Workflow entry message",
                            }
                        ],
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "Workflow entry message",
                                }
                            },
                            "required": ["message"],
                            "additionalProperties": True,
                        },
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "data": {
                        "title": "Answer",
                        "answer": "{{message}}",
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "answer": {
                                    "type": "string",
                                    "description": "Workflow answer text",
                                }
                            },
                            "required": ["answer"],
                            "additionalProperties": True,
                        },
                    },
                },
            ],
            "edges": [{"id": "start-answer", "source": "start", "target": "answer"}],
        },
    }

    definition, version, _report = await service.import_workflow(
        name="Blank Contract",
        source_format="json",
        source_payload=source_payload,
        dry_run=False,
        user=_user(),
    )
    contract = await service.get_workflow_io_contract(
        definition.workflow_id,
        owner_user_id="user-1",
        version_id=version.version_id,
    )

    assert contract["workflow_id"] == "wf-created"
    assert contract["version_id"] == "wfv-created"
    assert contract["input_schema_source"] == "declared"
    assert contract["output_schema_source"] == "declared"
    assert contract["input_schema"]["required"] == ["message"]
    assert contract["input_schema"]["properties"]["message"]["description"] == "Workflow entry message"
    assert contract["output_schema"]["required"] == ["answer"]
    assert contract["output_schema"]["properties"]["answer"]["description"] == "Workflow answer text"
    assert contract["inferred_input_fields"] == []
    assert contract["inferred_output_fields"] == []


def test_normalize_credential_ref_mappings_keeps_only_safe_reference_metadata() -> None:
    mappings = _normalize_credential_ref_mappings(
        {
            " llm:provider_credential_id:openai-main ": {
                "type": "model",
                "model_id": "model-openai-main",
                "label": "OpenAI main",
                "secret": "must-not-leak",
            },
            "http:http_auth": "http-credential-alias",
            "empty": {"target": ""},
            "": {"target": "ignored"},
        }
    )

    assert mappings == {
        "llm:provider_credential_id:openai-main": {
            "ref": "llm:provider_credential_id:openai-main",
            "type": "model",
            "target": "model-openai-main",
            "label": "OpenAI main",
        },
        "http:http_auth": {
            "ref": "http:http_auth",
            "type": "credential_ref",
            "target": "http-credential-alias",
        },
    }


@pytest.mark.asyncio
async def test_import_workflow_reports_credential_mapping_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_mappings():
        return {
            "llm:provider_credential_id:openai-main": {
                "ref": "llm:provider_credential_id:openai-main",
                "type": "model",
                "target": "model-openai-main",
            }
        }

    monkeypatch.setattr(
        "src.plugins.workflow.service._resolve_credential_ref_mappings",
        fake_mappings,
    )
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    _definition, _version, report = await service.import_workflow(
        name="Mapped credentials",
        source_format="json",
        source_payload={
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {}},
                    {
                        "id": "llm",
                        "type": "llm",
                        "data": {
                            "model": {"provider": "openai"},
                            "provider_credential_id": "openai-main",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "llm"}],
            },
        },
        dry_run=True,
        user=_user(),
    )

    assert report["credential_refs_required"] == [
        "llm:llm_provider:openai",
        "llm:provider_credential_id:openai-main",
    ]
    assert report["credential_refs_resolved"] == [
        {
            "ref": "llm:provider_credential_id:openai-main",
            "type": "model",
            "target": "model-openai-main",
        }
    ]
    assert report["credential_refs_unresolved"] == ["llm:llm_provider:openai"]


@pytest.mark.asyncio
async def test_workflow_credential_vault_crud_exposes_masked_metadata() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    credential = await service.upsert_credential(
        user=_user(),
        ref="llm:provider_credential_id:openai-main",
        credential_type="model",
        label="OpenAI main",
        description="Imported Workflow provider credential",
        secret="sk-test",
        metadata={"provider": "openai"},
    )
    credentials = await service.list_credentials(user=_user())
    deleted = await service.delete_credential(user=_user(), credential_id=credential.credential_id)

    assert credential.ref == "llm:provider_credential_id:openai-main"
    assert credential.has_secret is True
    assert credential.metadata == {"provider": "openai"}
    assert credentials == [credential]
    assert deleted is True
    assert await service.list_credentials(user=_user()) == []


@pytest.mark.asyncio
async def test_import_workflow_resolves_credentials_from_vault() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    storage = _FakeStorage()
    storage.credentials_by_ref["llm:provider_credential_id:openai-main"] = WorkflowCredential(
        credential_id="wfc-openai",
        owner_user_id="user-1",
        ref="llm:provider_credential_id:openai-main",
        type="model",
        label="OpenAI main",
        description="Imported Workflow provider credential",
        has_secret=True,
        metadata={},
        created_at=now,
        updated_at=now,
    )
    service = WorkflowPluginService(storage=storage)

    _definition, _version, report = await service.import_workflow(
        name="Vault credentials",
        source_format="json",
        source_payload={
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {}},
                    {
                        "id": "llm",
                        "type": "llm",
                        "data": {
                            "model": {"provider": "openai"},
                            "provider_credential_id": "openai-main",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "llm"}],
            },
        },
        dry_run=True,
        user=_user(),
    )

    assert report["credential_refs_resolved"] == [
        {
            "ref": "llm:provider_credential_id:openai-main",
            "type": "model",
            "target": "credential:wfc-openai",
            "label": "OpenAI main",
            "description": "Imported Workflow provider credential",
        }
    ]
    assert report["credential_refs_unresolved"] == ["llm:llm_provider:openai"]


@pytest.mark.asyncio
async def test_import_workflow_accepts_yaml_source_content() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    source_content = """
version: 0.3.0
workflow:
  nodes:
    - id: start
      type: start
      data:
        title: Start
"""

    definition, version, report = await service.import_workflow(
        name="YAML",
        source_format="yaml",
        source_content=source_content,
        dry_run=False,
        user=_user(),
    )

    assert definition.workflow_id == "wf-created"
    assert version.version_id == "wfv-created"
    assert report["source_version"] == "0.3.0"
    created = storage.created[0]
    assert created["source_format"] == "yaml"
    assert created["source_payload"]["workflow"]["nodes"][0]["id"] == "start"


@pytest.mark.asyncio
async def test_run_workflow_executes_minimal_graph_and_records_events() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]
    assert events[0].payload == {"status": "running", "mode": "sync", "input_keys": ["name"]}
    assert "LambChat" not in repr(events[0].payload)
    assert events[-1].payload == {"status": "succeeded", "output_keys": ["answer"]}
    assert "Hi LambChat" not in repr(events[-1].payload)
    assert storage.finished[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_run_workflow_rejects_explicit_version_from_another_workflow_before_creating_run() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(LookupError, match="workflow_version_not_found"):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id="wfv-child",
            workflow_input={"name": "LambChat"},
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_run_workflow_rejects_missing_required_entry_fields_before_creating_run() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_input_required_missing:explicit_message"):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id="wfv-explicit",
            workflow_input={},
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_run_workflow_accepts_missing_required_entry_field_when_schema_has_default() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    run, _events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={},
        mode="sync",
        user=_user(),
    )

    assert run.status == "succeeded"
    assert storage.created_runs[0]["workflow_input"] == {}


@pytest.mark.asyncio
async def test_run_workflow_rejects_entry_type_mismatch_before_creating_run() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_input_type_mismatch:count:integer"):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id=None,
            workflow_input={"name": "Ada", "count": "two"},
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_run_workflow_rejects_entry_enum_mismatch_before_creating_run() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_input_enum_mismatch:tone"):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id=None,
            workflow_input={"name": "Ada", "tone": "cold"},
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow_input", "expected_error"),
        [
            (
            {"profile": {"nickname": "Ada"}, "items": [{"score": 1}], "tone": "warm"},
            r"workflow_input_required_missing:profile\.name",
        ),
        (
            {"profile": {"name": "Ada"}, "items": [{"score": "high"}], "tone": "warm"},
            r"workflow_input_type_mismatch:items\[0\]\.score:integer",
        ),
        (
            {"profile": {"name": "Ada"}, "items": [{"score": 1}], "tone": "cold"},
            "workflow_input_enum_mismatch:tone",
        ),
    ],
)
async def test_run_workflow_rejects_nested_entry_contract_violations_before_creating_run(
    workflow_input: dict[str, Any],
    expected_error: str,
) -> None:
    storage = _FakeStorage()
    storage.latest_internal_model = {
        "graph": {
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "supported": True,
                    "data": {
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "profile": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                    "required": ["name"],
                                },
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"score": {"type": "integer"}},
                                        "required": ["score"],
                                    },
                                },
                                "tone": {"type": "string", "enum": ["warm", "formal"]},
                            },
                            "required": ["profile", "items", "tone"],
                        }
                    },
                },
                {
                    "id": "answer",
                    "type": "answer",
                    "supported": True,
                    "data": {"answer": "ok"},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
        }
    }
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match=expected_error):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id=None,
            workflow_input=workflow_input,
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow_input", "expected_error"),
    [
        ({"name": "A"}, "workflow_input_constraint_violation:name:minLength"),
        ({"name": "Ada", "count": 6}, "workflow_input_constraint_violation:count:maximum"),
        ({"name": "Ada", "links": []}, "workflow_input_constraint_violation:links:minItems"),
        (
            {"name": "Ada", "contact": "not-an-email"},
            "workflow_input_constraint_violation:contact:format",
        ),
    ],
)
async def test_run_workflow_rejects_entry_constraint_violations_before_creating_run(
    workflow_input: dict[str, Any],
    expected_error: str,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match=expected_error):
        await service.run_workflow(
            workflow_id="wf-created",
            version_id=None,
            workflow_input=workflow_input,
            mode="sync",
            user=_user(),
        )

    assert storage.created_runs == []
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_run_workflow_async_returns_running_run_and_finishes_in_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    created_tasks: list[asyncio.Task] = []
    original_create_task = asyncio.create_task

    def capture_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.plugins.workflow.service.asyncio.create_task", capture_task)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="async",
        user=_user(),
    )

    assert run.status == "running"
    assert run.mode == "async"
    assert [event.event_type for event in events] == ["run_queued"]
    assert created_tasks

    await created_tasks[0]

    assert storage.finished[0]["status"] == "succeeded"
    assert storage.finished[0]["output"] == {"answer": "Hi LambChat"}


@pytest.mark.asyncio
async def test_run_workflow_async_dispatches_persisted_run_without_local_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    dispatches: list[tuple[str, str, list[str]]] = []

    async def dispatch(run_id: str, owner_user_id: str, user_roles: list[str]) -> None:
        dispatches.append((run_id, owner_user_id, user_roles))

    def fail_create_task(coro):
        raise AssertionError("dispatched async workflow runs should not create local tasks")

    service = WorkflowPluginService(storage=storage, async_run_dispatcher=dispatch)
    monkeypatch.setattr("src.plugins.workflow.service.asyncio.create_task", fail_create_task)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="async",
        user=_user(),
    )

    assert run.status == "running"
    assert [event.event_type for event in events] == ["run_queued"]
    assert dispatches == [("wfr-created", "user-1", ["user"])]
    assert storage.finished == []


@pytest.mark.asyncio
async def test_run_workflow_async_dispatch_failure_marks_run_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()

    async def dispatch(run_id: str, owner_user_id: str, user_roles: list[str]) -> None:
        del run_id, owner_user_id, user_roles
        raise RuntimeError("redis unavailable")

    def fail_create_task(coro):
        raise AssertionError("failed dispatch should not fall back to local tasks")

    service = WorkflowPluginService(storage=storage, async_run_dispatcher=dispatch)
    monkeypatch.setattr("src.plugins.workflow.service.asyncio.create_task", fail_create_task)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="async",
        user=_user(),
    )

    assert run.status == "failed"
    assert run.error == "workflow_run_dispatch_failed:redis unavailable"
    assert [event.event_type for event in events] == ["run_queued", "run_failed"]
    assert storage.run_events == [
        {"event_type": "run_queued", "payload": {"mode": "async"}},
        {
            "event_type": "run_failed",
            "payload": {"error": "workflow_run_dispatch_failed:redis unavailable"},
        },
    ]
    assert storage.finished == [
        {
            "run_id": "wfr-created",
            "owner_user_id": "user-1",
            "status": "failed",
            "error": "workflow_run_dispatch_failed:redis unavailable",
        }
    ]


@pytest.mark.asyncio
async def test_run_workflow_stream_returns_running_run_and_dispatches_persisted_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    dispatches: list[tuple[str, str, list[str]]] = []

    async def dispatch(run_id: str, owner_user_id: str, user_roles: list[str]) -> None:
        dispatches.append((run_id, owner_user_id, user_roles))

    def fail_create_task(coro):
        raise AssertionError("stream workflow runs should use durable dispatch")

    service = WorkflowPluginService(storage=storage, async_run_dispatcher=dispatch)
    monkeypatch.setattr("src.plugins.workflow.service.asyncio.create_task", fail_create_task)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="stream",
        user=_user(),
    )

    assert run.status == "running"
    assert run.mode == "stream"
    assert [event.event_type for event in events] == ["run_queued"]
    assert events[0].payload["mode"] == "stream"
    assert dispatches == [("wfr-created", "user-1", ["user"])]
    assert storage.finished == []


@pytest.mark.asyncio
async def test_execute_existing_run_reloads_run_version_and_input() -> None:
    class _RunningStorage(_FakeStorage):
        async def get_run(self, run_id: str, **kwargs):
            run = await super().get_run(run_id, **kwargs)
            if run is None:
                return None
            return run.model_copy(update={"status": "running", "mode": "async", "finished_at": None})

    storage = _RunningStorage()
    service = WorkflowPluginService(storage=storage)

    run, events = await service.execute_existing_run(
        run_id="wfr-created",
        owner_user_id="user-1",
        user_roles=["user"],
    )

    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]
    assert storage.finished[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_execute_existing_run_executes_persisted_queued_run() -> None:
    class _QueuedStorage(_FakeStorage):
        async def get_run(self, run_id: str, **kwargs):
            run = await super().get_run(run_id, **kwargs)
            if run is None:
                return None
            if self.current_run_status == "running":
                return run.model_copy(update={"status": "queued", "mode": "async", "finished_at": None})
            return run

    storage = _QueuedStorage()
    service = WorkflowPluginService(storage=storage)

    run, events = await service.execute_existing_run(
        run_id="wfr-created",
        owner_user_id="user-1",
        user_roles=["user"],
    )

    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]
    assert events[0].payload == {"status": "running", "mode": "async", "input_keys": ["name"]}
    assert storage.finished[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_dispatch_workflow_run_to_arq_enqueues_worker_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakePool:
        def __init__(self) -> None:
            self.enqueued: list[tuple[str, tuple, dict]] = []
            self.closed = False
            self.waited = False

        async def enqueue_job(self, function: str, *args, **kwargs) -> None:
            self.enqueued.append((function, args, kwargs))

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            self.waited = True

    fake_pool = _FakePool()
    create_pool_calls: list[dict] = []

    async def fake_create_pool(redis_settings, **kwargs):
        create_pool_calls.append({"redis_settings": redis_settings, **kwargs})
        return fake_pool

    monkeypatch.setattr("src.plugins.workflow.service.create_pool", fake_create_pool)
    monkeypatch.setattr(
        "src.plugins.workflow.service.build_arq_redis_settings",
        lambda settings: "redis-settings",
    )

    await dispatch_workflow_run_to_arq(
        run_id="wfr-1",
        owner_user_id="user-1",
        user_roles=["user"],
    )

    assert create_pool_calls == [
        {"redis_settings": "redis-settings", "default_queue_name": "lambchat:arq"}
    ]
    assert fake_pool.enqueued == [
        (
            "run_workflow_task",
            ("wfr-1", "user-1", ["user"]),
            {"_job_id": "wfr-1"},
        )
    ]
    assert fake_pool.closed is True
    assert fake_pool.waited is True


@pytest.mark.asyncio
async def test_cancel_run_marks_owned_running_run_cancelled() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    run, events = await service.cancel_run(
        workflow_id="wf-created",
        run_id="wfr-created",
        user=_user(),
    )

    assert run.status == "cancelled"
    assert run.error == "workflow_run_cancelled_by_user"
    assert events[0].event_type == "run_cancelled"
    assert events[0].payload["cancelled_by"] == "user-1"
    assert storage.finished[0] == {
        "run_id": "wfr-created",
        "owner_user_id": "user-1",
        "status": "cancelled",
    }


@pytest.mark.asyncio
async def test_execute_run_to_completion_does_not_overwrite_cancelled_run() -> None:
    class _CancelledStorage(_FakeStorage):
        def __init__(self) -> None:
            super().__init__()
            self.current_run_status = "cancelled"
            self.current_run_error = "workflow_run_cancelled_by_user"

        async def get_run(self, run_id: str, **kwargs):
            run = await super().get_run(run_id, **kwargs)
            if run is None:
                return None
            return run

    storage = _CancelledStorage()
    service = WorkflowPluginService(storage=storage)
    run = WorkflowRun(
        run_id="wfr-created",
        workflow_id="wf-created",
        version_id="wfv-created",
        owner_user_id="user-1",
        status="running",
        mode="async",
        input={"name": "LambChat"},
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    finished_run, events = await service._execute_run_to_completion(
        run=run,
        internal_model=storage._version().internal_model,
        workflow_input={"name": "LambChat"},
        user=_user(),
    )

    assert finished_run.status == "cancelled"
    assert finished_run.error == "workflow_run_cancelled_by_user"
    assert events[0].event_type == "node_started"
    assert [event["event_type"] for event in storage.run_events] == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_execute_run_to_completion_does_not_append_success_after_terminal_run() -> None:
    storage = _FakeStorage()
    storage.current_run_status = "failed"
    storage.current_run_error = "workflow_run_interrupted_by_server_restart"
    service = WorkflowPluginService(storage=storage)
    run = WorkflowRun(
        run_id="wfr-created",
        workflow_id="wf-created",
        version_id="wfv-created",
        owner_user_id="user-1",
        status="running",
        mode="async",
        input={"name": "LambChat"},
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    finished_run, events = await service._execute_run_to_completion(
        run=run,
        internal_model=storage._version().internal_model,
        workflow_input={"name": "LambChat"},
        user=_user(),
    )

    assert finished_run.status == "failed"
    assert finished_run.error == "workflow_run_interrupted_by_server_restart"
    assert [event.event_type for event in events] == ["node_started"]
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_pause_run_does_not_append_pause_after_terminal_run() -> None:
    class _PausingExecutor:
        async def execute_async(self, internal_model, **kwargs):
            del internal_model, kwargs
            from src.plugins.workflow.executor import WorkflowExecutionPaused

            raise WorkflowExecutionPaused(
                "workflow_human_approval_paused:approval",
                node_id="approval",
                pending_approval={"node_id": "approval"},
                pause_state={"kind": "human_approval", "node_id": "approval"},
                output={"name": "LambChat"},
                events=[{"event_type": "node_started", "node_id": "approval", "node_type": "human_approval"}],
            )

    storage = _FakeStorage()
    storage.current_run_status = "cancelled"
    storage.current_run_error = "workflow_run_cancelled_by_user"
    service = WorkflowPluginService(storage=storage, executor=_PausingExecutor())  # type: ignore[arg-type]
    run = WorkflowRun(
        run_id="wfr-created",
        workflow_id="wf-created",
        version_id="wfv-created",
        owner_user_id="user-1",
        status="running",
        mode="async",
        input={"name": "LambChat"},
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    finished_run, events = await service._execute_run_to_completion(
        run=run,
        internal_model=storage._version().internal_model,
        workflow_input={"name": "LambChat"},
        user=_user(),
    )

    assert finished_run.status == "cancelled"
    assert finished_run.error == "workflow_run_cancelled_by_user"
    assert [event.event_type for event in events] == ["node_started"]
    assert storage.run_events == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_execute_run_to_completion_passes_persistent_cancel_checker() -> None:
    class _CancelAwareStorage(_FakeStorage):
        def __init__(self) -> None:
            super().__init__()
            self.current_run_status = "cancelled"
            self.current_run_error = "workflow_run_cancelled_by_user"

        async def get_run(self, run_id: str, **kwargs):
            run = await super().get_run(run_id, **kwargs)
            if run is None:
                return None
            return run

    class _CancelCheckingExecutor:
        def __init__(self) -> None:
            self.cancelled = False

        async def execute_async(self, internal_model, **kwargs):
            self.cancelled = await kwargs["cancel_checker"]()
            return type("Execution", (), {"output": {"answer": "late"}, "events": []})()

    storage = _CancelAwareStorage()
    executor = _CancelCheckingExecutor()
    service = WorkflowPluginService(storage=storage, executor=executor)  # type: ignore[arg-type]
    run = WorkflowRun(
        run_id="wfr-created",
        workflow_id="wf-created",
        version_id="wfv-created",
        owner_user_id="user-1",
        status="running",
        mode="async",
        input={"name": "LambChat"},
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    finished_run, events = await service._execute_run_to_completion(
        run=run,
        internal_model=storage._version().internal_model,
        workflow_input={"name": "LambChat"},
        user=_user(),
    )

    assert executor.cancelled is True
    assert finished_run.status == "cancelled"
    assert finished_run.error == "workflow_run_cancelled_by_user"
    assert events[0].event_type == "node_started"
    assert [event["event_type"] for event in storage.run_events] == []
    assert storage.finished == []


@pytest.mark.asyncio
async def test_create_workflow_version_parses_and_persists_next_snapshot() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    source_payload = {
        "version": "0.3.0",
        "workflow": {"nodes": [{"id": "start", "type": "start"}]},
    }

    definition, version, report = await service.create_workflow_version(
        workflow_id="wf-created",
        name="Updated",
        source_format="json",
        source_payload=source_payload,
        user=_user(),
    )

    assert definition.latest_version_id == "wfv-2"
    assert version.version_number == 2
    assert report["workflow_id"] == "wf-created"
    created = storage.created_versions[0]
    assert created["owner_user_id"] == "user-1"
    assert created["name"] == "Updated"
    assert created["internal_model"]["format"] == "lambchat.workflow.v1"


@pytest.mark.asyncio
async def test_create_workflow_version_accepts_editor_workflow_dsl_payload() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)
    source_payload = {
        "version": "0.3.0",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {"id": "answer", "type": "answer", "data": {"title": "Answer", "answer": "{{message}}"}},
                {
                    "id": "node_3",
                    "type": "llm",
                    "data": {
                        "title": "Node 3",
                        "prompt_template": "Answer {{message}}",
                        "model": {"provider": "openai", "name": "gpt-4o-mini"},
                    },
                    "position": {"x": 320, "y": 120},
                },
            ],
            "edges": [{"id": "start-answer", "source": "start", "target": "answer"}],
        },
    }

    _definition, version, report = await service.create_workflow_version(
        workflow_id="wf-created",
        name="Imported Workflow",
        source_format="json",
        source_payload=source_payload,
        user=_user(),
    )

    created = storage.created_versions[0]
    graph = created["internal_model"]["graph"]
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert version.version_id == "wfv-2"
    assert created["source_payload"]["workflow"]["nodes"][2]["id"] == "node_3"
    assert nodes_by_id["node_3"]["type"] == "llm"
    assert nodes_by_id["node_3"]["data"]["prompt_template"] == "Answer {{message}}"
    assert nodes_by_id["node_3"]["position"] == {"x": 320, "y": 120}
    assert graph["edges"] == [
        {
            "id": "start-answer",
            "source": "start",
            "target": "answer",
            "source_handle": None,
            "target_handle": None,
            "data": {},
            "valid": True,
        }
    ]
    assert report["supported_nodes"] == ["answer", "llm", "start"]
    assert report["metadata"]["detected_node_count"] == 3
    assert report["lossless"] is True


@pytest.mark.asyncio
async def test_create_workflow_version_accepts_yaml_source_content() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    definition, version, report = await service.create_workflow_version(
        workflow_id="wf-created",
        name="YAML Update",
        source_format="yaml",
        source_content="version: 0.3.0\nworkflow:\n  nodes:\n    - id: start\n      type: start\n",
        user=_user(),
    )

    assert definition.latest_version_id == "wfv-2"
    assert version.version_number == 2
    assert report["metadata"]["detected_node_count"] == 1
    assert storage.created_versions[0]["source_format"] == "yaml"


@pytest.mark.asyncio
async def test_get_workflow_input_schema_uses_published_or_latest_version() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    draft_payload = await service.get_workflow_input_schema(
        "wf-created",
        owner_user_id="user-1",
    )
    await service.publish_workflow(workflow_id="wf-created", version_id="wfv-created", user=_user())
    published_payload = await service.get_workflow_input_schema(
        "wf-created",
        owner_user_id="user-1",
    )

    assert draft_payload["version_id"] == "wfv-created"
    assert published_payload["status"] == "published"
    assert published_payload["input_schema"]["required"] == ["name"]
    assert published_payload["input_schema"]["properties"]["name"]["default"] == "Visitor"
    assert published_payload["input_schema"]["properties"]["name"]["minLength"] == 2
    assert published_payload["input_schema"]["properties"]["name"]["maxLength"] == 40
    assert published_payload["input_schema"]["properties"]["tone"]["type"] == "string"
    assert published_payload["input_schema"]["properties"]["tone"]["default"] == "warm"
    assert published_payload["input_schema"]["properties"]["tone"]["enum"] == ["warm", "formal"]
    assert published_payload["input_schema"]["properties"]["count"]["type"] == "integer"
    assert published_payload["input_schema"]["properties"]["count"]["default"] == 2
    assert published_payload["input_schema"]["properties"]["count"]["minimum"] == 1
    assert published_payload["input_schema"]["properties"]["count"]["maximum"] == 5
    assert published_payload["input_schema"]["properties"]["contact"]["format"] == "email"
    assert published_payload["input_schema"]["properties"]["links"]["type"] == "array"
    assert published_payload["input_schema"]["properties"]["links"]["minItems"] == 1
    assert published_payload["input_schema"]["properties"]["links"]["maxItems"] == 3
    assert published_payload["input_schema"]["properties"]["attachment"]["type"] == "object"
    assert published_payload["input_schema"]["properties"]["attachment"]["x-lambchat-input-kind"] == "file"
    assert published_payload["input_schema"]["properties"]["attachment"]["description"] == "Uploaded file metadata"
    assert published_payload["input_schema"]["properties"]["query"]["x-lambchat-source"] == "inferred"
    assert "rendered" not in published_payload["input_schema"]["properties"]
    assert published_payload["schema_source"] == "declared_and_inferred"


@pytest.mark.asyncio
async def test_get_workflow_input_schema_accepts_explicit_version_id() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_inputs"
    service = WorkflowPluginService(storage=storage)

    payload = await service.get_workflow_input_schema(
        "wf-created",
        owner_user_id="user-1",
        version_id="wfv-explicit",
    )

    assert payload["version_id"] == "wfv-explicit"
    assert payload["version_number"] == 7
    assert payload["input_schema"]["required"] == ["explicit_message"]
    assert set(payload["input_schema"]["properties"]) == {"explicit_message"}


@pytest.mark.asyncio
async def test_get_workflow_io_contract_returns_input_and_output_schema() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "schema_outputs"
    service = WorkflowPluginService(storage=storage)

    payload = await service.get_workflow_io_contract(
        "wf-created",
        owner_user_id="user-1",
    )

    assert payload["workflow_id"] == "wf-created"
    assert payload["version_id"] == "wfv-created"
    assert payload["input_schema"]["type"] == "object"
    assert payload["output_schema"]["properties"]["summary"]["type"] == "string"
    assert payload["output_schema"]["properties"]["summary"]["description"] == "Rendered summary"
    assert payload["output_schema"]["properties"]["count"]["type"] == "integer"
    assert payload["output_schema_source"] == "inferred"
    assert payload["inferred_output_fields"] == ["count", "summary"]


def test_infer_workflow_input_schema_normalizes_bracket_index_paths() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-indexed",
        status="draft",
        version_id="wfv-indexed",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {
                            "answer": "First {{items[0].name}} and nested {{matrix[0][1]}}",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
            }
        },
    )

    assert sorted(payload["input_schema"]["properties"]) == ["items", "matrix"]
    assert payload["inferred_fields"] == ["items", "matrix"]
    assert "items[0]" not in payload["input_schema"]["properties"]


def test_infer_workflow_output_schema_prefers_declared_end_schema() -> None:
    payload = infer_workflow_output_schema_payload(
        workflow_id="wf-output",
        status="draft",
        version_id="wfv-output",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "end",
                        "type": "end",
                        "supported": True,
                        "data": {
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "result": {"type": "object", "additionalProperties": True},
                                },
                                "required": ["result"],
                            },
                            "outputs": [{"name": "fallback", "type": "string"}],
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "end", "valid": True}],
            }
        },
    )

    assert payload["output_schema"]["required"] == ["result"]
    assert set(payload["output_schema"]["properties"]) == {"result"}
    assert payload["schema_source"] == "declared"
    assert payload["inferred_fields"] == []


def test_infer_workflow_output_schema_accepts_declared_answer_exit_schema() -> None:
    payload = infer_workflow_output_schema_payload(
        workflow_id="wf-answer-contract",
        status="draft",
        version_id="wfv-answer-contract",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {
                            "answer": "{{message}}",
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "answer": {"type": "string", "description": "Workflow answer text"},
                                },
                                "required": ["answer"],
                            },
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
            }
        },
    )

    assert payload["output_schema"]["required"] == ["answer"]
    assert payload["output_schema"]["properties"]["answer"]["description"] == "Workflow answer text"
    assert payload["schema_source"] == "declared"
    assert payload["inferred_fields"] == []


def test_infer_workflow_output_schema_falls_back_to_answer_output() -> None:
    payload = infer_workflow_output_schema_payload(
        workflow_id="wf-answer",
        status="published",
        version_id="wfv-answer",
        version_number=2,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {"id": "answer", "type": "answer", "supported": True, "data": {"answer": "Hi"}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
            }
        },
    )

    assert payload["output_schema"]["properties"]["answer"]["type"] == "string"
    assert payload["output_schema"]["properties"]["answer"]["x-lambchat-source"] == "inferred"
    assert payload["inferred_fields"] == ["answer"]


def test_infer_workflow_input_schema_excludes_variable_assign_target_aliases() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-assign",
        status="draft",
        version_id="wfv-assign",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "assign",
                        "type": "variable_assign",
                        "supported": True,
                        "data": {
                            "variables": [
                                {
                                    "target_variable": "copied",
                                    "value_selector": ["source"],
                                }
                            ]
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {"answer": "{{copied}} from {{source}}"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "assign", "valid": True},
                    {"id": "e2", "source": "assign", "target": "answer", "valid": True},
                ],
            }
        },
    )

    assert sorted(payload["input_schema"]["properties"]) == ["source"]
    assert payload["inferred_fields"] == ["source"]


def test_infer_workflow_input_schema_excludes_variable_assign_mapping_outputs() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-assign-mapping",
        status="draft",
        version_id="wfv-assign-mapping",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "assign",
                        "type": "variable_assign",
                        "supported": True,
                        "data": {
                            "variables": {
                                "copied": {"value_selector": ["source"]},
                                "summary": "{{source}}",
                            }
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {"answer": "{{copied}} {{summary}} {{source}}"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "assign", "valid": True},
                    {"id": "e2", "source": "assign", "target": "answer", "valid": True},
                ],
            }
        },
    )

    assert sorted(payload["input_schema"]["properties"]) == ["source"]
    assert payload["inferred_fields"] == ["source"]


def test_infer_workflow_input_schema_excludes_variable_assign_list_alias_outputs() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-assign-list-aliases",
        status="draft",
        version_id="wfv-assign-list-aliases",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "supported": True, "data": {}},
                    {
                        "id": "assign",
                        "type": "variable_assign",
                        "supported": True,
                        "data": {
                            "variable_assignments": [
                                {
                                    "assigned_variable_selector": ["copied"],
                                    "value_selector": ["source"],
                                },
                                {
                                    "assignedVariable": "summary",
                                    "value": "{{source}}",
                                },
                            ],
                            "assignments": [
                                {
                                    "variableSelector": ["title"],
                                    "sourceSelector": ["source_title"],
                                }
                            ],
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {"answer": "{{copied}} {{summary}} {{title}} {{source}} {{source_title}}"},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "assign", "valid": True},
                    {"id": "e2", "source": "assign", "target": "answer", "valid": True},
                ],
            }
        },
    )

    assert sorted(payload["input_schema"]["properties"]) == ["source", "source_title"]
    assert payload["inferred_fields"] == ["source", "source_title"]


def test_infer_workflow_input_schema_accepts_start_variable_name_aliases() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-start-aliases",
        status="draft",
        version_id="wfv-start-aliases",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {
                        "id": "start",
                        "type": "start",
                        "supported": True,
                        "data": {
                            "variables": [
                                {
                                    "field_name": "topic",
                                    "type": "string",
                                    "required": True,
                                    "default": "workflow",
                                },
                                {
                                    "parameterName": "count",
                                    "type": "integer",
                                    "required": True,
                                    "default": 2,
                                    "minimum": 1,
                                },
                            ]
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {"answer": "{{topic}} x {{count}}"},
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
            }
        },
    )

    schema = payload["input_schema"]

    assert schema["required"] == ["count", "topic"]
    assert schema["properties"]["topic"]["default"] == "workflow"
    assert schema["properties"]["count"]["type"] == "integer"
    assert schema["properties"]["count"]["minimum"] == 1
    assert payload["schema_source"] == "declared"
    assert payload["inferred_fields"] == []


def test_infer_workflow_input_schema_accepts_start_variable_mapping() -> None:
    payload = infer_workflow_input_schema_payload(
        workflow_id="wf-start-mapping",
        status="draft",
        version_id="wfv-start-mapping",
        version_number=1,
        internal_model={
            "graph": {
                "nodes": [
                    {
                        "id": "start",
                        "type": "start",
                        "supported": True,
                        "data": {
                            "variables": {
                                "topic": {
                                    "type": "string",
                                    "required": True,
                                    "default": "workflow",
                                    "minLength": 3,
                                },
                                "count": {
                                    "type": "integer",
                                    "required": True,
                                    "default": 2,
                                    "minimum": 1,
                                },
                                "tone": "string",
                            }
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "supported": True,
                        "data": {"answer": "{{topic}} x {{count}} / {{tone}}"},
                    },
                ],
                "edges": [{"id": "e1", "source": "start", "target": "answer", "valid": True}],
            }
        },
    )

    schema = payload["input_schema"]

    assert schema["required"] == ["count", "topic"]
    assert schema["properties"]["topic"]["default"] == "workflow"
    assert schema["properties"]["topic"]["minLength"] == 3
    assert schema["properties"]["count"]["type"] == "integer"
    assert schema["properties"]["count"]["minimum"] == 1
    assert schema["properties"]["tone"]["type"] == "string"
    assert payload["schema_source"] == "declared"
    assert payload["inferred_fields"] == []


def test_resolve_workflow_source_payload_rejects_non_mapping_text() -> None:
    with pytest.raises(ValueError, match="workflow_source_must_be_mapping"):
        resolve_workflow_source_payload(source_format="yaml", source_content="- just\n- a\n- list")


@pytest.mark.asyncio
async def test_publish_workflow_requires_runtime_executable_version() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert published.status == "published"
    assert storage.published == [
        {"workflow_id": "wf-created", "owner_user_id": "user-1", "version_id": "wfv-created"}
    ]

    storage.version_node_type = "llm"
    with pytest.raises(ValueError, match="workflow_llm_prompt_missing"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_validate_workflow_version_returns_publish_time_static_result() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    payload = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert payload["workflow_id"] == "wf-created"
    assert payload["version_id"] == "wfv-created"
    assert payload["version_number"] == 1
    assert payload["runnable"] is True
    assert payload["errors"] == []
    assert payload["reachable_node_ids"] == ["answer", "start"]
    assert payload["credential_refs_required"] == []
    assert payload["credential_refs_resolved"] == []
    assert payload["credential_refs_unresolved"] == []
    assert storage.published == []

    storage.version_node_type = "llm"
    failed = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert failed["runnable"] is False
    assert any("workflow_llm_prompt_missing" in error for error in failed["errors"])
    assert storage.published == []

    storage.version_node_type = "boundary_edges"
    boundary_failed = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert boundary_failed["runnable"] is False
    assert "workflow_boundary_edge_targets_entry:to-start:answer->start" in boundary_failed["errors"]
    assert "workflow_boundary_edge_starts_from_exit:from-exit:end->answer" in boundary_failed["errors"]
    assert storage.published == []


@pytest.mark.asyncio
async def test_validate_workflow_version_reports_credential_mapping_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_mappings():
        return {
            "http:http_auth": {
                "ref": "http:http_auth",
                "type": "http_auth",
                "target": "workflow-http-auth",
            }
        }

    monkeypatch.setattr(
        "src.plugins.workflow.service._resolve_credential_ref_mappings",
        fake_mappings,
    )
    storage = _FakeStorage()
    storage.credential_refs_required = ["http:http_auth", "llm:llm_provider:openai"]
    service = WorkflowPluginService(storage=storage)

    payload = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert payload["runnable"] is True
    assert payload["credential_refs_required"] == ["http:http_auth", "llm:llm_provider:openai"]
    assert payload["credential_refs_resolved"] == [
        {
            "ref": "http:http_auth",
            "type": "http_auth",
            "target": "workflow-http-auth",
        }
    ]
    assert payload["credential_refs_unresolved"] == ["llm:llm_provider:openai"]


@pytest.mark.asyncio
async def test_publish_workflow_accepts_condition_versions() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "condition"
    service = WorkflowPluginService(storage=storage)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert published.status == "published"
    assert storage.published[0]["version_id"] == "wfv-created"


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_sub_workflow_with_owned_child() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "sub_workflow"
    service = WorkflowPluginService(storage=storage)

    validation = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert validation["runnable"] is True
    assert validation["errors"] == []
    assert published.status == "published"
    assert run.status == "succeeded"
    assert run.output == {"answer": "Child LambChat"}
    assert any(event.node_type == "sub_workflow" for event in events)


@pytest.mark.asyncio
async def test_publish_workflow_rejects_unpublished_sub_workflow_child() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "sub_workflow"
    storage.child_published_version_id = None
    service = WorkflowPluginService(storage=storage)

    validation = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert validation["runnable"] is False
    assert any("workflow_sub_workflow_not_published:wf-child" in error for error in validation["errors"])
    with pytest.raises(ValueError, match="workflow_sub_workflow_not_published:wf-child"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_self_referencing_sub_workflow() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "self_sub_workflow"
    service = WorkflowPluginService(storage=storage)

    validation = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert validation["runnable"] is False
    assert any("workflow_sub_workflow_cycle_detected:wf-created" in error for error in validation["errors"])
    with pytest.raises(ValueError, match="workflow_sub_workflow_cycle_detected:wf-created"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_nested_sub_workflow_cycle() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "sub_workflow"
    storage.child_version_node_type = "child_calls_parent"
    service = WorkflowPluginService(storage=storage)

    validation = await service.validate_workflow_version(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert validation["runnable"] is False
    assert any("workflow_sub_workflow_cycle_detected:wf-created" in error for error in validation["errors"])
    with pytest.raises(ValueError, match="workflow_sub_workflow_cycle_detected:wf-created"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_run_workflow_executes_tool_call_through_internal_tool_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "tool_call"
    service = WorkflowPluginService(storage=storage)
    calls: list[dict[str, Any]] = []

    async def fake_tools_for_user(**kwargs):
        calls.append(kwargs)
        return [_EchoTool()]

    monkeypatch.setattr("src.infra.tool.internal_registry.get_internal_tools_for_user", fake_tools_for_user)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert calls == [{"user_id": "user-1", "user_roles": ["user"], "is_admin": False}]
    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_publish_workflow_validates_tool_call_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "tool_call"
    service = WorkflowPluginService(storage=storage)

    async def fake_tools_for_user(**kwargs):
        return [_EchoTool()]

    monkeypatch.setattr("src.infra.tool.internal_registry.get_internal_tools_for_user", fake_tools_for_user)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )

    assert published.status == "published"

    async def no_tools_for_user(**kwargs):
        return []

    monkeypatch.setattr("src.infra.tool.internal_registry.get_internal_tools_for_user", no_tools_for_user)
    with pytest.raises(ValueError, match="workflow_tool_not_available:echo_tool"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_http_request_when_policy_disabled() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "http_request"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_http_policy_disabled"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_http_request_with_policy() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_http(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "HTTP OK"}

    storage = _FakeStorage()
    storage.version_node_type = "http_request"
    service = WorkflowPluginService(
        storage=storage,
        http_policy=build_http_request_policy(
            policy="allowlist",
            allowlist=["api.example.com"],
        ),
        http_invoker=invoke_http,
    )

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert requests[0]["url"] == "https://api.example.com/status/LambChat"
    assert run.status == "succeeded"
    assert run.output == {"answer": "HTTP OK"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_run_workflow_resolves_http_credential_secret_from_vault() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_http(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"status_code": 200, "headers": {}, "body": "HTTP OK"}

    storage = _FakeStorage()
    storage.version_node_type = "http_request_auth"
    storage.credential_secrets_by_ref["http:http_auth"] = "vault-token"
    service = WorkflowPluginService(
        storage=storage,
        http_policy=build_http_request_policy(
            policy="allowlist",
            allowlist=["api.example.com"],
        ),
        http_invoker=invoke_http,
    )

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert requests[0]["headers"] == {"Authorization": "Bearer vault-token"}
    assert run.status == "succeeded"
    assert run.output == {"answer": "HTTP OK"}
    assert "vault-token" not in repr([event.payload for event in events])


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_knowledge_retrieval_with_retriever() -> None:
    requests: list[dict[str, Any]] = []

    async def retrieve(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"success": True, "memories": [{"memory_id": "m1", "content": "Knowledge OK"}]}

    storage = _FakeStorage()
    storage.version_node_type = "knowledge_retrieval"
    service = WorkflowPluginService(storage=storage, knowledge_retriever=retrieve)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert requests == [
        {
            "query": "LambChat",
            "dataset_ids": ["dataset-1"],
            "dataset_filters": {},
            "top_k": 5,
            "score_threshold": None,
        }
    ]
    assert run.status == "succeeded"
    assert run.output == {"answer": "Knowledge OK"}
    assert any(event.node_type == "knowledge_retrieval" for event in events)


def test_knowledge_dataset_mapping_normalization() -> None:
    mappings = _normalize_knowledge_dataset_mappings(
        {
            "dataset-project": {"memory_types": ["project", "reference", "project"]},
            "dataset-user": "user, feedback",
            "empty": [],
            "": ["project"],
        }
    )

    assert mappings == {
        "dataset-project": ["project", "reference"],
        "dataset-user": ["feedback", "user"],
        "empty": [],
    }
    assert _memory_types_for_dataset_ids(
        ["dataset-project", "missing", "dataset-user"],
        mappings,
    ) == {
        "resolved_dataset_ids": ["dataset-project", "dataset-user"],
        "unresolved_dataset_ids": ["missing"],
        "memory_types": ["feedback", "project", "reference", "user"],
    }


@pytest.mark.asyncio
async def test_memory_knowledge_retriever_maps_workflow_dataset_ids_to_memory_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class Backend:
        async def recall(self, user_id, query, max_results=5, memory_types=None):
            calls.append(
                {
                    "user_id": user_id,
                    "query": query,
                    "max_results": max_results,
                    "memory_types": memory_types,
                }
            )
            return {"success": True, "memories": [{"content": "Project memory"}]}

    async def get_backend():
        return Backend()

    monkeypatch.setattr("src.infra.memory.tools._get_backend", get_backend)

    async def dataset_mappings() -> dict[str, list[str]]:
        return {"dataset-project": ["project"], "dataset-reference": ["reference"]}

    monkeypatch.setattr(
        "src.plugins.workflow.service._resolve_knowledge_dataset_mappings",
        dataset_mappings,
    )

    retriever = WorkflowPluginService()._build_memory_knowledge_retriever(user=_user())
    result = await retriever(
        {
            "query": "LambChat",
            "dataset_ids": ["dataset-project", "missing"],
            "top_k": 3,
        }
    )

    assert calls == [
        {
            "user_id": "user-1",
            "query": "LambChat",
            "max_results": 3,
            "memory_types": ["project"],
        }
    ]
    assert result["resolved_dataset_ids"] == ["dataset-project"]
    assert result["unresolved_dataset_ids"] == ["missing"]
    assert result["memory_types"] == ["project"]


@pytest.mark.asyncio
async def test_publish_workflow_rejects_knowledge_retrieval_without_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "knowledge_retrieval"
    service = WorkflowPluginService(storage=storage)
    monkeypatch.setattr("src.plugins.workflow.service.settings.ENABLE_MEMORY", False, raising=False)

    with pytest.raises(ValueError, match="workflow_knowledge_retriever_unavailable"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_llm_node_with_invoker() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_llm(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"text": "Hi LambChat", "model": request.get("model"), "usage": {}}

    storage = _FakeStorage()
    storage.version_node_type = "llm_prompt"
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert requests == [
        {
            "prompt": "Say hi to LambChat",
            "messages": [],
            "model_id": None,
            "model": "openai/gpt-4o-mini",
        }
    ]
    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_default_llm_invoker_retries_without_streaming_after_empty_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    direct_calls: list[dict[str, Any]] = []

    class FakeModel:
        async def ainvoke(self, _messages):
            raise ValueError("No generations found in stream.")

    async def fake_get_model(**kwargs):
        calls.append(dict(kwargs))
        return FakeModel()

    async def fake_get_default_model() -> str:
        return "gpt-5.5"

    class FakeChatCompletions:
        async def create(self, **payload):
            direct_calls.append(dict(payload))
            return {
                "model": payload.get("model"),
                "choices": [{"message": {"content": "Hi from fallback"}}],
                "usage": {"total_tokens": 3},
            }

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = dict(kwargs)
            self.chat = SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model", fake_get_default_model)
    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)

    service = WorkflowPluginService()
    invoker = service._build_llm_invoker()
    result = await invoker(
        {
            "prompt": "Say hi",
            "messages": [],
            "model": None,
            "model_id": None,
            "max_tokens": 64,
        }
    )

    assert result["text"] == "Hi from fallback"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 64
    assert calls[0]["streaming"] is False
    assert direct_calls == [
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Say hi"}],
            "temperature": 0.7,
            "stream": False,
            "max_tokens": 64,
        }
    ]
    assert result["usage"] == {"total_tokens": 3}


@pytest.mark.asyncio
async def test_default_llm_invoker_retries_without_streaming_after_model_dump_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_calls: list[dict[str, Any]] = []

    class FakeModel:
        async def ainvoke(self, _messages):
            raise AttributeError("'str' object has no attribute 'model_dump'")

    async def fake_get_model(**_kwargs):
        return FakeModel()

    async def fake_get_default_model() -> str:
        return "openai/gpt-5.5"

    class FakeChatCompletions:
        async def create(self, **payload):
            direct_calls.append(dict(payload))
            return "fallback text"

    class FakeAsyncOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model", fake_get_default_model)
    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)

    service = WorkflowPluginService()
    result = await service._build_llm_invoker()({"prompt": "Say hi", "messages": []})

    assert result["text"] == "fallback text"
    assert direct_calls[0]["model"] == "gpt-5.5"
    assert direct_calls[0]["stream"] is False


@pytest.mark.asyncio
async def test_default_llm_invoker_direct_fallback_uses_model_storage_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_kwargs: list[dict[str, Any]] = []
    direct_calls: list[dict[str, Any]] = []

    class FakeModel:
        async def ainvoke(self, _messages):
            raise ValueError("No generations found in stream.")

    async def fake_get_model(**_kwargs):
        return FakeModel()

    stored_model = ModelConfig(
        id="model-1",
        value="openai/gpt-5.5",
        provider="openai",
        label="GPT 5.5",
        api_key="stored-key",
        api_base="https://llm.example/v1",
        temperature=0.2,
        max_tokens=32,
    )

    class FakeModelStorage:
        async def get(self, model_id: str) -> ModelConfig | None:
            assert model_id == "model-1"
            return stored_model

    async def fake_get_default_model_id() -> str:
        return "model-1"

    class FakeChatCompletions:
        async def create(self, **payload):
            direct_calls.append(dict(payload))
            return {
                "model": payload.get("model"),
                "choices": [{"message": {"content": "configured fallback"}}],
            }

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            client_kwargs.append(dict(kwargs))
            self.chat = SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setattr("src.infra.llm.client.LLMClient.get_model", fake_get_model)
    monkeypatch.setattr("src.infra.agent.model_storage.get_model_storage", lambda: FakeModelStorage())
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model_id", fake_get_default_model_id)
    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)

    service = WorkflowPluginService()
    result = await service._build_llm_invoker()(
        {
            "prompt": "Say hi",
            "messages": [],
            "model": None,
            "model_id": None,
            "max_tokens": None,
        }
    )

    assert result["text"] == "configured fallback"
    assert client_kwargs == [{"api_key": "stored-key", "base_url": "https://llm.example/v1"}]
    assert direct_calls == [
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Say hi"}],
            "temperature": 0.2,
            "stream": False,
            "max_tokens": 32,
        }
    ]


@pytest.mark.asyncio
async def test_run_workflow_resolves_llm_credential_secret_from_vault() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_llm(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"text": "Hi LambChat", "model": request.get("model"), "usage": {}}

    storage = _FakeStorage()
    storage.version_node_type = "llm_prompt"
    storage.credential_secrets_by_ref["llm:llm_provider:openai"] = "llm-secret"
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert requests[0]["api_key"] == "llm-secret"
    assert run.status == "succeeded"
    assert run.output == {"answer": "Hi LambChat"}
    assert "llm-secret" not in repr([event.payload for event in events])


@pytest.mark.asyncio
async def test_run_workflow_resolves_llm_json_credential_payload_from_vault() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_llm(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"text": "Hi LambChat", "model": request.get("model"), "usage": {}}

    storage = _FakeStorage()
    storage.version_node_type = "llm_prompt"
    storage.credential_secrets_by_ref["llm:llm_provider:openai"] = (
        '{"api_key":"json-key","api_base":"https://llm.example/v1"}'
    )
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)

    run, _events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert requests[0]["api_key"] == "json-key"
    assert requests[0]["api_base"] == "https://llm.example/v1"
    assert run.status == "succeeded"


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_parameter_extractor_node_with_invoker() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_llm(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"text": '{"topic":"workflow help"}', "model": request.get("model"), "usage": {}}

    storage = _FakeStorage()
    storage.version_node_type = "parameter_extractor"
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert "LambChat wants workflow help" in requests[0]["prompt"]
    assert run.status == "succeeded"
    assert run.output == {"answer": "workflow help"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_question_classifier_node_with_invoker() -> None:
    requests: list[dict[str, Any]] = []

    async def invoke_llm(request: dict[str, Any]) -> dict[str, Any]:
        requests.append(request)
        return {"text": '{"class":"billing"}', "model": request.get("model"), "usage": {}}

    storage = _FakeStorage()
    storage.version_node_type = "question_classifier"
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert "LambChat needs help" in requests[0]["prompt"]
    assert "billing: Billing" in requests[0]["prompt"]
    assert run.status == "succeeded"
    assert run.output == {"answer": "Billing"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_publish_and_run_workflow_allow_data_transform_nodes() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "data_transform"
    service = WorkflowPluginService(storage=storage)

    published = await service.publish_workflow(
        workflow_id="wf-created",
        version_id=None,
        user=_user(),
    )
    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert published.status == "published"
    assert run.status == "succeeded"
    assert run.output == {"answer": "Hello LambChat"}
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_publish_workflow_rejects_unsupported_nodes_on_hidden_branches() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "hidden_llm_branch"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_llm_prompt_missing"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_unreachable_nodes() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "unreachable_llm"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_unreachable_node:orphan_llm"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_code_nodes_by_policy() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "blocked_code"
    service = WorkflowPluginService(storage=storage)

    with pytest.raises(ValueError, match="workflow_code_node_blocked_by_policy:code"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_publish_workflow_rejects_unavailable_tools_on_hidden_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "hidden_missing_tool_branch"
    service = WorkflowPluginService(storage=storage)

    async def fake_tools_for_user(**kwargs):
        return [_EchoTool()]

    monkeypatch.setattr("src.infra.tool.internal_registry.get_internal_tools_for_user", fake_tools_for_user)

    with pytest.raises(ValueError, match="workflow_tool_not_available:missing_tool"):
        await service.publish_workflow(workflow_id="wf-created", version_id=None, user=_user())


@pytest.mark.asyncio
async def test_run_workflow_records_node_failed_events_for_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    storage.version_node_type = "missing_tool_runtime"
    service = WorkflowPluginService(storage=storage)

    async def no_tools_for_user(**kwargs):
        return []

    monkeypatch.setattr("src.infra.tool.internal_registry.get_internal_tools_for_user", no_tools_for_user)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={},
        mode="sync",
        user=_user(),
    )

    assert run.status == "failed"
    assert run.error == "workflow_tool_not_available:missing_tool"
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_failed",
        "run_failed",
    ]
    assert events[-2].node_id == "tool"
    assert events[-2].payload["error"] == "workflow_tool_not_available:missing_tool"


@pytest.mark.asyncio
async def test_run_workflow_rejects_unreachable_nodes_in_latest_version() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "unreachable_llm"
    service = WorkflowPluginService(storage=storage)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={},
        mode="sync",
        user=_user(),
    )

    assert run.status == "failed"
    assert run.error == "workflow_static_validation_failed:workflow_unreachable_node:orphan_llm"
    assert [event.event_type for event in events] == ["run_started", "run_failed"]
    assert events[0].payload == {"status": "running", "mode": "sync", "input_keys": []}
    assert events[1].payload["error"] == run.error


@pytest.mark.asyncio
async def test_run_workflow_pauses_and_resumes_human_approval() -> None:
    storage = _FakeStorage()
    storage.version_node_type = "human_approval"
    service = WorkflowPluginService(storage=storage)

    run, events = await service.run_workflow(
        workflow_id="wf-created",
        version_id=None,
        workflow_input={"name": "LambChat"},
        mode="sync",
        user=_user(),
    )

    assert run.status == "paused"
    assert run.error == "workflow_human_approval_paused:approval"
    assert run.pause["kind"] == "human_approval"
    assert run.pause["pending_approval"]["instructions"] == "Approve LambChat"
    assert [event.event_type for event in events] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "human_approval_required",
        "run_paused",
    ]

    resumed, resume_events = await service.resume_run(
        workflow_id="wf-created",
        run_id="wfr-created",
        approval_response={"approved": True, "comment": "OK"},
        user=_user(),
    )

    assert resumed.status == "succeeded"
    assert resumed.output == {"answer": "Approved OK"}
    assert [event.event_type for event in resume_events] == [
        "human_approval_resumed",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]


@pytest.mark.asyncio
async def test_unpublish_workflow_returns_to_draft() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    workflow = await service.unpublish_workflow(workflow_id="wf-created", user=_user())

    assert workflow.status == "draft"
    assert storage.unpublished == [{"workflow_id": "wf-created", "owner_user_id": "user-1"}]


@pytest.mark.asyncio
async def test_list_versions_requires_owned_workflow() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    versions = await service.list_versions(
        "wf-created",
        owner_user_id="user-1",
        skip=1,
        limit=10,
    )

    assert versions[0].version_id == "wfv-created"
    assert storage.list_versions_calls == [
        {"workflow_id": "wf-created", "owner_user_id": "user-1", "skip": 1, "limit": 10}
    ]

    with pytest.raises(LookupError, match="workflow_not_found"):
        await service.list_versions("missing", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_list_runs_requires_owned_workflow() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    runs = await service.list_runs(
        "wf-created",
        owner_user_id="user-1",
        skip=2,
        limit=5,
    )

    assert runs[0].run_id == "wfr-created"
    assert storage.list_runs_calls == [
        {"workflow_id": "wf-created", "owner_user_id": "user-1", "skip": 2, "limit": 5}
    ]

    with pytest.raises(LookupError, match="workflow_not_found"):
        await service.list_runs("missing", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_list_pending_approvals_delegates_user_scope_to_storage() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    runs = await service.list_pending_approvals(owner_user_id="user-1", skip=3, limit=7)

    assert runs[0].run_id == "wfr-paused"
    assert runs[0].pause["pending_approval"]["instructions"] == "Approve LambChat"
    assert storage.list_pending_approval_runs_calls == [
        {"owner_user_id": "user-1", "skip": 3, "limit": 7}
    ]


@pytest.mark.asyncio
async def test_list_run_events_requires_run_to_belong_to_workflow() -> None:
    storage = _FakeStorage()
    service = WorkflowPluginService(storage=storage)

    run, events = await service.list_run_events(
        workflow_id="wf-created",
        run_id="wfr-created",
        owner_user_id="user-1",
        skip=0,
        limit=20,
    )

    assert run.run_id == "wfr-created"
    assert events[0].event_type == "node_started"
    assert storage.list_run_events_calls == [
        {"run_id": "wfr-created", "owner_user_id": "user-1", "skip": 0, "limit": 20}
    ]

    with pytest.raises(LookupError, match="workflow_run_not_found"):
        await service.list_run_events(
            workflow_id="other-workflow",
            run_id="wfr-created",
            owner_user_id="user-1",
        )
