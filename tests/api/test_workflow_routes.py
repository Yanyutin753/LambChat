from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api import main as api_main
from src.kernel.extensions import (
    WORKFLOW_PLUGIN_ID,
    PluginRuntime,
    build_workflow_plugin_manifest,
)
from src.kernel.schemas.user import TokenPayload
from src.plugins.workflow import routes as workflow_routes


def _workflow_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=[
            "workflow:read",
            "workflow:write",
            "workflow:run",
            "workflow:credential:manage",
        ],
    )


def _enabled_app(fake_service) -> FastAPI:
    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)
    app = FastAPI()
    app.state.plugin_runtime = runtime
    app.include_router(workflow_routes.router, prefix="/api/plugins/workflow")
    app.dependency_overrides[api_deps.get_current_user_required] = _workflow_user
    app.dependency_overrides[workflow_routes.get_workflow_service] = lambda: fake_service
    return app


class _FakeWorkflow:
    def __init__(self, workflow_id: str, name: str) -> None:
        self.workflow_id = workflow_id
        self.name = name
        self.status = "draft"
        self.latest_version_id = "wfv-1"
        self.published_version_id = None
        self.description = "Imported workflow"
        self.version_count = 1
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def model_dump(self):
        return self.__dict__


class _FakeVersion:
    def __init__(self) -> None:
        self.version_id = "wfv-1"
        self.workflow_id = "wf-1"
        self.version_number = 1
        self.source = "workflow"
        self.source_format = "json"
        self.internal_model = {
            "format": "lambchat.workflow.v1",
            "graph": {"nodes": [{"id": "start", "type": "start"}], "edges": []},
        }
        self.compatibility_report = {"lossless": True, "supported_nodes": ["start"]}
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def model_dump(self):
        return self.__dict__


class _FakeRun:
    run_id = "wfr-1"
    workflow_id = "wf-1"
    version_id = "wfv-1"
    mode = "sync"
    status = "succeeded"
    output = {"answer": "ok"}
    error = None
    pause = {}
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeRunningRun(_FakeRun):
    mode = "stream"
    status = "running"
    output = {}
    finished_at = None


class _FakeSucceededStreamRun(_FakeRun):
    mode = "stream"
    status = "succeeded"
    output = {"answer": "done"}


class _FakeRunEvent:
    def __init__(
        self,
        *,
        sequence: int = 1,
        event_type: str = "node_started",
        node_id: str | None = "start",
        node_type: str | None = "start",
        payload: dict | None = None,
    ) -> None:
        self.event_id = f"wfe-{sequence}"
        self.run_id = "wfr-1"
        self.workflow_id = "wf-1"
        self.version_id = "wfv-1"
        self.sequence = sequence
        self.event_type = event_type
        self.node_id = node_id
        self.node_type = node_type
        self.payload = payload or {"title": "Start"}
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def model_dump(self):
        return self.__dict__


class _FakeFinishedRunEvent(_FakeRunEvent):
    def __init__(self) -> None:
        super().__init__()
        self.event_id = "wfe-2"
        self.sequence = 2
        self.event_type = "run_finished"
        self.node_id = None
        self.node_type = None
        self.payload = {"status": "succeeded"}


def _fake_run_started_events() -> list[_FakeRunEvent]:
    return [
        _FakeRunEvent(
            sequence=1,
            event_type="run_started",
            node_id=None,
            node_type=None,
            payload={"status": "running", "mode": "sync", "input_keys": ["name"]},
        ),
        _FakeRunEvent(sequence=2),
    ]


class _FakeCancelledRun(_FakeRun):
    status = "cancelled"
    output = {}
    error = "workflow_run_cancelled_by_user"


class _FakeNestedRun(_FakeRun):
    output = {
        "report": {"summary": "Nested route summary"},
        "items": [{"summary": "First item"}],
    }


class _FakePausedRun(_FakeRun):
    status = "paused"
    output = {}
    error = "workflow_human_approval_paused:approval"
    pause = {
        "kind": "human_approval",
        "pending_approval": {"node_id": "approval", "instructions": "Approve"},
    }
    finished_at = None


class _FakeCredential:
    def __init__(self) -> None:
        self.credential_id = "wfc-1"
        self.ref = "llm:provider_credential_id:openai-main"
        self.type = "model"
        self.label = "OpenAI main"
        self.description = "Workflow imported credential"
        self.has_secret = True
        self.metadata = {"provider": "openai"}
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def model_dump(self):
        return self.__dict__


class _WorkflowVersionDefinitionsCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = [dict(doc) for doc in docs]
        self.update_calls: list[tuple[dict, dict]] = []

    async def find_one(self, query: dict, **_: object) -> dict | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query: dict, update: dict) -> None:
        self.update_calls.append((query, update))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return


class _WorkflowVersionVersionsCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = [dict(doc) for doc in docs]
        self.inserted_docs: list[dict] = []

    async def find_one(
        self,
        query: dict,
        sort: list[tuple[str, int]] | None = None,
    ) -> dict | None:
        matches = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        if not matches:
            return None
        if sort == [("version_number", -1)]:
            return dict(max(matches, key=lambda doc: doc.get("version_number", 0)))
        return dict(matches[0])

    async def insert_one(self, doc: dict) -> None:
        stored = dict(doc)
        self.docs.append(stored)
        self.inserted_docs.append(stored)


