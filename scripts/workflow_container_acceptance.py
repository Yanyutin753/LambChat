"""Live acceptance checks for the Workflow plugin in a deployed LambChat.

This script is intentionally dependency-free so it can run from a workstation,
CI runner, or inside a remote container after Docker/SSH deployment.

Typical usage:

    python scripts/workflow_container_acceptance.py \
        --base-url http://127.0.0.1:8000 \
        --token "$LAMBCHAT_TOKEN"

For final deployment acceptance, use --profile full with --agent-team-id and
an output file. The profile enables the optional Chat, Agent Team, scheduled
task, internal tool, human approval, versioned run, LLM, knowledge retrieval,
nested entry-contract, persistence, and disable/enable checks.

You can also pass --token-file path/to/token.json with an access_token field,
matching the UI/CDP acceptance token file format. If no token is supplied, set
--username/--password or the matching environment variables. The authenticated
user needs workflow:read, workflow:write, and workflow:run. It also needs
marketplace:admin when the plugin must be enabled first, and mcp:admin when
--include-tool-discovery is used to discover and invoke workflow_list,
workflow_get_schema, workflow_get_run, and workflow_run through the LambChat
internal MCP server, including a failed workflow_get_run outlet check. Use
--output-file to persist the JSON result for deployment evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

PLUGIN_ID = "workflow"
AGENT_TEAM_PLUGIN_ID = "agent_team"
WORKFLOW_PANEL_RENDERER = "workflow.WorkflowPanel"
EXPECTED_WORKFLOW_APP_TABS = [
    {
        "tab": "workflows",
        "path": "/workflows",
        "panel": "workflow:workflows-panel",
        "insert_after": "agent-team",
    },
    {
        "tab": "workflows-editor",
        "path": "/workflows/:workflowId/editor",
        "panel": "workflow:workflow-editor-panel",
        "insert_after": "workflows",
    },
    {
        "tab": "workflows-run",
        "path": "/workflows/:workflowId/runs/:runId",
        "panel": "workflow:workflow-run-panel",
        "insert_after": "workflows-editor",
    },
]
EXPECTED_WORKFLOW_SIDEBAR_PATH = "/workflows"
EXPECTED_WORKFLOW_SIDEBAR_ICON = "Workflow"
FAILED_PRE_RUN_WORKFLOW_ID = "__lambchat_acceptance_missing_workflow__"
FAILED_INTERNAL_TOOL_RUN_ID = "__lambchat_acceptance_missing_run__"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FIXTURE = Path("tests/fixtures/workflow/list_operator.json")
DEFAULT_HUMAN_APPROVAL_FIXTURE = Path("tests/fixtures/workflow/human_approval_resume.json")
DEFAULT_VERSION_RUN_V1_FIXTURE = Path("tests/fixtures/workflow/version_run_v1.json")
DEFAULT_VERSION_RUN_V2_FIXTURE = Path("tests/fixtures/workflow/version_run_v2.json")
DEFAULT_KNOWLEDGE_RETRIEVAL_FIXTURE = Path("tests/fixtures/workflow/knowledge_retrieval.json")
DEFAULT_LLM_FIXTURE = Path("tests/fixtures/workflow/default_llm.json")
DEFAULT_NESTED_ENTRY_CONTRACT_FIXTURE = Path("tests/fixtures/workflow/nested_entry_contract.json")
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
WAITING_STATUSES = {"paused"}
TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
SYSTEM_INPUT_ALIASES = {"sys.query": "query", "sys.input": "input"}
INTERNAL_TEMPLATE_KEYS = {"item", "iteration_item", "index", "iteration_index"}
ACCEPTANCE_PROFILES = {"full", "final"}
FIXTURE_NODE_OUTPUT_DEFAULTS = {
    "condition": {"branch", "matched"},
    "tool_call": {"tool_result", "tool_name"},
    "knowledge-retrieval": {"knowledge_result"},
    "knowledge_retrieval": {"knowledge_result"},
    "llm": {"llm_result", "llm_text", "text"},
    "parameter-extractor": {"parameters", "parameter_extractor_text"},
    "parameter_extractor": {"parameters", "parameter_extractor_text"},
    "question-classifier": {
        "branch",
        "matched",
        "question_class",
        "question_class_name",
        "question_classifier_text",
    },
    "question_classifier": {
        "branch",
        "matched",
        "question_class",
        "question_class_name",
        "question_classifier_text",
    },
    "iteration": {"iteration_count"},
    "document-extractor": {"document_text", "document_count"},
    "document_extractor": {"document_text", "document_count"},
}


class AcceptanceError(RuntimeError):
    """Raised when the deployed app does not satisfy an acceptance check."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    data: Any
    text: str = ""


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse:
        ...


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse:
        request_headers = dict(headers or {})
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request_headers.setdefault("Accept", "application/json")
        request = urllib.request.Request(
            url,
            data=body,
            method=method.upper(),
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                text = response.read().decode("utf-8", errors="replace")
                return HttpResponse(response.status, _decode_json(text), text)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(exc.code, _decode_json(text), text)
        except TimeoutError as exc:
            raise AcceptanceError(f"request_timeout:{method.upper()} {url}: {exc}") from exc
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"request_failed:{method.upper()} {url}: {exc}") from exc

    def stream_sse(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> Any:
        request_headers = dict(headers or {})
        request_headers.setdefault("Accept", "text/event-stream")
        request = urllib.request.Request(url, method="GET", headers=request_headers)
        deadline = time.monotonic() + timeout
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                yield from _iter_sse_events(response, deadline=deadline)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise AcceptanceError(f"sse_stream_failed:{exc.code}:{text}") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise AcceptanceError(f"sse_stream_failed:{url}: {exc}") from exc


@dataclass
class AcceptanceSettings:
    base_url: str = DEFAULT_BASE_URL
    token: str | None = None
    token_file: Path | None = None
    username: str | None = None
    password: str | None = None
    fixture_path: Path = DEFAULT_FIXTURE
    human_approval_fixture_path: Path = DEFAULT_HUMAN_APPROVAL_FIXTURE
    version_run_v1_fixture_path: Path = DEFAULT_VERSION_RUN_V1_FIXTURE
    version_run_v2_fixture_path: Path = DEFAULT_VERSION_RUN_V2_FIXTURE
    knowledge_retrieval_fixture_path: Path = DEFAULT_KNOWLEDGE_RETRIEVAL_FIXTURE
    llm_fixture_path: Path = DEFAULT_LLM_FIXTURE
    nested_entry_contract_fixture_path: Path = DEFAULT_NESTED_ENTRY_CONTRACT_FIXTURE
    request_timeout: float = 15.0
    async_timeout: float = 60.0
    poll_interval: float = 1.0
    output_file: Path | None = None
    skip_async: bool = False
    include_chat: bool = False
    include_failed_pre_run: bool = False
    include_agent_team: bool = False
    agent_team_id: str | None = None
    include_scheduled_task: bool = False
    include_tool_discovery: bool = False
    include_human_approval: bool = False
    include_version_run: bool = False
    include_knowledge_retrieval: bool = False
    include_llm: bool = False
    include_nested_entry_contract: bool = False
    verify_persistence: bool = False
    test_disable_enable: bool = False
    restart_command: str | None = None
    restart_wait: float = 5.0
    restart_timeout: float = 90.0

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


@dataclass
class AcceptanceRecorder:
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, **details: Any) -> None:
        self.checks.append({"name": name, **details})

    def summary(self) -> dict[str, Any]:
        return {"status": "passed", "checks": self.checks}


@dataclass(frozen=True)
class SessionWorkflowRunRef:
    source: str
    workflow_id: str
    run_id: str
    version_id: str | None = None


