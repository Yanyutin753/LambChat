import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.plugins.workflow.models import (
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowVersion,
)

WORKFLOW_TOOL_NAMES = {
    "workflow_run",
    "workflow_list",
    "workflow_get_schema",
    "workflow_get_run",
    "workflow_resume",
}


def _patch_workflow_service_factory(
    monkeypatch: pytest.MonkeyPatch,
    workflow_tools,
    service,
) -> None:
    async def _create_service():
        return service

    monkeypatch.setattr(workflow_tools, "create_workflow_service", _create_service)


class _RuntimeWorkflowStorage:
    def __init__(self, *, internal_model: dict, compatibility_report: dict) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.definition = WorkflowDefinition(
            workflow_id="wf-editor-tool",
            owner_user_id="user-1",
            name="Editor Tool Workflow",
            status="published",
            latest_version_id="wfv-editor-tool",
            published_version_id="wfv-editor-tool",
            version_count=1,
            created_at=now,
            updated_at=now,
        )
        self.version = WorkflowVersion(
            version_id="wfv-editor-tool",
            workflow_id="wf-editor-tool",
            owner_user_id="user-1",
            version_number=1,
            source="workflow",
            source_format="json",
            source_payload={},
            internal_model=internal_model,
            compatibility_report=compatibility_report,
            created_by="user-1",
            created_at=now,
        )
        self.run: WorkflowRun | None = None
        self.events: list[WorkflowRunEvent] = []

    async def get_workflow(self, workflow_id: str, **kwargs):
        if workflow_id == self.definition.workflow_id and kwargs.get("owner_user_id") == "user-1":
            return self.definition
        return None

    async def get_version(self, version_id: str, **kwargs):
        if version_id == self.version.version_id and kwargs.get("owner_user_id") == "user-1":
            return self.version
        return None

    async def get_latest_version(self, workflow_id: str, **kwargs):
        if workflow_id == self.definition.workflow_id and kwargs.get("owner_user_id") == "user-1":
            return self.version
        return None

    async def create_run(self, **kwargs):
        self.run = WorkflowRun(
            run_id="wfr-editor-tool",
            workflow_id=kwargs["workflow_id"],
            version_id=kwargs["version_id"],
            owner_user_id=kwargs["owner_user_id"],
            status="running",
            mode=kwargs["mode"],
            input=kwargs["workflow_input"],
            output={},
            error=None,
            pause={},
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=None,
        )
        return self.run

    async def append_run_events(self, *, run: WorkflowRun, events: list[dict]):
        started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        persisted: list[WorkflowRunEvent] = []
        for index, event in enumerate(events, start=len(self.events) + 1):
            persisted.append(
                WorkflowRunEvent(
                    event_id=f"wfe-editor-tool-{index}",
                    run_id=run.run_id,
                    workflow_id=run.workflow_id,
                    version_id=run.version_id,
                    owner_user_id=run.owner_user_id,
                    sequence=index,
                    event_type=str(event.get("event_type") or "event"),
                    node_id=event.get("node_id"),
                    node_type=event.get("node_type"),
                    payload=event.get("payload") if isinstance(event.get("payload"), dict) else {},
                    created_at=started_at,
                )
            )
        self.events.extend(persisted)
        return persisted

    async def get_run(self, run_id: str, **kwargs):
        if self.run and self.run.run_id == run_id and kwargs.get("owner_user_id") == "user-1":
            return self.run
        return None

    async def finish_run(self, **kwargs):
        if self.run is None:
            raise RuntimeError("run_missing")
        self.run = self.run.model_copy(
            update={
                "status": kwargs["status"],
                "output": kwargs.get("output") or {},
                "error": kwargs.get("error"),
                "finished_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        )
        return self.run

    async def list_run_events(self, run_id: str, **kwargs):
        if run_id != "wfr-editor-tool" or kwargs.get("owner_user_id") != "user-1":
            return []
        skip = max(int(kwargs.get("skip", 0)), 0)
        limit = max(int(kwargs.get("limit", 200)), 1)
        return self.events[skip : skip + limit]


@pytest.mark.asyncio
async def test_workflow_tools_are_hidden_without_plugin_runtime(monkeypatch: pytest.MonkeyPatch):
    from src.infra.tool import internal_registry

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def workflow_mcp_access(_user_id):
        return ["user"], False

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", None)

    infos = await internal_registry.get_internal_tool_infos(
        user_id="user-1",
        user_roles=["user"],
        is_admin=False,
    )
    assert {info.name for info in infos}.isdisjoint(WORKFLOW_TOOL_NAMES)


@pytest.mark.asyncio
async def test_workflow_tools_are_hidden_when_plugin_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry
    from src.kernel.extensions import PluginRuntime, build_workflow_plugin_manifest

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def workflow_mcp_access(_user_id):
        return ["user"], False

    runtime = PluginRuntime([build_workflow_plugin_manifest()])

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    infos = await internal_registry.get_internal_tool_infos(
        user_id="user-1",
        user_roles=["user"],
        is_admin=False,
    )

    assert {info.name for info in infos}.isdisjoint(WORKFLOW_TOOL_NAMES)


@pytest.mark.asyncio
async def test_workflow_tools_are_exposed_when_plugin_enabled_and_role_can_use_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry
    from src.kernel.extensions import (
        WORKFLOW_PLUGIN_ID,
        PluginRuntime,
        build_workflow_plugin_manifest,
    )

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def workflow_mcp_access(_user_id):
        return ["user"], False

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    infos = await internal_registry.get_internal_tool_infos(
        user_id="user-1",
        user_roles=["user"],
        is_admin=False,
    )

    infos_by_name = {info.name: info for info in infos}
    assert WORKFLOW_TOOL_NAMES <= set(infos_by_name)
    assert infos_by_name["workflow_run"].parameters[0]["name"] == "workflow_id"
    assert infos_by_name["workflow_get_run"].parameters[0]["name"] == "workflow_id"
    assert infos_by_name["workflow_resume"].parameters[0]["name"] == "workflow_id"
    assert "async/stream" in infos_by_name["workflow_get_run"].description
    assert "debug events" in infos_by_name["workflow_get_run"].description
    assert "Resume a paused workflow run" in infos_by_name["workflow_resume"].description

    tools = await internal_registry.get_internal_tools_for_user(
        user_id="user-1",
        user_roles=["user"],
        is_admin=False,
    )
    tools_by_name = {tool.name: tool for tool in tools}

    assert WORKFLOW_TOOL_NAMES <= set(tools_by_name)
    assert await tools_by_name["workflow_list"]._arun(scope="published")


@pytest.mark.asyncio
async def test_workflow_run_requires_workflow_run_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import internal_registry
    from src.kernel.extensions import (
        WORKFLOW_PLUGIN_ID,
        PluginRuntime,
        build_workflow_plugin_manifest,
    )

    async def no_internal_tool_policies():
        return {}

    async def read_only_workflow_permissions(_user_roles):
        return {"workflow:read"}

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(
        internal_registry,
        "_resolve_permissions_for_roles",
        read_only_workflow_permissions,
    )
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)

    infos = await internal_registry.get_internal_tool_infos(
        user_id="user-1",
        user_roles=["user"],
        is_admin=False,
    )

    names = {info.name for info in infos}
    assert "workflow_run" not in names
    assert "workflow_resume" not in names
    assert {"workflow_list", "workflow_get_schema", "workflow_get_run"} <= names


@pytest.mark.asyncio
async def test_fast_agent_context_includes_workflow_tools_when_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.fast_agent.context import FastAgentContext
    from src.infra.tool import internal_registry
    from src.kernel.extensions import (
        WORKFLOW_PLUGIN_ID,
        PluginRuntime,
        build_workflow_plugin_manifest,
    )

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def workflow_mcp_access(_user_id):
        return ["user"], False

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)
    monkeypatch.setattr("src.infra.mcp.quota.resolve_user_mcp_access", workflow_mcp_access)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_MEMORY", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_SANDBOX", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_SKILLS", False)

    context = FastAgentContext(user_id="user-1")
    await context.setup()

    tool_names = {tool.name for tool in context.tools}
    assert WORKFLOW_TOOL_NAMES <= tool_names