class _WorkflowVersionRunsCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.inserted_docs: list[dict] = []
        self.update_calls: list[tuple[dict, dict]] = []

    async def insert_one(self, doc: dict) -> None:
        stored = dict(doc)
        self.docs.append(stored)
        self.inserted_docs.append(stored)

    async def find_one(self, query: dict, **_: object) -> dict | None:
        for doc in self.docs:
            if all(self._matches(doc.get(key), value) for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query: dict, update: dict) -> object:
        self.update_calls.append((query, update))
        for doc in self.docs:
            if all(self._matches(doc.get(key), value) for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return type("Result", (), {"matched_count": 1})()
        return type("Result", (), {"matched_count": 0})()

    def _matches(self, actual: object, expected: object) -> bool:
        if isinstance(expected, dict) and "$in" in expected:
            allowed = expected.get("$in")
            return isinstance(allowed, list) and actual in allowed
        return actual == expected


class _WorkflowVersionEventsCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.inserted_batches: list[list[dict]] = []

    async def find_one(
        self,
        query: dict,
        sort: list[tuple[str, int]] | None = None,
    ) -> dict | None:
        matches = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        if not matches:
            return None
        if sort == [("sequence", -1)]:
            return dict(max(matches, key=lambda doc: doc.get("sequence", 0)))
        return dict(matches[0])

    async def insert_many(self, docs: list[dict]) -> None:
        batch = [dict(doc) for doc in docs]
        self.docs.extend(batch)
        self.inserted_batches.append(batch)


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.workflow = _FakeWorkflow("wf-1", "Imported")
        self.run_error: str | None = None

    async def list_workflows(self, **kwargs):
        self.calls.append(("list", kwargs))
        return type("Result", (), {"workflows": [self.workflow], "total": 1})()

    async def get_workflow(self, workflow_id: str, **kwargs):
        self.calls.append(("get", {"workflow_id": workflow_id, **kwargs}))
        return self.workflow if workflow_id == "wf-1" else None

    async def get_workflow_detail(self, workflow_id: str, **kwargs):
        self.calls.append(("detail", {"workflow_id": workflow_id, **kwargs}))
        if workflow_id != "wf-1":
            return None, None
        return self.workflow, _FakeVersion()

    async def list_versions(self, workflow_id: str, **kwargs):
        self.calls.append(("versions", {"workflow_id": workflow_id, **kwargs}))
        return [_FakeVersion()]

    async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
        self.calls.append(("input_schema", {"workflow_id": workflow_id, **kwargs}))
        return {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "version_id": "wfv-1",
            "version_number": 1,
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string", "default": "hello"}},
                "additionalProperties": True,
            },
            "status": self.workflow.status,
            "schema_source": "declared",
            "inferred_fields": [],
        }

    async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
        self.calls.append(("io_contract", {"workflow_id": workflow_id, **kwargs}))
        return {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "version_id": "wfv-1",
            "version_number": 1,
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string", "default": "hello"}},
                "additionalProperties": True,
            },
            "output_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string", "x-lambchat-source": "inferred"}},
                "additionalProperties": True,
            },
            "status": self.workflow.status,
            "input_schema_source": "declared",
            "output_schema_source": "inferred",
            "inferred_input_fields": [],
            "inferred_output_fields": ["answer"],
        }

    async def import_workflow(self, **kwargs):
        self.calls.append(("import", kwargs))
        report = {
            "source": "workflow",
            "source_version": "workflow-0.3.0",
            "workflow_id": None if kwargs["dry_run"] else "wf-1",
            "supported_nodes": [],
            "unsupported_nodes": [],
            "credential_refs_required": [],
            "warnings": ["minimal parser"],
            "errors": [],
            "lossless": False,
        }
        if kwargs["dry_run"]:
            return None, None, report
        return self.workflow, _FakeVersion(), report

    async def create_workflow_version(self, **kwargs):
        self.calls.append(("create_version", kwargs))
        report = {
            "source": "workflow",
            "source_version": "workflow-0.3.0",
            "workflow_id": kwargs["workflow_id"],
            "supported_nodes": ["start"],
            "unsupported_nodes": [],
            "credential_refs_required": [],
            "warnings": [],
            "errors": [],
            "lossless": True,
        }
        version = _FakeVersion()
        version.version_id = "wfv-2"
        version.version_number = 2
        return self.workflow, version, report

    async def publish_workflow(self, **kwargs):
        self.calls.append(("publish", kwargs))
        self.workflow.status = "published"
        self.workflow.published_version_id = kwargs.get("version_id") or "wfv-1"
        return self.workflow

    async def validate_workflow_version(self, **kwargs):
        self.calls.append(("validate", kwargs))
        return {
            "workflow_id": kwargs["workflow_id"],
            "version_id": kwargs.get("version_id") or "wfv-1",
            "version_number": 1,
            "runnable": True,
            "errors": [],
            "reachable_node_ids": ["start", "answer"],
        }

    async def unpublish_workflow(self, **kwargs):
        self.calls.append(("unpublish", kwargs))
        self.workflow.status = "draft"
        self.workflow.published_version_id = None
        return self.workflow

    async def delete_workflow(self, **kwargs):
        self.calls.append(("delete_workflow", kwargs))
        self.workflow.status = "archived"
        self.workflow.published_version_id = None
        return self.workflow

    async def run_workflow(self, **kwargs):
        self.calls.append(("run", kwargs))
        if self.run_error:
            raise ValueError(self.run_error)
        return _FakeRun(), _fake_run_started_events()

    async def list_runs(self, workflow_id: str, **kwargs):
        self.calls.append(("runs", {"workflow_id": workflow_id, **kwargs}))
        return [_FakeRun()]

    async def list_pending_approvals(self, **kwargs):
        self.calls.append(("pending_approvals", kwargs))
        return [_FakePausedRun()]

    async def list_run_events(self, **kwargs):
        self.calls.append(("events", kwargs))
        return _FakeRun(), _fake_run_started_events()

    async def cancel_run(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        event = _FakeRunEvent()
        event.event_type = "run_cancelled"
        event.node_id = None
        event.node_type = None
        event.payload = {
            "error": "workflow_run_cancelled_by_user",
            "cancelled_by": kwargs["user"].sub,
        }
        return _FakeCancelledRun(), [event]

    async def resume_run(self, **kwargs):
        self.calls.append(("resume", kwargs))
        event = _FakeRunEvent()
        event.event_type = "human_approval_resumed"
        event.node_id = "approval"
        event.node_type = "human_approval"
        event.payload = {"approved": kwargs["approval_response"]["approved"]}
        return _FakeRun(), [event]

    async def list_credentials(self, **kwargs):
        self.calls.append(("list_credentials", kwargs))
        return [_FakeCredential()]

    async def upsert_credential(self, **kwargs):
        self.calls.append(("upsert_credential", kwargs))
        return _FakeCredential()

    async def delete_credential(self, **kwargs):
        self.calls.append(("delete_credential", kwargs))
        return kwargs["credential_id"] == "wfc-1"


def _nested_output_schema() -> dict:
    return {
        "type": "object",
        "required": ["report"],
        "properties": {
            "report": {
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                },
            },
        },
        "additionalProperties": True,
    }


def _assert_nested_output_contract(payload: dict, *, valid: bool) -> None:
    output_contract = payload["output_contract"]
    assert output_contract["valid"] is valid
    assert output_contract["declared_fields"] == ["items", "report"]
    assert output_contract["declared_field_paths"] == ["report.summary", "items[].summary"]
    assert output_contract["required_fields"] == ["report"]
    assert output_contract["required_field_paths"] == ["report.summary"]


def _assert_workflow_run_interface(payload: dict, *, next_action_type: str = "use_output") -> None:
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
        "events_field": "events",
    }
    assert payload["next_action"]["type"] == next_action_type


