from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import workflow_container_acceptance as acceptance_script
from scripts.workflow_container_acceptance import (
    FAILED_INTERNAL_TOOL_RUN_ID,
    FAILED_PRE_RUN_WORKFLOW_ID,
    AcceptanceError,
    AcceptanceSettings,
    WorkflowAcceptance,
    HttpResponse,
    _decode_json,
    _iter_sse_events,
    fixture_expected_input_fields,
    fixture_expected_node_event_ids,
    load_fixture,
    parse_args,
    require_key,
    sample_input_for_fields,
)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        timeout: float = 15.0,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "json_body": json_body,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError(f"unexpected request {method} {url}")
        next_response = self.responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return next_response


class FakeStreamTransport(FakeTransport):
    def __init__(
        self,
        responses: list[HttpResponse | Exception],
        *,
        stream_events: list[dict[str, Any]] | None = None,
        stream_error: AcceptanceError | None = None,
    ) -> None:
        super().__init__(responses)
        self.stream_events = list(stream_events or [])
        self.stream_error = stream_error
        self.stream_calls: list[dict[str, Any]] = []

    def stream_sse(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> Any:
        self.stream_calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        if self.stream_error is not None:
            raise self.stream_error
        yield from self.stream_events


def response(
    data: Any, status: int = 200, *, include_default_saved_boundary: bool = True
) -> HttpResponse:
    data = _with_default_workflow_rest_contract(
        data,
        include_default_saved_boundary=include_default_saved_boundary,
    )
    return HttpResponse(status=status, data=data, text=json.dumps(data))


def _with_default_workflow_rest_contract(
    data: Any,
    *,
    include_default_saved_boundary: bool = True,
) -> Any:
    if not isinstance(data, dict):
        return data
    payload = dict(data)
    if _looks_like_workflow_rest_run(payload):
        payload.update(
            {
                key: value
                for key, value in workflow_output_contract_payload().items()
                if key not in payload
            }
        )
    if include_default_saved_boundary and _looks_like_workflow_saved_version_response(payload):
        payload.update(
            {
                key: value
                for key, value in workflow_saved_version_boundary_payload(payload).items()
                if key not in payload
            }
        )
    run = payload.get("run")
    if isinstance(run, dict) and _looks_like_workflow_rest_run(run):
        payload["run"] = {
            **run,
            **{
                key: value
                for key, value in workflow_output_contract_payload().items()
                if key not in run
            },
        }
    return payload


def _looks_like_workflow_rest_run(payload: dict[str, Any]) -> bool:
    if "run_id" not in payload and "run" not in payload and set(payload) != {"status"}:
        return False
    return payload.get("status") in {
        "succeeded",
        "queued",
        "running",
        "paused",
        "failed",
        "cancelled",
    }


def _looks_like_workflow_saved_version_response(payload: dict[str, Any]) -> bool:
    return payload.get("status") in {"imported", "versioned"} and bool(
        payload.get("workflow_id") and payload.get("version_id")
    )


def test_decode_json_returns_payload_for_valid_json_and_none_for_empty_or_invalid_text() -> None:
    assert _decode_json('{"status": "ok", "count": 2}') == {"status": "ok", "count": 2}
    assert _decode_json("") is None
    assert _decode_json("not-json") is None


def test_sse_parser_decodes_named_json_events_and_ignores_heartbeats() -> None:
    stream = io.BytesIO(
        b": heartbeat\n\n"
        b"event: workflow:run\n"
        b"id: 1700000000000-0\n"
        b'data: {"plugin_id":"workflow","workflow_id":"wf-1"}\n\n'
    )

    assert list(_iter_sse_events(stream)) == [
        {
            "event": "workflow:run",
            "event_type": "workflow:run",
            "data": {"plugin_id": "workflow", "workflow_id": "wf-1"},
            "id": "1700000000000-0",
        }
    ]


def contribution_payload(*, executable: bool) -> dict[str, Any]:
    return {
        "plugins": [
            {
                "plugin_id": "workflow",
                "enabled": executable,
                "executable": executable,
                "frontend": {
                    "app_tabs": [
                        {
                            "id": "workflow:workflows-tab",
                            "tab": "workflows",
                            "path": "/workflows",
                            "panel": "workflow:workflows-panel",
                            "insert_after": "agent-team",
                            "permissions": ["workflow:read"],
                        },
                        {
                            "id": "workflow:workflow-editor-tab",
                            "tab": "workflows-editor",
                            "path": "/workflows/:workflowId/editor",
                            "panel": "workflow:workflow-editor-panel",
                            "insert_after": "workflows",
                            "permissions": ["workflow:read"],
                        },
                        {
                            "id": "workflow:workflow-run-tab",
                            "tab": "workflows-run",
                            "path": "/workflows/:workflowId/runs/:runId",
                            "panel": "workflow:workflow-run-panel",
                            "insert_after": "workflows-editor",
                            "permissions": ["workflow:read"],
                        },
                    ],
                    "app_panels": [
                        {
                            "id": "workflow:workflows-panel",
                            "tab": "workflows",
                            "renderer": "workflow.WorkflowPanel",
                        },
                        {
                            "id": "workflow:workflow-editor-panel",
                            "tab": "workflows-editor",
                            "renderer": "workflow.WorkflowPanel",
                        },
                        {
                            "id": "workflow:workflow-run-panel",
                            "tab": "workflows-run",
                            "renderer": "workflow.WorkflowPanel",
                        },
                    ],
                    "sidebar_items": [
                        {
                            "id": "workflow:workflows-nav",
                            "path": "/workflows",
                            "icon": "Workflow",
                            "permissions": ["workflow:read"],
                        }
                    ],
                },
            }
        ],
        "total": 1,
    }


def runtime_payload(*, enabled: bool = True) -> dict[str, Any]:
    return {
        "plugins": [
            {
                "plugin_id": "workflow",
                "enabled": enabled,
                "status": "enabled" if enabled else "disabled",
            }
        ],
        "total": 1,
    }


def workflow_success_events() -> list[dict[str, str]]:
    return [
        {"event_type": "run_started"},
        {"event_type": "node_started", "node_id": "pick", "node_type": "list_operator"},
        {"event_type": "node_finished", "node_id": "pick", "node_type": "list_operator"},
        {"event_type": "node_started", "node_id": "answer", "node_type": "answer"},
        {"event_type": "node_finished", "node_id": "answer", "node_type": "answer"},
        {"event_type": "run_succeeded"},
    ]


def test_fixture_expected_node_event_ids_excludes_start_node() -> None:
    fixture = load_fixture(Path("tests/fixtures/workflow/list_operator.json"))

    assert fixture_expected_node_event_ids(fixture) == {"pick", "answer"}


def workflow_output_contract_payload() -> dict[str, Any]:
    return {
        "io_contract": {
            "output_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            }
        },
        "output_contract": {
            "valid": True,
            "schema_field": "output_schema",
            "declared_fields": ["answer"],
            "declared_field_paths": ["answer"],
            "required_fields": ["answer"],
            "required_field_paths": ["answer"],
            "missing_required": [],
            "type_mismatches": [],
            "extra_fields": [],
        },
        "next_action": {
            "type": "use_output",
            "field": "output",
            "reason": "workflow_run_succeeded",
        },
    }


def workflow_schema_output_schema_payload() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }


def workflow_failed_pre_run_next_action() -> dict[str, str]:
    return {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
    }


def workflow_result_interface_payload(
    *,
    workflow_id: str = "wf-1",
    run_id: str = "wfr-tool",
    version_id: str | None = "wfv-1",
) -> dict[str, Any]:
    return {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": workflow_id,
            "version_id": version_id,
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
            "workflow_id": workflow_id,
            "run_id": run_id,
            "events_field": "events",
        },
    }


def workflow_callable_interface_payload(
    *,
    workflow_id: str = "wf-1",
    version_id: str | None = "wfv-1",
) -> dict[str, Any]:
    return {
        "entry": {
            "type": "workflow.input",
            "tool": "workflow_run",
            "argument": "input",
            "workflow_id": workflow_id,
            "version_id": version_id,
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
            "workflow_id": workflow_id,
            "version_id": version_id,
            "input_schema_field": "input_schema",
            "output_schema_field": "output_schema",
        },
        "run": {
            "tool": "workflow_run",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "input_argument": "input",
            "output_field": "output",
        },
        "debug": {
            "tool": "workflow_get_run",
            "workflow_id": workflow_id,
            "run_id_field": "run_id",
        },
    }


def workflow_http_io_contract_payload(
    *,
    workflow_id: str = "wf-1",
    version_id: str = "wfv-1",
) -> dict[str, Any]:
    return {
        "plugin_id": "workflow",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "version_number": 1,
        "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}},
        "output_schema": workflow_schema_output_schema_payload(),
        "status": "published",
        "input_schema_source": "declared",
        "output_schema_source": "declared",
        "inferred_input_fields": [],
        "inferred_output_fields": ["answer"],
        "interface": workflow_callable_interface_payload(
            workflow_id=workflow_id,
            version_id=version_id,
        ),
    }


def workflow_saved_version_boundary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_id = str(payload.get("workflow_id") or "wf-1")
    version_id = str(payload.get("version_id") or "wfv-1")
    return {
        "io_contract": {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "version_id": version_id,
            "version_number": 1,
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
            "output_schema": workflow_schema_output_schema_payload(),
            "status": "draft",
            "input_schema_source": "declared",
            "output_schema_source": "inferred",
            "inferred_input_fields": [],
            "inferred_output_fields": ["answer"],
        },
        "interface": workflow_result_interface_payload(
            workflow_id=workflow_id,
            run_id=None,
            version_id=version_id,
        ),
    }


def invalid_nested_workflow_output_contract_payload(*, with_detail: bool = True) -> dict[str, Any]:
    payload = workflow_output_contract_payload()
    payload["io_contract"] = {
        "output_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"score": {"type": "integer"}},
                    },
                }
            },
            "required": ["items"],
        }
    }
    payload["output_contract"] = {
        "valid": False,
        "schema_field": "output_schema",
        "declared_fields": ["items"],
        "declared_field_paths": ["items[].score"],
        "required_fields": ["items"],
        "required_field_paths": ["items[].score"],
        "missing_required": [],
        "type_mismatches": (
            [{"field": "items[0].score", "expected": "integer", "actual": "str"}]
            if with_detail
            else []
        ),
        "extra_fields": [],
    }
    return payload


def workflow_run_payload(
    run_id: str,
    *,
    status: str = "succeeded",
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"run_id": run_id, "status": status, **workflow_output_contract_payload()}
    if output is not None:
        payload["output"] = output
    return payload


def workflow_events_payload(
    *,
    status: str = "succeeded",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "run": {"status": status, **workflow_output_contract_payload()},
        "events": events if events is not None else workflow_success_events(),
    }


def internal_workflow_tools_payload() -> dict[str, Any]:
    return {
        "server_name": "lambchat_internal",
        "tools": [
            {
                "name": "workflow_run",
                "description": "Run a workflow",
                "parameters": [
                    {"name": "workflow_id", "type": "string"},
                    {"name": "version_id", "type": "string"},
                    {"name": "input", "type": "object"},
                    {"name": "mode", "type": "string"},
                ],
            },
            {"name": "workflow_list", "description": "List", "parameters": []},
            {
                "name": "workflow_get_schema",
                "description": "Schema",
                "parameters": [
                    {"name": "workflow_id", "type": "string"},
                    {"name": "version_id", "type": "string"},
                ],
            },
            {
                "name": "workflow_get_run",
                "description": "Run snapshot",
                "parameters": [
                    {"name": "workflow_id", "type": "string"},
                    {"name": "run_id", "type": "string"},
                    {"name": "skip", "type": "integer"},
                    {"name": "limit", "type": "integer"},
                ],
            },
        ],
        "count": 4,
        "error": None,
    }


