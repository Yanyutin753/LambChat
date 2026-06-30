"""Local CDP smoke for Agent Team selected-workflow pre-run entry/exit."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from workflow_chat_selected_entry_cdp import click_testid
from workflow_editor_interaction_cdp import start_vite_mock_server
from workflow_tool_approval_result_cdp import DEFAULT_BASE_URL, DEFAULT_NODE
from workflow_ui_acceptance_cdp import (
    DEFAULT_CHROME,
    CdpClient,
    connect_tab,
    evaluate,
    free_port,
    launch_chrome,
    navigate,
    render_console_issues,
    screenshot,
    wait_for_text,
    wait_until,
)

OUT_DIR = Path(__file__).resolve().parent
AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH = "/codex/workflow-agent-team-selected-entry-smoke"


def agent_team_selected_entry_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const evidence = window.__workflowAgentTeamSelectedEntryEvidence || {};
  const workflowPart = evidence.workflowPart || {};
  const subagentPart = evidence.subagentPart || {};
  const entry = workflowPart.interface?.entry || {};
  const exit = workflowPart.interface?.exit || {};
  const debug = workflowPart.interface?.debug || {};
  const nextAction = workflowPart.next_action || {};
  const outputContract = workflowPart.output_contract || {};
  const outputText = JSON.stringify(workflowPart.output || {});
  const bodyText = document.body.textContent || '';
  return {
    sendState: evidence.sendState,
    hasSelection: evidence.hasSelection,
    selectedWorkflowId: evidence.pluginOptions?.workflow?.SELECTED_WORKFLOW_ID,
    selectedTeamId: evidence.pluginOptions?.agent_team?.SELECTED_TEAM_ID,
    selectedInput: evidence.pluginOptions?.workflow?.SELECTED_WORKFLOW_INPUT_JSON || null,
    eventTypes: (evidence.streamEvents || []).map((event) => event.event),
    subagentPart,
    workflowPart,
    hasSubagentPart: subagentPart.type === 'subagent'
      && (subagentPart.agent_name || '').includes('Workflow Researcher'),
    hasNestedWorkflowPart: workflowPart.type === 'workflow'
      && workflowPart.plugin_id === 'workflow'
      && workflowPart.depth === 1
      && workflowPart.agent_id === 'team-m-browser-researcher',
    hasWorkflowRunEntry: entry.tool === 'workflow_run' && entry.argument === 'input',
    hasSchemaEntry: entry.schema_tool === 'workflow_get_schema' && entry.schema_field === 'input_schema',
    hasWorkflowExit: exit.field === 'output' && exit.schema_tool === 'workflow_get_schema',
    hasDebugRun: debug.tool === 'workflow_get_run' && debug.run_id === 'run-agent-team-live-browser',
    hasOutputContract: outputContract.valid === true && outputContract.schema_field === 'output_schema',
    hasUseOutputAction: nextAction.type === 'use_output'
      && nextAction.reason === 'workflow_run_succeeded'
      && nextAction.field === 'output',
    hasOutputText: outputText.includes('Agent Team workflow saw: Agent Team explicit entry message'),
    hasRenderedTeamResult: (bodyText.includes('Workflow Researcher') || bodyText.includes('Workflow researcher'))
      && bodyText.includes('Agent Team synthesis after selected workflow.'),
    bodyText,
  };
})()
""",
        timeout=10,
    )