def _assert_workflow_version_interface(payload: dict, *, version_id: str) -> None:
    assert payload["io_contract"]["plugin_id"] == "workflow"
    assert payload["io_contract"]["workflow_id"] == "wf-1"
    assert payload["io_contract"]["version_id"] == version_id
    assert "input_schema" in payload["io_contract"]
    assert "output_schema" in payload["io_contract"]
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": version_id,
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": None,
        "events_field": "events",
    }


@pytest.mark.asyncio
async def test_workflow_credential_routes_mask_secret_values() -> None:
    service = _FakeService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get("/api/plugins/workflow/credentials")
        upserted = await client.put(
            "/api/plugins/workflow/credentials",
            json={
                "ref": "llm:provider_credential_id:openai-main",
                "type": "model",
                "label": "OpenAI main",
                "description": "Workflow imported credential",
                "secret": "sk-should-not-return",
                "metadata": {"provider": "openai"},
            },
        )
        deleted = await client.delete("/api/plugins/workflow/credentials/wfc-1")

    assert listed.status_code == 200
    assert listed.json()["credentials"][0]["has_secret"] is True
    assert "sk-should-not-return" not in listed.text
    assert "secret_payload" not in listed.text
    assert "secret" not in listed.json()["credentials"][0]
    assert upserted.status_code == 200
    assert upserted.json()["credential_id"] == "wfc-1"
    assert upserted.json()["ref"] == "llm:provider_credential_id:openai-main"
    assert "sk-should-not-return" not in upserted.text
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "credential_id": "wfc-1"}
    assert service.calls[-3][0] == "list_credentials"
    assert service.calls[-2][0] == "upsert_credential"
    assert service.calls[-2][1]["secret"] == "sk-should-not-return"
    assert service.calls[-1] == (
        "delete_credential",
        {"user": _workflow_user(), "credential_id": "wfc-1"},
    )