def internal_workflow_get_run_response(
    *,
    workflow_id: str,
    run_id: str,
    status: str = "succeeded",
) -> dict[str, Any]:
    return {
        "server_name": "lambchat_internal",
        "tool_name": "workflow_get_run",
        "result": {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "status": status,
            "events": workflow_success_events(),
            "interface": workflow_result_interface_payload(
                workflow_id=workflow_id,
                run_id=run_id,
                version_id=None,
            ),
            **workflow_output_contract_payload(),
        },
    }


def internal_workflow_get_run_failure_response(
    *,
    workflow_id: str,
    run_id: str = FAILED_INTERNAL_TOOL_RUN_ID,
    error: str = "workflow_run_not_found",
) -> dict[str, Any]:
    return {
        "server_name": "lambchat_internal",
        "tool_name": "workflow_get_run",
        "result": {
            "plugin_id": "workflow",
            "workflow_id": workflow_id,
            "version_id": None,
            "run_id": run_id,
            "mode": None,
            "status": "failed",
            "output": {},
            "error": error,
            "interface": workflow_result_interface_payload(
                workflow_id=workflow_id,
                run_id=run_id,
                version_id=None,
            ),
            "next_action": {
                "type": "handle_terminal_error",
                "field": "error",
                "reason": "workflow_run_failed",
                "tool": "workflow_get_run",
            },
        },
    }


def test_acceptance_runs_full_live_check_sequence_with_enable_and_async_poll() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload(enabled=False)),
            response(contribution_payload(executable=False)),
            response({"plugin_id": "workflow", "status": "enabled"}),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 5}}}),
            response(
                {
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-1", "status": "published"}}),
            response(workflow_run_payload("sync-1", output={"answer": "alpha"})),
            response(workflow_events_payload()),
            response(workflow_run_payload("async-1", status="queued")),
            response(
                workflow_events_payload(status="running", events=[{"event_type": "run_started"}])
            ),
            response(
                workflow_events_payload(
                    events=[{"event_type": "run_started"}, {"event_type": "run_succeeded"}],
                )
            ),
        ]
    )
    sleeps: list[float] = []
    clock_values = iter([0.0, 0.0, 0.5, 0.5])
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
        poll_interval=0.25,
    )

    summary = WorkflowAcceptance(
        settings,
        transport=transport,
        sleeper=sleeps.append,
        clock=lambda: next(clock_values),
    ).run()

    assert summary["status"] == "passed"
    assert [call["method"] for call in transport.calls] == [
        "GET",
        "GET",
        "GET",
        "POST",
        "GET",
        "GET",
        "POST",
        "POST",
        "POST",
        "GET",
        "POST",
        "GET",
        "GET",
    ]
    assert [call["url"] for call in transport.calls] == [
        "http://lambchat.example.test/health",
        "http://lambchat.example.test/api/extensions/plugins/",
        "http://lambchat.example.test/api/extensions/plugins/contributions",
        "http://lambchat.example.test/api/extensions/plugins/workflow/enable",
        "http://lambchat.example.test/api/extensions/plugins/contributions",
        "http://lambchat.example.test/api/plugins/workflow/node-types",
        "http://lambchat.example.test/api/plugins/workflow/workflows/import",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/publish",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/run",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/sync-1/events",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/run",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/async-1/events",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/async-1/events",
    ]
    assert transport.calls[6]["json_body"]["dry_run"] is False
    assert (
        transport.calls[6]["json_body"]["source_payload"]["workflow"]["nodes"][1]["type"]
        == "list-operator"
    )
    assert transport.calls[8]["json_body"] == {
        "input": {"items": ["alpha", "beta", "gamma"]},
        "mode": "sync",
    }
    assert transport.calls[10]["json_body"]["mode"] == "async"
    assert sleeps == [0.25]
    protected_call_indexes = [1, 3, 5, 6, 7, 8, 9, 10, 11, 12]
    assert all(
        transport.calls[index]["headers"].get("Authorization") == "Bearer token-1"
        for index in protected_call_indexes
    )
    assert transport.calls[4]["headers"] == {}


def test_acceptance_optional_failed_pre_run_check_keeps_chat_successful() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 5}}}),
            response(
                {
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-1", "status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded", "output": {"answer": "alpha"}}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response({"session_id": "chat-session", "run_id": "chat-run", "status": "pending"}),
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                                "run_id": None,
                                "status": "failed",
                                "output": {},
                                "error": "workflow_not_found",
                                "interface": workflow_result_interface_payload(
                                    workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
                                    run_id=None,
                                    version_id=None,
                                ),
                                "next_action": workflow_failed_pre_run_next_action(),
                            },
                        }
                    ]
                }
            ),
        ]
    )
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
        skip_async=True,
        include_failed_pre_run=True,
    )

    summary = WorkflowAcceptance(settings, transport=transport).run()

    assert summary["status"] == "passed"
    assert summary["checks"][-1] == {
        "name": "chat_failed_pre_run",
        "agent_id": "search",
        "session_id": "chat-session",
        "run_id": "chat-run",
        "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
        "status": "failed",
        "error": "workflow_not_found",
        "next_action": "handle_terminal_error",
        "next_action_reason": "workflow_run_failed",
    }
    assert (
        transport.calls[8]["url"] == "http://lambchat.example.test/api/chat/stream?agent_id=search"
    )
    assert transport.calls[8]["json_body"]["plugin_options"] == {
        "workflow": {"SELECTED_WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID}
    }
    assert transport.calls[9]["url"] == (
        "http://lambchat.example.test/api/sessions/chat-session/events?run_id=chat-run&limit=100"
    )


def test_acceptance_agent_team_failed_pre_run_check_keeps_team_chat_successful() -> None:
    transport = FakeTransport(
        [
            response({"session_id": "team-session", "run_id": "team-run", "status": "pending"}),
            response(
                {
                    "events": [
                        {
                            "event_type": "workflow:run",
                            "payload": {
                                "plugin_id": "workflow",
                                "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                                "run_id": None,
                                "status": "failed",
                                "output": {},
                                "error": "workflow_not_found",
                                "interface": workflow_result_interface_payload(
                                    workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
                                    run_id=None,
                                    version_id=None,
                                ),
                                "next_action": workflow_failed_pre_run_next_action(),
                            },
                        }
                    ]
                }
            ),
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
            agent_team_id="team-1",
        ),
        transport=transport,
    )

    result = acceptance.check_agent_team_failed_pre_run_invocation()

    assert result["session_id"] == "team-session"
    assert acceptance.recorder.checks[-1] == {
        "name": "agent_team_failed_pre_run",
        "team_id": "team-1",
        "session_id": "team-session",
        "run_id": "team-run",
        "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
        "status": "failed",
        "error": "workflow_not_found",
        "team_plugin_option": "SELECTED_TEAM_ID",
        "next_action": "handle_terminal_error",
        "next_action_reason": "workflow_run_failed",
    }
    assert transport.calls[0]["url"] == "http://lambchat.example.test/api/chat/stream?agent_id=team"
    assert transport.calls[0]["json_body"]["team_id"] == "team-1"
    assert transport.calls[0]["json_body"]["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"},
        "workflow": {"SELECTED_WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID},
    }
    assert transport.calls[1]["url"] == (
        "http://lambchat.example.test/api/sessions/team-session/events?run_id=team-run&limit=100"
    )


def test_acceptance_scheduled_task_failed_pre_run_check_keeps_task_successful() -> None:
    transport = FakeTransport(
        [
            response({"id": "task-1", "status": "active"}, status=201),
            response({"run_id": "task-run-1", "status": "accepted"}),
            response(
                {
                    "items": [
                        {
                            "id": "task-run-1",
                            "status": "success",
                            "session_id": "scheduled-session",
                            "trace_id": "scheduled-trace",
                        }
                    ],
                    "total": 1,
                }
            ),
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                                "run_id": None,
                                "status": "failed",
                                "output": {},
                                "error": "workflow_not_found",
                                "interface": workflow_result_interface_payload(
                                    workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
                                    run_id=None,
                                    version_id=None,
                                ),
                                "next_action": workflow_failed_pre_run_next_action(),
                            },
                        }
                    ]
                }
            ),
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
        ),
        transport=transport,
    )

    result = acceptance.check_scheduled_task_failed_pre_run_invocation()

    assert result["id"] == "task-1"
    assert acceptance.recorder.checks[-1] == {
        "name": "scheduled_task_failed_pre_run",
        "task_id": "task-1",
        "run_id": "task-run-1",
        "status": "success",
        "session_id": "scheduled-session",
        "trace_id": "scheduled-trace",
        "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
        "workflow_status": "failed",
        "error": "workflow_not_found",
        "next_action": "handle_terminal_error",
        "next_action_reason": "workflow_run_failed",
    }
    assert transport.calls[0]["url"] == "http://lambchat.example.test/api/scheduled-tasks/"
    assert transport.calls[0]["json_body"]["input_payload"]["plugin_options"] == {
        "workflow": {"WORKFLOW_ID": FAILED_PRE_RUN_WORKFLOW_ID}
    }
    assert transport.calls[3]["url"] == (
        "http://lambchat.example.test/api/sessions/scheduled-session/events?"
        "run_id=task-run-1&limit=100"
    )


def test_acceptance_scheduled_task_trigger_timeout_uses_running_session_stream() -> None:
    transport = FakeStreamTransport(
        [
            response({"id": "task-1", "status": "active"}, status=201),
            AcceptanceError(
                "request_timeout:POST http://lambchat.example.test/api/scheduled-tasks/task-1/run: timed out"
            ),
            response(
                {
                    "items": [
                        {
                            "id": "task-run-1",
                            "status": "running",
                            "session_id": "scheduled-session",
                            "trace_id": "scheduled-trace",
                        }
                    ],
                    "total": 1,
                }
            ),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ],
        stream_events=[
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "run_id": "wfr-scheduled",
                    "status": "succeeded",
                    "interface": workflow_result_interface_payload(
                        workflow_id="wf-1",
                        run_id="wfr-scheduled",
                        version_id="wfv-1",
                    ),
                    **workflow_output_contract_payload(),
                },
            }
        ],
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
        ),
        transport=transport,
    )

    result = acceptance.check_scheduled_task_invocation("wf-1", version_id="wfv-1")

    assert result["id"] == "task-1"
    assert acceptance.recorder.checks[0] == {
        "name": "scheduled_task_manual_trigger_timeout",
        "source": "scheduled_task",
        "task_id": "task-1",
    }
    assert acceptance.recorder.checks[-1] == {
        "name": "scheduled_task_invocation",
        "task_id": "task-1",
        "version_id": "wfv-1",
        "run_id": "task-run-1",
        "status": "running",
        "session_id": "scheduled-session",
        "trace_id": "scheduled-trace",
        "workflow_run_id": "wfr-scheduled",
        "next_action": "use_output",
        "next_action_reason": "workflow_run_succeeded",
        "workflow_input_keys": ["items"],
        "workflow_event_count": len(workflow_success_events()),
    }
    assert transport.calls[0]["json_body"]["input_payload"]["plugin_options"] == {
        "workflow": {
            "WORKFLOW_ID": "wf-1",
            "WORKFLOW_VERSION_ID": "wfv-1",
            "WORKFLOW_INPUT_JSON": {"items": ["alpha", "beta", "gamma"]},
        }
    }
    assert transport.stream_calls == [
        {
            "url": "http://lambchat.example.test/api/chat/sessions/scheduled-session/stream?run_id=task-run-1",
            "headers": {"Authorization": "Bearer token-1"},
            "timeout": 15.0,
        }
    ]