@pytest.mark.asyncio
async def test_team_agent_context_includes_workflow_tools_when_plugin_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.team_agent.context import TeamAgentContext
    from src.infra.tool import internal_registry
    from src.kernel.extensions import (
        WORKFLOW_PLUGIN_ID,
        PluginRuntime,
        build_workflow_plugin_manifest,
    )

    async def no_internal_tool_policies():
        return {}

    async def workflow_permissions(_user_roles):
        return {"workflow:read", "workflow:run"}

    async def workflow_mcp_access(_user_id):
        return ["user"], False

    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin(WORKFLOW_PLUGIN_ID)

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_internal_tool_policies)
    monkeypatch.setattr(internal_registry, "_resolve_permissions_for_roles", workflow_permissions)
    monkeypatch.setattr(internal_registry, "_plugin_runtime", runtime)
    monkeypatch.setattr("src.infra.mcp.quota.resolve_user_mcp_access", workflow_mcp_access)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_MEMORY", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_SANDBOX", False)
    monkeypatch.setattr("src.agents.fast_agent.context.settings.ENABLE_SKILLS", False)

    context = TeamAgentContext(user_id="user-1")
    await context.setup()

    tool_names = {tool.name for tool in context.tools}
    assert WORKFLOW_TOOL_NAMES <= tool_names
    assert {"workflow_run", "workflow_get_schema", "workflow_get_run", "workflow_resume"} <= tool_names


@pytest.mark.asyncio
async def test_workflow_run_tool_returns_debug_events(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {"answer": "ok"}
        error = None

    class _Event:
        def __init__(self, sequence: int, event_type: str, node_id: str | None, node_type: str | None, payload: dict) -> None:
            self.sequence = sequence
            self.event_type = event_type
            self.node_id = node_id
            self.node_type = node_type
            self.payload = payload

        def model_dump(self, **kwargs):
            return {
                "event_id": f"wfe-{self.sequence}",
                "run_id": "wfr-1",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "sequence": self.sequence,
                "event_type": self.event_type,
                "node_id": self.node_id,
                "node_type": self.node_type,
                "payload": self.payload,
                "created_at": "2026-01-01T00:00:00Z",
            }

    class _Service:
        async def run_workflow(self, **kwargs):
            return _Run(), [
                _Event(
                    1,
                    "run_started",
                    None,
                    None,
                    {"status": "running", "mode": "sync", "input_keys": ["message"]},
                ),
                _Event(2, "node_started", "start", "start", {"title": "Start"}),
            ]

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "ok"}
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
    assert payload["next_action"] == {
        "type": "use_output",
        "field": "output",
        "reason": "workflow_run_succeeded",
    }
    assert payload["events"][0]["event_type"] == "run_started"
    assert payload["events"][0]["payload"] == {"status": "running", "mode": "sync", "input_keys": ["message"]}
    assert payload["events"][1]["event_type"] == "node_started"
    assert payload["events"][1]["node_id"] == "start"