@pytest.mark.asyncio
async def test_workflow_routes_list_get_and_import() -> None:
    service = _FakeService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get("/api/plugins/workflow/workflows?skip=2&limit=10")
        fetched = await client.get("/api/plugins/workflow/workflows/wf-1")
        versions = await client.get("/api/plugins/workflow/workflows/wf-1/versions")
        input_schema = await client.get(
            "/api/plugins/workflow/workflows/wf-1/input-schema?version_id=wfv-2"
        )
        io_contract = await client.get(
            "/api/plugins/workflow/workflows/wf-1/io-contract?version_id=wfv-2"
        )
        dry_run = await client.post(
            "/api/plugins/workflow/workflows/import",
            json={"name": "Imported", "source_payload": {"version": "0.3.0"}, "dry_run": True},
        )
        yaml_dry_run = await client.post(
            "/api/plugins/workflow/workflows/import",
            json={
                "name": "YAML",
                "source_format": "yaml",
                "source_content": "version: 0.3.0\nworkflow:\n  nodes: []\n",
                "dry_run": True,
            },
        )
        imported = await client.post(
            "/api/plugins/workflow/workflows/import",
            json={"name": "Imported", "source_payload": {"version": "0.3.0"}, "dry_run": False},
        )
        versioned = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={"name": "Updated", "source_payload": {"version": "0.3.0"}},
        )
        yaml_versioned = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={
                "name": "Updated YAML",
                "source_format": "yaml",
                "source_content": "version: 0.3.0\nworkflow:\n  nodes: []\n",
            },
        )
        published = await client.post(
            "/api/plugins/workflow/workflows/wf-1/publish",
            json={"version_id": "wfv-2"},
        )
        validated = await client.post(
            "/api/plugins/workflow/workflows/wf-1/validate",
            json={"version_id": "wfv-2"},
        )
        unpublished = await client.post(
            "/api/plugins/workflow/workflows/wf-1/unpublish",
        )
        ran = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={"input": {"name": "LambChat"}, "mode": "sync", "version_id": "wfv-2"},
        )
        runs = await client.get("/api/plugins/workflow/workflows/wf-1/runs?limit=10")
        events = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events"
        )
        event_stream = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream"
        )
        cancelled = await client.post(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/cancel"
        )
        resumed = await client.post(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/resume",
            json={"approved": True, "comment": "OK"},
        )
        node_types = await client.get("/api/plugins/workflow/node-types")
        deleted = await client.delete("/api/plugins/workflow/workflows/wf-1")

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["workflows"][0]["workflow_id"] == "wf-1"
    assert fetched.status_code == 200
    assert fetched.json()["latest_version_id"] == "wfv-1"
    assert fetched.json()["latest_version"]["internal_model"]["graph"]["nodes"][0]["id"] == "start"
    assert versions.status_code == 200
    assert versions.json()["versions"][0]["version_id"] == "wfv-1"
    assert input_schema.status_code == 200
    assert input_schema.json()["input_schema"]["properties"]["message"]["default"] == "hello"
    assert input_schema.json()["schema_source"] == "declared"
    assert input_schema.json()["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert input_schema.json()["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert input_schema.json()["interface"]["schema"]["tool"] == "workflow_get_schema"
    assert input_schema.json()["interface"]["run"]["input_argument"] == "input"
    assert io_contract.status_code == 200
    assert io_contract.json()["input_schema"]["properties"]["message"]["default"] == "hello"
    assert io_contract.json()["output_schema"]["properties"]["answer"]["type"] == "string"
    assert io_contract.json()["output_schema_source"] == "inferred"
    assert io_contract.json()["interface"]["entry"]["tool"] == "workflow_run"
    assert io_contract.json()["interface"]["entry"]["argument"] == "input"
    assert io_contract.json()["interface"]["exit"]["field"] == "output"
    assert io_contract.json()["interface"]["schema"]["output_schema_field"] == "output_schema"
    assert dry_run.status_code == 200
    assert dry_run.json()["status"] == "stub"
    assert dry_run.json()["workflow_id"] is None
    assert dry_run.json()["io_contract"] is None
    assert dry_run.json()["interface"] is None
    assert yaml_dry_run.status_code == 200
    assert imported.status_code == 200
    assert imported.json()["status"] == "imported"
    assert imported.json()["workflow_id"] == "wf-1"
    assert imported.json()["version_id"] == "wfv-1"
    _assert_workflow_version_interface(imported.json(), version_id="wfv-1")
    assert versioned.status_code == 200
    assert versioned.json()["status"] == "versioned"
    assert versioned.json()["version_id"] == "wfv-2"
    _assert_workflow_version_interface(versioned.json(), version_id="wfv-2")
    assert yaml_versioned.status_code == 200
    _assert_workflow_version_interface(yaml_versioned.json(), version_id="wfv-2")
    assert published.status_code == 200
    assert published.json()["workflow"]["status"] == "published"
    assert published.json()["workflow"]["published_version_id"] == "wfv-2"
    assert validated.status_code == 200
    assert validated.json()["runnable"] is True
    assert validated.json()["reachable_node_ids"] == ["start", "answer"]
    assert unpublished.status_code == 200
    assert unpublished.json()["workflow"]["status"] == "draft"
    assert unpublished.json()["workflow"]["published_version_id"] is None
    assert ran.status_code == 200
    assert ran.json()["run_id"] == "wfr-1"
    assert ran.json()["mode"] == "sync"
    assert ran.json()["status"] == "succeeded"
    assert ran.json()["output"] == {"answer": "ok"}
    assert ran.json()["io_contract"]["output_schema"]["properties"]["answer"]["type"] == "string"
    assert ran.json()["output_contract"]["valid"] is True
    assert ran.json()["output_contract"]["declared_fields"] == ["answer"]
    _assert_workflow_run_interface(ran.json())
    assert ran.json()["events"][0]["event_type"] == "run_started"
    assert ran.json()["events"][0]["payload"]["mode"] == "sync"
    assert ran.json()["events"][1]["event_type"] == "node_started"
    assert ran.json()["events"][1]["node_id"] == "start"
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["run_id"] == "wfr-1"
    assert runs.json()["runs"][0]["mode"] == "sync"
    assert runs.json()["runs"][0]["events"] == []
    assert runs.json()["runs"][0]["output_contract"]["valid"] is True
    _assert_workflow_run_interface(runs.json()["runs"][0])
    assert events.status_code == 200
    assert events.json()["run"]["mode"] == "sync"
    assert events.json()["run"]["output_contract"]["valid"] is True
    _assert_workflow_run_interface(events.json()["run"])
    assert events.json()["events"][0]["event_type"] == "run_started"
    assert events.json()["events"][1]["event_type"] == "node_started"
    assert events.json()["events"][1]["node_id"] == "start"
    assert event_stream.status_code == 200
    assert event_stream.headers["content-type"].startswith("text/event-stream")
    assert "event: workflow_run_event" in event_stream.text
    assert "event: workflow_run_snapshot" in event_stream.text
    assert '"event_type": "run_started"' in event_stream.text
    assert '"event_type": "node_started"' in event_stream.text
    assert '"event_count": 2' in event_stream.text
    assert '"output_contract"' in event_stream.text
    assert '"interface"' in event_stream.text
    assert '"next_action"' in event_stream.text
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["output_contract"]["valid"] is True
    _assert_workflow_run_interface(cancelled.json(), next_action_type="handle_terminal_error")
    assert cancelled.json()["events"][0]["event_type"] == "run_cancelled"
    assert cancelled.json()["events"][0]["payload"]["cancelled_by"] == "user-1"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "succeeded"
    assert resumed.json()["output_contract"]["valid"] is True
    _assert_workflow_run_interface(resumed.json())
    assert resumed.json()["events"][0]["event_type"] == "human_approval_resumed"
    assert node_types.status_code == 200
    node_payload = node_types.json()
    assert node_payload["plugin_id"] == "workflow"
    assert node_payload["compatibility"]["summary"]["guarded"] >= 1
    assert any(item["type"] == "question_classifier" for item in node_payload["node_types"])
    assert any(
        item["source_type"] == "code" and item["status"] == "blocked"
        for item in node_payload["compatibility"]["items"]
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["workflow_id"] == "wf-1"
    assert deleted.json()["workflow"]["status"] == "archived"
    assert service.calls[0] == (
        "list",
        {
            "owner_user_id": "user-1",
            "skip": 2,
            "limit": 10,
            "query": None,
            "status_filter": None,
        },
    )
    assert service.calls[1] == ("detail", {"workflow_id": "wf-1", "owner_user_id": "user-1"})
    assert service.calls[2] == (
        "versions",
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "skip": 0, "limit": 50},
    )
    assert service.calls[3] == (
        "input_schema",
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-2"},
    )
    assert service.calls[4] == (
        "io_contract",
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-2"},
    )
    assert service.calls[5][1]["user"].sub == "user-1"
    assert service.calls[6][0] == "import"
    assert service.calls[6][1]["source_format"] == "yaml"
    assert service.calls[6][1]["source_content"].startswith("version")
    assert service.calls[8][0] == "create_version"
    assert service.calls[8][1]["user"].sub == "user-1"
    assert service.calls[9][0] == "create_version"
    assert service.calls[9][1]["source_format"] == "yaml"
    assert service.calls[10][0] == "publish"
    assert service.calls[10][1]["version_id"] == "wfv-2"
    assert service.calls[11][0] == "validate"
    assert service.calls[11][1]["version_id"] == "wfv-2"
    assert service.calls[12][0] == "unpublish"
    assert service.calls[13][0] == "run"
    assert service.calls[13][1]["user"].sub == "user-1"
    assert service.calls[13][1]["version_id"] == "wfv-2"
    assert (
        "io_contract",
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-1"},
    ) in service.calls
    assert (
        "runs",
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "skip": 0, "limit": 10},
    ) in service.calls
    event_calls = [call for call in service.calls if call[0] == "events"]
    assert len(event_calls) >= 2
    cancel_calls = [call for call in service.calls if call[0] == "cancel"]
    assert cancel_calls[0][1]["workflow_id"] == "wf-1"
    assert cancel_calls[0][1]["run_id"] == "wfr-1"
    assert cancel_calls[0][1]["user"].sub == "user-1"
    resume_calls = [call for call in service.calls if call[0] == "resume"]
    assert resume_calls[0][1]["approval_response"]["comment"] == "OK"
    assert resume_calls[0][1]["user"].sub == "user-1"
    delete_calls = [call for call in service.calls if call[0] == "delete_workflow"]
    assert delete_calls[0][1]["workflow_id"] == "wf-1"
    assert delete_calls[0][1]["user"].sub == "user-1"