def test_acceptance_requires_success_event_for_sync_run() -> None:
    transport = FakeTransport(
        [
            response({"run_id": "sync-1", "status": "succeeded", "output": {"answer": "alpha"}}),
            response({"run": {"status": "succeeded"}, "events": [{"event_type": "node_finished"}]}),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    run = acceptance.run_workflow("wf-1", mode="sync")

    with pytest.raises(AcceptanceError, match="workflow_success_event_missing:sync-1"):
        acceptance.check_run_events("wf-1", run["run_id"], require_success_event=True)


def test_acceptance_requires_started_event_for_sync_run() -> None:
    transport = FakeTransport(
        [
            response({"run_id": "sync-1", "status": "succeeded", "output": {"answer": "alpha"}}),
            response({"run": {"status": "succeeded"}, "events": [{"event_type": "run_succeeded"}]}),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    run = acceptance.run_workflow("wf-1", mode="sync")

    with pytest.raises(AcceptanceError, match="workflow_started_event_missing:sync-1"):
        acceptance.check_run_events(
            "wf-1", run["run_id"], require_started_event=True, require_success_event=True
        )


def test_acceptance_requires_expected_node_events_for_sync_run() -> None:
    transport = FakeTransport(
        [
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(AcceptanceError, match="workflow_node_event_missing:sync-1:\\['missing'\\]"):
        acceptance.check_run_events(
            "wf-1",
            "sync-1",
            require_started_event=True,
            require_success_event=True,
            expected_node_event_ids={"pick", "answer", "missing"},
        )


def test_acceptance_records_node_event_counts_for_sync_run() -> None:
    transport = FakeTransport(
        [
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    acceptance.check_run_events(
        "wf-1",
        "sync-1",
        require_started_event=True,
        require_success_event=True,
        expected_node_event_ids={"pick", "answer"},
    )

    check = acceptance.recorder.checks[-1]
    assert check["name"] == "workflow_events"
    assert check["event_node_ids"] == ["answer", "pick"]
    assert check["event_node_counts"] == {"pick": 2, "answer": 2}


def test_acceptance_rest_workflow_run_requires_output_contract() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                data={"run_id": "sync-1", "status": "succeeded"},
                text='{"run_id":"sync-1","status":"succeeded"}',
            ),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(AcceptanceError, match="workflow_sync_run_workflow_io_contract_missing"):
        acceptance.run_workflow("wf-1", mode="sync")


def test_acceptance_rest_workflow_run_requires_invalid_output_contract_details() -> None:
    payload = {
        "run_id": "sync-1",
        "status": "succeeded",
        "output": {"items": [{"score": "high"}]},
        **invalid_nested_workflow_output_contract_payload(with_detail=False),
    }
    transport = FakeTransport([HttpResponse(status=200, data=payload, text=json.dumps(payload))])
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(
        AcceptanceError, match="workflow_sync_run_workflow_output_contract_failure_detail_missing"
    ):
        acceptance.run_workflow("wf-1", mode="sync")


def test_acceptance_rest_workflow_run_requires_output_contract_field_paths() -> None:
    payload = {
        "run_id": "sync-1",
        "status": "succeeded",
        "output": {"answer": "ok"},
        **workflow_output_contract_payload(),
    }
    payload["output_contract"].pop("declared_field_paths")
    transport = FakeTransport([HttpResponse(status=200, data=payload, text=json.dumps(payload))])
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(
        AcceptanceError,
        match="workflow_sync_run_workflow_output_contract_declared_field_paths_invalid",
    ):
        acceptance.run_workflow("wf-1", mode="sync")


def test_acceptance_rest_workflow_run_requires_output_contract_required_field_paths() -> None:
    payload = {
        "run_id": "sync-1",
        "status": "succeeded",
        "output": {"answer": "ok"},
        **workflow_output_contract_payload(),
    }
    payload["output_contract"].pop("required_field_paths")
    transport = FakeTransport([HttpResponse(status=200, data=payload, text=json.dumps(payload))])
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(
        AcceptanceError,
        match="workflow_sync_run_workflow_output_contract_required_field_paths_invalid",
    ):
        acceptance.run_workflow("wf-1", mode="sync")


def test_acceptance_rest_workflow_run_accepts_nested_output_contract_details() -> None:
    payload = {
        "run_id": "sync-1",
        "status": "succeeded",
        "output": {"items": [{"score": "high"}]},
        **invalid_nested_workflow_output_contract_payload(with_detail=True),
    }
    transport = FakeTransport([HttpResponse(status=200, data=payload, text=json.dumps(payload))])
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    run = acceptance.run_workflow("wf-1", mode="sync")

    assert run["output_contract"]["type_mismatches"][0] == {
        "field": "items[0].score",
        "expected": "integer",
        "actual": "str",
    }
    assert run["output_contract"]["declared_field_paths"] == ["items[].score"]
    assert run["output_contract"]["required_field_paths"] == ["items[].score"]


def test_acceptance_nested_entry_contract_rejection_records_path_level_error() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-nested",
                    "version_id": "wfv-nested",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-nested", "status": "published"}}),
            HttpResponse(
                status=422,
                data={"detail": "workflow_input_required_missing:profile.name"},
                text='{"detail":"workflow_input_required_missing:profile.name"}',
            ),
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            token="token-1",
            nested_entry_contract_fixture_path=Path(
                "tests/fixtures/workflow/nested_entry_contract.json"
            ),
        ),
        transport=transport,
    )

    acceptance.check_nested_entry_contract_rejection()

    assert acceptance.recorder.checks[-1]["name"] == "nested_entry_contract_rejection"
    run_request = transport.calls[-1]["json_body"]
    assert run_request == {
        "input": {"profile": {"nickname": "Ada"}, "items": [{"score": "high"}]},
        "mode": "sync",
        "version_id": "wfv-nested",
    }


def test_acceptance_nested_entry_contract_rejection_fails_when_bad_input_succeeds() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-nested",
                    "version_id": "wfv-nested",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-nested", "status": "published"}}),
            response(workflow_run_payload("run-accepted", output={"answer": "accepted"})),
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            token="token-1",
            nested_entry_contract_fixture_path=Path(
                "tests/fixtures/workflow/nested_entry_contract.json"
            ),
        ),
        transport=transport,
    )

    with pytest.raises(AcceptanceError, match="nested_entry_contract_run_unexpected_success"):
        acceptance.check_nested_entry_contract_rejection()


def test_acceptance_rest_workflow_events_require_output_contract() -> None:
    payload = {"run": {"status": "succeeded"}, "events": workflow_success_events()}
    transport = FakeTransport(
        [
            HttpResponse(status=200, data=payload, text=json.dumps(payload)),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(AcceptanceError, match="workflow_events_run_workflow_io_contract_missing"):
        acceptance.check_run_events(
            "wf-1",
            "sync-1",
            require_started_event=True,
            require_success_event=True,
        )


def test_acceptance_requires_started_event_for_async_terminal_run() -> None:
    transport = FakeTransport(
        [
            response({"run": {"status": "succeeded"}, "events": [{"event_type": "run_succeeded"}]}),
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=transport, clock=lambda: 0
    )

    with pytest.raises(AcceptanceError, match="workflow_async_started_event_missing:async-1"):
        acceptance.poll_async_run("wf-1", "async-1")


def test_acceptance_can_login_when_token_is_not_supplied() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response({"access_token": "login-token"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 1}}}),
            response({"workflow_id": "wf-1", "version_id": "wfv-1", "status": "imported"}),
            response({"workflow": {"status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )

    WorkflowAcceptance(
        AcceptanceSettings(
            username="admin",
            password="secret",
            fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
            skip_async=True,
        ),
        transport=transport,
    ).run()

    assert transport.calls[1]["url"] == "http://127.0.0.1:8000/api/auth/login"
    assert transport.calls[1]["json_body"] == {"username": "admin", "password": "secret"}
    assert transport.calls[2]["headers"]["Authorization"] == "Bearer login-token"
    assert transport.calls[3]["headers"] == {}


def test_acceptance_can_read_token_from_token_file(tmp_path: Path) -> None:
    token_file = tmp_path / "lambchat-token.json"
    token_file.write_text(
        json.dumps({"access_token": "file-token", "refresh_token": "refresh-token"}),
        encoding="utf-8",
    )
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 1}}}),
            response({"workflow_id": "wf-1", "version_id": "wfv-1", "status": "imported"}),
            response({"workflow": {"status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )

    summary = WorkflowAcceptance(
        AcceptanceSettings(
            token_file=token_file,
            fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
            skip_async=True,
        ),
        transport=transport,
    ).run()

    assert summary["checks"][1]["name"] == "auth"
    assert summary["checks"][1]["mode"] == "token_file"
    assert transport.calls[1]["headers"]["Authorization"] == "Bearer file-token"
    assert not any(call["url"].endswith("/api/auth/login") for call in transport.calls)


def test_acceptance_import_requires_saved_version_boundary() -> None:
    transport = FakeTransport(
        [
            response(
                {"workflow_id": "wf-1", "version_id": "wfv-1", "status": "imported"},
                include_default_saved_boundary=False,
            ),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(AcceptanceError, match="workflow_import_workflow_io_contract_missing"):
        acceptance.import_workflow({"workflow": {"nodes": []}})


def test_acceptance_version_create_requires_saved_version_boundary() -> None:
    transport = FakeTransport(
        [
            response(
                {"workflow_id": "wf-1", "version_id": "wfv-2", "status": "versioned"},
                include_default_saved_boundary=False,
            ),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    with pytest.raises(
        AcceptanceError, match="workflow_version_create_workflow_io_contract_missing"
    ):
        acceptance.create_workflow_version("wf-1", {"workflow": {"nodes": []}})


def test_acceptance_requires_credentials_after_health() -> None:
    transport = FakeTransport([response({"status": "ok"})])

    with pytest.raises(AcceptanceError, match="auth_required"):
        WorkflowAcceptance(AcceptanceSettings(), transport=transport).run()


def test_acceptance_fails_when_plugin_panel_contribution_is_missing() -> None:
    payload = contribution_payload(executable=True)
    payload["plugins"][0]["frontend"]["app_panels"] = []
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(payload),
        ]
    )

    with pytest.raises(AcceptanceError, match="plugin_contribution_missing_panel"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).run()


def test_acceptance_records_workflow_peer_editor_run_and_sidebar_contribution() -> None:
    transport = FakeTransport([response(contribution_payload(executable=True))])
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"),
        transport=transport,
    )

    plugin = acceptance.check_plugin_contribution()

    assert plugin["executable"] is True
    contribution = acceptance.recorder.checks[0]
    assert contribution["name"] == "plugin_contribution"
    assert contribution["tabs"] == [
        "workflows",
        "workflows-editor",
        "workflows-run",
    ]
    assert contribution["paths"] == {
        "workflows": "/workflows",
        "workflows-editor": "/workflows/:workflowId/editor",
        "workflows-run": "/workflows/:workflowId/runs/:runId",
    }
    assert contribution["peer_insert_after"] == "agent-team"
    assert contribution["editor_insert_after"] == "workflows"
    assert contribution["run_insert_after"] == "workflows-editor"
    assert contribution["sidebar_path"] == "/workflows"
    assert contribution["sidebar_icon"] == "Workflow"
    assert contribution["sidebar_permissions"] == ["workflow:read"]


def test_acceptance_fails_when_workflow_peer_tab_is_not_after_agent_team() -> None:
    payload = contribution_payload(executable=True)
    tab = payload["plugins"][0]["frontend"]["app_tabs"][0]
    tab["insert_after"] = "chat"
    transport = FakeTransport([response(payload)])

    with pytest.raises(
        AcceptanceError, match="plugin_contribution_tab_insert_after_mismatch:workflows"
    ):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_plugin_contribution()


def test_acceptance_fails_when_workflow_editor_route_is_missing() -> None:
    payload = contribution_payload(executable=True)
    frontend = payload["plugins"][0]["frontend"]
    frontend["app_tabs"] = [
        tab for tab in frontend["app_tabs"] if tab.get("tab") != "workflows-editor"
    ]
    transport = FakeTransport([response(payload)])

    with pytest.raises(AcceptanceError, match="plugin_contribution_missing_tab:workflows-editor"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_plugin_contribution()


def test_acceptance_fails_when_workflow_sidebar_entry_is_missing() -> None:
    payload = contribution_payload(executable=True)
    payload["plugins"][0]["frontend"]["sidebar_items"] = []
    transport = FakeTransport([response(payload)])

    with pytest.raises(AcceptanceError, match="plugin_contribution_missing_sidebar:/workflows"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_plugin_contribution()


def test_parse_args_uses_env_defaults_and_cli_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAMBCHAT_BASE_URL", "http://env.example")
    monkeypatch.setenv("LAMBCHAT_TOKEN", "env-token")
    monkeypatch.setenv("LAMBCHAT_TOKEN_FILE", "env-token.json")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_SKIP_ASYNC", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_CHAT", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_FAILED_PRE_RUN", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_HUMAN_APPROVAL", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_VERSION_RUN", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_KNOWLEDGE_RETRIEVAL", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_LLM", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_INCLUDE_NESTED_ENTRY_CONTRACT", "true")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_KNOWLEDGE_RETRIEVAL_FIXTURE", "knowledge.json")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_LLM_FIXTURE", "llm.json")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_NESTED_ENTRY_CONTRACT_FIXTURE", "nested-env.json")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_AGENT_TEAM_ID", "team-env")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_OUTPUT_FILE", "env-output.json")

    settings = parse_args(
        [
            "--base-url",
            "http://cli.example",
            "--token-file",
            "cli-token.json",
            "--request-timeout",
            "3",
            "--output-file",
            "cli-output.json",
            "--include-scheduled-task",
            "--include-tool-discovery",
            "--nested-entry-contract-fixture",
            "nested-cli.json",
            "--verify-persistence",
            "--restart-command",
            "restart-app",
        ]
    )

    assert settings.base_url == "http://cli.example"
    assert settings.token == "env-token"
    assert settings.token_file == Path("cli-token.json")
    assert settings.output_file == Path("cli-output.json")
    assert settings.request_timeout == 3
    assert settings.skip_async is True
    assert settings.include_chat is True
    assert settings.include_failed_pre_run is True
    assert settings.include_human_approval is True
    assert settings.include_version_run is True
    assert settings.include_knowledge_retrieval is True
    assert settings.include_llm is True
    assert settings.include_nested_entry_contract is True
    assert settings.knowledge_retrieval_fixture_path == Path("knowledge.json")
    assert settings.llm_fixture_path == Path("llm.json")
    assert settings.nested_entry_contract_fixture_path == Path("nested-cli.json")
    assert settings.agent_team_id == "team-env"
    assert settings.include_scheduled_task is True
    assert settings.include_tool_discovery is True
    assert settings.verify_persistence is True
    assert settings.restart_command == "restart-app"


def test_parse_args_full_profile_enables_final_acceptance_checks() -> None:
    settings = parse_args(
        [
            "--profile",
            "full",
            "--token",
            "token-1",
            "--agent-team-id",
            "team-1",
            "--output-file",
            "full-acceptance.json",
        ]
    )

    assert settings.token == "token-1"
    assert settings.agent_team_id == "team-1"
    assert settings.output_file == Path("full-acceptance.json")
    assert settings.include_chat is True
    assert settings.include_failed_pre_run is True
    assert settings.include_agent_team is True
    assert settings.include_scheduled_task is True
    assert settings.include_tool_discovery is True
    assert settings.include_human_approval is True
    assert settings.include_version_run is True
    assert settings.include_knowledge_retrieval is True
    assert settings.include_llm is True
    assert settings.include_nested_entry_contract is True
    assert settings.verify_persistence is True
    assert settings.test_disable_enable is True


def test_settings_from_env_final_profile_enables_final_acceptance_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_PROFILE", "final")
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_AGENT_TEAM_ID", "team-env")

    settings = acceptance_script.settings_from_env()

    assert settings.agent_team_id == "team-env"
    assert settings.include_chat is True
    assert settings.include_failed_pre_run is True
    assert settings.include_agent_team is True
    assert settings.include_scheduled_task is True
    assert settings.include_tool_discovery is True
    assert settings.include_human_approval is True
    assert settings.include_version_run is True
    assert settings.include_knowledge_retrieval is True
    assert settings.include_llm is True
    assert settings.include_nested_entry_contract is True
    assert settings.verify_persistence is True
    assert settings.test_disable_enable is True


def test_settings_from_env_rejects_unknown_acceptance_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAMBCHAT_ACCEPTANCE_PROFILE", "tiny")

    with pytest.raises(AcceptanceError, match="acceptance_profile_unknown:tiny"):
        acceptance_script.settings_from_env()


def test_main_writes_success_output_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_file = tmp_path / "acceptance" / "result.json"

    class FakeAcceptance:
        def __init__(self, settings: AcceptanceSettings) -> None:
            assert settings.output_file == output_file

        def run(self) -> dict[str, Any]:
            return {"status": "passed", "checks": [{"name": "health", "app_status": "ok"}]}

    monkeypatch.setattr(acceptance_script, "WorkflowAcceptance", FakeAcceptance)

    exit_code = acceptance_script.main(["--token", "token-1", "--output-file", str(output_file)])

    assert exit_code == 0
    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "status": "passed",
        "checks": [{"name": "health", "app_status": "ok"}],
    }


def test_main_writes_failure_output_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_file = tmp_path / "failed.json"

    class FakeAcceptance:
        def __init__(self, settings: AcceptanceSettings) -> None:
            assert settings.output_file == output_file

        def run(self) -> dict[str, Any]:
            raise AcceptanceError("acceptance_failed_for_test")

    monkeypatch.setattr(acceptance_script, "WorkflowAcceptance", FakeAcceptance)

    exit_code = acceptance_script.main(["--token", "token-1", "--output-file", str(output_file)])

    assert exit_code == 1
    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "status": "failed",
        "error": "acceptance_failed_for_test",
    }


def test_acceptance_optional_human_approval_checks_pending_inbox_and_resume() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 5}}}),
            response(
                {
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-1", "status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(
                {
                    "workflow_id": "wf-approval",
                    "version_id": "wfv-approval",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-approval", "status": "published"}}),
            response(
                {
                    "run_id": "approval-run",
                    "workflow_id": "wf-approval",
                    "status": "paused",
                    "pause": {
                        "kind": "human_approval",
                        "pending_approval": {
                            "node_id": "approval",
                            "instructions": "Approve LambChat before continuing.",
                        },
                    },
                }
            ),
            response(
                {
                    "plugin_id": "workflow",
                    "runs": [
                        {
                            "run_id": "approval-run",
                            "workflow_id": "wf-approval",
                            "status": "paused",
                            "pause": {"kind": "human_approval"},
                        }
                    ],
                    "skip": 0,
                    "limit": 20,
                }
            ),
            response(
                {
                    "run_id": "approval-run",
                    "workflow_id": "wf-approval",
                    "status": "succeeded",
                    "output": {"answer": "Approved=True comment=accepted by container acceptance"},
                    "events": [{"event_type": "human_approval_resumed"}],
                }
            ),
        ]
    )
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
        human_approval_fixture_path=Path("tests/fixtures/workflow/human_approval_resume.json"),
        skip_async=True,
        include_human_approval=True,
    )

    summary = WorkflowAcceptance(settings, transport=transport).run()

    assert summary["status"] == "passed"
    check_names = [check["name"] for check in summary["checks"]]
    assert "pending_approvals" in check_names
    assert "workflow_resume" in check_names
    assert "human_approval_resume" in check_names
    assert (
        transport.calls[8]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/import"
    )
    assert (
        transport.calls[8]["json_body"]["source_payload"]["workflow"]["nodes"][1]["type"]
        == "human-approval"
    )
    assert transport.calls[10]["json_body"] == {"input": {"name": "LambChat"}, "mode": "async"}
    assert (
        transport.calls[11]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/approvals/pending?limit=20"
    )
    assert (
        transport.calls[12]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-approval/runs/approval-run/resume"
    )
    assert transport.calls[12]["json_body"] == {
        "approved": True,
        "comment": "accepted by container acceptance",
    }


def test_acceptance_optional_advanced_node_checks_import_publish_run_and_events() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-knowledge",
                    "version_id": "wfv-knowledge",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-knowledge", "status": "published"}}),
            response(
                {
                    "run_id": "run-knowledge",
                    "workflow_id": "wf-knowledge",
                    "version_id": "wfv-knowledge",
                    "status": "succeeded",
                }
            ),
            response(
                {
                    "run": {"status": "succeeded"},
                    "events": [
                        {"event_type": "run_started"},
                        {"event_type": "node_finished", "node_type": "knowledge_retrieval"},
                        {"event_type": "run_succeeded"},
                    ],
                }
            ),
            response(
                {
                    "workflow_id": "wf-llm",
                    "version_id": "wfv-llm",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-llm", "status": "published"}}),
            response(
                {
                    "run_id": "run-llm",
                    "workflow_id": "wf-llm",
                    "version_id": "wfv-llm",
                    "status": "succeeded",
                }
            ),
            response(
                {
                    "run": {"status": "succeeded"},
                    "events": [
                        {"event_type": "run_started"},
                        {"event_type": "node_finished", "node_type": "llm"},
                        {"event_type": "run_succeeded"},
                    ],
                }
            ),
        ]
    )
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        knowledge_retrieval_fixture_path=Path("tests/fixtures/workflow/knowledge_retrieval.json"),
        llm_fixture_path=Path("tests/fixtures/workflow/default_llm.json"),
    )
    acceptance = WorkflowAcceptance(settings, transport=transport)

    acceptance.check_knowledge_retrieval_run()
    acceptance.check_llm_run()

    check_names = [check["name"] for check in acceptance.recorder.checks]
    assert "knowledge_retrieval_run" in check_names
    assert "llm_run" in check_names
    assert (
        transport.calls[0]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/import"
    )
    assert (
        transport.calls[0]["json_body"]["source_payload"]["workflow"]["nodes"][1]["type"]
        == "knowledge-retrieval"
    )
    assert transport.calls[2]["json_body"] == {
        "input": {"items": ["alpha", "beta", "gamma"]},
        "mode": "sync",
        "version_id": "wfv-knowledge",
    }
    llm_node = transport.calls[4]["json_body"]["source_payload"]["workflow"]["graph"]["nodes"][1]
    assert llm_node["data"]["type"] == "llm"
    assert "model" not in llm_node["data"]
    assert transport.calls[6]["json_body"] == {
        "input": {"query": "acceptance query"},
        "mode": "async",
        "version_id": "wfv-llm",
    }