class WorkflowAcceptance:
    def __init__(
        self,
        settings: AcceptanceSettings,
        *,
        transport: HttpTransport | None = None,
        sleeper=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.settings = settings
        self.transport = transport or UrllibTransport()
        self.sleeper = sleeper
        self.clock = clock
        self.recorder = AcceptanceRecorder()
        self.session_workflow_run_refs: list[SessionWorkflowRunRef] = []

    def run(self) -> dict[str, Any]:
        self.check_health()
        self.ensure_token()
        self.check_plugin_runtime_listing()
        contribution = self.check_plugin_contribution()
        if not contribution.get("executable"):
            contribution = self.enable_plugin_and_recheck()
        if self.settings.test_disable_enable:
            contribution = self.disable_enable_and_recheck()
        self.check_node_catalog()
        fixture = load_fixture(self.settings.fixture_path)
        fixture_input_fields = fixture_expected_input_fields(fixture)
        fixture_node_event_ids = fixture_expected_node_event_ids(fixture)
        fixture_input = sample_input_for_fields(fixture_input_fields)
        import_payload = self.import_workflow(fixture)
        workflow_id = require_key(import_payload, "workflow_id")
        version_id = require_key(import_payload, "version_id")
        self.publish_workflow(workflow_id, version_id)
        sync_run = self.run_workflow(workflow_id, mode="sync", workflow_input=fixture_input)
        run_id = require_key(sync_run, "run_id")
        self.check_run_events(
            workflow_id,
            run_id,
            require_started_event=True,
            require_success_event=True,
            expected_node_event_ids=fixture_node_event_ids,
        )
        async_run_id: str | None = None
        if not self.settings.skip_async:
            async_run = self.run_workflow(workflow_id, mode="async", workflow_input=fixture_input)
            async_run_id = require_key(async_run, "run_id")
            self.poll_async_run(workflow_id, async_run_id)
        if self.settings.include_chat:
            self.check_chat_invocation(workflow_id, version_id=version_id, workflow_input=fixture_input)
        if self.settings.include_failed_pre_run:
            self.check_failed_pre_run_invocation()
        if self.settings.include_agent_team:
            self.check_agent_team_invocation(
                workflow_id,
                version_id=version_id,
                workflow_input=fixture_input,
            )
            if self.settings.include_failed_pre_run:
                self.check_agent_team_failed_pre_run_invocation()
        if self.settings.include_scheduled_task:
            self.check_scheduled_task_invocation(
                workflow_id,
                version_id=version_id,
                workflow_input=fixture_input,
            )
            if self.settings.include_failed_pre_run:
                self.check_scheduled_task_failed_pre_run_invocation()
        if self.settings.include_tool_discovery:
            self.check_internal_tool_discovery()
            self.check_internal_tool_list_invocation(workflow_id)
            self.check_internal_tool_schema_invocation(
                workflow_id,
                version_id=version_id,
                expected_input_fields=fixture_input_fields,
            )
            tool_run = self.check_internal_tool_invocation(
                workflow_id,
                version_id=version_id,
                workflow_input=fixture_input,
            )
            self.check_internal_tool_get_run_invocation(
                workflow_id,
                require_key(tool_run, "run_id"),
                require_started_event=True,
                require_success_event=True,
            )
            self.check_internal_tool_get_run_failure_invocation(workflow_id)
            if async_run_id is not None:
                self.check_internal_tool_get_run_invocation(
                    workflow_id,
                    async_run_id,
                    require_started_event=True,
                    require_success_event=True,
                )
            self.check_session_workflow_get_run_invocations()
        if self.settings.include_human_approval:
            self.check_human_approval_resume()
        if self.settings.include_version_run:
            self.check_version_scoped_run()
        if self.settings.include_knowledge_retrieval:
            self.check_knowledge_retrieval_run()
        if self.settings.include_llm:
            self.check_llm_run()
        if self.settings.include_nested_entry_contract:
            self.check_nested_entry_contract_rejection()
        if self.settings.restart_command:
            self.run_restart_command()
            self.wait_for_health_after_restart()
        if self.settings.verify_persistence or self.settings.restart_command:
            self.check_persistence(workflow_id, run_id)
        return self.recorder.summary()

    def check_health(self) -> None:
        response = self._request("GET", "/health", auth=False)
        status = response.data.get("status") if isinstance(response.data, dict) else None
        if response.status != 200 or status != "ok":
            raise AcceptanceError(f"health_check_failed:{response.status}:{response.text}")
        self.recorder.add("health", app_status=status)

    def ensure_token(self) -> None:
        if self.settings.token:
            self.recorder.add("auth", mode="token")
            return
        if self.settings.token_file:
            self.settings.token = read_token_file(self.settings.token_file)
            self.recorder.add("auth", mode="token_file", token_file=str(self.settings.token_file))
            return
        if not self.settings.username or not self.settings.password:
            raise AcceptanceError(
                "auth_required: provide LAMBCHAT_TOKEN, LAMBCHAT_TOKEN_FILE, or LAMBCHAT_USERNAME/LAMBCHAT_PASSWORD"
            )
        response = self._request(
            "POST",
            "/api/auth/login",
            auth=False,
            json_body={"username": self.settings.username, "password": self.settings.password},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"login_failed:{response.status}:{response.text}")
        token = response.data.get("access_token")
        if not token:
            raise AcceptanceError("login_failed:missing_access_token")
        self.settings.token = str(token)
        self.recorder.add("auth", mode="login")

    def check_plugin_contribution(self) -> dict[str, Any]:
        response = self._request("GET", "/api/extensions/plugins/contributions", auth=False)
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"plugin_contributions_failed:{response.status}:{response.text}")
        plugin = _find_plugin(response.data.get("plugins", []), PLUGIN_ID)
        frontend = plugin.get("frontend") if isinstance(plugin.get("frontend"), dict) else {}
        contribution_evidence = _check_workflow_frontend_contribution(frontend)
        self.recorder.add(
            "plugin_contribution",
            enabled=plugin.get("enabled"),
            executable=plugin.get("executable"),
            **contribution_evidence,
        )
        return plugin

    def check_plugin_runtime_listing(self) -> None:
        response = self._request("GET", "/api/extensions/plugins/")
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"plugin_runtime_list_failed:{response.status}:{response.text}")
        plugin = _find_plugin(response.data.get("plugins", []), PLUGIN_ID)
        self.recorder.add(
            "plugin_runtime_listing",
            enabled=plugin.get("enabled"),
            status=plugin.get("status"),
        )

    def enable_plugin_and_recheck(self) -> dict[str, Any]:
        response = self._request("POST", f"/api/extensions/plugins/{PLUGIN_ID}/enable")
        if response.status != 200:
            raise AcceptanceError(
                "plugin_enable_failed:" f"{response.status}:{response.text}"
            )
        self.recorder.add("plugin_enable", status=response.data.get("status"))
        plugin = self.check_plugin_contribution()
        if not plugin.get("executable"):
            raise AcceptanceError("plugin_not_executable_after_enable")
        return plugin

    def disable_enable_and_recheck(self) -> dict[str, Any]:
        disable_response = self._request("POST", f"/api/extensions/plugins/{PLUGIN_ID}/disable")
        if disable_response.status != 200:
            raise AcceptanceError(
                "plugin_disable_failed:" f"{disable_response.status}:{disable_response.text}"
            )
        disabled = self.check_plugin_contribution()
        if disabled.get("executable"):
            raise AcceptanceError("plugin_still_executable_after_disable")
        enabled = self.enable_plugin_and_recheck()
        self.recorder.add("plugin_disable_enable", status="roundtrip_ok")
        return enabled

    def check_node_catalog(self) -> None:
        response = self._request("GET", "/api/plugins/workflow/node-types")
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"node_catalog_failed:{response.status}:{response.text}")
        compatibility = response.data.get("compatibility") or {}
        summary = compatibility.get("summary") or {}
        if int(summary.get("supported", 0)) < 1:
            raise AcceptanceError("node_catalog_failed:no_supported_nodes")
        self.recorder.add("node_catalog", supported=summary.get("supported"))

    def import_workflow(self, fixture: dict[str, Any]) -> dict[str, Any]:
        name = "Container Acceptance " + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        response = self._request(
            "POST",
            "/api/plugins/workflow/workflows/import",
            json_body={
                "name": name,
                "source_payload": fixture,
                "source_format": "json",
                "dry_run": False,
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_import_failed:{response.status}:{response.text}")
        if response.data.get("status") != "imported":
            raise AcceptanceError(f"workflow_import_unexpected_status:{response.data}")
        workflow_id = require_key(response.data, "workflow_id")
        version_id = require_key(response.data, "version_id")
        _check_workflow_saved_version_boundary(
            response.data,
            source="workflow_import",
            workflow_id=workflow_id,
            version_id=version_id,
        )
        self.recorder.add(
            "workflow_import",
            workflow_id=workflow_id,
            version_id=version_id,
            lossless=(response.data.get("compatibility_report") or {}).get("lossless"),
        )
        return response.data

    def create_workflow_version(self, workflow_id: str, fixture: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/plugins/workflow/workflows/{workflow_id}/versions",
            json_body={
                "name": "Container Acceptance Version",
                "source_payload": fixture,
                "source_format": "json",
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_version_create_failed:{response.status}:{response.text}")
        if response.data.get("status") != "versioned":
            raise AcceptanceError(f"workflow_version_create_unexpected_status:{response.data}")
        response_workflow_id = str(response.data.get("workflow_id") or workflow_id)
        version_id = require_key(response.data, "version_id")
        _check_workflow_saved_version_boundary(
            response.data,
            source="workflow_version_create",
            workflow_id=response_workflow_id,
            version_id=version_id,
        )
        self.recorder.add(
            "workflow_version_create",
            workflow_id=response_workflow_id,
            version_id=version_id,
        )
        return response.data

    def check_version_scoped_run(self) -> None:
        fixture_v1 = load_fixture(self.settings.version_run_v1_fixture_path)
        fixture_v2 = load_fixture(self.settings.version_run_v2_fixture_path)
        import_payload = self.import_workflow(fixture_v1)
        workflow_id = require_key(import_payload, "workflow_id")
        version_v1 = require_key(import_payload, "version_id")
        version_payload = self.create_workflow_version(workflow_id, fixture_v2)
        version_v2 = require_key(version_payload, "version_id")
        schema_v1 = self.check_input_schema(workflow_id, version_id=version_v1)
        schema_v2 = self.check_input_schema(workflow_id, version_id=version_v2)
        contract_v1 = self.check_io_contract(workflow_id, version_id=version_v1)
        contract_v2 = self.check_io_contract(workflow_id, version_id=version_v2)
        run_v1 = self.run_workflow(
            workflow_id,
            mode="sync",
            workflow_input={"message": "LambChat"},
            version_id=version_v1,
        )
        run_v2 = self.run_workflow(
            workflow_id,
            mode="sync",
            workflow_input={"message": "LambChat"},
            version_id=version_v2,
        )
        output_v1 = _stringify_output(run_v1.get("output"))
        output_v2 = _stringify_output(run_v2.get("output"))
        if "version-one" not in output_v1:
            raise AcceptanceError(f"version_scoped_run_v1_output_mismatch:{run_v1}")
        if "version-two" not in output_v2:
            raise AcceptanceError(f"version_scoped_run_v2_output_mismatch:{run_v2}")
        self.recorder.add(
            "version_scoped_run",
            workflow_id=workflow_id,
            version_v1=version_v1,
            version_v2=version_v2,
            schema_v1=schema_v1.get("version_id"),
            schema_v2=schema_v2.get("version_id"),
            contract_v1=contract_v1.get("version_id"),
            contract_v2=contract_v2.get("version_id"),
            run_v1=run_v1.get("run_id"),
            run_v2=run_v2.get("run_id"),
        )

    def check_input_schema(self, workflow_id: str, *, version_id: str | None = None) -> dict[str, Any]:
        path = f"/api/plugins/workflow/workflows/{workflow_id}/input-schema"
        if version_id is not None:
            path = f"{path}?version_id={version_id}"
        response = self._request("GET", path)
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_input_schema_failed:{response.status}:{response.text}")
        if version_id is not None and response.data.get("version_id") != version_id:
            raise AcceptanceError(f"workflow_input_schema_version_mismatch:{version_id}:{response.data}")
        schema = response.data.get("input_schema")
        if not isinstance(schema, dict):
            raise AcceptanceError(f"workflow_input_schema_invalid:{response.data}")
        _check_workflow_callable_interface(
            response.data,
            source="workflow_input_schema",
            workflow_id=workflow_id,
        )
        self.recorder.add(
            "workflow_input_schema",
            workflow_id=workflow_id,
            version_id=version_id or response.data.get("version_id"),
            schema_source=response.data.get("schema_source"),
        )
        return response.data

    def check_io_contract(self, workflow_id: str, *, version_id: str | None = None) -> dict[str, Any]:
        path = f"/api/plugins/workflow/workflows/{workflow_id}/io-contract"
        if version_id is not None:
            path = f"{path}?version_id={version_id}"
        response = self._request("GET", path)
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_io_contract_failed:{response.status}:{response.text}")
        if version_id is not None and response.data.get("version_id") != version_id:
            raise AcceptanceError(f"workflow_io_contract_version_mismatch:{version_id}:{response.data}")
        input_schema = response.data.get("input_schema")
        if not isinstance(input_schema, dict):
            raise AcceptanceError(f"workflow_io_contract_input_schema_invalid:{response.data}")
        output_schema = response.data.get("output_schema")
        if not isinstance(output_schema, dict):
            raise AcceptanceError(f"workflow_io_contract_output_schema_invalid:{response.data}")
        _check_workflow_callable_interface(
            response.data,
            source="workflow_io_contract",
            workflow_id=workflow_id,
        )
        self.recorder.add(
            "workflow_io_contract",
            workflow_id=workflow_id,
            version_id=version_id or response.data.get("version_id"),
            input_schema_source=response.data.get("input_schema_source"),
            output_schema_source=response.data.get("output_schema_source"),
        )
        return response.data

    def check_human_approval_resume(self) -> None:
        fixture = load_fixture(self.settings.human_approval_fixture_path)
        import_payload = self.import_workflow(fixture)
        workflow_id = require_key(import_payload, "workflow_id")
        version_id = require_key(import_payload, "version_id")
        self.publish_workflow(workflow_id, version_id)
        paused_run = self.run_workflow(
            workflow_id,
            mode="async",
            workflow_input={"name": "LambChat"},
            expected_statuses={"queued", "running", "paused"},
        )
        run_id = require_key(paused_run, "run_id")
        if paused_run.get("status") != "paused":
            paused_run = self.poll_async_run(
                workflow_id,
                run_id,
                expected_statuses={"paused"},
            ).get("run") or paused_run
        pause = paused_run.get("pause") if isinstance(paused_run.get("pause"), dict) else {}
        pending = pause.get("pending_approval") if isinstance(pause.get("pending_approval"), dict) else {}
        if pause.get("kind") != "human_approval" or not pending:
            raise AcceptanceError(f"human_approval_pause_metadata_missing:{paused_run}")
        pending_runs = self.check_pending_approvals(run_id)
        resumed = self.resume_workflow_run(
            workflow_id,
            run_id,
            approved=True,
            comment="accepted by container acceptance",
        )
        status = resumed.get("status")
        if status == "running":
            resumed = self.poll_async_run(workflow_id, run_id).get("run") or resumed
            status = resumed.get("status")
        if status != "succeeded":
            raise AcceptanceError(f"human_approval_resume_not_succeeded:{resumed}")
        output = resumed.get("output") if isinstance(resumed.get("output"), dict) else {}
        self.recorder.add(
            "human_approval_resume",
            workflow_id=workflow_id,
            run_id=run_id,
            pending_count=len(pending_runs),
            output=output,
        )

    def check_knowledge_retrieval_run(self) -> None:
        fixture = load_fixture(self.settings.knowledge_retrieval_fixture_path)
        fixture_input = sample_input_for_fields(fixture_expected_input_fields(fixture))
        import_payload = self.import_workflow(fixture)
        workflow_id = require_key(import_payload, "workflow_id")
        version_id = require_key(import_payload, "version_id")
        self.publish_workflow(workflow_id, version_id)
        run = self.run_workflow(
            workflow_id,
            mode="sync",
            workflow_input=fixture_input,
            version_id=version_id,
        )
        run_id = require_key(run, "run_id")
        event_payload = self.check_run_events(
            workflow_id,
            run_id,
            require_started_event=True,
            require_success_event=True,
        )
        events = event_payload.get("events") or []
        if not _has_node_finished_event(events, "knowledge_retrieval"):
            raise AcceptanceError(f"knowledge_retrieval_event_missing:{run_id}:{events}")
        self.recorder.add(
            "knowledge_retrieval_run",
            workflow_id=workflow_id,
            version_id=version_id,
            run_id=run_id,
            event_count=len(events),
        )

    def check_llm_run(self) -> None:
        fixture = load_fixture(self.settings.llm_fixture_path)
        fixture_input = sample_input_for_fields(fixture_expected_input_fields(fixture))
        import_payload = self.import_workflow(fixture)
        workflow_id = require_key(import_payload, "workflow_id")
        version_id = require_key(import_payload, "version_id")
        self.publish_workflow(workflow_id, version_id)
        run = self.run_workflow(
            workflow_id,
            mode="async",
            workflow_input=fixture_input,
            version_id=version_id,
        )
        run_id = require_key(run, "run_id")
        event_payload = self.poll_async_run(workflow_id, run_id)
        events = event_payload.get("events") or []
        if not _has_node_finished_event(events, "llm"):
            raise AcceptanceError(f"llm_event_missing:{run_id}:{events}")
        self.recorder.add(
            "llm_run",
            workflow_id=workflow_id,
            version_id=version_id,
            run_id=run_id,
            event_count=len(events),
        )

    def check_nested_entry_contract_rejection(self) -> None:
        fixture = load_fixture(self.settings.nested_entry_contract_fixture_path)
        import_payload = self.import_workflow(fixture)
        workflow_id = require_key(import_payload, "workflow_id")
        version_id = require_key(import_payload, "version_id")
        self.publish_workflow(workflow_id, version_id)
        invalid_input = {"profile": {"nickname": "Ada"}, "items": [{"score": "high"}]}
        response = self._request(
            "POST",
            f"/api/plugins/workflow/workflows/{workflow_id}/run",
            json_body={
                "input": invalid_input,
                "mode": "sync",
                "version_id": version_id,
            },
        )
        error_text = _stringify_output(response.data) if response.data is not None else response.text
        if not _contains_nested_entry_contract_error(error_text):
            if response.status == 200 and isinstance(response.data, dict) and response.data.get("status") == "succeeded":
                raise AcceptanceError(f"nested_entry_contract_run_unexpected_success:{response.data}")
            raise AcceptanceError(f"nested_entry_contract_error_missing:{response.status}:{error_text}")
        self.recorder.add(
            "nested_entry_contract_rejection",
            workflow_id=workflow_id,
            version_id=version_id,
            status=response.status,
        )

    def publish_workflow(self, workflow_id: str, version_id: str) -> None:
        response = self._request(
            "POST",
            f"/api/plugins/workflow/workflows/{workflow_id}/publish",
            json_body={"version_id": version_id},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_publish_failed:{response.status}:{response.text}")
        workflow = response.data.get("workflow") or {}
        if workflow.get("status") != "published":
            raise AcceptanceError(f"workflow_publish_unexpected_status:{workflow}")
        self.recorder.add("workflow_publish", workflow_id=workflow_id, version_id=version_id)

    def run_workflow(
        self,
        workflow_id: str,
        *,
        mode: str,
        workflow_input: dict[str, Any] | None = None,
        version_id: str | None = None,
        expected_statuses: set[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "input": workflow_input or {"items": ["alpha", "beta", "gamma"]},
            "mode": mode,
        }
        if version_id is not None:
            body["version_id"] = version_id
        response = self._request(
            "POST",
            f"/api/plugins/workflow/workflows/{workflow_id}/run",
            json_body=body,
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_run_failed:{mode}:{response.status}:{response.text}")
        status = response.data.get("status")
        if expected_statuses is not None:
            if status not in expected_statuses:
                raise AcceptanceError(f"workflow_run_unexpected_status:{mode}:{response.data}")
        else:
            if mode == "sync" and status != "succeeded":
                raise AcceptanceError(f"workflow_sync_run_not_succeeded:{response.data}")
            if mode == "async" and status not in {"queued", "running", "succeeded"}:
                raise AcceptanceError(f"workflow_async_run_unexpected_status:{response.data}")
        _check_workflow_output_contract_payload(response.data, source=f"workflow_{mode}_run")
        self.recorder.add(
            "workflow_run",
            mode=mode,
            run_id=response.data.get("run_id"),
            status=status,
            version_id=version_id or response.data.get("version_id"),
        )
        return response.data

    def check_pending_approvals(self, run_id: str) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/plugins/workflow/approvals/pending?limit=20")
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"pending_approvals_failed:{response.status}:{response.text}")
        runs = response.data.get("runs") or []
        if not any(isinstance(run, dict) and run.get("run_id") == run_id for run in runs):
            raise AcceptanceError(f"pending_approval_run_not_found:{run_id}:{runs}")
        self.recorder.add("pending_approvals", run_id=run_id, pending_count=len(runs))
        return [run for run in runs if isinstance(run, dict)]

    def resume_workflow_run(
        self,
        workflow_id: str,
        run_id: str,
        *,
        approved: bool,
        comment: str,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/plugins/workflow/workflows/{workflow_id}/runs/{run_id}/resume",
            json_body={"approved": approved, "comment": comment},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_resume_failed:{response.status}:{response.text}")
        status = response.data.get("status")
        if status not in TERMINAL_STATUSES | WAITING_STATUSES | {"running"}:
            raise AcceptanceError(f"workflow_resume_unexpected_status:{response.data}")
        self.recorder.add("workflow_resume", run_id=run_id, status=status)
        return response.data

    def check_run_events(
        self,
        workflow_id: str,
        run_id: str,
        *,
        require_started_event: bool = False,
        require_success_event: bool = False,
        expected_node_event_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/api/plugins/workflow/workflows/{workflow_id}/runs/{run_id}/events",
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"workflow_events_failed:{response.status}:{response.text}")
        events = response.data.get("events") or []
        if not events:
            raise AcceptanceError("workflow_events_failed:no_events")
        if require_started_event and not _has_workflow_started_event(events):
            raise AcceptanceError(f"workflow_started_event_missing:{run_id}:{events}")
        if require_success_event and not _has_workflow_success_event(events):
            raise AcceptanceError(f"workflow_success_event_missing:{run_id}:{events}")
        node_event_counts = _workflow_event_node_counts(events)
        missing_node_events = sorted((expected_node_event_ids or set()) - set(node_event_counts))
        if missing_node_events:
            raise AcceptanceError(f"workflow_node_event_missing:{run_id}:{missing_node_events}:{events}")
        run = response.data.get("run")
        if not isinstance(run, dict):
            raise AcceptanceError(f"workflow_events_run_snapshot_missing:{run_id}:{response.data}")
        _check_workflow_output_contract_payload(run, source="workflow_events_run")
        self.recorder.add(
            "workflow_events",
            run_id=run_id,
            event_count=len(events),
            event_node_ids=sorted(node_event_counts),
            event_node_counts=node_event_counts,
        )
        return response.data

    def poll_async_run(
        self,
        workflow_id: str,
        run_id: str,
        *,
        expected_statuses: set[str] | None = None,
    ) -> dict[str, Any]:
        deadline = self.clock() + self.settings.async_timeout
        latest: dict[str, Any] | None = None
        while self.clock() <= deadline:
            latest = self.check_run_events(workflow_id, run_id)
            run = latest.get("run") or {}
            status = run.get("status")
            if expected_statuses is not None and status in expected_statuses:
                self.recorder.add("workflow_async_status", run_id=run_id, status=status)
                return latest
            if status in TERMINAL_STATUSES:
                if expected_statuses is not None:
                    raise AcceptanceError(
                        f"workflow_async_unexpected_terminal_status:{run_id}:{run}"
                    )
                if status != "succeeded":
                    raise AcceptanceError(f"workflow_async_run_terminal_failure:{run}")
                if not _has_workflow_started_event(latest.get("events") or []):
                    raise AcceptanceError(f"workflow_async_started_event_missing:{run_id}:{latest}")
                if not _has_workflow_success_event(latest.get("events") or []):
                    raise AcceptanceError(f"workflow_async_success_event_missing:{run_id}:{latest}")
                self.recorder.add("workflow_async_complete", run_id=run_id, status=status)
                return latest
            self.sleeper(self.settings.poll_interval)
        raise AcceptanceError(f"workflow_async_run_timeout:{run_id}:{latest}")

    def check_chat_invocation(
        self,
        workflow_id: str,
        *,
        agent_id: str = "search",
        version_id: str | None = None,
        workflow_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workflow_options = {"SELECTED_WORKFLOW_ID": workflow_id}
        if version_id:
            workflow_options["SELECTED_WORKFLOW_VERSION_ID"] = version_id
        workflow_input_payload = _workflow_input_payload(workflow_input)
        workflow_options["SELECTED_WORKFLOW_INPUT_JSON"] = workflow_input_payload
        response = self._request(
            "POST",
            f"/api/chat/stream?agent_id={agent_id}",
            json_body={
                "message": "Run the selected Workflow workflow for container acceptance.",
                "plugin_options": {PLUGIN_ID: workflow_options},
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"chat_invocation_failed:{response.status}:{response.text}")
        session_id = require_key(response.data, "session_id")
        run_id = require_key(response.data, "run_id")
        event = self.poll_session_workflow_event(
            session_id,
            run_id,
            workflow_id,
            version_id=version_id,
            live_stream=True,
        )
        event_data, workflow_events = self.check_session_workflow_run_events(
            event,
            source="chat",
            workflow_id=workflow_id,
            version_id=version_id,
        )
        self.recorder.add(
            "chat_invocation",
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            version_id=version_id,
            workflow_run_id=event_data.get("run_id"),
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
            workflow_input_keys=sorted(workflow_input_payload),
            workflow_event_count=len(workflow_events.get("events") or []),
        )
        return response.data

    def check_failed_pre_run_invocation(
        self,
        *,
        agent_id: str = "search",
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/chat/stream?agent_id={agent_id}",
            json_body={
                "message": "Verify that a failed selected Workflow workflow pre-run does not abort chat.",
                "plugin_options": {
                    PLUGIN_ID: {"SELECTED_WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID},
                },
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"chat_failed_pre_run_invocation_failed:{response.status}:{response.text}")
        session_id = require_key(response.data, "session_id")
        run_id = require_key(response.data, "run_id")
        event = self.poll_session_workflow_event(
            session_id,
            run_id,
            FAILED_PRE_RUN_WORKFLOW_ID,
            live_stream=True,
        )
        event_data = self.check_session_workflow_failure_event(
            event,
            source="chat_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )
        self.recorder.add(
            "chat_failed_pre_run",
            agent_id=agent_id,
            session_id=session_id,
            run_id=run_id,
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
            status=event_data.get("status"),
            error=event_data.get("error"),
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
        )
        return response.data

    def check_agent_team_invocation(
        self,
        workflow_id: str,
        *,
        version_id: str | None = None,
        workflow_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.agent_team_id:
            raise AcceptanceError("agent_team_id_required: pass --agent-team-id with --include-agent-team")
        workflow_options = {"SELECTED_WORKFLOW_ID": workflow_id}
        if version_id:
            workflow_options["SELECTED_WORKFLOW_VERSION_ID"] = version_id
        workflow_input_payload = _workflow_input_payload(workflow_input)
        workflow_options["SELECTED_WORKFLOW_INPUT_JSON"] = workflow_input_payload
        response = self._request(
            "POST",
            "/api/chat/stream?agent_id=team",
            json_body={
                "message": "Run the selected Workflow workflow through Agent Team acceptance.",
                "team_id": self.settings.agent_team_id,
                "plugin_options": {
                    AGENT_TEAM_PLUGIN_ID: {"SELECTED_TEAM_ID": self.settings.agent_team_id},
                    PLUGIN_ID: workflow_options,
                },
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"agent_team_invocation_failed:{response.status}:{response.text}")
        session_id = require_key(response.data, "session_id")
        run_id = require_key(response.data, "run_id")
        event = self.poll_session_workflow_event(
            session_id,
            run_id,
            workflow_id,
            version_id=version_id,
            live_stream=True,
        )
        event_data, workflow_events = self.check_session_workflow_run_events(
            event,
            source="agent_team",
            workflow_id=workflow_id,
            version_id=version_id,
        )
        self.recorder.add(
            "agent_team_invocation",
            team_id=self.settings.agent_team_id,
            session_id=session_id,
            run_id=run_id,
            version_id=version_id,
            workflow_run_id=event_data.get("run_id"),
            team_plugin_option="SELECTED_TEAM_ID",
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
            workflow_input_keys=sorted(workflow_input_payload),
            workflow_event_count=len(workflow_events.get("events") or []),
        )
        return response.data

    def check_agent_team_failed_pre_run_invocation(self) -> dict[str, Any]:
        if not self.settings.agent_team_id:
            raise AcceptanceError("agent_team_id_required: pass --agent-team-id with --include-agent-team")
        response = self._request(
            "POST",
            "/api/chat/stream?agent_id=team",
            json_body={
                "message": "Verify that a failed selected Workflow workflow pre-run does not abort Agent Team.",
                "team_id": self.settings.agent_team_id,
                "plugin_options": {
                    AGENT_TEAM_PLUGIN_ID: {"SELECTED_TEAM_ID": self.settings.agent_team_id},
                    PLUGIN_ID: {"SELECTED_WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID},
                },
            },
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"agent_team_failed_pre_run_invocation_failed:{response.status}:{response.text}")
        session_id = require_key(response.data, "session_id")
        run_id = require_key(response.data, "run_id")
        event = self.poll_session_workflow_event(
            session_id,
            run_id,
            FAILED_PRE_RUN_WORKFLOW_ID,
            live_stream=True,
        )
        event_data = self.check_session_workflow_failure_event(
            event,
            source="agent_team_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )
        self.recorder.add(
            "agent_team_failed_pre_run",
            team_id=self.settings.agent_team_id,
            session_id=session_id,
            run_id=run_id,
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
            status=event_data.get("status"),
            error=event_data.get("error"),
            team_plugin_option="SELECTED_TEAM_ID",
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
        )
        return response.data

    def poll_session_workflow_event(
        self,
        session_id: str,
        run_id: str,
        workflow_id: str,
        *,
        version_id: str | None = None,
        live_stream: bool = False,
    ) -> dict[str, Any]:
        deadline = self.clock() + self.settings.async_timeout
        latest: dict[str, Any] | None = None
        version_mismatch: dict[str, Any] | None = None
        if live_stream:
            stream_method = getattr(self.transport, "stream_sse", None)
            if stream_method is not None:
                try:
                    for event in stream_method(
                        self._url(
                            "/api/chat/sessions/"
                            f"{urllib.parse.quote(session_id, safe='')}/stream"
                            f"?run_id={urllib.parse.quote(run_id, safe='')}"
                        ),
                        headers=self._auth_headers(),
                        timeout=min(
                            self.settings.request_timeout,
                            max(deadline - self.clock(), 0.1),
                        ),
                    ):
                        latest = event if isinstance(event, dict) else {"event": event}
                        matched, mismatch = _match_workflow_session_event(
                            event,
                            workflow_id,
                            version_id=version_id,
                        )
                        if matched:
                            return event
                        if mismatch is not None:
                            version_mismatch = mismatch
                        if self.clock() > deadline:
                            break
                except AcceptanceError as exc:
                    latest = {"stream_error": str(exc), "latest_event": latest}
        while self.clock() <= deadline:
            response = self._request(
                "GET",
                f"/api/sessions/{session_id}/events?run_id={run_id}&limit=100",
            )
            if response.status != 200 or not isinstance(response.data, dict):
                raise AcceptanceError(
                    f"session_events_failed:{session_id}:{response.status}:{response.text}"
                )
            latest = response.data
            for event in response.data.get("events") or []:
                matched, mismatch = _match_workflow_session_event(
                    event,
                    workflow_id,
                    version_id=version_id,
                )
                if matched:
                    return event
                if mismatch is not None:
                    version_mismatch = mismatch
            self.sleeper(self.settings.poll_interval)
        if version_mismatch is not None:
            raise AcceptanceError(
                f"session_workflow_event_version_mismatch:{session_id}:{run_id}:{version_mismatch}"
            )
        raise AcceptanceError(f"session_workflow_event_timeout:{session_id}:{run_id}:{latest}")

    def check_session_workflow_run_events(
        self,
        event: dict[str, Any],
        *,
        source: str,
        workflow_id: str,
        version_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        data = _workflow_session_event_data(event)
        if data is None:
            raise AcceptanceError(f"{source}_workflow_event_invalid:{event}")
        event_workflow_id = str(data.get("workflow_id") or "")
        if event_workflow_id != workflow_id:
            raise AcceptanceError(f"{source}_workflow_event_workflow_mismatch:{workflow_id}:{data}")
        if version_id is not None and data.get("version_id") != version_id:
            raise AcceptanceError(f"{source}_workflow_event_version_mismatch:{version_id}:{data}")
        workflow_run_id = str(data.get("run_id") or "")
        if not workflow_run_id:
            raise AcceptanceError(f"{source}_workflow_run_id_missing:{data}")
        if data.get("status") != "succeeded":
            raise AcceptanceError(f"{source}_workflow_run_status_unexpected:{data}")
        _check_workflow_output_contract_payload(data, source=source)
        _check_workflow_result_interface(
            data,
            source=source,
            workflow_id=event_workflow_id,
            run_id=workflow_run_id,
        )
        _check_workflow_next_action_payload(
            data,
            source=source,
            expected_type="use_output",
            expected_field="output",
            expected_reason="workflow_run_succeeded",
        )
        events = self.check_run_events(
            event_workflow_id,
            workflow_run_id,
            require_started_event=True,
            require_success_event=True,
        )
        self._remember_session_workflow_run(
            source=source,
            workflow_id=event_workflow_id,
            run_id=workflow_run_id,
            version_id=version_id,
        )
        return data, events

    def _remember_session_workflow_run(
        self,
        *,
        source: str,
        workflow_id: str,
        run_id: str,
        version_id: str | None = None,
    ) -> None:
        ref = SessionWorkflowRunRef(
            source=source,
            workflow_id=workflow_id,
            run_id=run_id,
            version_id=version_id,
        )
        if ref not in self.session_workflow_run_refs:
            self.session_workflow_run_refs.append(ref)

    def check_session_workflow_failure_event(
        self,
        event: dict[str, Any],
        *,
        source: str,
        workflow_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        data = _workflow_session_event_data(event)
        if data is None:
            raise AcceptanceError(f"{source}_workflow_event_invalid:{event}")
        event_workflow_id = str(data.get("workflow_id") or "")
        if event_workflow_id != workflow_id:
            raise AcceptanceError(f"{source}_workflow_event_workflow_mismatch:{workflow_id}:{data}")
        if version_id is not None and data.get("version_id") != version_id:
            raise AcceptanceError(f"{source}_workflow_event_version_mismatch:{version_id}:{data}")
        if data.get("status") != "failed":
            raise AcceptanceError(f"{source}_workflow_run_status_unexpected:{data}")
        if data.get("run_id") not in (None, ""):
            raise AcceptanceError(f"{source}_workflow_run_id_unexpected:{data}")
        if not str(data.get("error") or "").strip():
            raise AcceptanceError(f"{source}_workflow_error_missing:{data}")
        _check_workflow_result_interface(
            data,
            source=source,
            workflow_id=event_workflow_id,
            run_id=None,
        )
        _check_workflow_next_action_payload(
            data,
            source=source,
            expected_type="handle_terminal_error",
            expected_field="error",
            expected_reason="workflow_run_failed",
        )
        return data

    def check_scheduled_task_invocation(
        self,
        workflow_id: str,
        *,
        version_id: str | None = None,
        workflow_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workflow_options = {"WORKFLOW_ID": workflow_id}
        if version_id:
            workflow_options["WORKFLOW_VERSION_ID"] = version_id
        workflow_input_payload = _workflow_input_payload(workflow_input)
        workflow_options["WORKFLOW_INPUT_JSON"] = workflow_input_payload
        response = self._request(
            "POST",
            "/api/scheduled-tasks/",
            json_body={
                "name": "Workflow Container Acceptance",
                "agent_id": "search",
                "trigger_type": "date",
                "trigger_config": {"run_date": "2099-01-01T00:00:00Z"},
                "timezone": "UTC",
                "input_payload": {
                    "message": "Run selected Workflow workflow from scheduled task acceptance.",
                    "plugin_options": {PLUGIN_ID: workflow_options},
                },
                "enabled": True,
                "run_on_start": False,
                "max_retries": 0,
                "timeout_seconds": 300,
                "created_by": "api",
            },
        )
        if response.status != 201 or not isinstance(response.data, dict):
            raise AcceptanceError(f"scheduled_task_create_failed:{response.status}:{response.text}")
        task_id = require_key(response.data, "id")
        trigger_data, trigger_timed_out = self.trigger_scheduled_task_run(
            task_id,
            source="scheduled_task",
        )
        run = self.poll_scheduled_task_run(
            task_id,
            allow_running_with_session_context=trigger_timed_out,
        )
        session_id = _scheduled_task_run_session_id(run)
        event_run_id = _scheduled_task_run_event_run_id(run, trigger_data)
        if session_id is None or event_run_id is None:
            raise AcceptanceError(f"scheduled_task_workflow_event_context_missing:{task_id}:{run}")
        event = self.poll_session_workflow_event(
            session_id,
            event_run_id,
            workflow_id,
            version_id=version_id,
            live_stream=run.get("status") != "success",
        )
        event_data, workflow_events = self.check_session_workflow_run_events(
            event,
            source="scheduled_task",
            workflow_id=workflow_id,
            version_id=version_id,
        )
        self.recorder.add(
            "scheduled_task_invocation",
            task_id=task_id,
            version_id=version_id,
            run_id=run.get("id"),
            status=run.get("status"),
            session_id=session_id,
            trace_id=_scheduled_task_run_trace_id(run),
            workflow_run_id=event_data.get("run_id"),
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
            workflow_input_keys=sorted(workflow_input_payload),
            workflow_event_count=len(workflow_events.get("events") or []),
        )
        return response.data

    def check_scheduled_task_failed_pre_run_invocation(self) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/scheduled-tasks/",
            json_body={
                "name": "Workflow Failed Pre-Run Acceptance",
                "agent_id": "search",
                "trigger_type": "date",
                "trigger_config": {"run_date": "2099-01-01T00:00:00Z"},
                "timezone": "UTC",
                "input_payload": {
                    "message": "Verify failed selected Workflow workflow pre-run from scheduled task acceptance.",
                    "plugin_options": {
                        PLUGIN_ID: {"WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID},
                    },
                },
                "enabled": True,
                "run_on_start": False,
                "max_retries": 0,
                "timeout_seconds": 300,
                "created_by": "api",
            },
        )
        if response.status != 201 or not isinstance(response.data, dict):
            raise AcceptanceError(f"scheduled_task_failed_pre_run_create_failed:{response.status}:{response.text}")
        task_id = require_key(response.data, "id")
        trigger_data, trigger_timed_out = self.trigger_scheduled_task_run(
            task_id,
            source="scheduled_task_failed_pre_run",
        )
        run = self.poll_scheduled_task_run(
            task_id,
            allow_running_with_session_context=trigger_timed_out,
        )
        session_id = _scheduled_task_run_session_id(run)
        event_run_id = _scheduled_task_run_event_run_id(run, trigger_data)
        if session_id is None or event_run_id is None:
            raise AcceptanceError(f"scheduled_task_failed_pre_run_event_context_missing:{task_id}:{run}")
        event = self.poll_session_workflow_event(
            session_id,
            event_run_id,
            FAILED_PRE_RUN_WORKFLOW_ID,
            live_stream=run.get("status") != "success",
        )
        event_data = self.check_session_workflow_failure_event(
            event,
            source="scheduled_task_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )
        self.recorder.add(
            "scheduled_task_failed_pre_run",
            task_id=task_id,
            run_id=run.get("id"),
            status=run.get("status"),
            session_id=session_id,
            trace_id=_scheduled_task_run_trace_id(run),
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
            workflow_status=event_data.get("status"),
            error=event_data.get("error"),
            next_action=_workflow_next_action_type(event_data),
            next_action_reason=_workflow_next_action_reason(event_data),
        )
        return response.data

    def trigger_scheduled_task_run(self, task_id: str, *, source: str) -> tuple[dict[str, Any], bool]:
        try:
            trigger_response = self._request("POST", f"/api/scheduled-tasks/{task_id}/run")
        except AcceptanceError as exc:
            if not str(exc).startswith("request_timeout:"):
                raise
            self.recorder.add(
                "scheduled_task_manual_trigger_timeout",
                source=source,
                task_id=task_id,
            )
            return {"status": "request_timeout"}, True
        if trigger_response.status != 200 or not isinstance(trigger_response.data, dict):
            raise AcceptanceError(
                f"{source}_run_failed:{trigger_response.status}:{trigger_response.text}"
            )
        return trigger_response.data, False

    def poll_scheduled_task_run(
        self,
        task_id: str,
        *,
        allow_running_with_session_context: bool = False,
    ) -> dict[str, Any]:
        deadline = self.clock() + self.settings.async_timeout
        latest: dict[str, Any] | None = None
        terminal = {"success", "failed", "skipped", "timeout"}
        while self.clock() <= deadline:
            response = self._request("GET", f"/api/scheduled-tasks/{task_id}/runs?limit=5")
            if response.status != 200 or not isinstance(response.data, dict):
                raise AcceptanceError(
                    f"scheduled_task_runs_failed:{task_id}:{response.status}:{response.text}"
                )
            latest = response.data
            runs = response.data.get("items") or []
            if runs:
                run = runs[0]
                status = run.get("status")
                if status in terminal:
                    if status != "success":
                        raise AcceptanceError(f"scheduled_task_terminal_failure:{run}")
                    return run
                if allow_running_with_session_context and _scheduled_task_run_session_id(run):
                    return run
            self.sleeper(self.settings.poll_interval)
        raise AcceptanceError(f"scheduled_task_run_timeout:{task_id}:{latest}")

    def check_internal_tool_discovery(self) -> dict[str, Any]:
        response = self._request("GET", "/api/admin/mcp/lambchat_internal/tools")
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(
                f"internal_tool_discovery_failed:{response.status}:{response.text}"
            )
        tools = response.data.get("tools") or []
        tools_by_name = {
            str(tool.get("name")): tool
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        }
        required = {"workflow_run", "workflow_list", "workflow_get_schema", "workflow_get_run"}
        missing = sorted(required - set(tools_by_name))
        if missing:
            raise AcceptanceError(f"internal_workflow_tools_missing:{missing}")
        run_tool = tools_by_name["workflow_run"]
        run_params = run_tool.get("parameters") or []
        run_param_names = {
            str(param.get("name"))
            for param in run_params
            if isinstance(param, dict) and param.get("name")
        }
        required_run_params = {"workflow_id", "version_id", "input", "mode"}
        missing_run_params = sorted(required_run_params - run_param_names)
        if missing_run_params:
            raise AcceptanceError(f"internal_workflow_run_tool_missing_params:{missing_run_params}")
        schema_tool = tools_by_name["workflow_get_schema"]
        schema_params = schema_tool.get("parameters") or []
        schema_param_names = {
            str(param.get("name"))
            for param in schema_params
            if isinstance(param, dict) and param.get("name")
        }
        required_schema_params = {"workflow_id", "version_id"}
        missing_schema_params = sorted(required_schema_params - schema_param_names)
        if missing_schema_params:
            raise AcceptanceError(f"internal_workflow_get_schema_tool_missing_params:{missing_schema_params}")
        get_run_tool = tools_by_name["workflow_get_run"]
        get_run_params = get_run_tool.get("parameters") or []
        get_run_param_names = {
            str(param.get("name"))
            for param in get_run_params
            if isinstance(param, dict) and param.get("name")
        }
        required_get_run_params = {"workflow_id", "run_id"}
        missing_get_run_params = sorted(required_get_run_params - get_run_param_names)
        if missing_get_run_params:
            raise AcceptanceError(f"internal_workflow_get_run_tool_missing_params:{missing_get_run_params}")
        self.recorder.add(
            "internal_tool_discovery",
            server_name=response.data.get("server_name"),
            workflow_tools=sorted(required),
            workflow_run_params=sorted(run_param_names),
            workflow_get_schema_params=sorted(schema_param_names),
            workflow_get_run_params=sorted(get_run_param_names),
        )
        return response.data

    def check_internal_tool_invocation(
        self,
        workflow_id: str,
        *,
        version_id: str | None = None,
        workflow_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_payload = workflow_input or sample_input_for_fields({"items"})
        arguments: dict[str, Any] = {
            "workflow_id": workflow_id,
            "input": input_payload,
            "mode": "sync",
        }
        if version_id:
            arguments["version_id"] = version_id
        response = self._request(
            "POST",
            "/api/admin/mcp/lambchat_internal/tools/workflow_run/invoke",
            json_body={"arguments": arguments},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"internal_workflow_run_invoke_failed:{response.status}:{response.text}")
        result = response.data.get("result")
        if not isinstance(result, dict):
            raise AcceptanceError(f"internal_workflow_run_result_invalid:{response.data}")
        if result.get("plugin_id") != PLUGIN_ID or result.get("workflow_id") != workflow_id:
            raise AcceptanceError(f"internal_workflow_run_result_mismatch:{workflow_id}:{result}")
        if version_id is not None and result.get("version_id") != version_id:
            raise AcceptanceError(f"internal_workflow_run_version_mismatch:{version_id}:{result}")
        if result.get("status") != "succeeded":
            raise AcceptanceError(f"internal_workflow_run_status_unexpected:{result}")
        run_id = str(result.get("run_id") or "")
        if not run_id:
            raise AcceptanceError(f"internal_workflow_run_id_missing:{result}")
        events = result.get("events") or []
        if not _has_workflow_started_event(events):
            raise AcceptanceError(f"internal_workflow_run_started_event_missing:{run_id}:{events}")
        if not _has_workflow_success_event(events):
            raise AcceptanceError(f"internal_workflow_run_success_event_missing:{run_id}:{events}")
        _check_workflow_output_contract_payload(result, source="internal_workflow_run")
        _check_workflow_result_interface(
            result,
            source="internal_workflow_run",
            workflow_id=workflow_id,
            run_id=run_id,
        )
        _check_workflow_next_action_payload(
            result,
            source="internal_workflow_run",
            expected_type="use_output",
            expected_field="output",
            expected_reason="workflow_run_succeeded",
        )
        interface = result.get("interface") if isinstance(result.get("interface"), dict) else {}
        entry = interface.get("entry") if isinstance(interface.get("entry"), dict) else {}
        exit_contract = interface.get("exit") if isinstance(interface.get("exit"), dict) else {}
        self.recorder.add(
            "internal_tool_invocation",
            server_name=response.data.get("server_name"),
            tool_name=response.data.get("tool_name"),
            workflow_id=workflow_id,
            version_id=version_id,
            run_id=run_id,
            workflow_input_keys=sorted(input_payload),
            run_entry=f"{entry.get('tool')}.{entry.get('argument')}",
            run_exit=exit_contract.get("field"),
            next_action=_workflow_next_action_type(result),
            next_action_reason=_workflow_next_action_reason(result),
            event_count=len(events),
        )
        return result

    def check_internal_tool_list_invocation(self, workflow_id: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/admin/mcp/lambchat_internal/tools/workflow_list/invoke",
            json_body={"arguments": {"scope": "published"}},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"internal_workflow_list_invoke_failed:{response.status}:{response.text}")
        result = response.data.get("result")
        if not isinstance(result, dict):
            raise AcceptanceError(f"internal_workflow_list_result_invalid:{response.data}")
        if result.get("plugin_id") != PLUGIN_ID or result.get("scope") != "published":
            raise AcceptanceError(f"internal_workflow_list_result_mismatch:{result}")
        workflows = result.get("workflows")
        if not isinstance(workflows, list):
            raise AcceptanceError(f"internal_workflow_list_workflows_invalid:{result}")
        if not any(
            isinstance(workflow, dict)
            and workflow.get("workflow_id") == workflow_id
            and workflow.get("status") == "published"
            for workflow in workflows
        ):
            raise AcceptanceError(f"internal_workflow_list_missing_workflow:{workflow_id}:{workflows}")
        self.recorder.add(
            "internal_tool_list_invocation",
            server_name=response.data.get("server_name"),
            tool_name=response.data.get("tool_name"),
            workflow_id=workflow_id,
            workflow_count=len(workflows),
        )
        return result

    def check_internal_tool_schema_invocation(
        self,
        workflow_id: str,
        *,
        version_id: str | None = None,
        expected_input_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"workflow_id": workflow_id}
        if version_id:
            arguments["version_id"] = version_id
        response = self._request(
            "POST",
            "/api/admin/mcp/lambchat_internal/tools/workflow_get_schema/invoke",
            json_body={"arguments": arguments},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"internal_workflow_get_schema_invoke_failed:{response.status}:{response.text}")
        result = response.data.get("result")
        if not isinstance(result, dict):
            raise AcceptanceError(f"internal_workflow_get_schema_result_invalid:{response.data}")
        if result.get("plugin_id") != PLUGIN_ID or result.get("workflow_id") != workflow_id:
            raise AcceptanceError(f"internal_workflow_get_schema_result_mismatch:{workflow_id}:{result}")
        if version_id is not None and result.get("version_id") != version_id:
            raise AcceptanceError(f"internal_workflow_get_schema_version_mismatch:{version_id}:{result}")
        schema = result.get("input_schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise AcceptanceError(f"internal_workflow_get_schema_input_schema_invalid:{result}")
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            raise AcceptanceError(f"internal_workflow_get_schema_properties_invalid:{result}")
        missing_fields = sorted((expected_input_fields or set()) - set(properties))
        if missing_fields:
            raise AcceptanceError(f"internal_workflow_get_schema_missing_fixture_inputs:{missing_fields}:{result}")
        output_schema = result.get("output_schema")
        if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
            raise AcceptanceError(f"internal_workflow_get_schema_output_schema_invalid:{result}")
        output_properties = output_schema.get("properties")
        if not isinstance(output_properties, dict):
            raise AcceptanceError(f"internal_workflow_get_schema_output_properties_invalid:{result}")
        _check_workflow_callable_interface(
            result,
            source="internal_workflow_get_schema",
            workflow_id=workflow_id,
        )
        interface = result.get("interface") if isinstance(result.get("interface"), dict) else {}
        entry = interface.get("entry") if isinstance(interface.get("entry"), dict) else {}
        exit_contract = interface.get("exit") if isinstance(interface.get("exit"), dict) else {}
        schema_contract = interface.get("schema") if isinstance(interface.get("schema"), dict) else {}
        self.recorder.add(
            "internal_tool_schema_invocation",
            server_name=response.data.get("server_name"),
            tool_name=response.data.get("tool_name"),
            workflow_id=workflow_id,
            version_id=version_id,
            schema_source=result.get("schema_source"),
            input_fields=sorted(str(field) for field in properties),
            output_fields=sorted(str(field) for field in output_properties),
            run_entry=f"{entry.get('tool')}.{entry.get('argument')}",
            run_exit=exit_contract.get("field"),
            schema_tool=schema_contract.get("tool"),
        )
        return result

    def check_internal_tool_get_run_invocation(
        self,
        workflow_id: str,
        run_id: str,
        *,
        source: str = "direct",
        require_started_event: bool = False,
        require_success_event: bool = False,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke",
            json_body={"arguments": {"workflow_id": workflow_id, "run_id": run_id}},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(f"internal_workflow_get_run_invoke_failed:{response.status}:{response.text}")
        result = response.data.get("result")
        if not isinstance(result, dict):
            raise AcceptanceError(f"internal_workflow_get_run_result_invalid:{response.data}")
        if result.get("plugin_id") != PLUGIN_ID or result.get("workflow_id") != workflow_id:
            raise AcceptanceError(f"internal_workflow_get_run_result_mismatch:{workflow_id}:{result}")
        if result.get("run_id") != run_id:
            raise AcceptanceError(f"internal_workflow_get_run_id_mismatch:{run_id}:{result}")
        events = result.get("events") or []
        if not isinstance(events, list):
            raise AcceptanceError(f"internal_workflow_get_run_events_invalid:{run_id}:{result}")
        if require_started_event and not _has_workflow_started_event(events):
            raise AcceptanceError(f"internal_workflow_get_run_started_event_missing:{run_id}:{events}")
        if require_success_event and not _has_workflow_success_event(events):
            raise AcceptanceError(f"internal_workflow_get_run_success_event_missing:{run_id}:{events}")
        _check_workflow_output_contract_payload(result, source="internal_workflow_get_run")
        _check_workflow_result_interface(
            result,
            source="internal_workflow_get_run",
            workflow_id=workflow_id,
            run_id=run_id,
        )
        _check_workflow_next_action_payload(
            result,
            source="internal_workflow_get_run",
            expected_type="use_output",
            expected_field="output",
            expected_reason="workflow_run_succeeded",
        )
        interface = result.get("interface") if isinstance(result.get("interface"), dict) else {}
        entry = interface.get("entry") if isinstance(interface.get("entry"), dict) else {}
        exit_contract = interface.get("exit") if isinstance(interface.get("exit"), dict) else {}
        self.recorder.add(
            "internal_tool_get_run_invocation",
            source=source,
            server_name=response.data.get("server_name"),
            tool_name=response.data.get("tool_name"),
            workflow_id=workflow_id,
            run_id=run_id,
            status=result.get("status"),
            run_entry=f"{entry.get('tool')}.{entry.get('argument')}",
            run_exit=exit_contract.get("field"),
            next_action=_workflow_next_action_type(result),
            next_action_reason=_workflow_next_action_reason(result),
            event_count=len(events),
        )
        return result

    def check_internal_tool_get_run_failure_invocation(
        self,
        workflow_id: str,
        *,
        run_id: str = FAILED_INTERNAL_TOOL_RUN_ID,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke",
            json_body={"arguments": {"workflow_id": workflow_id, "run_id": run_id}},
        )
        if response.status != 200 or not isinstance(response.data, dict):
            raise AcceptanceError(
                f"internal_workflow_get_run_failure_invoke_failed:{response.status}:{response.text}"
            )
        result = response.data.get("result")
        if not isinstance(result, dict):
            raise AcceptanceError(f"internal_workflow_get_run_failure_result_invalid:{response.data}")
        if result.get("plugin_id") != PLUGIN_ID or result.get("workflow_id") != workflow_id:
            raise AcceptanceError(
                f"internal_workflow_get_run_failure_result_mismatch:{workflow_id}:{result}"
            )
        if result.get("run_id") != run_id:
            raise AcceptanceError(f"internal_workflow_get_run_failure_id_mismatch:{run_id}:{result}")
        if result.get("status") != "failed":
            raise AcceptanceError(f"internal_workflow_get_run_failure_status_unexpected:{result}")
        if not result.get("error"):
            raise AcceptanceError(f"internal_workflow_get_run_failure_error_missing:{result}")
        _check_workflow_result_interface(
            result,
            source="internal_workflow_get_run_failure",
            workflow_id=workflow_id,
            run_id=run_id,
        )
        _check_workflow_next_action_payload(
            result,
            source="internal_workflow_get_run_failure",
            expected_type="handle_terminal_error",
            expected_field="error",
            expected_reason="workflow_run_failed",
        )
        action = _workflow_next_action(result)
        if not action or action.get("tool") != "workflow_get_run":
            raise AcceptanceError(f"internal_workflow_get_run_failure_next_action_tool_missing:{result}")
        interface = result.get("interface") if isinstance(result.get("interface"), dict) else {}
        entry = interface.get("entry") if isinstance(interface.get("entry"), dict) else {}
        exit_contract = interface.get("exit") if isinstance(interface.get("exit"), dict) else {}
        self.recorder.add(
            "internal_tool_get_run_failure_invocation",
            server_name=response.data.get("server_name"),
            tool_name=response.data.get("tool_name"),
            workflow_id=workflow_id,
            run_id=run_id,
            status=result.get("status"),
            error=result.get("error"),
            run_entry=f"{entry.get('tool')}.{entry.get('argument')}",
            run_exit=exit_contract.get("field"),
            next_action=_workflow_next_action_type(result),
            next_action_reason=_workflow_next_action_reason(result),
        )
        return result

    def check_session_workflow_get_run_invocations(self) -> None:
        for ref in self.session_workflow_run_refs:
            self.check_internal_tool_get_run_invocation(
                ref.workflow_id,
                ref.run_id,
                source=ref.source,
                require_started_event=True,
                require_success_event=True,
            )

    def check_persistence(self, workflow_id: str, run_id: str) -> None:
        detail = self._request("GET", f"/api/plugins/workflow/workflows/{workflow_id}")
        if detail.status != 200 or not isinstance(detail.data, dict):
            raise AcceptanceError(f"persistence_workflow_missing:{detail.status}:{detail.text}")
        runs = self._request("GET", f"/api/plugins/workflow/workflows/{workflow_id}/runs?limit=20")
        if runs.status != 200 or not isinstance(runs.data, dict):
            raise AcceptanceError(f"persistence_runs_missing:{runs.status}:{runs.text}")
        persisted_runs = runs.data.get("runs") or []
        if not any(isinstance(run, dict) and run.get("run_id") == run_id for run in persisted_runs):
            raise AcceptanceError(f"persistence_run_not_found:{run_id}:{persisted_runs}")
        events = self.check_run_events(
            workflow_id,
            run_id,
            require_started_event=True,
            require_success_event=True,
        )
        self.recorder.add(
            "persistence",
            workflow_id=workflow_id,
            run_id=run_id,
            run_count=len(persisted_runs),
            event_count=len(events.get("events") or []),
        )

    def run_restart_command(self) -> None:
        if not self.settings.restart_command:
            return
        try:
            args = shlex.split(self.settings.restart_command, posix=os.name != "nt")
            completed = subprocess.run(  # noqa: S603 - explicit acceptance command supplied by caller
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.settings.restart_timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AcceptanceError(f"restart_command_failed:{exc}") from exc
        if completed.returncode != 0:
            raise AcceptanceError(
                "restart_command_failed:"
                f"exit={completed.returncode}:stdout={completed.stdout}:stderr={completed.stderr}"
            )
        self.recorder.add("restart_command", command=self.settings.restart_command)
        if self.settings.restart_wait > 0:
            self.sleeper(self.settings.restart_wait)

    def wait_for_health_after_restart(self) -> None:
        deadline = self.clock() + self.settings.restart_timeout
        latest: str | None = None
        while self.clock() <= deadline:
            try:
                response = self._request("GET", "/health", auth=False)
            except AcceptanceError as exc:
                latest = str(exc)
            else:
                status = response.data.get("status") if isinstance(response.data, dict) else None
                if response.status == 200 and status == "ok":
                    self.recorder.add("restart_health", app_status=status)
                    return
                latest = f"{response.status}:{response.text}"
            self.sleeper(self.settings.poll_interval)
        raise AcceptanceError(f"restart_health_timeout:{latest}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json_body: Any | None = None,
    ) -> HttpResponse:
        headers: dict[str, str] = {}
        if auth:
            if not self.settings.token:
                raise AcceptanceError("auth_token_missing")
            headers["Authorization"] = f"Bearer {self.settings.token}"
        return self.transport.request(
            method,
            self._url(path),
            headers=headers,
            json_body=json_body,
            timeout=self.settings.request_timeout,
        )

    def _auth_headers(self) -> dict[str, str]:
        if not self.settings.token:
            raise AcceptanceError("auth_token_missing")
        return {"Authorization": f"Bearer {self.settings.token}"}

    def _url(self, path: str) -> str:
        return self.settings.normalized_base_url() + "/" + path.lstrip("/")


def _decode_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _iter_sse_events(response: Any, *, deadline: float | None = None) -> Any:
    event_name = "message"
    event_id: str | None = None
    data_lines: list[str] = []
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise AcceptanceError("sse_stream_timeout")
        raw_line = response.readline()
        if raw_line == b"" or raw_line == "":
            break
        if deadline is not None and time.monotonic() >= deadline:
            raise AcceptanceError("sse_stream_timeout")
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r\n")
        if not line:
            if data_lines:
                data_text = "\n".join(data_lines)
                payload = _decode_json(data_text)
                yield {
                    "event": event_name,
                    "event_type": event_name,
                    "data": payload if payload is not None else data_text,
                    "id": event_id,
                }
            event_name = "message"
            event_id = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
        elif field == "id":
            event_id = value
    if data_lines:
        data_text = "\n".join(data_lines)
        payload = _decode_json(data_text)
        yield {
            "event": event_name,
            "event_type": event_name,
            "data": payload if payload is not None else data_text,
            "id": event_id,
        }


def _stringify_output(output: Any) -> str:
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(output)


def _contains_nested_entry_contract_error(text: str) -> bool:
    return (
        "workflow_input_required_missing:profile.name" in text
        or "workflow_input_type_mismatch:items[0].score:integer" in text
    )


def _check_workflow_frontend_contribution(frontend: dict[str, Any]) -> dict[str, Any]:
    app_tabs = frontend.get("app_tabs")
    if not isinstance(app_tabs, list):
        raise AcceptanceError("plugin_contribution_app_tabs_invalid")
    app_panels = frontend.get("app_panels")
    if not isinstance(app_panels, list):
        raise AcceptanceError("plugin_contribution_app_panels_invalid")
    sidebar_items = frontend.get("sidebar_items")
    if not isinstance(sidebar_items, list):
        raise AcceptanceError("plugin_contribution_sidebar_items_invalid")

    tabs_by_name = {
        str(tab.get("tab")): tab
        for tab in app_tabs
        if isinstance(tab, dict) and tab.get("tab") not in (None, "")
    }
    panels_by_id = {
        str(panel.get("id")): panel
        for panel in app_panels
        if isinstance(panel, dict) and panel.get("id") not in (None, "")
    }

    paths: dict[str, str] = {}
    panels: dict[str, str] = {}
    insert_after: dict[str, str] = {}
    for expected in EXPECTED_WORKFLOW_APP_TABS:
        tab_name = expected["tab"]
        tab = tabs_by_name.get(tab_name)
        if tab is None:
            raise AcceptanceError(f"plugin_contribution_missing_tab:{tab_name}")
        _check_workflow_tab(tab, expected)
        paths[tab_name] = expected["path"]
        panels[tab_name] = expected["panel"]
        insert_after[tab_name] = expected["insert_after"]

        panel = panels_by_id.get(expected["panel"])
        if panel is None:
            raise AcceptanceError(f"plugin_contribution_missing_panel:{expected['panel']}")
        _check_workflow_panel(panel, expected)

    sidebar = _find_workflow_sidebar(sidebar_items)
    sidebar_permissions = _list_strings(sidebar.get("permissions"))
    if EXPECTED_WORKFLOW_SIDEBAR_ICON != sidebar.get("icon"):
        raise AcceptanceError(f"plugin_contribution_sidebar_icon_mismatch:{EXPECTED_WORKFLOW_SIDEBAR_PATH}")
    if "workflow:read" not in sidebar_permissions:
        raise AcceptanceError(f"plugin_contribution_sidebar_permission_missing:{EXPECTED_WORKFLOW_SIDEBAR_PATH}")

    return {
        "tabs": [expected["tab"] for expected in EXPECTED_WORKFLOW_APP_TABS],
        "paths": paths,
        "panels": panels,
        "peer_insert_after": insert_after["workflows"],
        "editor_insert_after": insert_after["workflows-editor"],
        "run_insert_after": insert_after["workflows-run"],
        "sidebar_path": EXPECTED_WORKFLOW_SIDEBAR_PATH,
        "sidebar_icon": sidebar.get("icon"),
        "sidebar_permissions": sidebar_permissions,
    }


def _check_workflow_tab(tab: dict[str, Any], expected: dict[str, str]) -> None:
    tab_name = expected["tab"]
    if tab.get("path") != expected["path"]:
        raise AcceptanceError(f"plugin_contribution_tab_path_mismatch:{tab_name}")
    if tab.get("insert_after") != expected["insert_after"]:
        raise AcceptanceError(f"plugin_contribution_tab_insert_after_mismatch:{tab_name}")
    if tab.get("panel") != expected["panel"]:
        raise AcceptanceError(f"plugin_contribution_tab_panel_mismatch:{tab_name}")
    if "workflow:read" not in _list_strings(tab.get("permissions")):
        raise AcceptanceError(f"plugin_contribution_tab_permission_missing:{tab_name}")


def _check_workflow_panel(panel: dict[str, Any], expected: dict[str, str]) -> None:
    tab_name = expected["tab"]
    if panel.get("tab") != tab_name:
        raise AcceptanceError(f"plugin_contribution_panel_tab_mismatch:{expected['panel']}")
    if panel.get("renderer") != WORKFLOW_PANEL_RENDERER:
        raise AcceptanceError(f"plugin_contribution_renderer_mismatch:{expected['panel']}")


def _find_workflow_sidebar(sidebar_items: list[Any]) -> dict[str, Any]:
    for item in sidebar_items:
        if isinstance(item, dict) and item.get("path") == EXPECTED_WORKFLOW_SIDEBAR_PATH:
            return item
    raise AcceptanceError(f"plugin_contribution_missing_sidebar:{EXPECTED_WORKFLOW_SIDEBAR_PATH}")


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _find_plugin(plugins: Any, plugin_id: str) -> dict[str, Any]:
    if not isinstance(plugins, list):
        raise AcceptanceError("plugin_contributions_failed:plugins_not_list")
    for plugin in plugins:
        if isinstance(plugin, dict) and plugin.get("plugin_id") == plugin_id:
            return plugin
    raise AcceptanceError(f"plugin_contribution_missing:{plugin_id}")


def _workflow_session_event_data(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_name = event.get("event") or event.get("event_type") or event.get("type")
    data = event.get("data") if isinstance(event.get("data"), dict) else event.get("payload")
    if event_name != "workflow:run" or not isinstance(data, dict):
        return None
    return data


def _check_workflow_output_contract_payload(payload: dict[str, Any], *, source: str) -> None:
    io_contract = payload.get("io_contract")
    if not isinstance(io_contract, dict):
        raise AcceptanceError(f"{source}_workflow_io_contract_missing:{payload}")
    output_schema = io_contract.get("output_schema")
    if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
        raise AcceptanceError(f"{source}_workflow_output_schema_invalid:{payload}")
    properties = output_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise AcceptanceError(f"{source}_workflow_output_schema_properties_missing:{payload}")
    output_contract = payload.get("output_contract")
    if not isinstance(output_contract, dict):
        raise AcceptanceError(f"{source}_workflow_output_contract_missing:{payload}")
    if not isinstance(output_contract.get("valid"), bool):
        raise AcceptanceError(f"{source}_workflow_output_contract_valid_invalid:{payload}")
    declared_fields = output_contract.get("declared_fields")
    if not isinstance(declared_fields, list):
        raise AcceptanceError(f"{source}_workflow_output_contract_declared_fields_invalid:{payload}")
    missing_declared = sorted(str(field) for field in properties if field not in declared_fields)
    if missing_declared:
        raise AcceptanceError(
            f"{source}_workflow_output_contract_declared_fields_missing:{missing_declared}:{payload}"
        )
    for key in ("required_fields", "missing_required", "extra_fields"):
        if not isinstance(output_contract.get(key), list):
            raise AcceptanceError(f"{source}_workflow_output_contract_{key}_invalid:{payload}")
    missing_required = output_contract.get("missing_required")
    if any(not isinstance(item, str) or not item for item in missing_required):
        raise AcceptanceError(f"{source}_workflow_output_contract_missing_required_item_invalid:{payload}")
    type_mismatches = output_contract.get("type_mismatches")
    if not isinstance(type_mismatches, list):
        raise AcceptanceError(f"{source}_workflow_output_contract_type_mismatches_invalid:{payload}")
    if any(
        not isinstance(item, dict)
        or not item.get("field")
        or "expected" not in item
        or "actual" not in item
        for item in type_mismatches
    ):
        raise AcceptanceError(f"{source}_workflow_output_contract_type_mismatch_item_invalid:{payload}")
    if output_contract.get("valid") is False and not missing_required and not type_mismatches:
        raise AcceptanceError(f"{source}_workflow_output_contract_failure_detail_missing:{payload}")

    expected_paths = _workflow_output_schema_field_paths(output_schema)
    declared_field_paths = output_contract.get("declared_field_paths")
    if not isinstance(declared_field_paths, list):
        raise AcceptanceError(f"{source}_workflow_output_contract_declared_field_paths_invalid:{payload}")
    missing_declared_paths = sorted(path for path in expected_paths if path not in declared_field_paths)
    if missing_declared_paths:
        raise AcceptanceError(
            f"{source}_workflow_output_contract_declared_field_paths_missing:{missing_declared_paths}:{payload}"
        )
    required_field_paths = output_contract.get("required_field_paths")
    if not isinstance(required_field_paths, list):
        raise AcceptanceError(f"{source}_workflow_output_contract_required_field_paths_invalid:{payload}")
    expected_required_paths = _workflow_output_schema_required_field_paths(output_schema)
    missing_required_paths = sorted(path for path in expected_required_paths if path not in required_field_paths)
    if missing_required_paths:
        raise AcceptanceError(
            f"{source}_workflow_output_contract_required_field_paths_missing:{missing_required_paths}:{payload}"
        )


def _check_workflow_saved_version_boundary(
    payload: dict[str, Any],
    *,
    source: str,
    workflow_id: str,
    version_id: str,
) -> None:
    io_contract = payload.get("io_contract")
    if not isinstance(io_contract, dict):
        raise AcceptanceError(f"{source}_workflow_io_contract_missing:{payload}")
    if io_contract.get("plugin_id") != PLUGIN_ID:
        raise AcceptanceError(f"{source}_workflow_io_contract_plugin_unexpected:{payload}")
    if io_contract.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_io_contract_workflow_mismatch:{workflow_id}:{payload}")
    if io_contract.get("version_id") != version_id:
        raise AcceptanceError(f"{source}_workflow_io_contract_version_mismatch:{version_id}:{payload}")
    input_schema = io_contract.get("input_schema")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
        raise AcceptanceError(f"{source}_workflow_input_schema_invalid:{payload}")
    output_schema = io_contract.get("output_schema")
    if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
        raise AcceptanceError(f"{source}_workflow_output_schema_invalid:{payload}")
    if not isinstance(output_schema.get("properties"), dict):
        raise AcceptanceError(f"{source}_workflow_output_schema_properties_missing:{payload}")
    _check_workflow_result_interface(
        payload,
        source=source,
        workflow_id=workflow_id,
        run_id=None,
    )


def _workflow_next_action(payload: dict[str, Any]) -> dict[str, Any] | None:
    action = payload.get("next_action")
    return action if isinstance(action, dict) else None


def _workflow_next_action_type(payload: dict[str, Any]) -> str | None:
    action = _workflow_next_action(payload)
    value = action.get("type") if action else None
    return str(value) if value else None


def _workflow_next_action_reason(payload: dict[str, Any]) -> str | None:
    action = _workflow_next_action(payload)
    value = action.get("reason") if action else None
    return str(value) if value else None


def _check_workflow_next_action_payload(
    payload: dict[str, Any],
    *,
    source: str,
    expected_type: str,
    expected_field: str,
    expected_reason: str,
) -> None:
    action = _workflow_next_action(payload)
    if action is None:
        raise AcceptanceError(f"{source}_workflow_next_action_missing:{payload}")
    if action.get("type") != expected_type:
        raise AcceptanceError(f"{source}_workflow_next_action_type_unexpected:{expected_type}:{payload}")
    if action.get("field") != expected_field:
        raise AcceptanceError(f"{source}_workflow_next_action_field_unexpected:{expected_field}:{payload}")
    if action.get("reason") != expected_reason:
        raise AcceptanceError(f"{source}_workflow_next_action_reason_unexpected:{expected_reason}:{payload}")


def _check_workflow_result_interface(
    payload: dict[str, Any],
    *,
    source: str,
    workflow_id: str,
    run_id: Any,
) -> None:
    contract = payload.get("interface")
    if not isinstance(contract, dict):
        raise AcceptanceError(f"{source}_workflow_interface_missing:{payload}")
    entry = contract.get("entry")
    if not isinstance(entry, dict):
        raise AcceptanceError(f"{source}_workflow_interface_entry_missing:{payload}")
    if entry.get("type") != "workflow.input":
        raise AcceptanceError(f"{source}_workflow_interface_entry_type_unexpected:{payload}")
    if entry.get("tool") != "workflow_run" or entry.get("argument") != "input":
        raise AcceptanceError(f"{source}_workflow_interface_entry_tool_unexpected:{payload}")
    if entry.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_entry_workflow_mismatch:{workflow_id}:{payload}")
    if entry.get("schema_tool") != "workflow_get_schema" or entry.get("schema_field") != "input_schema":
        raise AcceptanceError(f"{source}_workflow_interface_entry_schema_unexpected:{payload}")

    exit_contract = contract.get("exit")
    if not isinstance(exit_contract, dict):
        raise AcceptanceError(f"{source}_workflow_interface_exit_missing:{payload}")
    if exit_contract.get("type") != "workflow.output" or exit_contract.get("field") != "output":
        raise AcceptanceError(f"{source}_workflow_interface_exit_unexpected:{payload}")
    if (
        exit_contract.get("schema_tool") != "workflow_get_schema"
        or exit_contract.get("schema_field") != "output_schema"
    ):
        raise AcceptanceError(f"{source}_workflow_interface_exit_schema_unexpected:{payload}")

    debug = contract.get("debug")
    if not isinstance(debug, dict):
        raise AcceptanceError(f"{source}_workflow_interface_debug_missing:{payload}")
    if debug.get("tool") != "workflow_get_run" or debug.get("events_field") != "events":
        raise AcceptanceError(f"{source}_workflow_interface_debug_tool_unexpected:{payload}")
    if debug.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_debug_workflow_mismatch:{workflow_id}:{payload}")
    if debug.get("run_id") != run_id:
        raise AcceptanceError(f"{source}_workflow_interface_debug_run_mismatch:{run_id}:{payload}")


def _check_workflow_callable_interface(
    payload: dict[str, Any],
    *,
    source: str,
    workflow_id: str,
) -> None:
    contract = payload.get("interface")
    if not isinstance(contract, dict):
        raise AcceptanceError(f"{source}_workflow_interface_missing:{payload}")
    entry = contract.get("entry")
    if not isinstance(entry, dict):
        raise AcceptanceError(f"{source}_workflow_interface_entry_missing:{payload}")
    if entry.get("type") != "workflow.input":
        raise AcceptanceError(f"{source}_workflow_interface_entry_type_unexpected:{payload}")
    if entry.get("tool") != "workflow_run" or entry.get("argument") != "input":
        raise AcceptanceError(f"{source}_workflow_interface_entry_tool_unexpected:{payload}")
    if entry.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_entry_workflow_mismatch:{workflow_id}:{payload}")
    if entry.get("schema_tool") != "workflow_get_schema" or entry.get("schema_field") != "input_schema":
        raise AcceptanceError(f"{source}_workflow_interface_entry_schema_unexpected:{payload}")

    exit_contract = contract.get("exit")
    if not isinstance(exit_contract, dict):
        raise AcceptanceError(f"{source}_workflow_interface_exit_missing:{payload}")
    if exit_contract.get("type") != "workflow.output" or exit_contract.get("field") != "output":
        raise AcceptanceError(f"{source}_workflow_interface_exit_unexpected:{payload}")
    if (
        exit_contract.get("schema_tool") != "workflow_get_schema"
        or exit_contract.get("schema_field") != "output_schema"
    ):
        raise AcceptanceError(f"{source}_workflow_interface_exit_schema_unexpected:{payload}")

    schema = contract.get("schema")
    if not isinstance(schema, dict):
        raise AcceptanceError(f"{source}_workflow_interface_schema_missing:{payload}")
    if schema.get("tool") != "workflow_get_schema" or schema.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_schema_unexpected:{payload}")
    if schema.get("input_schema_field") != "input_schema" or schema.get("output_schema_field") != "output_schema":
        raise AcceptanceError(f"{source}_workflow_interface_schema_fields_unexpected:{payload}")

    run = contract.get("run")
    if not isinstance(run, dict):
        raise AcceptanceError(f"{source}_workflow_interface_run_missing:{payload}")
    if run.get("tool") != "workflow_run" or run.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_run_unexpected:{payload}")
    if run.get("input_argument") != "input" or run.get("output_field") != "output":
        raise AcceptanceError(f"{source}_workflow_interface_run_fields_unexpected:{payload}")

    debug = contract.get("debug")
    if not isinstance(debug, dict):
        raise AcceptanceError(f"{source}_workflow_interface_debug_missing:{payload}")
    if debug.get("tool") != "workflow_get_run" or debug.get("run_id_field") != "run_id":
        raise AcceptanceError(f"{source}_workflow_interface_debug_tool_unexpected:{payload}")
    if debug.get("workflow_id") != workflow_id:
        raise AcceptanceError(f"{source}_workflow_interface_debug_workflow_mismatch:{workflow_id}:{payload}")


def _workflow_output_schema_field_paths(schema: dict[str, Any], *, prefix: str = "") -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    ordered_fields = [str(field) for field in sorted(required) if str(field) in properties]
    ordered_fields.extend(
        field for field in sorted(str(field) for field in properties) if field not in ordered_fields
    )
    paths: list[str] = []
    for field_name in ordered_fields:
        raw_schema = properties.get(field_name)
        child_schema = raw_schema if isinstance(raw_schema, dict) else {}
        path = f"{prefix}.{field_name}" if prefix else field_name
        field_type = _workflow_output_schema_type(child_schema)
        if field_type == "object":
            nested = _workflow_output_schema_field_paths(child_schema, prefix=path)
            paths.extend(nested or [path])
        elif field_type == "array":
            item_schema = child_schema.get("items")
            nested = _workflow_output_schema_field_paths(
                item_schema if isinstance(item_schema, dict) else {},
                prefix=f"{path}[]",
            )
            paths.extend(nested or [path])
        else:
            paths.append(path)
    return paths


def _workflow_output_schema_required_field_paths(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    required_roots = {str(field) for field in required if field}
    return [
        path
        for path in _workflow_output_schema_field_paths(schema)
        if path.split(".", 1)[0].removesuffix("[]") in required_roots
    ]


def _workflow_output_schema_type(schema: dict[str, Any]) -> str:
    raw_type = schema.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    if isinstance(schema.get("properties"), dict):
        return "object"
    if isinstance(schema.get("items"), dict):
        return "array"
    return "unknown"


def _match_workflow_session_event(
    event: Any,
    workflow_id: str,
    *,
    version_id: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    data = _workflow_session_event_data(event)
    if data is None:
        return False, None
    if data.get("plugin_id") != PLUGIN_ID or data.get("workflow_id") != workflow_id:
        return False, None
    if version_id is not None and data.get("version_id") != version_id:
        return False, {"expected": version_id, "actual": data.get("version_id"), "event": event}
    return True, None


def _has_workflow_success_event(events: Any) -> bool:
    if not isinstance(events, list):
        return False
    return any(
        isinstance(event, dict)
        and (event.get("event_type") or event.get("event") or event.get("type")) == "run_succeeded"
        for event in events
    )


def _has_workflow_started_event(events: Any) -> bool:
    if not isinstance(events, list):
        return False
    return any(
        isinstance(event, dict)
        and (event.get("event_type") or event.get("event") or event.get("type")) == "run_started"
        for event in events
    )


def _has_node_finished_event(events: Any, node_type: str) -> bool:
    if not isinstance(events, list):
        return False
    return any(
        isinstance(event, dict)
        and (event.get("event_type") or event.get("event") or event.get("type")) == "node_finished"
        and event.get("node_type") == node_type
        for event in events
    )


def _workflow_event_node_counts(events: Any) -> dict[str, int]:
    if not isinstance(events, list):
        return {}
    counts: dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        node_id = str(event.get("node_id") or "").strip()
        if not node_id:
            continue
        counts[node_id] = counts.get(node_id, 0) + 1
    return counts


def _scheduled_task_run_output(run: dict[str, Any]) -> dict[str, Any]:
    output = run.get("output_result")
    return output if isinstance(output, dict) else {}


def _scheduled_task_run_session_id(run: dict[str, Any]) -> str | None:
    output = _scheduled_task_run_output(run)
    value = run.get("session_id") or output.get("session_id")
    return str(value) if value else None


def _scheduled_task_run_trace_id(run: dict[str, Any]) -> str | None:
    output = _scheduled_task_run_output(run)
    value = run.get("trace_id") or output.get("trace_id")
    return str(value) if value else None


def _scheduled_task_run_event_run_id(
    run: dict[str, Any],
    trigger_response: dict[str, Any],
) -> str | None:
    output = _scheduled_task_run_output(run)
    value = run.get("id") or trigger_response.get("run_id") or output.get("run_id")
    return str(value) if value else None


def _is_workflow_session_event(
    event: Any,
    workflow_id: str,
    *,
    version_id: str | None = None,
) -> bool:
    data = _workflow_session_event_data(event)
    if data is None:
        return False
    if data.get("plugin_id") != PLUGIN_ID or data.get("workflow_id") != workflow_id:
        return False
    if version_id is not None and data.get("version_id") != version_id:
        return False
    return True


def require_key(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not value:
        raise AcceptanceError(f"missing_required_response_key:{key}:{payload}")
    return str(value)


def fixture_expected_input_fields(fixture: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    nodes = _fixture_nodes(fixture)
    produced_fields = _fixture_produced_fields(nodes)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = _fixture_node_type(node)
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        if node_type == "start":
            fields.update(_fixture_start_fields(data))
            continue
        for candidate in _fixture_input_candidates(data):
            field = _fixture_field_name(candidate)
            if field and field not in produced_fields and field not in INTERNAL_TEMPLATE_KEYS:
                fields.add(field)
    return fields


def fixture_expected_node_event_ids(fixture: dict[str, Any]) -> set[str]:
    node_ids: set[str] = set()
    for node in _fixture_nodes(fixture):
        if not isinstance(node, dict):
            continue
        node_type = _fixture_node_type(node)
        node_id = str(node.get("id") or "").strip()
        if node_id and node_type != "start":
            node_ids.add(node_id)
    return node_ids


def sample_input_for_fields(fields: set[str]) -> dict[str, Any]:
    selected_fields = set(fields) or {"items"}
    return {field: _sample_value_for_field(field) for field in sorted(selected_fields)}


def _workflow_input_payload(workflow_input: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(workflow_input, dict):
        return dict(workflow_input)
    return sample_input_for_fields({"items"})


def _fixture_nodes(fixture: dict[str, Any]) -> list[Any]:
    workflow = fixture.get("workflow") if isinstance(fixture.get("workflow"), dict) else fixture
    graph = workflow.get("graph") if isinstance(workflow, dict) and isinstance(workflow.get("graph"), dict) else workflow
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    return nodes if isinstance(nodes, list) else []


def _fixture_node_type(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(node.get("type") or data.get("type") or "")


def _fixture_start_fields(data: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for key in ("input_schema", "inputSchema", "schema", "parameters"):
        raw_schema = data.get(key)
        properties = raw_schema.get("properties") if isinstance(raw_schema, dict) else None
        if isinstance(properties, dict):
            fields.update(str(name) for name in properties if name)
    for key in ("variables", "inputs"):
        for item in _fixture_start_variable_items(data.get(key)):
            name = _fixture_start_variable_name(item)
            if name:
                fields.add(name)
    return fields


def _fixture_start_variable_items(raw_items: Any) -> list[dict[str, Any]]:
    if isinstance(raw_items, list):
        return [item for item in raw_items if isinstance(item, dict)]
    if isinstance(raw_items, dict):
        items: list[dict[str, Any]] = []
        for name, raw_item in raw_items.items():
            item = dict(raw_item) if isinstance(raw_item, dict) else {"type": raw_item}
            item.setdefault("name", str(name))
            items.append(item)
        return items
    return []


def _fixture_start_variable_name(item: dict[str, Any]) -> str:
    for key in (
        "variable",
        "name",
        "key",
        "field",
        "field_name",
        "fieldName",
        "parameter",
        "parameter_name",
        "parameterName",
        "id",
        "label",
    ):
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _fixture_input_candidates(value: Any) -> set[str]:
    candidates: set[str] = set()
    if isinstance(value, str):
        candidates.update(_fixture_template_variables(value))
        return candidates
    if isinstance(value, list):
        for item in value:
            candidates.update(_fixture_input_candidates(item))
        return candidates
    if not isinstance(value, dict):
        return candidates
    for key, item in value.items():
        if _fixture_is_selector_key(str(key)):
            candidates.add(_fixture_selector_to_key(item))
        else:
            candidates.update(_fixture_input_candidates(item))
    return candidates


def _fixture_template_variables(template: str) -> set[str]:
    result: set[str] = set()
    for match in TEMPLATE_PATTERN.finditer(template):
        raw = match.group(1).strip().strip("#").strip()
        if raw:
            result.add(raw)
    return result


def _fixture_is_selector_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized.endswith("selector") or normalized in {
        "variable_selector",
        "variableselector",
        "query_variable_selector",
        "queryvariableselector",
        "iterator_selector",
        "iteratorselector",
        "input_selector",
        "inputselector",
        "selector",
    }


def _fixture_selector_to_key(selector: Any) -> str:
    if isinstance(selector, list):
        return ".".join(str(part) for part in selector if part not in (None, ""))
    if isinstance(selector, str):
        return selector.strip()
    return ""


def _fixture_field_name(candidate: str) -> str:
    normalized = candidate.replace("#", ".").strip(".").strip()
    normalized = re.sub(r"\[(\d+)\]", r".\1", normalized)
    normalized = SYSTEM_INPUT_ALIASES.get(normalized, normalized)
    if not normalized:
        return ""
    return normalized.split(".", 1)[0]


def _fixture_produced_fields(nodes: list[Any]) -> set[str]:
    produced: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = _fixture_node_type(node)
        node_id = str(node.get("id") or "")
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        produced.update(FIXTURE_NODE_OUTPUT_DEFAULTS.get(node_type, set()))
        if node_id and node_type != "start":
            produced.add(node_id)
        output_key = data.get("output_key") or data.get("outputKey") or data.get("variable") or data.get("name")
        if output_key:
            produced.add(str(output_key))
        if node_type in {"variable_assign", "variable-assigner"}:
            produced.update(_fixture_variable_assign_outputs(data))
    return produced


def _fixture_variable_assign_outputs(data: dict[str, Any]) -> set[str]:
    outputs: set[str] = set()
    for item in _fixture_assignment_items(data):
        name = _fixture_assignment_target_name(item)
        if name:
            outputs.add(name)
    assignments = data.get("assignments")
    if isinstance(assignments, dict):
        outputs.update(str(key) for key in assignments)
    return outputs


def _fixture_assignment_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in (
        "variables",
        "items",
        "assignments",
        "variable_assignments",
        "variableAssignments",
        "assignment_items",
        "assignmentItems",
    ):
        value = data.get(key)
        if key == "assignments" and isinstance(value, dict):
            continue
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            for name, raw_item in value.items():
                item = dict(raw_item) if isinstance(raw_item, dict) else {"value": raw_item}
                item.setdefault("name", str(name))
                items.append(item)
    return items


def _fixture_assignment_target_name(item: dict[str, Any]) -> str:
    for key in (
        "variable",
        "name",
        "key",
        "output_key",
        "outputKey",
        "target_variable",
        "targetVariable",
        "assigned_variable",
        "assignedVariable",
        "assigned_variable_selector",
        "assignedVariableSelector",
        "variable_selector",
        "variableSelector",
        "target",
        "selector",
    ):
        value = item.get(key)
        if value in (None, "", [], {}):
            continue
        return _fixture_selector_to_key(value) if isinstance(value, list) else str(value)
    return ""


def _sample_value_for_field(field: str) -> Any:
    if field in {"items", "documents"} or field.endswith("_ids"):
        return ["alpha", "beta", "gamma"]
    if field in {"retrieval", "limits"}:
        return {"limit": 3, "threshold": 0.1, "max": 2}
    if field in {"query", "message", "input", "name"}:
        return f"acceptance {field}"
    return f"acceptance {field}"


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise AcceptanceError(f"fixture_unreadable:{path}:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"fixture_invalid_json:{path}:{exc}") from exc
    if not isinstance(data, dict):
        raise AcceptanceError(f"fixture_invalid_shape:{path}")
    return data


def read_token_file(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise AcceptanceError(f"token_file_unreadable:{path}:{exc}") from exc
    if not raw:
        raise AcceptanceError(f"token_file_empty:{path}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if not isinstance(payload, dict):
        raise AcceptanceError(f"token_file_invalid_shape:{path}")
    token = payload.get("access_token") or payload.get("token")
    if not isinstance(token, str) or not token.strip():
        raise AcceptanceError(f"token_file_missing_access_token:{path}")
    return token.strip()


def write_json_output(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        raise AcceptanceError(f"output_file_unwritable:{path}:{exc}") from exc


def settings_from_env() -> AcceptanceSettings:
    settings = AcceptanceSettings(
        base_url=os.getenv("LAMBCHAT_BASE_URL", DEFAULT_BASE_URL),
        token=os.getenv("LAMBCHAT_TOKEN"),
        token_file=Path(token_file) if (token_file := os.getenv("LAMBCHAT_TOKEN_FILE")) else None,
        username=os.getenv("LAMBCHAT_USERNAME"),
        password=os.getenv("LAMBCHAT_PASSWORD"),
        fixture_path=Path(os.getenv("LAMBCHAT_ACCEPTANCE_FIXTURE", str(DEFAULT_FIXTURE))),
        human_approval_fixture_path=Path(
            os.getenv("LAMBCHAT_ACCEPTANCE_HUMAN_APPROVAL_FIXTURE", str(DEFAULT_HUMAN_APPROVAL_FIXTURE))
        ),
        version_run_v1_fixture_path=Path(
            os.getenv("LAMBCHAT_ACCEPTANCE_VERSION_RUN_V1_FIXTURE", str(DEFAULT_VERSION_RUN_V1_FIXTURE))
        ),
        version_run_v2_fixture_path=Path(
            os.getenv("LAMBCHAT_ACCEPTANCE_VERSION_RUN_V2_FIXTURE", str(DEFAULT_VERSION_RUN_V2_FIXTURE))
        ),
        knowledge_retrieval_fixture_path=Path(
            os.getenv("LAMBCHAT_ACCEPTANCE_KNOWLEDGE_RETRIEVAL_FIXTURE", str(DEFAULT_KNOWLEDGE_RETRIEVAL_FIXTURE))
        ),
        llm_fixture_path=Path(os.getenv("LAMBCHAT_ACCEPTANCE_LLM_FIXTURE", str(DEFAULT_LLM_FIXTURE))),
        nested_entry_contract_fixture_path=Path(
            os.getenv(
                "LAMBCHAT_ACCEPTANCE_NESTED_ENTRY_CONTRACT_FIXTURE",
                str(DEFAULT_NESTED_ENTRY_CONTRACT_FIXTURE),
            )
        ),
        request_timeout=float(os.getenv("LAMBCHAT_ACCEPTANCE_REQUEST_TIMEOUT", "15")),
        async_timeout=float(os.getenv("LAMBCHAT_ACCEPTANCE_ASYNC_TIMEOUT", "60")),
        poll_interval=float(os.getenv("LAMBCHAT_ACCEPTANCE_POLL_INTERVAL", "1")),
        output_file=Path(output_file) if (output_file := os.getenv("LAMBCHAT_ACCEPTANCE_OUTPUT_FILE")) else None,
        skip_async=os.getenv("LAMBCHAT_ACCEPTANCE_SKIP_ASYNC", "").lower() in {"1", "true", "yes"},
        include_chat=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_CHAT", "").lower() in {"1", "true", "yes"},
        include_failed_pre_run=(
            os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_FAILED_PRE_RUN", "").lower() in {"1", "true", "yes"}
        ),
        include_agent_team=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_AGENT_TEAM", "").lower() in {"1", "true", "yes"},
        agent_team_id=os.getenv("LAMBCHAT_ACCEPTANCE_AGENT_TEAM_ID"),
        include_scheduled_task=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_SCHEDULED_TASK", "").lower() in {"1", "true", "yes"},
        include_tool_discovery=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_TOOL_DISCOVERY", "").lower() in {"1", "true", "yes"},
        include_human_approval=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_HUMAN_APPROVAL", "").lower() in {"1", "true", "yes"},
        include_version_run=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_VERSION_RUN", "").lower() in {"1", "true", "yes"},
        include_knowledge_retrieval=(
            os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_KNOWLEDGE_RETRIEVAL", "").lower() in {"1", "true", "yes"}
        ),
        include_llm=os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_LLM", "").lower() in {"1", "true", "yes"},
        include_nested_entry_contract=(
            os.getenv("LAMBCHAT_ACCEPTANCE_INCLUDE_NESTED_ENTRY_CONTRACT", "").lower() in {"1", "true", "yes"}
        ),
        verify_persistence=os.getenv("LAMBCHAT_ACCEPTANCE_VERIFY_PERSISTENCE", "").lower() in {"1", "true", "yes"},
        test_disable_enable=os.getenv("LAMBCHAT_ACCEPTANCE_TEST_DISABLE_ENABLE", "").lower() in {"1", "true", "yes"},
        restart_command=os.getenv("LAMBCHAT_ACCEPTANCE_RESTART_COMMAND"),
        restart_wait=float(os.getenv("LAMBCHAT_ACCEPTANCE_RESTART_WAIT", "5")),
        restart_timeout=float(os.getenv("LAMBCHAT_ACCEPTANCE_RESTART_TIMEOUT", "90")),
    )
    return apply_acceptance_profile(
        settings,
        os.getenv("LAMBCHAT_ACCEPTANCE_PROFILE", "").strip().lower(),
    )


def apply_acceptance_profile(settings: AcceptanceSettings, profile: str | None) -> AcceptanceSettings:
    if not profile:
        return settings
    if profile not in ACCEPTANCE_PROFILES:
        raise AcceptanceError(f"acceptance_profile_unknown:{profile}")
    settings.include_chat = True
    settings.include_failed_pre_run = True
    settings.include_agent_team = True
    settings.include_scheduled_task = True
    settings.include_tool_discovery = True
    settings.include_human_approval = True
    settings.include_version_run = True
    settings.include_knowledge_retrieval = True
    settings.include_llm = True
    settings.include_nested_entry_contract = True
    settings.verify_persistence = True
    settings.test_disable_enable = True
    return settings


def parse_args(argv: list[str]) -> AcceptanceSettings:
    defaults = settings_from_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(ACCEPTANCE_PROFILES),
        default=os.getenv("LAMBCHAT_ACCEPTANCE_PROFILE", "").strip().lower() or None,
        help="Use a bundled acceptance profile. 'full' and 'final' enable every optional final-deployment check.",
    )
    parser.add_argument("--base-url", default=defaults.base_url)
    parser.add_argument("--token", default=defaults.token)
    parser.add_argument("--token-file", type=Path, default=defaults.token_file)
    parser.add_argument("--username", default=defaults.username)
    parser.add_argument("--password", default=defaults.password)
    parser.add_argument("--fixture", type=Path, default=defaults.fixture_path)
    parser.add_argument("--human-approval-fixture", type=Path, default=defaults.human_approval_fixture_path)
    parser.add_argument("--version-run-v1-fixture", type=Path, default=defaults.version_run_v1_fixture_path)
    parser.add_argument("--version-run-v2-fixture", type=Path, default=defaults.version_run_v2_fixture_path)
    parser.add_argument("--knowledge-retrieval-fixture", type=Path, default=defaults.knowledge_retrieval_fixture_path)
    parser.add_argument("--llm-fixture", type=Path, default=defaults.llm_fixture_path)
    parser.add_argument(
        "--nested-entry-contract-fixture",
        type=Path,
        default=defaults.nested_entry_contract_fixture_path,
    )
    parser.add_argument("--request-timeout", type=float, default=defaults.request_timeout)
    parser.add_argument("--async-timeout", type=float, default=defaults.async_timeout)
    parser.add_argument("--poll-interval", type=float, default=defaults.poll_interval)
    parser.add_argument(
        "--output-file",
        type=Path,
        default=defaults.output_file,
        help="Write the JSON success or failure result to a file for deployment evidence.",
    )
    parser.add_argument("--skip-async", action="store_true", default=defaults.skip_async)
    parser.add_argument("--include-chat", action="store_true", default=defaults.include_chat)
    parser.add_argument(
        "--include-failed-pre-run",
        action="store_true",
        default=defaults.include_failed_pre_run,
        help=(
            "Verify that a missing selected Workflow workflow emits a failed workflow:run event "
            "without aborting chat; requires chat/agent permissions."
        ),
    )
    parser.add_argument("--include-agent-team", action="store_true", default=defaults.include_agent_team)
    parser.add_argument("--agent-team-id", default=defaults.agent_team_id)
    parser.add_argument("--include-scheduled-task", action="store_true", default=defaults.include_scheduled_task)
    parser.add_argument(
        "--include-tool-discovery",
        action="store_true",
        default=defaults.include_tool_discovery,
        help=(
            "Discover and invoke workflow_list, workflow_get_schema, workflow_get_run, and workflow_run "
            "through lambchat_internal; requires mcp:admin plus workflow permissions."
        ),
    )
    parser.add_argument("--include-human-approval", action="store_true", default=defaults.include_human_approval)
    parser.add_argument("--include-version-run", action="store_true", default=defaults.include_version_run)
    parser.add_argument(
        "--include-knowledge-retrieval",
        action="store_true",
        default=defaults.include_knowledge_retrieval,
        help="Import, publish, and run the knowledge retrieval fixture against the deployed retrieval backend.",
    )
    parser.add_argument(
        "--include-llm",
        action="store_true",
        default=defaults.include_llm,
        help="Import, publish, and run the LLM fixture against the deployed model configuration.",
    )
    parser.add_argument(
        "--include-nested-entry-contract",
        action="store_true",
        default=defaults.include_nested_entry_contract,
        help="Import a nested-input workflow and verify invalid nested input is rejected with path-level detail.",
    )
    parser.add_argument("--verify-persistence", action="store_true", default=defaults.verify_persistence)
    parser.add_argument("--test-disable-enable", action="store_true", default=defaults.test_disable_enable)
    parser.add_argument("--restart-command", default=defaults.restart_command)
    parser.add_argument("--restart-wait", type=float, default=defaults.restart_wait)
    parser.add_argument("--restart-timeout", type=float, default=defaults.restart_timeout)
    args = parser.parse_args(argv)
    settings = AcceptanceSettings(
        base_url=args.base_url,
        token=args.token,
        token_file=args.token_file,
        username=args.username,
        password=args.password,
        fixture_path=args.fixture,
        human_approval_fixture_path=args.human_approval_fixture,
        version_run_v1_fixture_path=args.version_run_v1_fixture,
        version_run_v2_fixture_path=args.version_run_v2_fixture,
        knowledge_retrieval_fixture_path=args.knowledge_retrieval_fixture,
        llm_fixture_path=args.llm_fixture,
        nested_entry_contract_fixture_path=args.nested_entry_contract_fixture,
        request_timeout=args.request_timeout,
        async_timeout=args.async_timeout,
        poll_interval=args.poll_interval,
        output_file=args.output_file,
        skip_async=args.skip_async,
        include_chat=args.include_chat,
        include_failed_pre_run=args.include_failed_pre_run,
        include_agent_team=args.include_agent_team,
        agent_team_id=args.agent_team_id,
        include_scheduled_task=args.include_scheduled_task,
        include_tool_discovery=args.include_tool_discovery,
        include_human_approval=args.include_human_approval,
        include_version_run=args.include_version_run,
        include_knowledge_retrieval=args.include_knowledge_retrieval,
        include_llm=args.include_llm,
        include_nested_entry_contract=args.include_nested_entry_contract,
        verify_persistence=args.verify_persistence,
        test_disable_enable=args.test_disable_enable,
        restart_command=args.restart_command,
        restart_wait=args.restart_wait,
        restart_timeout=args.restart_timeout,
    )
    return apply_acceptance_profile(settings, args.profile)


def main(argv: list[str] | None = None) -> int:
    settings = parse_args(argv or sys.argv[1:])
    try:
        summary = WorkflowAcceptance(settings).run()
    except AcceptanceError as exc:
        failure = {"status": "failed", "error": str(exc)}
        if settings.output_file:
            write_json_output(settings.output_file, failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 1
    if settings.output_file:
        write_json_output(settings.output_file, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