@pytest.mark.asyncio
async def test_workflow_route_forwards_editor_dsl_version_payload() -> None:
    service = _FakeService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)
    source_payload = {
        "version": "0.3.0",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {"id": "answer", "type": "answer", "data": {"title": "Answer", "answer": "{{message}}"}},
                {
                    "id": "node_3",
                    "type": "llm",
                    "data": {"title": "Node 3", "prompt_template": "Answer {{message}}"},
                },
            ],
            "edges": [{"id": "start-answer", "source": "start", "target": "answer"}],
        },
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={
                "name": "Imported Workflow",
                "source_payload": source_payload,
                "source_format": "json",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "versioned"
    assert service.calls == [
        (
            "create_version",
            {
                "workflow_id": "wf-1",
                "name": "Imported Workflow",
                "source_format": "json",
                "source_payload": source_payload,
                "source_content": None,
                "user": _workflow_user(),
            },
        )
    ]


@pytest.mark.asyncio
async def test_workflow_route_saves_editor_dsl_through_real_service_and_storage() -> None:
    from src.plugins.workflow.service import WorkflowPluginService
    from src.plugins.workflow.storage import WorkflowPluginStorage

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    definitions = _WorkflowVersionDefinitionsCollection(
        [
            {
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "name": "Imported",
                "description": "",
                "status": "draft",
                "latest_version_id": "wfv-1",
                "published_version_id": None,
                "version_count": 1,
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    versions = _WorkflowVersionVersionsCollection(
        [
            {
                "version_id": "wfv-1",
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "version_number": 1,
                "source": "workflow",
                "source_format": "json",
                "source_payload": {"version": "0.3.0", "workflow": {"nodes": []}},
                "internal_model": {
                    "format": "lambchat.workflow.v1",
                    "graph": {"nodes": [], "edges": []},
                },
                "compatibility_report": {"lossless": True},
                "created_by": "user-1",
                "created_at": now,
            }
        ]
    )
    storage = WorkflowPluginStorage()
    storage._definitions = definitions  # type: ignore[assignment]
    storage._versions = versions  # type: ignore[assignment]
    service = WorkflowPluginService(storage=storage)
    app = _enabled_app(service)
    transport = ASGITransport(app=app)
    source_payload = {
        "version": "0.3.0",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {
                    "id": "node_3",
                    "type": "llm",
                    "data": {"title": "Node 3", "prompt_template": "Answer {{message}}"},
                    "position": {"x": 320, "y": 120},
                },
                {"id": "answer", "type": "answer", "data": {"title": "Answer", "answer": "{{node_3.text}}"}},
            ],
            "edges": [
                {"id": "start-node_3", "source": "start", "target": "node_3"},
                {"id": "node_3-answer", "source": "node_3", "target": "answer"},
            ],
        },
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={"name": "Saved In Editor", "source_payload": source_payload},
        )

    assert response.status_code == 200
    payload = response.json()
    inserted = versions.inserted_docs[0]
    nodes_by_id = {
        node["id"]: node
        for node in inserted["internal_model"]["graph"]["nodes"]
    }
    assert payload["status"] == "versioned"
    assert payload["workflow_id"] == "wf-1"
    assert payload["version_id"] == inserted["version_id"]
    assert inserted["version_number"] == 2
    assert inserted["source_payload"] == source_payload
    assert nodes_by_id["node_3"]["type"] == "llm"
    assert nodes_by_id["node_3"]["position"] == {"x": 320, "y": 120}
    assert nodes_by_id["node_3"]["data"]["prompt_template"] == "Answer {{message}}"
    assert inserted["internal_model"]["graph"]["edges"] == [
        {
            "id": "start-node_3",
            "source": "start",
            "target": "node_3",
            "source_handle": None,
            "target_handle": None,
            "data": {},
            "valid": True,
        },
        {
            "id": "node_3-answer",
            "source": "node_3",
            "target": "answer",
            "source_handle": None,
            "target_handle": None,
            "data": {},
            "valid": True,
        },
    ]
    assert inserted["compatibility_report"]["supported_nodes"] == ["answer", "llm", "start"]
    assert inserted["compatibility_report"]["lossless"] is True
    assert definitions.docs[0]["latest_version_id"] == inserted["version_id"]
    assert definitions.docs[0]["version_count"] == 2
    assert definitions.docs[0]["name"] == "Saved In Editor"


@pytest.mark.asyncio
async def test_workflow_route_runs_editor_saved_llm_workflow_through_real_runtime() -> None:
    from src.plugins.workflow.service import WorkflowPluginService
    from src.plugins.workflow.storage import WorkflowPluginStorage

    llm_requests: list[dict] = []

    async def invoke_llm(request: dict) -> dict:
        llm_requests.append(request)
        return {"text": "LLM says hello", "model": request.get("model"), "usage": {"total_tokens": 3}}

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    definitions = _WorkflowVersionDefinitionsCollection(
        [
            {
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "name": "Imported",
                "description": "",
                "status": "draft",
                "latest_version_id": "wfv-1",
                "published_version_id": None,
                "version_count": 1,
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    versions = _WorkflowVersionVersionsCollection(
        [
            {
                "version_id": "wfv-1",
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "version_number": 1,
                "source": "workflow",
                "source_format": "json",
                "source_payload": {"version": "0.3.0", "workflow": {"nodes": []}},
                "internal_model": {
                    "format": "lambchat.workflow.v1",
                    "graph": {"nodes": [], "edges": []},
                },
                "compatibility_report": {"lossless": True},
                "created_by": "user-1",
                "created_at": now,
            }
        ]
    )
    runs = _WorkflowVersionRunsCollection()
    events = _WorkflowVersionEventsCollection()
    storage = WorkflowPluginStorage()
    storage._definitions = definitions  # type: ignore[assignment]
    storage._versions = versions  # type: ignore[assignment]
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)
    app = _enabled_app(service)
    transport = ASGITransport(app=app)
    source_payload = {
        "version": "0.3.0",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {
                    "id": "node_3",
                    "type": "llm",
                    "data": {
                        "title": "Node 3",
                        "prompt_template": "Answer {{message}}",
                        "model": "gpt-4o-mini",
                    },
                },
                {"id": "answer", "type": "answer", "data": {"title": "Answer", "answer": "{{llm_text}}"}},
            ],
            "edges": [
                {"id": "start-node_3", "source": "start", "target": "node_3"},
                {"id": "node_3-answer", "source": "node_3", "target": "answer"},
            ],
        },
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        version_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={"name": "Runnable Editor Graph", "source_payload": source_payload},
        )
        run_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={
                "version_id": version_response.json()["version_id"],
                "mode": "sync",
                "input": {"message": "hello from chat"},
            },
        )

    assert version_response.status_code == 200
    assert run_response.status_code == 200
    payload = run_response.json()
    assert llm_requests == [
        {
            "prompt": "Answer hello from chat",
            "messages": [],
            "model_id": None,
            "model": "gpt-4o-mini",
        }
    ]
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "LLM says hello"}
    assert payload["version_id"] == version_response.json()["version_id"]
    assert payload["io_contract"]["output_schema"]["properties"]["answer"]["type"] == "string"
    assert payload["output_contract"]["valid"] is True
    assert [event["event_type"] for event in payload["events"]] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]
    assert [event["node_id"] for event in payload["events"] if event["event_type"] == "node_started"] == [
        "start",
        "node_3",
        "answer",
    ]
    assert runs.docs[0]["status"] == "succeeded"
    assert runs.docs[0]["output"] == {"answer": "LLM says hello"}
    assert events.inserted_batches[0][-1]["event_type"] == "run_succeeded"