def test_acceptance_advanced_node_check_requires_matching_finished_event() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-knowledge",
                    "version_id": "wfv-knowledge",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-knowledge", "status": "published"}}),
            response({"run_id": "run-knowledge", "status": "succeeded"}),
            response(
                {
                    "run": {"status": "succeeded"},
                    "events": [
                        {"event_type": "run_started"},
                        {"event_type": "node_finished", "node_type": "answer"},
                        {"event_type": "run_succeeded"},
                    ],
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="knowledge_retrieval_event_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(
                token="token-1",
                knowledge_retrieval_fixture_path=Path(
                    "tests/fixtures/workflow/knowledge_retrieval.json"
                ),
            ),
            transport=transport,
        ).check_knowledge_retrieval_run()


def test_acceptance_human_approval_polls_until_paused_when_run_starts_running() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-approval",
                    "version_id": "wfv-approval",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-approval", "status": "published"}}),
            response(
                {
                    "run_id": "approval-run",
                    "workflow_id": "wf-approval",
                    "status": "running",
                }
            ),
            response(
                {
                    "run": {
                        "run_id": "approval-run",
                        "workflow_id": "wf-approval",
                        "status": "paused",
                        "pause": {
                            "kind": "human_approval",
                            "pending_approval": {"node_id": "approval"},
                        },
                    },
                    "events": [{"event_type": "run_started"}],
                }
            ),
            response(
                {
                    "plugin_id": "workflow",
                    "runs": [
                        {
                            "run_id": "approval-run",
                            "workflow_id": "wf-approval",
                            "status": "paused",
                            "pause": {"kind": "human_approval"},
                        }
                    ],
                    "skip": 0,
                    "limit": 20,
                }
            ),
            response(
                {
                    "run_id": "approval-run",
                    "workflow_id": "wf-approval",
                    "status": "succeeded",
                    "output": {"answer": "Approved=True"},
                }
            ),
        ]
    )
    sleeps: list[float] = []

    WorkflowAcceptance(
        AcceptanceSettings(
            token="token-1",
            human_approval_fixture_path=Path("tests/fixtures/workflow/human_approval_resume.json"),
            poll_interval=0.25,
        ),
        transport=transport,
        sleeper=sleeps.append,
    ).check_human_approval_resume()

    assert sleeps == []
    assert transport.calls[2]["json_body"] == {"input": {"name": "LambChat"}, "mode": "async"}
    assert transport.calls[3]["url"] == (
        "http://127.0.0.1:8000/api/plugins/workflow/workflows/wf-approval/runs/approval-run/events"
    )
    assert (
        transport.calls[4]["url"]
        == "http://127.0.0.1:8000/api/plugins/workflow/approvals/pending?limit=20"
    )