def request_log_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(async () => {
  const response = await fetch('/api/codex/request-log');
  const data = await response.json();
  const chatBody = data.last_chat_stream_body || {};
  const runBody = data.last_workflow_run_body || {};
  const workflowOptions = chatBody.plugin_options?.workflow || {};
  const teamOptions = chatBody.plugin_options?.agent_team || {};
  return {
    last_chat_stream_body: chatBody,
    last_workflow_run_body: runBody,
    chatAgentId: chatBody.agent_id,
    selectedTeamId: teamOptions.SELECTED_TEAM_ID,
    selectedWorkflowId: workflowOptions.SELECTED_WORKFLOW_ID,
    selectedVersionId: workflowOptions.SELECTED_WORKFLOW_VERSION_ID,
    selectedInput: workflowOptions.SELECTED_WORKFLOW_INPUT_JSON || null,
    runSource: runBody.source,
    callerPluginId: runBody.caller_plugin_id,
    runAgentId: runBody.agent_id,
    runTeamId: runBody.team_id,
    runWorkflowId: runBody.workflow_id,
    runVersionId: runBody.version_id,
    runMode: runBody.mode,
    runInput: runBody.input || {},
    runEntryTool: runBody.interface?.entry?.tool,
    runEntryArgument: runBody.interface?.entry?.argument,
    runExitField: runBody.interface?.exit?.field,
  };
})()
""",
        timeout=15,
        await_promise=True,
    )


def assert_agent_team_selected_entry(evidence: dict[str, Any], request_log: dict[str, Any]) -> None:
    required_flags = [
        "hasSelection",
        "hasSubagentPart",
        "hasNestedWorkflowPart",
        "hasWorkflowRunEntry",
        "hasSchemaEntry",
        "hasWorkflowExit",
        "hasDebugRun",
        "hasOutputContract",
        "hasUseOutputAction",
        "hasOutputText",
        "hasRenderedTeamResult",
    ]
    missing = [flag for flag in required_flags if evidence.get(flag) is not True]
    if missing:
        raise AssertionError(f"Agent Team selected workflow evidence failed: {missing}")
    if evidence.get("sendState") != "streamed":
        raise AssertionError(f"Agent Team chat stream did not complete: {evidence.get('sendState')}")
    expected_events = [
        "user:message",
        "agent:call",
        "workflow:run",
        "agent:result",
        "message:chunk",
        "done",
    ]
    if evidence.get("eventTypes") != expected_events:
        raise AssertionError(f"unexpected Agent Team stream events: {evidence.get('eventTypes')}")
    if request_log.get("chatAgentId") != "team":
        raise AssertionError(f"chat was not sent to Agent Team: {request_log}")
    if request_log.get("selectedTeamId") != "team-browser" or request_log.get("runTeamId") != "team-browser":
        raise AssertionError(f"missing selected Agent Team option: {request_log}")
    if request_log.get("selectedWorkflowId") != "wf-browser":
        raise AssertionError(f"missing selected workflow option: {request_log}")
    if request_log.get("selectedVersionId") != "wfv-browser-2":
        raise AssertionError(f"missing selected workflow version option: {request_log}")
    if request_log.get("selectedInput") != {
        "topic": "agent-team-selected-entry",
        "query": "agent team explicit query",
    }:
        raise AssertionError(f"missing selected workflow input payload: {request_log}")
    if request_log.get("runSource") != "agent_team_selected_workflow":
        raise AssertionError(f"workflow run source mismatch: {request_log}")
    if request_log.get("callerPluginId") != "agent_team":
        raise AssertionError(f"caller plugin mismatch: {request_log}")
    if request_log.get("runAgentId") != "team":
        raise AssertionError(f"workflow run agent mismatch: {request_log}")
    if request_log.get("runEntryTool") != "workflow_run" or request_log.get("runEntryArgument") != "input":
        raise AssertionError(f"workflow run entry mismatch: {request_log}")
    if request_log.get("runExitField") != "output":
        raise AssertionError(f"workflow run exit mismatch: {request_log}")
    run_input = request_log.get("runInput") or {}
    if run_input.get("message") != "Agent Team explicit entry message":
        raise AssertionError(f"workflow run input did not include Agent Team message: {request_log}")
    if run_input.get("topic") != "agent-team-selected-entry" or run_input.get("query") != "agent team explicit query":
        raise AssertionError(f"workflow run input did not merge Agent Team explicit input: {request_log}")


def run_agent_team_selected_entry(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-agent-team-workflow-entry-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH)
        wait_for_text(client, "workflow agent team selected entry smoke", timeout=60)
        click_testid(client, "codex-send-agent-team-selected-workflow-chat", timeout=30)
        evidence = wait_until(
            lambda: item
            if (item := agent_team_selected_entry_evidence(client)).get("sendState") == "streamed"
            and item.get("hasNestedWorkflowPart")
            and item.get("hasOutputText")
            else None,
            timeout=45,
            interval=0.5,
        )
        request_log = wait_until(
            lambda: item
            if (item := request_log_evidence(client)).get("runSource") == "agent_team_selected_workflow"
            and item.get("runEntryTool") == "workflow_run"
            and item.get("runExitField") == "output"
            else None,
            timeout=30,
            interval=0.5,
        )
        assert_agent_team_selected_entry(evidence, request_log)

        screenshot_path = out_dir / f"workflow-agent-team-selected-entry-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "evidence": evidence,
            "request_log": request_log,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-agent-team-selected-entry-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "selected_team_id": request_log["selectedTeamId"],
                    "selected_workflow_id": request_log["selectedWorkflowId"],
                    "run_source": request_log["runSource"],
                    "run_entry_tool": request_log["runEntryTool"],
                    "run_exit_field": request_log["runExitField"],
                    "has_nested_workflow_part": evidence["hasNestedWorkflowPart"],
                    "console_issue_count": len(console_issues),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return result
    finally:
        if client:
            client.close()
        if proc:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
            if proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.kill()
        with contextlib.suppress(Exception):
            shutil.rmtree(temp_profile)


def evaluate_health(base_url: str) -> bool:
    import requests

    response = requests.get(base_url + AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH, timeout=2)
    return response.ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--node", default=DEFAULT_NODE)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--start-vite", action="store_true")
    parser.add_argument("--vite-port", type=int, default=3232)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chrome_path = Path(args.chrome)
    vite_proc: subprocess.Popen[bytes] | None = None
    base_url = args.base_url.rstrip("/")

    try:
        if args.start_vite:
            node_path = Path(args.node)
            vite_proc = start_vite_mock_server(node_path, args.vite_port)
            base_url = f"http://127.0.0.1:{args.vite_port}"
            wait_until(lambda: evaluate_health(base_url), timeout=60, interval=0.5)
        run_agent_team_selected_entry(base_url, chrome_path, out_dir)
        return 0
    finally:
        if vite_proc:
            vite_proc.terminate()
            with contextlib.suppress(Exception):
                vite_proc.wait(timeout=10)
            if vite_proc.poll() is None:
                with contextlib.suppress(Exception):
                    vite_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