@pytest.mark.asyncio
async def test_workflow_run_tool_guides_human_approval_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-approval"
        version_id = "wfv-approval"
        run_id = "wfr-approval"
        mode = "async"
        status = "paused"
        output = {}
        error = "workflow_human_approval_paused:approval"
        pause = {
            "kind": "human_approval",
            "pending_approval": {
                "node_id": "approval",
                "title": "Review answer",
                "instructions": "Approve generated answer",
                "assignee": "reviewer",
                "output_key": "approval",
            },
        }
        started_at = "2026-01-01T00:00:00Z"
        finished_at = None

    class _Service:
        async def run_workflow(self, **kwargs):
            return _Run(), []

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-approval",
        input={"message": "please check"},
        mode="async",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "paused"
    assert payload["pause"]["kind"] == "human_approval"
    assert payload["next_action"] == {
        "type": "await_human_approval",
        "tool": "workflow_get_run",
        "reason": "workflow_run_paused_human_approval",
        "field": "pause.pending_approval",
        "approval": {
            "kind": "human_approval",
            "node_id": "approval",
            "title": "Review answer",
            "assignee": "reviewer",
            "output_key": "approval",
        },
        "pending": {
            "method": "GET",
            "path": "/api/plugins/workflow/approvals/pending",
        },
        "resume": {
            "tool": "workflow_resume",
            "method": "POST",
            "path": "/api/plugins/workflow/workflows/wf-approval/runs/wfr-approval/resume",
            "body": {"approved": True, "comment": "", "values": {}},
            "arguments": {
                "workflow_id": "wf-approval",
                "run_id": "wfr-approval",
                "approved": True,
                "comment": "",
                "values": {},
            },
        },
    }


@pytest.mark.asyncio
async def test_workflow_run_tool_executes_editor_saved_workflow_through_real_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools
    from src.plugins.workflow.parser import parse_workflow
    from src.plugins.workflow.service import WorkflowPluginService

    llm_requests: list[dict] = []

    async def invoke_llm(request: dict) -> dict:
        llm_requests.append(request)
        return {"text": "Tool workflow answer", "model": request.get("model"), "usage": {"total_tokens": 4}}

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
    parsed = parse_workflow(source_payload, name="Editor Tool Workflow")
    storage = _RuntimeWorkflowStorage(
        internal_model=parsed.internal_model,
        compatibility_report=parsed.report,
    )
    service = WorkflowPluginService(storage=storage, llm_invoker=invoke_llm)
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-editor-tool",
        input={"message": "hello from tool"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert llm_requests == [
        {
            "prompt": "Answer hello from tool",
            "messages": [],
            "model_id": None,
            "model": "gpt-4o-mini",
        }
    ]
    assert payload["status"] == "succeeded"
    assert payload["workflow_id"] == "wf-editor-tool"
    assert payload["version_id"] == "wfv-editor-tool"
    assert payload["output"] == {"answer": "Tool workflow answer"}
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-editor-tool",
        "version_id": "wfv-editor-tool",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert payload["next_action"] == {
        "type": "use_output",
        "field": "output",
        "reason": "workflow_run_succeeded",
    }
    assert payload["io_contract"]["input_schema"]["properties"]["message"]["type"] == "string"
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


@pytest.mark.asyncio
async def test_workflow_run_tool_passes_explicit_version_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-selected"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {"answer": "selected"}
        error = None

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def run_workflow(self, **kwargs):
            self.calls.append(kwargs)
            return _Run(), []

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-selected",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls[0]["version_id"] == "wfv-selected"
    assert service.calls[0]["workflow_input"] == {"message": "hi"}
    assert payload["version_id"] == "wfv-selected"
    assert payload["output"] == {"answer": "selected"}


@pytest.mark.asyncio
async def test_workflow_run_tool_returns_version_scoped_io_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-selected"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {"answer": "selected"}
        error = None

    class _Service:
        def __init__(self) -> None:
            self.contract_calls: list[dict] = []

        async def run_workflow(self, **kwargs):
            return _Run(), []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            self.contract_calls.append({"workflow_id": workflow_id, **kwargs})
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-selected",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
                "input_schema_source": "declared",
                "output_schema_source": "declared",
            }

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-selected",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.contract_calls == [
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-selected"}
    ]
    assert payload["io_contract"]["input_schema"]["properties"]["message"]["type"] == "string"
    assert payload["io_contract"]["output_schema"]["properties"]["answer"]["type"] == "string"
    assert payload["output_contract"] == {
        "valid": True,
        "schema_field": "output_schema",
        "declared_fields": ["answer"],
        "declared_field_paths": ["answer"],
        "required_fields": [],
        "required_field_paths": [],
        "missing_required": [],
        "type_mismatches": [],
        "extra_fields": [],
    }
    assert payload["interface"]["entry"]["schema_field"] == "input_schema"
    assert payload["interface"]["exit"]["schema_field"] == "output_schema"


@pytest.mark.asyncio
async def test_workflow_run_tool_marks_output_contract_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-selected"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {"answer": 123, "extra": True}
        error = None

    class _Service:
        async def run_workflow(self, **kwargs):
            return _Run(), []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-selected",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["answer", "summary"],
                    "additionalProperties": True,
                },
                "input_schema_source": "declared",
                "output_schema_source": "declared",
            }

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-selected",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "succeeded"
    assert payload["output_contract"] == {
        "valid": False,
        "schema_field": "output_schema",
        "declared_fields": ["answer", "summary"],
        "declared_field_paths": ["answer", "summary"],
        "required_fields": ["answer", "summary"],
        "required_field_paths": ["answer", "summary"],
        "missing_required": ["summary"],
        "type_mismatches": [
            {"field": "answer", "expected": "string", "actual": "int"},
        ],
        "extra_fields": ["extra"],
    }