def test_acceptance_human_approval_fails_when_pending_run_is_missing() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-approval",
                    "version_id": "wfv-approval",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-approval", "status": "published"}}),
            response(
                {
                    "run_id": "approval-run",
                    "workflow_id": "wf-approval",
                    "status": "paused",
                    "pause": {
                        "kind": "human_approval",
                        "pending_approval": {"node_id": "approval"},
                    },
                }
            ),
            response({"plugin_id": "workflow", "runs": [], "skip": 0, "limit": 20}),
        ]
    )

    with pytest.raises(AcceptanceError, match="pending_approval_run_not_found"):
        WorkflowAcceptance(
            AcceptanceSettings(
                token="token-1",
                human_approval_fixture_path=Path(
                    "tests/fixtures/workflow/human_approval_resume.json"
                ),
            ),
            transport=transport,
        ).check_human_approval_resume()


def test_acceptance_optional_version_run_creates_and_runs_specific_versions() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 5}}}),
            response(
                {
                    "workflow_id": "wf-1",
                    "version_id": "wfv-base",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-1", "status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow_id": "wf-version", "version_id": "wfv-two", "status": "versioned"}),
            response(
                {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "version_number": 1,
                    "input_schema": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                    },
                    "status": "draft",
                    "schema_source": "declared",
                    "inferred_fields": [],
                    "interface": workflow_callable_interface_payload(
                        workflow_id="wf-version",
                        version_id="wfv-one",
                    ),
                }
            ),
            response(
                {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-two",
                    "version_number": 2,
                    "input_schema": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                    },
                    "status": "draft",
                    "schema_source": "declared",
                    "inferred_fields": [],
                    "interface": workflow_callable_interface_payload(
                        workflow_id="wf-version",
                        version_id="wfv-two",
                    ),
                }
            ),
            response(
                workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-one")
            ),
            response(
                workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-two")
            ),
            response(
                {
                    "run_id": "run-v1",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "status": "succeeded",
                    "output": {"answer": "version-one LambChat"},
                }
            ),
            response(
                {
                    "run_id": "run-v2",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-two",
                    "status": "succeeded",
                    "output": {"answer": "version-two LambChat"},
                }
            ),
        ]
    )
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
        version_run_v1_fixture_path=Path("tests/fixtures/workflow/version_run_v1.json"),
        version_run_v2_fixture_path=Path("tests/fixtures/workflow/version_run_v2.json"),
        skip_async=True,
        include_version_run=True,
    )

    summary = WorkflowAcceptance(settings, transport=transport).run()

    assert summary["status"] == "passed"
    check_names = [check["name"] for check in summary["checks"]]
    assert "workflow_version_create" in check_names
    assert check_names.count("workflow_input_schema") == 2
    assert check_names.count("workflow_io_contract") == 2
    assert "version_scoped_run" in check_names
    assert (
        transport.calls[9]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-version/versions"
    )
    assert transport.calls[9]["json_body"]["source_payload"]["workflow"]["nodes"][1]["data"][
        "answer"
    ].startswith("version-two")
    assert (
        transport.calls[10]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-version/input-schema?version_id=wfv-one"
    )
    assert (
        transport.calls[11]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-version/input-schema?version_id=wfv-two"
    )
    assert (
        transport.calls[12]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-version/io-contract?version_id=wfv-one"
    )
    assert (
        transport.calls[13]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-version/io-contract?version_id=wfv-two"
    )
    assert transport.calls[14]["json_body"] == {
        "input": {"message": "LambChat"},
        "mode": "sync",
        "version_id": "wfv-one",
    }
    assert transport.calls[15]["json_body"] == {
        "input": {"message": "LambChat"},
        "mode": "sync",
        "version_id": "wfv-two",
    }