@pytest.mark.asyncio
async def test_workflow_route_runs_published_editor_version_by_default() -> None:
    from src.plugins.workflow.service import WorkflowPluginService
    from src.plugins.workflow.storage import WorkflowPluginStorage

    llm_requests: list[dict] = []

    async def invoke_llm(request: dict) -> dict:
        llm_requests.append(request)
        return {"text": "LLM published hello", "model": request.get("model")}

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    definitions = _WorkflowVersionDefinitionsCollection(
        [
            {
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "name": "Imported",
                "description": "",
                "status": "draft",
                "latest_version_id": "wfv-1",
                "published_version_id": None,
                "version_count": 1,
                "created_at": now,
                "updated_at": now,
            }
        ]
    )
    versions = _WorkflowVersionVersionsCollection(
        [
            {
                "version_id": "wfv-1",
                "workflow_id": "wf-1",
                "owner_user_id": "user-1",
                "version_number": 1,
                "source": "workflow",
                "source_format": "json",
                "source_payload": {"version": "0.3.0", "workflow": {"nodes": []}},
                "internal_model": {
                    "format": "lambchat.workflow.v1",
                    "graph": {"nodes": [], "edges": []},
                },
                "compatibility_report": {"lossless": True},
                "created_by": "user-1",
                "created_at": now,
            }
        ]
    )
    runs = _WorkflowVersionRunsCollection()
    events = _WorkflowVersionEventsCollection()
    storage = WorkflowPluginStorage()
    storage._definitions = definitions  # type: ignore[assignment]
    storage._versions = versions  # type: ignore[assignment]
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)
    app = _enabled_app(service)
    transport = ASGITransport(app=app)
    source_payload = {
        "version": "0.3.0",
        "workflow": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"title": "Start"}},
                {
                    "id": "node_3",
                    "type": "llm",
                    "data": {
                        "title": "Node 3",
                        "prompt_template": "Answer {{message}}",
                        "model": "gpt-4o-mini",
                    },
                },
                {"id": "answer", "type": "answer", "data": {"title": "Answer", "answer": "{{llm_text}}"}},
            ],
            "edges": [
                {"id": "start-node_3", "source": "start", "target": "node_3"},
                {"id": "node_3-answer", "source": "node_3", "target": "answer"},
            ],
        },
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        version_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/versions",
            json={"name": "Published Editor Graph", "source_payload": source_payload},
        )
        version_id = version_response.json()["version_id"]
        publish_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/publish",
            json={"version_id": version_id},
        )
        run_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={
                "mode": "sync",
                "input": {"message": "published call"},
            },
        )

    assert version_response.status_code == 200
    assert publish_response.status_code == 200
    assert run_response.status_code == 200
    assert publish_response.json()["workflow"]["status"] == "published"
    assert publish_response.json()["workflow"]["published_version_id"] == version_id
    assert definitions.docs[0]["status"] == "published"
    assert definitions.docs[0]["published_version_id"] == version_id
    assert llm_requests == [
        {
            "prompt": "Answer published call",
            "messages": [],
            "model_id": None,
            "model": "gpt-4o-mini",
        }
    ]
    payload = run_response.json()
    assert payload["status"] == "succeeded"
    assert payload["version_id"] == version_id
    assert payload["output"] == {"answer": "LLM published hello"}
    assert payload["output_contract"]["valid"] is True
    assert [event["event_type"] for event in payload["events"]] == [
        "run_started",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "node_started",
        "node_finished",
        "run_succeeded",
    ]
    assert runs.docs[0]["version_id"] == version_id
    assert runs.docs[0]["output"] == {"answer": "LLM published hello"}
    assert events.inserted_batches[0][-1]["event_type"] == "run_succeeded"


@pytest.mark.asyncio
async def test_workflow_run_routes_include_nested_output_contract_paths() -> None:
    class _NestedContractService(_FakeService):
        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            payload = await super().get_workflow_io_contract(workflow_id, **kwargs)
            payload["output_schema"] = _nested_output_schema()
            payload["output_schema_source"] = "declared"
            payload["inferred_output_fields"] = []
            return payload

        async def run_workflow(self, **kwargs):
            self.calls.append(("run", kwargs))
            return _FakeNestedRun(), _fake_run_started_events()

        async def list_runs(self, workflow_id: str, **kwargs):
            self.calls.append(("runs", {"workflow_id": workflow_id, **kwargs}))
            return [_FakeNestedRun()]

        async def list_run_events(self, **kwargs):
            self.calls.append(("events", kwargs))
            return _FakeNestedRun(), _fake_run_started_events()

        async def resume_run(self, **kwargs):
            self.calls.append(("resume", kwargs))
            event = _FakeRunEvent()
            event.event_type = "human_approval_resumed"
            event.node_id = "approval"
            event.node_type = "human_approval"
            event.payload = {"approved": kwargs["approval_response"]["approved"]}
            return _FakeNestedRun(), [event]

    service = _NestedContractService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        ran = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={"input": {"name": "LambChat"}, "mode": "sync"},
        )
        runs = await client.get("/api/plugins/workflow/workflows/wf-1/runs")
        events = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events"
        )
        event_stream = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream"
        )
        cancelled = await client.post(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/cancel"
        )
        resumed = await client.post(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/resume",
            json={"approved": True},
        )

    assert ran.status_code == 200
    assert ran.json()["io_contract"]["output_schema"]["properties"]["report"]["type"] == "object"
    _assert_nested_output_contract(ran.json(), valid=True)
    assert runs.status_code == 200
    _assert_nested_output_contract(runs.json()["runs"][0], valid=True)
    assert events.status_code == 200
    _assert_nested_output_contract(events.json()["run"], valid=True)
    assert event_stream.status_code == 200
    assert '"declared_field_paths": ["report.summary", "items[].summary"]' in event_stream.text
    assert '"required_field_paths": ["report.summary"]' in event_stream.text
    assert cancelled.status_code == 200
    _assert_nested_output_contract(cancelled.json(), valid=False)
    assert cancelled.json()["output_contract"]["missing_required"] == ["report"]
    assert resumed.status_code == 200
    _assert_nested_output_contract(resumed.json(), valid=True)