@pytest.mark.asyncio
async def test_workflow_run_tool_validates_nested_output_contract_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-selected"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {
            "tone": "casual",
            "items": [{"name": 123}],
            "profile": {},
        }
        error = None

    class _Service:
        async def run_workflow(self, **kwargs):
            return _Run(), []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-selected",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "tone": {"type": "string", "enum": ["warm", "formal"]},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"],
                            },
                        },
                        "profile": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    },
                    "required": ["tone", "items", "profile"],
                },
                "input_schema_source": "declared",
                "output_schema_source": "declared",
            }

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-selected",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["output_contract"]["valid"] is False
    assert payload["output_contract"]["missing_required"] == []
    assert payload["output_contract"]["declared_field_paths"] == [
        "items[].name",
        "profile.name",
        "tone",
    ]
    assert payload["output_contract"]["required_field_paths"] == [
        "items[].name",
        "profile.name",
        "tone",
    ]
    assert payload["output_contract"]["type_mismatches"] == [
        {
            "field": "tone",
            "expected": {"enum": ["warm", "formal"]},
            "actual": "casual",
        },
        {"field": "items[0].name", "expected": "string", "actual": "int"},
        {"field": "profile.name", "expected": "required", "actual": "missing"},
    ]


@pytest.mark.asyncio
async def test_workflow_run_tool_reports_entry_contract_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def run_workflow(self, **kwargs):
            raise ValueError("workflow_input_required_missing:name")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        input={},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["version_id"] is None
    assert payload["run_id"] is None
    assert payload["mode"] == "sync"
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "workflow_input_required_missing:name"
    assert payload["interface"] == {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": "wf-1",
            "version_id": None,
            "schema_tool": "workflow_get_schema",
            "schema_field": "input_schema",
        },
        "exit": {
            "type": "workflow.output",
            "field": "output",
            "schema_tool": "workflow_get_schema",
            "schema_field": "output_schema",
        },
        "debug": {
            "tool": "workflow_get_run",
            "workflow_id": "wf-1",
            "run_id": None,
            "events_field": "events",
        },
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
    }


@pytest.mark.asyncio
async def test_workflow_run_tool_resolves_runtime_user_roles_for_nested_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "sync"
        status = "succeeded"
        output = {"answer": "ok"}
        error = None

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def run_workflow(self, **kwargs):
            self.calls.append(kwargs)
            return _Run(), []

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )

    async def workflow_access(user_id: str):
        assert user_id == "user-1"
        return ["user", "workflow-operator"], False

    monkeypatch.setattr("src.infra.mcp.quota.resolve_user_mcp_access", workflow_access)
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "succeeded"
    user = service.calls[0]["user"]
    assert user.sub == "user-1"
    assert user.roles == ["user", "workflow-operator"]
    assert user.permissions == ["workflow:read", "workflow:run"]


@pytest.mark.asyncio
async def test_workflow_run_tool_accepts_stream_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "stream"
        status = "running"
        output = {}
        error = None

    class _Event:
        def model_dump(self, **kwargs):
            return {
                "event_id": "wfe-1",
                "run_id": "wfr-1",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "sequence": 1,
                "event_type": "run_queued",
                "node_id": None,
                "node_type": None,
                "payload": {"mode": "stream"},
                "created_at": "2026-01-01T00:00:00Z",
            }

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def run_workflow(self, **kwargs):
            self.calls.append(kwargs)
            return _Run(), [_Event()]

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        input={"message": "hi"},
        mode="stream",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls[0]["mode"] == "stream"
    assert payload["mode"] == "stream"
    assert payload["status"] == "running"
    assert payload["events"][0]["event_type"] == "run_queued"
    assert payload["events"][0]["payload"]["mode"] == "stream"


@pytest.mark.asyncio
async def test_workflow_run_tool_without_user_context_returns_workflow_outlet() -> None:
    from src.plugins.workflow import tools as workflow_tools

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-1",
        input={"message": "hi"},
        mode="stream",
        runtime=None,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["version_id"] == "wfv-1"
    assert payload["run_id"] is None
    assert payload["mode"] == "stream"
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "No user context available"
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
        "run_id": None,
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
    }