def test_acceptance_version_run_fails_when_specific_version_output_does_not_match() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow_id": "wf-version", "version_id": "wfv-two", "status": "versioned"}),
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "input_schema": {"type": "object"},
                    "schema_source": "declared",
                    "interface": workflow_callable_interface_payload(
                        workflow_id="wf-version",
                        version_id="wfv-one",
                    ),
                }
            ),
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-two",
                    "input_schema": {"type": "object"},
                    "schema_source": "declared",
                    "interface": workflow_callable_interface_payload(
                        workflow_id="wf-version",
                        version_id="wfv-two",
                    ),
                }
            ),
            response(
                workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-one")
            ),
            response(
                workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-two")
            ),
            response(
                {
                    "run_id": "run-v1",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "status": "succeeded",
                    "output": {"answer": "wrong version"},
                }
            ),
            response(
                {
                    "run_id": "run-v2",
                    "workflow_id": "wf-version",
                    "version_id": "wfv-two",
                    "status": "succeeded",
                    "output": {"answer": "version-two LambChat"},
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="version_scoped_run_v1_output_mismatch"):
        WorkflowAcceptance(
            AcceptanceSettings(
                token="token-1",
                version_run_v1_fixture_path=Path("tests/fixtures/workflow/version_run_v1.json"),
                version_run_v2_fixture_path=Path("tests/fixtures/workflow/version_run_v2.json"),
            ),
            transport=transport,
        ).check_version_scoped_run()


def test_acceptance_input_schema_fails_when_version_id_does_not_match() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-other",
                    "input_schema": {"type": "object"},
                    "schema_source": "declared",
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="workflow_input_schema_version_mismatch"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_input_schema("wf-version", version_id="wfv-one")


def test_acceptance_input_schema_requires_callable_interface() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "workflow_id": "wf-version",
                    "version_id": "wfv-one",
                    "input_schema": {"type": "object"},
                    "schema_source": "declared",
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="workflow_input_schema_workflow_interface_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_input_schema("wf-version", version_id="wfv-one")


def test_acceptance_io_contract_fails_when_version_id_does_not_match() -> None:
    transport = FakeTransport(
        [
            response(
                workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-other")
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="workflow_io_contract_version_mismatch"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_io_contract("wf-version", version_id="wfv-one")


def test_acceptance_io_contract_requires_callable_interface() -> None:
    payload = workflow_http_io_contract_payload(workflow_id="wf-version", version_id="wfv-one")
    payload.pop("interface")
    transport = FakeTransport([response(payload)])

    with pytest.raises(AcceptanceError, match="workflow_io_contract_workflow_interface_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_io_contract("wf-version", version_id="wfv-one")


def test_acceptance_optional_channels_cover_chat_team_scheduled_and_persistence() -> None:
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"plugin_id": "workflow", "status": "disabled"}),
            response(contribution_payload(executable=False)),
            response({"plugin_id": "workflow", "status": "enabled"}),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 5}}}),
            response(
                {
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-1", "status": "published"}}),
            response({"run_id": "sync-1", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(
                {
                    "session_id": "chat-session",
                    "run_id": "chat-run",
                    "status": "pending",
                }
            ),
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": "wf-1",
                                "version_id": "wfv-1",
                                "run_id": "wfr-chat",
                                "status": "succeeded",
                                "interface": workflow_result_interface_payload(
                                    workflow_id="wf-1",
                                    run_id="wfr-chat",
                                    version_id="wfv-1",
                                ),
                                **workflow_output_contract_payload(),
                            },
                        }
                    ]
                }
            ),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response({"session_id": "team-session", "run_id": "team-run", "status": "pending"}),
            response(
                {
                    "events": [
                        {
                            "event_type": "workflow:run",
                            "payload": {
                                "plugin_id": "workflow",
                                "workflow_id": "wf-1",
                                "version_id": "wfv-1",
                                "run_id": "wfr-team",
                                "status": "succeeded",
                                "interface": workflow_result_interface_payload(
                                    workflow_id="wf-1",
                                    run_id="wfr-team",
                                    version_id="wfv-1",
                                ),
                                **workflow_output_contract_payload(),
                            },
                        }
                    ]
                }
            ),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response({"id": "task-1", "status": "active"}, status=201),
            response({"run_id": "task-run-1", "status": "accepted"}),
            response(
                {
                    "items": [
                        {
                            "id": "task-run-1",
                            "status": "success",
                            "session_id": "scheduled-session",
                            "trace_id": "scheduled-trace",
                        }
                    ],
                    "total": 1,
                }
            ),
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": "wf-1",
                                "version_id": "wfv-1",
                                "run_id": "wfr-scheduled",
                                "status": "succeeded",
                                "interface": workflow_result_interface_payload(
                                    workflow_id="wf-1",
                                    run_id="wfr-scheduled",
                                    version_id="wfv-1",
                                ),
                                **workflow_output_contract_payload(),
                            },
                        }
                    ]
                }
            ),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(internal_workflow_tools_payload()),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_list",
                    "result": {
                        "plugin_id": "workflow",
                        "scope": "published",
                        "workflows": [
                            {
                                "workflow_id": "wf-1",
                                "name": "List Operator",
                                "status": "published",
                            }
                        ],
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "version_number": 1,
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "items": {"type": "array", "x-lambchat-source": "inferred"},
                            },
                            "additionalProperties": True,
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                        "status": "published",
                        "schema_source": "inferred",
                        "inferred_fields": ["items"],
                        "interface": workflow_callable_interface_payload(
                            workflow_id="wf-1",
                            version_id="wfv-1",
                        ),
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "output": {"answer": "alpha beta gamma"},
                        "events": workflow_success_events(),
                        "interface": workflow_result_interface_payload(
                            workflow_id="wf-1",
                            run_id="wfr-tool",
                            version_id="wfv-1",
                        ),
                        **workflow_output_contract_payload(),
                    },
                }
            ),
            response(internal_workflow_get_run_response(workflow_id="wf-1", run_id="wfr-tool")),
            response(internal_workflow_get_run_failure_response(workflow_id="wf-1")),
            response(internal_workflow_get_run_response(workflow_id="wf-1", run_id="wfr-chat")),
            response(internal_workflow_get_run_response(workflow_id="wf-1", run_id="wfr-team")),
            response(
                internal_workflow_get_run_response(workflow_id="wf-1", run_id="wfr-scheduled")
            ),
            response({"workflow_id": "wf-1", "status": "published"}),
            response({"runs": [{"run_id": "sync-1", "status": "succeeded"}]}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )
    settings = AcceptanceSettings(
        base_url="http://lambchat.example.test/",
        token="token-1",
        fixture_path=Path("tests/fixtures/workflow/list_operator.json"),
        skip_async=True,
        include_chat=True,
        include_agent_team=True,
        agent_team_id="team-1",
        include_scheduled_task=True,
        include_tool_discovery=True,
        verify_persistence=True,
        test_disable_enable=True,
    )

    summary = WorkflowAcceptance(settings, transport=transport).run()

    assert summary["status"] == "passed"
    assert (
        transport.calls[3]["url"]
        == "http://lambchat.example.test/api/extensions/plugins/workflow/disable"
    )
    assert (
        transport.calls[12]["url"] == "http://lambchat.example.test/api/chat/stream?agent_id=search"
    )
    assert transport.calls[12]["json_body"]["plugin_options"] == {
        "workflow": {
            "SELECTED_WORKFLOW_ID": "wf-1",
            "SELECTED_WORKFLOW_VERSION_ID": "wfv-1",
            "SELECTED_WORKFLOW_INPUT_JSON": {"items": ["alpha", "beta", "gamma"]},
        }
    }
    assert transport.calls[14]["url"] == (
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/wfr-chat/events"
    )
    assert (
        transport.calls[15]["url"] == "http://lambchat.example.test/api/chat/stream?agent_id=team"
    )
    assert transport.calls[15]["json_body"]["team_id"] == "team-1"
    assert transport.calls[15]["json_body"]["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"},
        "workflow": {
            "SELECTED_WORKFLOW_ID": "wf-1",
            "SELECTED_WORKFLOW_VERSION_ID": "wfv-1",
            "SELECTED_WORKFLOW_INPUT_JSON": {"items": ["alpha", "beta", "gamma"]},
        },
    }
    assert transport.calls[17]["url"] == (
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/wfr-team/events"
    )
    assert transport.calls[18]["url"] == "http://lambchat.example.test/api/scheduled-tasks/"
    assert transport.calls[18]["json_body"]["input_payload"]["plugin_options"] == {
        "workflow": {
            "WORKFLOW_ID": "wf-1",
            "WORKFLOW_VERSION_ID": "wfv-1",
            "WORKFLOW_INPUT_JSON": {"items": ["alpha", "beta", "gamma"]},
        }
    }
    assert transport.calls[21]["url"] == (
        "http://lambchat.example.test/api/sessions/scheduled-session/events?"
        "run_id=task-run-1&limit=100"
    )
    assert transport.calls[22]["url"] == (
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/wfr-scheduled/events"
    )
    assert (
        transport.calls[23]["url"]
        == "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools"
    )
    assert transport.calls[24]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_list/invoke"
    )
    assert transport.calls[24]["json_body"] == {"arguments": {"scope": "published"}}
    assert transport.calls[25]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_schema/invoke"
    )
    assert transport.calls[25]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "version_id": "wfv-1"}
    }
    assert transport.calls[26]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_run/invoke"
    )
    assert transport.calls[26]["json_body"] == {
        "arguments": {
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "input": {"items": ["alpha", "beta", "gamma"]},
            "mode": "sync",
        }
    }
    assert transport.calls[27]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke"
    )
    assert transport.calls[27]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "wfr-tool"}
    }
    assert transport.calls[28]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": FAILED_INTERNAL_TOOL_RUN_ID}
    }
    assert transport.calls[29]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "wfr-chat"}
    }
    assert transport.calls[30]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "wfr-team"}
    }
    assert transport.calls[31]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "wfr-scheduled"}
    }
    get_run_checks = [
        check for check in summary["checks"] if check["name"] == "internal_tool_get_run_invocation"
    ]
    assert [(check["source"], check["run_id"]) for check in get_run_checks] == [
        ("direct", "wfr-tool"),
        ("chat", "wfr-chat"),
        ("agent_team", "wfr-team"),
        ("scheduled_task", "wfr-scheduled"),
    ]
    assert {(check["run_entry"], check["run_exit"]) for check in get_run_checks} == {
        ("workflow_run.input", "output")
    }
    tool_run_checks = [
        check for check in summary["checks"] if check["name"] == "internal_tool_invocation"
    ]
    assert tool_run_checks == [
        {
            "name": "internal_tool_invocation",
            "server_name": "lambchat_internal",
            "tool_name": "workflow_run",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "run_id": "wfr-tool",
            "workflow_input_keys": ["items"],
            "run_entry": "workflow_run.input",
            "run_exit": "output",
            "next_action": "use_output",
            "next_action_reason": "workflow_run_succeeded",
            "event_count": len(workflow_success_events()),
        }
    ]
    schema_checks = [
        check for check in summary["checks"] if check["name"] == "internal_tool_schema_invocation"
    ]
    assert schema_checks == [
        {
            "name": "internal_tool_schema_invocation",
            "server_name": "lambchat_internal",
            "tool_name": "workflow_get_schema",
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "schema_source": "inferred",
            "input_fields": ["items"],
            "output_fields": ["answer"],
            "run_entry": "workflow_run.input",
            "run_exit": "output",
            "schema_tool": "workflow_get_schema",
        }
    ]
    failure_checks = [
        check
        for check in summary["checks"]
        if check["name"] == "internal_tool_get_run_failure_invocation"
    ]
    assert failure_checks == [
        {
            "name": "internal_tool_get_run_failure_invocation",
            "server_name": "lambchat_internal",
            "tool_name": "workflow_get_run",
            "workflow_id": "wf-1",
            "run_id": FAILED_INTERNAL_TOOL_RUN_ID,
            "status": "failed",
            "error": "workflow_run_not_found",
            "run_entry": "workflow_run.input",
            "run_exit": "output",
            "next_action": "handle_terminal_error",
            "next_action_reason": "workflow_run_failed",
        }
    ]
    assert (
        transport.calls[32]["url"]
        == "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1"
    )


def test_acceptance_tool_invocation_uses_custom_fixture_inputs(tmp_path: Path) -> None:
    fixture_path = tmp_path / "message_workflow.json"
    fixture_path.write_text(
        json.dumps(
            {
                "version": "0.3.0",
                "app": {"name": "Message Workflow"},
                "workflow": {
                    "nodes": [
                        {"id": "start", "type": "start", "data": {"title": "Start"}},
                        {
                            "id": "answer",
                            "type": "answer",
                            "data": {"title": "Answer", "answer": "{{message}}"},
                        },
                    ],
                    "edges": [{"id": "e1", "source": "start", "target": "answer"}],
                },
            }
        ),
        encoding="utf-8",
    )
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 2}}}),
            response(
                {
                    "workflow_id": "wf-message",
                    "version_id": "wfv-message",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-message", "status": "published"}}),
            response({"run_id": "sync-message", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(internal_workflow_tools_payload()),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_list",
                    "result": {
                        "plugin_id": "workflow",
                        "scope": "published",
                        "workflows": [{"workflow_id": "wf-message", "status": "published"}],
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-message",
                        "version_id": "wfv-message",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "x-lambchat-source": "inferred"}
                            },
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                        "schema_source": "inferred",
                        "interface": workflow_callable_interface_payload(
                            workflow_id="wf-message",
                            version_id="wfv-message",
                        ),
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-message",
                        "version_id": "wfv-message",
                        "run_id": "wfr-message-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                        "interface": workflow_result_interface_payload(
                            workflow_id="wf-message",
                            run_id="wfr-message-tool",
                            version_id="wfv-message",
                        ),
                        **workflow_output_contract_payload(),
                    },
                }
            ),
            response(
                internal_workflow_get_run_response(
                    workflow_id="wf-message",
                    run_id="wfr-message-tool",
                )
            ),
            response(internal_workflow_get_run_failure_response(workflow_id="wf-message")),
        ]
    )

    summary = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
            fixture_path=fixture_path,
            skip_async=True,
            include_tool_discovery=True,
        ),
        transport=transport,
    ).run()

    assert summary["status"] == "passed"
    assert transport.calls[6]["json_body"] == {
        "input": {"message": "acceptance message"},
        "mode": "sync",
    }
    assert transport.calls[11]["json_body"] == {
        "arguments": {
            "workflow_id": "wf-message",
            "version_id": "wfv-message",
            "input": {"message": "acceptance message"},
            "mode": "sync",
        }
    }
    assert transport.calls[12]["json_body"] == {
        "arguments": {"workflow_id": "wf-message", "run_id": "wfr-message-tool"}
    }
    assert transport.calls[13]["json_body"] == {
        "arguments": {"workflow_id": "wf-message", "run_id": FAILED_INTERNAL_TOOL_RUN_ID}
    }
    failure_checks = [
        check
        for check in summary["checks"]
        if check["name"] == "internal_tool_get_run_failure_invocation"
    ]
    assert failure_checks[0]["workflow_id"] == "wf-message"
    assert failure_checks[0]["run_id"] == FAILED_INTERNAL_TOOL_RUN_ID


def test_acceptance_tool_get_run_inspects_rest_async_run(tmp_path: Path) -> None:
    fixture_path = tmp_path / "message_workflow.json"
    fixture_path.write_text(
        json.dumps(
            {
                "version": "0.3.0",
                "app": {"name": "Message Workflow"},
                "workflow": {
                    "nodes": [
                        {"id": "start", "type": "start", "data": {"title": "Start"}},
                        {
                            "id": "answer",
                            "type": "answer",
                            "data": {"title": "Answer", "answer": "{{message}}"},
                        },
                    ],
                    "edges": [{"id": "e1", "source": "start", "target": "answer"}],
                },
            }
        ),
        encoding="utf-8",
    )
    transport = FakeTransport(
        [
            response({"status": "ok"}),
            response(runtime_payload()),
            response(contribution_payload(executable=True)),
            response({"compatibility": {"summary": {"supported": 2}}}),
            response(
                {
                    "workflow_id": "wf-message",
                    "version_id": "wfv-message",
                    "status": "imported",
                    "compatibility_report": {"lossless": True},
                }
            ),
            response({"workflow": {"workflow_id": "wf-message", "status": "published"}}),
            response({"run_id": "sync-message", "status": "succeeded"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response({"run_id": "async-message", "status": "queued"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
            response(internal_workflow_tools_payload()),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_list",
                    "result": {
                        "plugin_id": "workflow",
                        "scope": "published",
                        "workflows": [{"workflow_id": "wf-message", "status": "published"}],
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-message",
                        "version_id": "wfv-message",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "x-lambchat-source": "inferred"}
                            },
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                        "schema_source": "inferred",
                        "interface": workflow_callable_interface_payload(
                            workflow_id="wf-message",
                            version_id="wfv-message",
                        ),
                    },
                }
            ),
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-message",
                        "version_id": "wfv-message",
                        "run_id": "wfr-message-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                        "interface": workflow_result_interface_payload(
                            workflow_id="wf-message",
                            run_id="wfr-message-tool",
                            version_id="wfv-message",
                        ),
                        **workflow_output_contract_payload(),
                    },
                }
            ),
            response(
                internal_workflow_get_run_response(
                    workflow_id="wf-message", run_id="wfr-message-tool"
                )
            ),
            response(internal_workflow_get_run_failure_response(workflow_id="wf-message")),
            response(
                internal_workflow_get_run_response(workflow_id="wf-message", run_id="async-message")
            ),
        ]
    )

    summary = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
            fixture_path=fixture_path,
            include_tool_discovery=True,
            poll_interval=0,
        ),
        transport=transport,
    ).run()

    assert summary["status"] == "passed"
    get_run_checks = [
        check for check in summary["checks"] if check["name"] == "internal_tool_get_run_invocation"
    ]
    assert [check["run_id"] for check in get_run_checks] == ["wfr-message-tool", "async-message"]
    failure_checks = [
        check
        for check in summary["checks"]
        if check["name"] == "internal_tool_get_run_failure_invocation"
    ]
    assert failure_checks[0]["run_id"] == FAILED_INTERNAL_TOOL_RUN_ID
    assert transport.calls[-1]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke"
    )
    assert transport.calls[-1]["json_body"] == {
        "arguments": {"workflow_id": "wf-message", "run_id": "async-message"}
    }