@pytest.mark.asyncio
async def test_run_workflow_route_returns_bad_request_for_entry_contract_error() -> None:
    service = _FakeService()
    service.run_error = "workflow_input_required_missing:name"
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={"input": {}, "mode": "sync"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "error": "workflow_input_required_missing:name",
        "workflow_id": "wf-1",
    }


@pytest.mark.asyncio
async def test_workflow_pending_approval_route_returns_user_scoped_paused_runs() -> None:
    service = _FakeService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/plugins/workflow/approvals/pending?skip=1&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == "workflow"
    assert payload["skip"] == 1
    assert payload["limit"] == 5
    assert payload["runs"][0]["status"] == "paused"
    assert payload["runs"][0]["pause"]["kind"] == "human_approval"
    assert payload["runs"][0]["pause"]["pending_approval"] == {
        "node_id": "approval",
        "instructions": "Approve",
    }
    assert payload["runs"][0]["next_action"] == {
        "type": "await_human_approval",
        "tool": "workflow_get_run",
        "reason": "workflow_run_paused_human_approval",
        "field": "pause.pending_approval",
        "approval": {
            "kind": "human_approval",
            "node_id": "approval",
            "title": None,
            "assignee": None,
            "output_key": None,
        },
        "pending": {
            "method": "GET",
            "path": "/api/plugins/workflow/approvals/pending",
        },
        "resume": {
            "tool": "workflow_resume",
            "method": "POST",
            "path": "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/resume",
            "body": {"approved": True, "comment": "", "values": {}},
            "arguments": {
                "workflow_id": "wf-1",
                "run_id": "wfr-1",
                "approved": True,
                "comment": "",
                "values": {},
            },
        },
    }
    assert payload["runs"][0]["output_contract"]["valid"] is True
    assert (
        "pending_approvals",
        {"owner_user_id": "user-1", "skip": 1, "limit": 5},
    ) in service.calls


@pytest.mark.asyncio
async def test_workflow_route_guard_blocks_disabled_plugin() -> None:
    class _FailService:
        async def list_workflows(self, **kwargs):
            raise AssertionError("disabled workflow plugin route must not reach service")

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    app = FastAPI()
    app.state.plugin_runtime = runtime
    app.include_router(workflow_routes.router, prefix="/api/plugins/workflow")
    app.dependency_overrides[api_deps.get_current_user_required] = _workflow_user
    app.dependency_overrides[workflow_routes.get_workflow_service] = lambda: _FailService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/plugins/workflow/workflows")

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "plugin_unavailable"
    assert response.json()["detail"]["plugin_id"] == WORKFLOW_PLUGIN_ID


@pytest.mark.asyncio
async def test_create_app_mounts_workflow_routes_behind_runtime_guard() -> None:
    app = api_main.create_app()
    app.dependency_overrides[api_deps.get_current_user_required] = _workflow_user
    app.dependency_overrides[workflow_routes.get_workflow_service] = lambda: _FakeService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "plugin_unavailable"
    assert response.json()["detail"]["plugin_id"] == WORKFLOW_PLUGIN_ID


@pytest.mark.asyncio
async def test_create_app_workflow_route_reaches_service_when_runtime_enabled() -> None:
    service = _FakeService()
    app = api_main.create_app()
    app.state.plugin_runtime.enable_plugin(WORKFLOW_PLUGIN_ID)
    app.dependency_overrides[api_deps.get_current_user_required] = _workflow_user
    app.dependency_overrides[workflow_routes.get_workflow_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows?skip=2&limit=10&query=invoice&status=published",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == WORKFLOW_PLUGIN_ID
    assert payload["workflows"][0]["workflow_id"] == "wf-1"
    assert service.calls == [
        (
            "list",
            {
                "owner_user_id": "user-1",
                "skip": 2,
                "limit": 10,
                "query": "invoice",
                "status_filter": "published",
            },
        )
    ]


@pytest.mark.asyncio
async def test_workflow_route_returns_structured_503_when_service_factory_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _create_service():
        raise RuntimeError("mongo password=secret-token host=mongodb://internal")

    app = api_main.create_app()
    app.state.plugin_runtime.enable_plugin(WORKFLOW_PLUGIN_ID)
    app.dependency_overrides[api_deps.get_current_user_required] = _workflow_user
    monkeypatch.setattr(workflow_routes, "create_workflow_service", _create_service)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "workflow_service_unavailable",
        "plugin_id": WORKFLOW_PLUGIN_ID,
    }
    assert "secret-token" not in response.text
    assert "mongodb://internal" not in response.text


@pytest.mark.asyncio
async def test_workflow_import_returns_400_for_invalid_source_content() -> None:
    from src.plugins.workflow.service import WorkflowPluginService

    app = _enabled_app(WorkflowPluginService())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/plugins/workflow/workflows/import",
            json={
                "name": "Invalid YAML",
                "source_format": "yaml",
                "source_content": "workflow: [",
                "dry_run": True,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "workflow_source_parse_failed:yaml"


@pytest.mark.asyncio
async def test_workflow_explicit_version_404_details_echo_requested_version() -> None:
    class _VersionMissingService(_FakeService):
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            self.calls.append(("input_schema", {"workflow_id": workflow_id, **kwargs}))
            raise LookupError("workflow_version_not_found")

        async def publish_workflow(self, **kwargs):
            self.calls.append(("publish", kwargs))
            raise LookupError("workflow_version_not_found")

        async def validate_workflow_version(self, **kwargs):
            self.calls.append(("validate", kwargs))
            raise LookupError("workflow_version_not_found")

        async def run_workflow(self, **kwargs):
            self.calls.append(("run", kwargs))
            raise LookupError("workflow_version_not_found")

    service = _VersionMissingService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        schema_response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/input-schema?version_id=wfv-other"
        )
        publish_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/publish",
            json={"version_id": "wfv-other"},
        )
        validate_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/validate",
            json={"version_id": "wfv-other"},
        )
        run_response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={"input": {"name": "LambChat"}, "version_id": "wfv-other"},
        )

    responses = [schema_response, publish_response, validate_response, run_response]
    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    for response in responses:
        assert response.json()["detail"] == {
            "error": "workflow_version_not_found",
            "workflow_id": "wf-1",
            "version_id": "wfv-other",
        }
    assert [call[0] for call in service.calls] == [
        "input_schema",
        "publish",
        "validate",
        "run",
    ]