@pytest.mark.asyncio
async def test_workflow_run_tool_returns_unexpected_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def run_workflow(self, **kwargs):
            raise RuntimeError("database unavailable")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_run.coroutine(
        workflow_id="wf-1",
        version_id="wfv-1",
        input={"message": "hi"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["version_id"] == "wfv-1"
    assert payload["run_id"] is None
    assert payload["mode"] == "sync"
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "workflow_tool_unexpected_error:database unavailable"
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["exit"]["field"] == "output"
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": None,
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
    }


@pytest.mark.asyncio
async def test_workflow_list_tool_returns_unexpected_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def list_workflows(self, **kwargs):
            raise RuntimeError("storage unavailable")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_list.coroutine(scope="published", runtime=runtime)

    payload = json.loads(raw)
    assert payload == {
        "plugin_id": "workflow",
        "scope": "published",
        "status": "failed",
        "workflows": [],
        "error": "workflow_tool_unexpected_error:storage unavailable",
    }


@pytest.mark.asyncio
async def test_workflow_list_tool_returns_selection_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def list_workflows(self, **kwargs):
            return SimpleNamespace(
                workflows=[
                    _workflow_definition(
                        workflow_id="wf-published",
                        status="published",
                        latest_version_id="wfv-latest",
                        published_version_id="wfv-published",
                    ),
                    _workflow_definition(
                        workflow_id="wf-draft",
                        status="draft",
                        latest_version_id="wfv-draft",
                        published_version_id=None,
                    ),
                ],
                total=2,
            )

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_list.coroutine(scope="published", runtime=runtime)

    payload = json.loads(raw)
    assert [workflow["workflow_id"] for workflow in payload["workflows"]] == ["wf-published"]
    workflow = payload["workflows"][0]
    assert workflow["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-published",
        "version_id": "wfv-published",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert workflow["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert workflow["interface"]["schema"] == {
        "tool": "workflow_get_schema",
        "workflow_id": "wf-published",
        "version_id": "wfv-published",
        "input_schema_field": "input_schema",
        "output_schema_field": "output_schema",
    }
    assert workflow["interface"]["run"] == {
        "tool": "workflow_run",
        "workflow_id": "wf-published",
        "version_id": "wfv-published",
        "input_argument": "input",
        "output_field": "output",
    }
    assert workflow["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-published",
        "run_id_field": "run_id",
    }


@pytest.mark.asyncio
async def test_workflow_get_run_tool_returns_run_snapshot_and_debug_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "async"
        status = "running"
        output = {"partial": True}
        error = None
        pause = {}
        started_at = "2026-01-01T00:00:00Z"
        finished_at = None

    class _Event:
        def model_dump(self, **kwargs):
            return {
                "event_id": "wfe-2",
                "run_id": "wfr-1",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "sequence": 2,
                "event_type": "node_started",
                "node_id": "answer",
                "node_type": "answer",
                "payload": {"title": "Answer"},
                "created_at": "2026-01-01T00:00:01Z",
            }

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def list_run_events(self, **kwargs):
            self.calls.append(kwargs)
            return _Run(), [_Event()]

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="wfr-1",
        skip=1,
        limit=10,
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls == [
        {
            "workflow_id": "wf-1",
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "skip": 1,
            "limit": 10,
        }
    ]
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["run_id"] == "wfr-1"
    assert payload["status"] == "running"
    assert payload["mode"] == "async"
    assert payload["skip"] == 1
    assert payload["limit"] == 10
    assert payload["interface"]["entry"]["schema_tool"] == "workflow_get_schema"
    assert payload["interface"]["entry"]["schema_field"] == "input_schema"
    assert payload["interface"]["exit"]["schema_field"] == "output_schema"
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "inspect_run",
        "tool": "workflow_get_run",
        "reason": "workflow_run_running",
    }
    assert payload["events"][0]["event_type"] == "node_started"
    assert payload["events"][0]["node_id"] == "answer"


@pytest.mark.asyncio
async def test_workflow_get_run_tool_guides_human_approval_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-approval"
        version_id = "wfv-approval"
        run_id = "wfr-approval"
        mode = "async"
        status = "paused"
        output = {}
        error = "workflow_human_approval_paused:approval"
        pause = {
            "kind": "human_approval",
            "pending_approval": {
                "node_id": "approval",
                "title": "Review answer",
                "assignee": "reviewer",
                "output_key": "approval",
            },
        }
        started_at = "2026-01-01T00:00:00Z"
        finished_at = None

    class _Event:
        def model_dump(self, **kwargs):
            return {
                "event_id": "wfe-approval-1",
                "run_id": "wfr-approval",
                "workflow_id": "wf-approval",
                "version_id": "wfv-approval",
                "sequence": 1,
                "event_type": "human_approval_required",
                "node_id": "approval",
                "node_type": "human_approval",
                "payload": {"node_id": "approval", "title": "Review answer"},
                "created_at": "2026-01-01T00:00:01Z",
            }

    class _Service:
        async def list_run_events(self, **kwargs):
            return _Run(), [_Event()]

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-approval",
        run_id="wfr-approval",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "paused"
    assert payload["events"][0]["event_type"] == "human_approval_required"
    assert payload["next_action"]["type"] == "await_human_approval"
    assert payload["next_action"]["reason"] == "workflow_run_paused_human_approval"
    assert payload["next_action"]["field"] == "pause.pending_approval"
    assert payload["next_action"]["resume"]["tool"] == "workflow_resume"
    assert (
        payload["next_action"]["resume"]["path"]
        == "/api/plugins/workflow/workflows/wf-approval/runs/wfr-approval/resume"
    )


@pytest.mark.asyncio
async def test_workflow_resume_tool_resumes_human_approval_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-approval"
        version_id = "wfv-approval"
        run_id = "wfr-approval"
        mode = "async"
        status = "succeeded"
        output = {"answer": "Approved ship it"}
        error = None
        pause = {}
        started_at = "2026-01-01T00:00:00Z"
        finished_at = "2026-01-01T00:00:02Z"

    class _Event:
        def model_dump(self, **kwargs):
            return {
                "event_id": "wfe-approval-2",
                "run_id": "wfr-approval",
                "workflow_id": "wf-approval",
                "version_id": "wfv-approval",
                "sequence": 2,
                "event_type": "human_approval_resumed",
                "node_id": "approval",
                "node_type": "human_approval",
                "payload": {"approved": True, "approval": {"comment": "ship it"}},
                "created_at": "2026-01-01T00:00:02Z",
            }

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def resume_run(self, **kwargs):
            self.calls.append(kwargs)
            return _Run(), [_Event()]

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_resume.coroutine(
        workflow_id="wf-approval",
        run_id="wfr-approval",
        approved=True,
        comment="ship it",
        values={"priority": "high"},
        response={"reviewer": "ops"},
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls[0]["workflow_id"] == "wf-approval"
    assert service.calls[0]["run_id"] == "wfr-approval"
    assert service.calls[0]["approval_response"] == {
        "approved": True,
        "comment": "ship it",
        "values": {"priority": "high"},
        "response": {"reviewer": "ops"},
    }
    assert service.calls[0]["user"].sub == "user-1"
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "Approved ship it"}
    assert payload["events"][0]["event_type"] == "human_approval_resumed"
    assert payload["interface"]["entry"]["tool"] == "workflow_run"
    assert payload["interface"]["exit"]["field"] == "output"
    assert payload["next_action"] == {
        "type": "use_output",
        "field": "output",
        "reason": "workflow_run_succeeded",
    }


@pytest.mark.asyncio
async def test_workflow_resume_tool_returns_resume_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def resume_run(self, **kwargs):
            raise ValueError("workflow_run_not_paused:succeeded")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_resume.coroutine(
        workflow_id="wf-approval",
        run_id="wfr-approval",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["status"] == "failed"
    assert payload["error"] == "workflow_run_not_paused:succeeded"
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
        "tool": "workflow_get_run",
    }


@pytest.mark.asyncio
async def test_workflow_get_run_tool_returns_version_scoped_io_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "async"
        status = "succeeded"
        output = {"answer": "done"}
        error = None
        pause = {}
        started_at = "2026-01-01T00:00:00Z"
        finished_at = "2026-01-01T00:00:02Z"

    class _Service:
        def __init__(self) -> None:
            self.contract_calls: list[dict] = []

        async def list_run_events(self, **kwargs):
            return _Run(), []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            self.contract_calls.append({"workflow_id": workflow_id, **kwargs})
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-1",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string", "description": "Answer text"}},
                },
                "input_schema_source": "declared",
                "output_schema_source": "declared",
            }

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="wfr-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.contract_calls == [
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-1"}
    ]
    assert payload["io_contract"]["output_schema"]["properties"]["answer"]["description"] == "Answer text"
    assert payload["output_contract"] == {
        "valid": True,
        "schema_field": "output_schema",
        "declared_fields": ["answer"],
        "declared_field_paths": ["answer"],
        "required_fields": [],
        "required_field_paths": [],
        "missing_required": [],
        "type_mismatches": [],
        "extra_fields": [],
    }
    assert payload["output"] == {"answer": "done"}
    assert payload["next_action"]["type"] == "use_output"