def test_acceptance_scheduled_task_invocation_requires_session_event_context() -> None:
    transport = FakeTransport(
        [
            response({"id": "task-1", "status": "active"}, status=201),
            response({"run_id": "task-run-1", "status": "accepted"}),
            response({"items": [{"id": "task-run-1", "status": "success"}], "total": 1}),
        ]
    )

    with pytest.raises(AcceptanceError, match="scheduled_task_workflow_event_context_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1", async_timeout=1, poll_interval=0),
            transport=transport,
        ).check_scheduled_task_invocation("wf-1", version_id="wfv-1")


def test_acceptance_chat_invocation_reads_live_session_stream_for_workflow_event() -> None:
    transport = FakeStreamTransport(
        [
            response({"session_id": "chat-session", "run_id": "chat-run", "status": "pending"}),
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ],
        stream_events=[
            {"event": "message:chunk", "data": {"content": "thinking"}},
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "run_id": "wfr-chat",
                    "status": "succeeded",
                    "interface": workflow_result_interface_payload(
                        workflow_id="wf-1",
                        run_id="wfr-chat",
                        version_id="wfv-1",
                    ),
                    **workflow_output_contract_payload(),
                },
            },
        ],
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(
            base_url="http://lambchat.example.test/",
            token="token-1",
        ),
        transport=transport,
    )

    result = acceptance.check_chat_invocation("wf-1", version_id="wfv-1")

    assert result["session_id"] == "chat-session"
    assert transport.stream_calls == [
        {
            "url": "http://lambchat.example.test/api/chat/sessions/chat-session/stream?run_id=chat-run",
            "headers": {"Authorization": "Bearer token-1"},
            "timeout": 15.0,
        }
    ]
    assert [call["url"] for call in transport.calls] == [
        "http://lambchat.example.test/api/chat/stream?agent_id=search",
        "http://lambchat.example.test/api/plugins/workflow/workflows/wf-1/runs/wfr-chat/events",
    ]
    assert transport.calls[0]["json_body"]["plugin_options"] == {
        "workflow": {
            "SELECTED_WORKFLOW_ID": "wf-1",
            "SELECTED_WORKFLOW_VERSION_ID": "wfv-1",
            "SELECTED_WORKFLOW_INPUT_JSON": {"items": ["alpha", "beta", "gamma"]},
        }
    }
    assert acceptance.recorder.checks[-1] == {
        "name": "chat_invocation",
        "agent_id": "search",
        "session_id": "chat-session",
        "run_id": "chat-run",
        "version_id": "wfv-1",
        "workflow_run_id": "wfr-chat",
        "next_action": "use_output",
        "next_action_reason": "workflow_run_succeeded",
        "workflow_input_keys": ["items"],
        "workflow_event_count": len(workflow_success_events()),
    }


def test_acceptance_session_workflow_event_falls_back_to_stored_events_after_stream_error() -> None:
    transport = FakeStreamTransport(
        [
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": "wf-1",
                                "run_id": "wfr-chat",
                                "status": "succeeded",
                                "interface": workflow_result_interface_payload(
                                    workflow_id="wf-1",
                                    run_id="wfr-chat",
                                    version_id=None,
                                ),
                                **workflow_output_contract_payload(),
                            },
                        }
                    ]
                }
            )
        ],
        stream_error=AcceptanceError("sse_stream_timeout"),
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    event = acceptance.poll_session_workflow_event(
        "chat-session",
        "chat-run",
        "wf-1",
        live_stream=True,
    )

    assert event["data"]["run_id"] == "wfr-chat"
    assert transport.stream_calls[0]["url"] == (
        "http://lambchat.example.test/api/chat/sessions/chat-session/stream?run_id=chat-run"
    )
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/sessions/chat-session/events?run_id=chat-run&limit=100"
    )


def test_acceptance_session_workflow_event_requires_expected_version_id() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "events": [
                        {
                            "event": "workflow:run",
                            "data": {
                                "plugin_id": "workflow",
                                "workflow_id": "wf-1",
                                "version_id": "wfv-other",
                                "run_id": "wfr-chat",
                            },
                        }
                    ]
                }
            )
        ]
    )
    clock_ticks = iter([0, 0, 1])

    with pytest.raises(AcceptanceError, match="session_workflow_event_version_mismatch"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1", async_timeout=0, poll_interval=0),
            transport=transport,
            clock=lambda: next(clock_ticks),
        ).poll_session_workflow_event(
            "session-1",
            "chat-run",
            "wf-1",
            version_id="wfv-1",
        )


def test_acceptance_checks_session_workflow_run_events() -> None:
    transport = FakeTransport(
        [
            response({"run": {"status": "succeeded"}, "events": workflow_success_events()}),
        ]
    )
    acceptance = WorkflowAcceptance(AcceptanceSettings(token="token-1"), transport=transport)

    data, events = acceptance.check_session_workflow_run_events(
        {
            "event": "workflow:run",
            "data": {
                "plugin_id": "workflow",
                "workflow_id": "wf-1",
                "version_id": "wfv-1",
                "run_id": "wfr-chat",
                "status": "succeeded",
                "interface": workflow_result_interface_payload(
                    workflow_id="wf-1",
                    run_id="wfr-chat",
                    version_id="wfv-1",
                ),
                **workflow_output_contract_payload(),
            },
        },
        source="chat",
        workflow_id="wf-1",
        version_id="wfv-1",
    )

    assert data["run_id"] == "wfr-chat"
    assert events["run"]["status"] == "succeeded"
    assert transport.calls[0]["url"] == (
        "http://127.0.0.1:8000/api/plugins/workflow/workflows/wf-1/runs/wfr-chat/events"
    )


def test_acceptance_session_workflow_event_requires_success_status() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    with pytest.raises(AcceptanceError, match="chat_workflow_run_status_unexpected"):
        acceptance.check_session_workflow_run_events(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "run_id": "wfr-chat",
                    "status": "failed",
                },
            },
            source="chat",
            workflow_id="wf-1",
            version_id="wfv-1",
        )


def test_acceptance_session_workflow_event_requires_interface() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    with pytest.raises(AcceptanceError, match="chat_workflow_interface_missing"):
        acceptance.check_session_workflow_run_events(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "run_id": "wfr-chat",
                    "status": "succeeded",
                    **workflow_output_contract_payload(),
                },
            },
            source="chat",
            workflow_id="wf-1",
            version_id="wfv-1",
        )


def test_acceptance_checks_session_workflow_failure_event_without_workflow_run_id() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    data = acceptance.check_session_workflow_failure_event(
        {
            "event": "workflow:run",
            "data": {
                "plugin_id": "workflow",
                "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                "run_id": None,
                "status": "failed",
                "error": "workflow_not_found",
                "interface": workflow_result_interface_payload(
                    workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
                    run_id=None,
                    version_id=None,
                ),
                "next_action": workflow_failed_pre_run_next_action(),
            },
        },
        source="chat_failed_pre_run",
        workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
    )

    assert data["status"] == "failed"
    assert data["error"] == "workflow_not_found"


def test_acceptance_failed_pre_run_event_requires_error_and_missing_run_id() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    with pytest.raises(AcceptanceError, match="chat_failed_pre_run_workflow_error_missing"):
        acceptance.check_session_workflow_failure_event(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                    "run_id": None,
                    "status": "failed",
                },
            },
            source="chat_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )

    with pytest.raises(AcceptanceError, match="chat_failed_pre_run_workflow_run_id_unexpected"):
        acceptance.check_session_workflow_failure_event(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                    "run_id": "wfr-should-not-exist",
                    "status": "failed",
                    "error": "workflow_not_found",
                },
            },
            source="chat_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )

    with pytest.raises(AcceptanceError, match="chat_failed_pre_run_workflow_interface_missing"):
        acceptance.check_session_workflow_failure_event(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": FAILED_PRE_RUN_WORKFLOW_ID,
                    "run_id": None,
                    "status": "failed",
                    "error": "workflow_not_found",
                    "next_action": workflow_failed_pre_run_next_action(),
                },
            },
            source="chat_failed_pre_run",
            workflow_id=FAILED_PRE_RUN_WORKFLOW_ID,
        )


def test_acceptance_session_workflow_event_requires_workflow_run_id() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    with pytest.raises(AcceptanceError, match="agent_team_workflow_run_id_missing"):
        acceptance.check_session_workflow_run_events(
            {
                "event_type": "workflow:run",
                "payload": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "status": "succeeded",
                },
            },
            source="agent_team",
            workflow_id="wf-1",
            version_id="wfv-1",
        )


def test_acceptance_session_workflow_event_requires_output_contract() -> None:
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(token="token-1"), transport=FakeTransport([])
    )

    with pytest.raises(AcceptanceError, match="chat_workflow_io_contract_missing"):
        acceptance.check_session_workflow_run_events(
            {
                "event": "workflow:run",
                "data": {
                    "plugin_id": "workflow",
                    "workflow_id": "wf-1",
                    "version_id": "wfv-1",
                    "run_id": "wfr-chat",
                    "status": "succeeded",
                },
            },
            source="chat",
            workflow_id="wf-1",
            version_id="wfv-1",
        )


def test_acceptance_fails_when_internal_workflow_tools_are_missing() -> None:
    transport = FakeTransport(
        [
            response({"server_name": "lambchat_internal", "tools": [], "count": 0}),
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_tools_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_discovery()


def test_acceptance_fails_when_workflow_run_tool_lacks_required_params() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tools": [
                        {"name": "workflow_run", "parameters": [{"name": "workflow_id"}]},
                        {"name": "workflow_list", "parameters": []},
                        {
                            "name": "workflow_get_schema",
                            "parameters": [{"name": "workflow_id"}, {"name": "version_id"}],
                        },
                        {
                            "name": "workflow_get_run",
                            "parameters": [{"name": "workflow_id"}, {"name": "run_id"}],
                        },
                    ],
                    "count": 4,
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_run_tool_missing_params"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_discovery()


def test_acceptance_fails_when_workflow_get_schema_tool_lacks_version_param() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tools": [
                        {
                            "name": "workflow_run",
                            "parameters": [
                                {"name": "workflow_id"},
                                {"name": "version_id"},
                                {"name": "input"},
                                {"name": "mode"},
                            ],
                        },
                        {"name": "workflow_list", "parameters": []},
                        {"name": "workflow_get_schema", "parameters": [{"name": "workflow_id"}]},
                        {
                            "name": "workflow_get_run",
                            "parameters": [{"name": "workflow_id"}, {"name": "run_id"}],
                        },
                    ],
                    "count": 4,
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_get_schema_tool_missing_params"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_discovery()