@pytest.mark.asyncio
async def test_workflow_non_versioned_404_details_do_not_require_request_version() -> None:
    class _WorkflowMissingService(_FakeService):
        async def list_versions(self, workflow_id: str, **kwargs):
            self.calls.append(("versions", {"workflow_id": workflow_id, **kwargs}))
            raise LookupError("workflow_not_found")

        async def unpublish_workflow(self, **kwargs):
            self.calls.append(("unpublish", kwargs))
            raise LookupError("workflow_not_found")

    service = _WorkflowMissingService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        versions_response = await client.get("/api/plugins/workflow/workflows/missing/versions")
        unpublish_response = await client.post(
            "/api/plugins/workflow/workflows/missing/unpublish"
        )

    assert versions_response.status_code == 404
    assert versions_response.json()["detail"] == {
        "error": "workflow_not_found",
        "workflow_id": "missing",
    }
    assert unpublish_response.status_code == 404
    assert unpublish_response.json()["detail"] == {
        "error": "workflow_not_found",
        "workflow_id": "missing",
    }
    assert [call[0] for call in service.calls] == ["versions", "unpublish"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["async", "stream"])
async def test_workflow_run_route_accepts_deferred_modes(mode: str) -> None:
    service = _FakeService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/plugins/workflow/workflows/wf-1/run",
            json={"input": {"name": "LambChat"}, "mode": mode},
        )

    assert response.status_code == 200
    assert response.json()["output_contract"]["valid"] is True
    run_calls = [call for call in service.calls if call[0] == "run"]
    assert run_calls[-1][1]["mode"] == mode


@pytest.mark.asyncio
async def test_workflow_run_event_stream_waits_for_new_events() -> None:
    class _StreamingService(_FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.event_calls = 0

        async def list_run_events(self, **kwargs):
            self.event_calls += 1
            self.calls.append(("events", kwargs))
            if self.event_calls == 1:
                return _FakeRunningRun(), []
            return _FakeSucceededStreamRun(), [_FakeFinishedRunEvent()]

    service = _StreamingService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream?poll_ms=100&timeout_ms=2000"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert ": workflow_run_keepalive" in response.text
    assert "event: workflow_run_event" in response.text
    assert '"event_type": "run_finished"' in response.text
    assert "event: workflow_run_snapshot" in response.text
    assert '"mode": "stream"' in response.text
    assert '"terminal": true' in response.text
    assert service.event_calls == 2
    assert service.calls[0][1]["skip"] == 0
    assert service.calls[1][1]["skip"] == 0


@pytest.mark.asyncio
async def test_workflow_run_events_route_returns_503_when_storage_fails() -> None:
    class _FailingEventsService(_FakeService):
        async def list_run_events(self, **kwargs):
            self.calls.append(("events", kwargs))
            raise RuntimeError("mongo password=secret-token host=mongodb://internal")

    service = _FailingEventsService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events"
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "workflow_run_events_unavailable",
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
    }
    assert "secret-token" not in response.text
    assert "mongodb://internal" not in response.text
    assert service.calls[0][0] == "events"


@pytest.mark.asyncio
async def test_workflow_run_event_stream_emits_error_when_later_poll_loses_run() -> None:
    class _LosingRunService(_FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.event_calls = 0

        async def list_run_events(self, **kwargs):
            self.event_calls += 1
            self.calls.append(("events", kwargs))
            if self.event_calls == 1:
                return _FakeRunningRun(), []
            raise LookupError("workflow_run_not_found")

    service = _LosingRunService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream?poll_ms=100&timeout_ms=2000"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert ": workflow_run_keepalive" in response.text
    assert "event: workflow_run_error" in response.text
    assert '"error": "workflow_run_not_found"' in response.text
    assert "event: workflow_run_snapshot" in response.text
    assert '"status": "failed"' in response.text
    assert '"terminal": true' in response.text
    assert '"waiting": false' in response.text
    assert service.event_calls == 2


@pytest.mark.asyncio
async def test_workflow_run_event_stream_emits_error_when_later_poll_fails() -> None:
    class _FailingPollService(_FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.event_calls = 0

        async def list_run_events(self, **kwargs):
            self.event_calls += 1
            self.calls.append(("events", kwargs))
            if self.event_calls == 1:
                return _FakeRunningRun(), []
            raise RuntimeError("redis unavailable")

    service = _FailingPollService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream?poll_ms=100&timeout_ms=2000"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: workflow_run_error" in response.text
    assert '"error": "workflow_run_event_stream_failed"' in response.text
    assert "redis unavailable" not in response.text
    assert "event: workflow_run_snapshot" in response.text
    assert '"status": "failed"' in response.text
    assert '"terminal": true' in response.text
    assert '"waiting": false' in response.text
    assert service.event_calls == 2


@pytest.mark.asyncio
async def test_workflow_run_event_stream_returns_503_when_initial_poll_fails() -> None:
    class _FailingInitialPollService(_FakeService):
        async def list_run_events(self, **kwargs):
            self.calls.append(("events", kwargs))
            raise RuntimeError("redis password=secret-token host=redis://internal")

    service = _FailingInitialPollService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream"
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "workflow_run_event_stream_failed",
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
    }
    assert "secret-token" not in response.text
    assert "redis://internal" not in response.text
    assert service.calls[0][0] == "events"


@pytest.mark.asyncio
async def test_workflow_run_event_stream_stops_when_run_is_paused() -> None:
    class _PausedService(_FakeService):
        async def list_run_events(self, **kwargs):
            self.calls.append(("events", kwargs))
            return _FakePausedRun(), []

    service = _PausedService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream?poll_ms=100&timeout_ms=2000"
        )

    assert response.status_code == 200
    assert '"status": "paused"' in response.text
    assert '"waiting": true' in response.text
    assert '"terminal": false' in response.text
    assert ": workflow_run_keepalive" not in response.text


@pytest.mark.asyncio
async def test_workflow_run_event_stream_marks_running_timeout_as_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RunningService(_FakeService):
        async def list_run_events(self, **kwargs):
            self.calls.append(("events", kwargs))
            return _FakeRunningRun(), []

    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(workflow_routes, "monotonic", lambda: next(ticks, 2.0))

    service = _RunningService()
    app = _enabled_app(service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/plugins/workflow/workflows/wf-1/runs/wfr-1/events/stream?poll_ms=100&timeout_ms=1000"
        )

    assert response.status_code == 200
    assert '"status": "running"' in response.text
    assert '"waiting": true' in response.text
    assert '"terminal": false' in response.text