@pytest.mark.asyncio
async def test_workflow_get_run_tool_marks_truncated_event_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Run:
        workflow_id = "wf-1"
        version_id = "wfv-1"
        run_id = "wfr-1"
        mode = "async"
        status = "running"
        output = {}
        error = None
        pause = {}
        started_at = "2026-01-01T00:00:00Z"
        finished_at = None

    class _Event:
        def model_dump(self, **kwargs):
            return {
                "event_id": "wfe-3",
                "run_id": "wfr-1",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "sequence": 3,
                "event_type": "node_finished",
                "node_id": "llm",
                "node_type": "llm",
                "payload": {
                    "truncated": True,
                    "reason": "workflow_event_payload_too_large",
                    "original_bytes": 1049600,
                    "max_bytes": 1048576,
                    "keys": ["prompt", "completion", 123],
                },
                "created_at": "2026-01-01T00:00:02Z",
            }

    class _Service:
        async def list_run_events(self, **kwargs):
            return _Run(), [_Event()]

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="wfr-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    event = payload["events"][0]
    assert event["payload"] == {
        "truncated": True,
        "reason": "workflow_event_payload_too_large",
        "original_bytes": 1049600,
        "max_bytes": 1048576,
        "keys": ["prompt", "completion", 123],
    }
    assert event["payload_truncation"] == {
        "reason": "workflow_event_payload_too_large",
        "original_bytes": 1049600,
        "max_bytes": 1048576,
        "keys": ["prompt", "completion"],
    }


@pytest.mark.asyncio
async def test_workflow_get_run_tool_without_user_context_returns_workflow_outlet() -> None:
    from src.plugins.workflow import tools as workflow_tools

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="wfr-1",
        runtime=None,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["run_id"] == "wfr-1"
    assert payload["mode"] is None
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "No user context available"
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": None,
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
        "tool": "workflow_get_run",
    }


@pytest.mark.asyncio
async def test_workflow_get_run_tool_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def list_run_events(self, **kwargs):
            raise LookupError("workflow_run_not_found")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="missing",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["run_id"] == "missing"
    assert payload["mode"] is None
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "workflow_run_not_found"
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "missing",
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
        "tool": "workflow_get_run",
    }