def test_acceptance_fails_when_workflow_get_run_tool_lacks_run_id_param() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tools": [
                        {
                            "name": "workflow_run",
                            "parameters": [
                                {"name": "workflow_id"},
                                {"name": "version_id"},
                                {"name": "input"},
                                {"name": "mode"},
                            ],
                        },
                        {"name": "workflow_list", "parameters": []},
                        {
                            "name": "workflow_get_schema",
                            "parameters": [{"name": "workflow_id"}, {"name": "version_id"}],
                        },
                        {"name": "workflow_get_run", "parameters": [{"name": "workflow_id"}]},
                    ],
                    "count": 4,
                }
            ),
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_get_run_tool_missing_params"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_discovery()


def test_acceptance_invokes_internal_workflow_run_tool() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                        "interface": workflow_result_interface_payload(),
                        **workflow_output_contract_payload(),
                    },
                }
            )
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    result = acceptance.check_internal_tool_invocation("wf-1", version_id="wfv-1")

    assert result["run_id"] == "wfr-tool"
    assert acceptance.recorder.checks[-1] == {
        "name": "internal_tool_invocation",
        "server_name": "lambchat_internal",
        "tool_name": "workflow_run",
        "workflow_id": "wf-1",
        "version_id": "wfv-1",
        "run_id": "wfr-tool",
        "workflow_input_keys": ["items"],
        "run_entry": "workflow_run.input",
        "run_exit": "output",
        "next_action": "use_output",
        "next_action_reason": "workflow_run_succeeded",
        "event_count": len(workflow_success_events()),
    }
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_run/invoke"
    )
    assert transport.calls[0]["json_body"] == {
        "arguments": {
            "workflow_id": "wf-1",
            "version_id": "wfv-1",
            "input": {"items": ["alpha", "beta", "gamma"]},
            "mode": "sync",
        }
    }


def test_acceptance_internal_workflow_run_tool_requires_output_contract() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_run_workflow_io_contract_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
            transport=transport,
        ).check_internal_tool_invocation("wf-1", version_id="wfv-1")


def test_acceptance_internal_workflow_run_tool_requires_interface() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                        **workflow_output_contract_payload(),
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_run_workflow_interface_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
            transport=transport,
        ).check_internal_tool_invocation("wf-1", version_id="wfv-1")


def test_acceptance_internal_workflow_run_tool_requires_next_action() -> None:
    payload = workflow_output_contract_payload()
    payload.pop("next_action")
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "events": workflow_success_events(),
                        "interface": workflow_result_interface_payload(),
                        **payload,
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_run_workflow_next_action_missing"):
        WorkflowAcceptance(
            AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
            transport=transport,
        ).check_internal_tool_invocation("wf-1", version_id="wfv-1")


def test_acceptance_invokes_internal_workflow_list_tool() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_list",
                    "result": {
                        "plugin_id": "workflow",
                        "scope": "published",
                        "workflows": [
                            {"workflow_id": "wf-1", "status": "published"},
                            {"workflow_id": "wf-archived", "status": "archived"},
                        ],
                    },
                }
            )
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    result = acceptance.check_internal_tool_list_invocation("wf-1")

    assert result["workflows"][0]["workflow_id"] == "wf-1"
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_list/invoke"
    )
    assert transport.calls[0]["json_body"] == {"arguments": {"scope": "published"}}


def test_acceptance_internal_workflow_list_tool_requires_imported_workflow() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_list",
                    "result": {
                        "plugin_id": "workflow",
                        "scope": "published",
                        "workflows": [{"workflow_id": "other", "status": "published"}],
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_list_missing_workflow:wf-1"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_list_invocation("wf-1")


def test_acceptance_invokes_internal_workflow_schema_tool() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "version_number": 1,
                        "input_schema": {
                            "type": "object",
                            "properties": {"items": {"type": "array"}},
                            "additionalProperties": True,
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                        "status": "published",
                        "schema_source": "inferred",
                        "interface": workflow_callable_interface_payload(
                            workflow_id="wf-1",
                            version_id="wfv-1",
                        ),
                    },
                }
            )
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    result = acceptance.check_internal_tool_schema_invocation("wf-1", version_id="wfv-1")

    assert result["input_schema"]["properties"]["items"]["type"] == "array"
    assert result["output_schema"]["properties"]["answer"]["type"] == "string"
    schema_record = next(
        item
        for item in acceptance.recorder.checks
        if item.get("name") == "internal_tool_schema_invocation"
    )
    assert schema_record["input_fields"] == ["items"]
    assert schema_record["output_fields"] == ["answer"]
    assert schema_record["run_entry"] == "workflow_run.input"
    assert schema_record["run_exit"] == "output"
    assert schema_record["schema_tool"] == "workflow_get_schema"
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_schema/invoke"
    )
    assert transport.calls[0]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "version_id": "wfv-1"}
    }


def test_acceptance_internal_workflow_schema_tool_requires_output_schema() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "input_schema": {
                            "type": "object",
                            "properties": {"items": {"type": "array"}},
                        },
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_get_schema_output_schema_invalid"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_schema_invocation(
            "wf-1",
            version_id="wfv-1",
            expected_input_fields={"items"},
        )


def test_acceptance_internal_workflow_schema_tool_requires_callable_interface() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "input_schema": {
                            "type": "object",
                            "properties": {"items": {"type": "array"}},
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                    },
                }
            )
        ]
    )

    with pytest.raises(
        AcceptanceError, match="internal_workflow_get_schema_workflow_interface_missing"
    ):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_schema_invocation(
            "wf-1",
            version_id="wfv-1",
            expected_input_fields={"items"},
        )


def test_acceptance_invokes_internal_workflow_get_run_tool() -> None:
    transport = FakeTransport(
        [
            response(
                internal_workflow_get_run_response(
                    workflow_id="wf-1",
                    run_id="wfr-tool",
                )
            )
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    result = acceptance.check_internal_tool_get_run_invocation(
        "wf-1",
        "wfr-tool",
        require_started_event=True,
        require_success_event=True,
    )

    assert result["run_id"] == "wfr-tool"
    assert acceptance.recorder.checks[-1]["run_entry"] == "workflow_run.input"
    assert acceptance.recorder.checks[-1]["run_exit"] == "output"
    assert acceptance.recorder.checks[-1]["next_action"] == "use_output"
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke"
    )
    assert transport.calls[0]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "wfr-tool"}
    }


def test_acceptance_invokes_internal_workflow_get_run_failure_tool() -> None:
    transport = FakeTransport(
        [
            response(
                internal_workflow_get_run_failure_response(
                    workflow_id="wf-1",
                    run_id="missing-run",
                )
            )
        ]
    )
    acceptance = WorkflowAcceptance(
        AcceptanceSettings(base_url="http://lambchat.example.test/", token="token-1"),
        transport=transport,
    )

    result = acceptance.check_internal_tool_get_run_failure_invocation(
        "wf-1",
        run_id="missing-run",
    )

    assert result["status"] == "failed"
    assert result["error"] == "workflow_run_not_found"
    assert result["interface"]["debug"] == {
        "tool": "workflow_get_run",
        "workflow_id": "wf-1",
        "run_id": "missing-run",
        "events_field": "events",
    }
    assert result["next_action"] == {
        "type": "handle_terminal_error",
        "field": "error",
        "reason": "workflow_run_failed",
        "tool": "workflow_get_run",
    }
    assert acceptance.recorder.checks[-1]["run_entry"] == "workflow_run.input"
    assert acceptance.recorder.checks[-1]["run_exit"] == "output"
    assert acceptance.recorder.checks[-1]["next_action"] == "handle_terminal_error"
    assert transport.calls[0]["url"] == (
        "http://lambchat.example.test/api/admin/mcp/lambchat_internal/tools/workflow_get_run/invoke"
    )
    assert transport.calls[0]["json_body"] == {
        "arguments": {"workflow_id": "wf-1", "run_id": "missing-run"}
    }


def test_acceptance_internal_workflow_schema_tool_requires_fixture_inputs() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_get_schema",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "version_id": "wfv-1",
                        "input_schema": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                        },
                        "output_schema": workflow_schema_output_schema_payload(),
                    },
                }
            )
        ]
    )

    with pytest.raises(
        AcceptanceError, match="internal_workflow_get_schema_missing_fixture_inputs"
    ):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_schema_invocation(
            "wf-1",
            version_id="wfv-1",
            expected_input_fields={"items"},
        )


def test_acceptance_internal_workflow_run_tool_requires_started_event() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "run_id": "wfr-tool",
                        "status": "succeeded",
                        "events": [{"event_type": "run_succeeded"}],
                    },
                }
            )
        ]
    )

    with pytest.raises(
        AcceptanceError, match="internal_workflow_run_started_event_missing:wfr-tool"
    ):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_invocation("wf-1")


def test_acceptance_internal_workflow_run_tool_requires_succeeded_status() -> None:
    transport = FakeTransport(
        [
            response(
                {
                    "server_name": "lambchat_internal",
                    "tool_name": "workflow_run",
                    "result": {
                        "plugin_id": "workflow",
                        "workflow_id": "wf-1",
                        "run_id": "wfr-tool",
                        "status": "failed",
                        "error": "boom",
                        "events": workflow_success_events(),
                    },
                }
            )
        ]
    )

    with pytest.raises(AcceptanceError, match="internal_workflow_run_status_unexpected"):
        WorkflowAcceptance(
            AcceptanceSettings(token="token-1"),
            transport=transport,
        ).check_internal_tool_invocation("wf-1")


def test_fixture_loading_and_required_key_helpers(tmp_path: Path) -> None:
    fixture_path = tmp_path / "workflow.json"
    fixture_path.write_text('{"workflow": {"nodes": []}}', encoding="utf-8")

    assert load_fixture(fixture_path) == {"workflow": {"nodes": []}}
    assert require_key({"workflow_id": "wf-1"}, "workflow_id") == "wf-1"
    with pytest.raises(AcceptanceError, match="missing_required_response_key"):
        require_key({}, "workflow_id")


def test_fixture_expected_input_fields_follow_templates_and_selectors() -> None:
    fixture = load_fixture(Path("tests/fixtures/workflow/dynamic_runtime_options.json"))

    assert fixture_expected_input_fields(fixture) == {"items", "limits", "message", "retrieval"}
    assert sample_input_for_fields(fixture_expected_input_fields(fixture)) == {
        "items": ["alpha", "beta", "gamma"],
        "limits": {"limit": 3, "threshold": 0.1, "max": 2},
        "message": "acceptance message",
        "retrieval": {"limit": 3, "threshold": 0.1, "max": 2},
    }


def test_fixture_expected_input_fields_ignore_produced_variables() -> None:
    fixture = load_fixture(Path("tests/fixtures/workflow/default_llm.json"))

    assert fixture_expected_input_fields(fixture) == {"query"}


def test_load_fixture_rejects_non_object_json(tmp_path: Path) -> None:
    fixture_path = tmp_path / "workflow.json"
    fixture_path.write_text("[]", encoding="utf-8")

    with pytest.raises(AcceptanceError, match="fixture_invalid_shape"):
        load_fixture(fixture_path)