@pytest.mark.asyncio
async def test_workflow_get_run_tool_returns_unexpected_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def list_run_events(self, **kwargs):
            raise RuntimeError("events unavailable")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_run.coroutine(
        workflow_id="wf-1",
        run_id="wfr-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["plugin_id"] == "workflow"
    assert payload["workflow_id"] == "wf-1"
    assert payload["run_id"] == "wfr-1"
    assert payload["mode"] is None
    assert payload["status"] == "failed"
    assert payload["output"] == {}
    assert payload["error"] == "workflow_tool_unexpected_error:events unavailable"
    assert payload["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "wfr-1",
        "events_field": "events",
    }
    assert payload["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
        "tool": "workflow_get_run",
    }


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_empty_schema_without_user_context() -> None:
    from src.plugins.workflow import tools as workflow_tools

    raw = await workflow_tools.workflow_get_schema.coroutine(workflow_id="wf-1", runtime=None)

    payload = json.loads(raw)
    assert payload == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "input_schema": {},
        "output_schema": {},
        "interface": {
            "entry": {
                "type": "workflow.input",
                "tool": "workflow_run",
                "argument": "input",
                "workflow_id": "wf-1",
                "version_id": None,
                "schema_tool": "workflow_get_schema",
                "schema_field": "input_schema",
            },
            "exit": {
                "type": "workflow.output",
                "field": "output",
                "schema_tool": "workflow_get_schema",
                "schema_field": "output_schema",
            },
            "schema": {
                "tool": "workflow_get_schema",
                "workflow_id": "wf-1",
                "version_id": None,
                "input_schema_field": "input_schema",
                "output_schema_field": "output_schema",
            },
            "run": {
                "tool": "workflow_run",
                "workflow_id": "wf-1",
                "version_id": None,
                "input_argument": "input",
                "output_field": "output",
            },
            "debug": {
                "tool": "workflow_get_run",
                "workflow_id": "wf-1",
                "run_id_field": "run_id",
            },
        },
    }


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            raise LookupError("workflow_not_found")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="missing",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload == {
        "plugin_id": "workflow",
        "workflow_id": "missing",
        "error": "workflow_not_found",
        "interface": {
            "entry": {
                "type": "workflow.input",
                "tool": "workflow_run",
                "argument": "input",
                "workflow_id": "missing",
                "version_id": None,
                "schema_tool": "workflow_get_schema",
                "schema_field": "input_schema",
            },
            "exit": {
                "type": "workflow.output",
                "field": "output",
                "schema_tool": "workflow_get_schema",
                "schema_field": "output_schema",
            },
            "schema": {
                "tool": "workflow_get_schema",
                "workflow_id": "missing",
                "version_id": None,
                "input_schema_field": "input_schema",
                "output_schema_field": "output_schema",
            },
            "run": {
                "tool": "workflow_run",
                "workflow_id": "missing",
                "version_id": None,
                "input_argument": "input",
                "output_field": "output",
            },
            "debug": {
                "tool": "workflow_get_run",
                "workflow_id": "missing",
                "run_id_field": "run_id",
            },
        },
    }


@pytest.mark.asyncio
async def test_workflow_get_schema_reports_missing_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            raise LookupError("workflow_version_not_found")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["error"] == "workflow_version_not_found"


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_unexpected_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            raise RuntimeError("schema backend unavailable")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        version_id="wfv-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload | {"interface": payload.get("interface")} == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "status": "failed",
        "input_schema": {},
        "output_schema": {},
        "error": "workflow_tool_unexpected_error:schema backend unavailable",
        "interface": payload["interface"],
    }
    assert payload["interface"]["entry"]["tool"] == "workflow_run"
    assert payload["interface"]["entry"]["argument"] == "input"
    assert payload["interface"]["entry"]["schema_field"] == "input_schema"
    assert payload["interface"]["exit"]["field"] == "output"
    assert payload["interface"]["schema"]["tool"] == "workflow_get_schema"


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_unexpected_factory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    async def unavailable_service():
        raise RuntimeError("settings unavailable")

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    monkeypatch.setattr(workflow_tools, "create_workflow_service", unavailable_service)

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        version_id="wfv-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload | {"interface": payload.get("interface")} == {
        "plugin_id": "workflow",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "status": "failed",
        "input_schema": {},
        "output_schema": {},
        "error": "workflow_tool_unexpected_error:settings unavailable",
        "interface": payload["interface"],
    }
    assert payload["interface"]["entry"]["tool"] == "workflow_run"
    assert payload["interface"]["entry"]["argument"] == "input"
    assert payload["interface"]["entry"]["schema_field"] == "input_schema"
    assert payload["interface"]["exit"]["field"] == "output"
    assert payload["interface"]["schema"]["tool"] == "workflow_get_schema"


@pytest.mark.asyncio
async def test_workflow_get_schema_passes_explicit_version_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            self.calls.append({"workflow_id": workflow_id, **kwargs})
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-selected",
                "version_number": 5,
                "input_schema": {
                    "type": "object",
                    "properties": {"selected": {"type": "string"}},
                    "additionalProperties": True,
                },
                "status": "draft",
                "schema_source": "declared",
                "inferred_fields": [],
            }

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        version_id="wfv-selected",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls[0]["version_id"] == "wfv-selected"
    assert service.calls[0]["owner_user_id"] == "user-1"
    assert payload["version_id"] == "wfv-selected"
    assert set(payload["input_schema"]["properties"]) == {"selected"}


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_output_contract_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            self.calls.append({"workflow_id": workflow_id, **kwargs})
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-contract",
                "version_number": 4,
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "additionalProperties": True,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "additionalProperties": True,
                },
                "status": "published",
                "input_schema_source": "declared",
                "output_schema_source": "inferred",
                "inferred_input_fields": [],
                "inferred_output_fields": ["answer"],
            }

    service = _Service()
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, service)

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        version_id="wfv-contract",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert service.calls == [
        {"workflow_id": "wf-1", "owner_user_id": "user-1", "version_id": "wfv-contract"}
    ]
    assert payload["input_schema"]["properties"]["message"]["type"] == "string"
    assert payload["output_schema"]["properties"]["answer"]["type"] == "string"
    assert payload["output_schema_source"] == "inferred"
    assert payload["interface"]["entry"] == {
        "type": "workflow.input",
        "tool": "workflow_run",
        "argument": "input",
        "workflow_id": "wf-1",
        "version_id": "wfv-contract",
        "schema_tool": "workflow_get_schema",
        "schema_field": "input_schema",
    }
    assert payload["interface"]["exit"] == {
        "type": "workflow.output",
        "field": "output",
        "schema_tool": "workflow_get_schema",
        "schema_field": "output_schema",
    }
    assert payload["interface"]["schema"] == {
        "tool": "workflow_get_schema",
        "workflow_id": "wf-1",
        "version_id": "wfv-contract",
        "input_schema_field": "input_schema",
        "output_schema_field": "output_schema",
    }
    assert payload["interface"]["run"] == {
        "tool": "workflow_run",
        "workflow_id": "wf-1",
        "version_id": "wfv-contract",
        "input_argument": "input",
        "output_field": "output",
    }


@pytest.mark.asyncio
async def test_workflow_get_schema_returns_nested_contract_hints_and_input_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_io_contract(self, workflow_id: str, **kwargs):
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-contract",
                "version_number": 4,
                "input_schema": {
                    "type": "object",
                    "required": ["profile", "items", "tone"],
                    "properties": {
                        "profile": {
                            "type": "object",
                            "description": "User profile",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "age": {"type": "integer"},
                            },
                        },
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["score"],
                                "properties": {"score": {"type": "integer"}},
                            },
                        },
                        "tone": {
                            "type": "string",
                            "enum": ["warm", "formal"],
                            "default": "warm",
                        },
                    },
                },
                "output_schema": {
                    "type": "object",
                    "required": ["answer"],
                    "properties": {
                        "answer": {"type": "string"},
                        "metrics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"score": {"type": "number"}},
                            },
                        },
                    },
                },
                "status": "published",
                "input_schema_source": "declared",
                "output_schema_source": "declared",
            }

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        version_id="wfv-contract",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["input_example"] == {
        "profile": {"name": "LambChat"},
        "items": [{"score": 1}],
        "tone": "warm",
    }
    input_fields = {item["field"]: item for item in payload["input_fields"]}
    assert input_fields["profile"] == {
        "field": "profile",
        "type": "object",
        "required": True,
        "description": "User profile",
    }
    assert input_fields["profile.name"] == {
        "field": "profile.name",
        "type": "string",
        "required": True,
    }
    assert input_fields["items[].score"] == {
        "field": "items[].score",
        "type": "integer",
        "required": True,
    }
    assert input_fields["tone"] == {
        "field": "tone",
        "type": "string",
        "required": True,
        "enum": ["warm", "formal"],
    }
    output_fields = {item["field"]: item for item in payload["output_fields"]}
    assert output_fields["answer"] == {
        "field": "answer",
        "type": "string",
        "required": True,
    }
    assert output_fields["metrics[].score"] == {
        "field": "metrics[].score",
        "type": "number",
        "required": False,
    }


@pytest.mark.asyncio
async def test_workflow_get_schema_infers_declared_and_template_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-published",
                "version_number": 3,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Display name",
                            "default": "Visitor",
                            "x-lambchat-source": "declared",
                        },
                        "tone": {
                            "type": "string",
                            "enum": ["warm", "formal"],
                            "default": "warm",
                            "x-lambchat-source": "declared",
                        },
                        "message": {"type": "string", "x-lambchat-source": "inferred"},
                    },
                    "required": ["name"],
                    "additionalProperties": True,
                },
                "status": "published",
                "schema_source": "declared_and_inferred",
                "inferred_fields": ["message"],
            }

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    schema = payload["input_schema"]
    assert payload["version_id"] == "wfv-published"
    assert payload["version_number"] == 3
    assert payload["schema_source"] == "declared_and_inferred"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True
    assert schema["required"] == ["name"]
    assert schema["properties"]["name"]["description"] == "Display name"
    assert schema["properties"]["name"]["default"] == "Visitor"
    assert schema["properties"]["tone"]["enum"] == ["warm", "formal"]
    assert schema["properties"]["tone"]["default"] == "warm"
    assert schema["properties"]["message"]["x-lambchat-source"] == "inferred"


@pytest.mark.asyncio
async def test_workflow_get_schema_falls_back_to_latest_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.plugins.workflow import tools as workflow_tools

    class _Service:
        async def get_workflow_input_schema(self, workflow_id: str, **kwargs):
            return {
                "plugin_id": "workflow",
                "workflow_id": workflow_id,
                "version_id": "wfv-latest",
                "version_number": 3,
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string", "x-lambchat-source": "inferred"}},
                    "additionalProperties": True,
                },
                "status": "draft",
                "schema_source": "inferred",
                "inferred_fields": ["message"],
            }

    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}}
    )
    _patch_workflow_service_factory(monkeypatch, workflow_tools, _Service())

    raw = await workflow_tools.workflow_get_schema.coroutine(
        workflow_id="wf-1",
        runtime=runtime,
    )

    payload = json.loads(raw)
    assert payload["version_id"] == "wfv-latest"
    assert payload["schema_source"] == "inferred"
    assert set(payload["input_schema"]["properties"]) == {"message"}


def _workflow_definition(
    *,
    workflow_id: str,
    status: str = "draft",
    latest_version_id: str | None = "wfv-latest",
    published_version_id: str | None = None,
) -> WorkflowDefinition:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return WorkflowDefinition(
        workflow_id=workflow_id,
        owner_user_id="user-1",
        name="Workflow",
        status=status,
        latest_version_id=latest_version_id,
        published_version_id=published_version_id,
        version_count=1,
        created_at=now,
        updated_at=now,
    )


def _workflow_version(
    *,
    version_id: str = "wfv-published",
    internal_model: dict | None = None,
) -> WorkflowVersion:
    return WorkflowVersion(
        version_id=version_id,
        workflow_id="wf-1",
        owner_user_id="user-1",
        version_number=3,
        source="workflow",
        source_format="json",
        source_payload={},
        internal_model=internal_model or {},
        compatibility_report={},
        created_by="user-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
