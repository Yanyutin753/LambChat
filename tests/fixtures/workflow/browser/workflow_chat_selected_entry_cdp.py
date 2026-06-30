"""Local CDP smoke for selected-workflow chat pre-run entry/exit."""

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
CHAT_SELECTED_ENTRY_SMOKE_PATH = "/codex/workflow-chat-selected-entry-smoke"


def click_testid(client: CdpClient, testid: str, timeout: float = 20) -> None:
    testid_json = json.dumps(testid)
    wait_until(
        lambda: evaluate(
            client,
            f"""
(() => {{
  const element = Array.from(document.querySelectorAll('[data-testid]'))
    .find((item) => item.getAttribute('data-testid') === {testid_json});
  return Boolean(element && !element.disabled);
}})()
""",
        ),
        timeout=timeout,
        interval=0.25,
    )
    evaluate(
        client,
        f"""
(() => {{
  const element = Array.from(document.querySelectorAll('[data-testid]'))
    .find((item) => item.getAttribute('data-testid') === {testid_json});
  if (!element) throw new Error('test id not found: ' + {testid_json});
  if (element.disabled) throw new Error('test id disabled: ' + {testid_json});
  element.click();
  return true;
}})()
""",
        timeout=10,
    )


def selected_entry_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const evidence = window.__workflowChatSelectedEntryEvidence || {};
  const workflowPart = evidence.workflowPart || {};
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
    selectedVersionId: evidence.pluginOptions?.workflow?.SELECTED_WORKFLOW_VERSION_ID,
    selectedInput: evidence.pluginOptions?.workflow?.SELECTED_WORKFLOW_INPUT_JSON || null,
    workflowPart,
    eventTypes: (evidence.streamEvents || []).map((event) => event.event),
    hasWorkflowPart: workflowPart.type === 'workflow',
    hasWorkflowRunEntry: entry.tool === 'workflow_run' && entry.argument === 'input',
    hasSchemaEntry: entry.schema_tool === 'workflow_get_schema' && entry.schema_field === 'input_schema',
    hasWorkflowExit: exit.field === 'output' && exit.schema_tool === 'workflow_get_schema',
    hasDebugRun: debug.tool === 'workflow_get_run' && debug.run_id === 'run-chat-browser',
    hasOutputContract: outputContract.valid === true && outputContract.schema_field === 'output_schema',
    hasUseOutputAction: nextAction.type === 'use_output'
      && nextAction.reason === 'workflow_run_succeeded'
      && nextAction.field === 'output',
    hasOutputText: outputText.includes('Workflow saw: Browser explicit entry message'),
    hasRenderedWorkflowResult: bodyText.includes('Workflow run wf-browser') && bodyText.includes('succeeded'),
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
  return {
    last_chat_stream_body: chatBody,
    last_workflow_run_body: runBody,
    selectedWorkflowId: workflowOptions.SELECTED_WORKFLOW_ID,
    selectedVersionId: workflowOptions.SELECTED_WORKFLOW_VERSION_ID,
    selectedInput: workflowOptions.SELECTED_WORKFLOW_INPUT_JSON || null,
    runSource: runBody.source,
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


def assert_selected_entry(evidence: dict[str, Any], request_log: dict[str, Any]) -> None:
    required_flags = [
        "hasSelection",
        "hasWorkflowPart",
        "hasWorkflowRunEntry",
        "hasSchemaEntry",
        "hasWorkflowExit",
        "hasDebugRun",
        "hasOutputContract",
        "hasUseOutputAction",
        "hasOutputText",
        "hasRenderedWorkflowResult",
    ]
    missing = [flag for flag in required_flags if evidence.get(flag) is not True]
    if missing:
        raise AssertionError(f"selected workflow chat evidence failed: {missing}")
    if evidence.get("sendState") != "streamed":
        raise AssertionError(f"chat stream did not complete: {evidence.get('sendState')}")
    if evidence.get("eventTypes") != ["user:message", "workflow:run", "message:chunk", "done"]:
        raise AssertionError(f"unexpected stream events: {evidence.get('eventTypes')}")
    if request_log.get("selectedWorkflowId") != "wf-browser":
        raise AssertionError(f"missing selected workflow option: {request_log}")
    if request_log.get("selectedVersionId") != "wfv-browser-2":
        raise AssertionError(f"missing selected workflow version option: {request_log}")
    if request_log.get("selectedInput") != {
        "topic": "browser-selected-entry",
        "query": "explicit chat query",
    }:
        raise AssertionError(f"missing selected workflow input payload: {request_log}")
    if request_log.get("runSource") != "chat_selected_workflow":
        raise AssertionError(f"workflow run source was not recorded: {request_log}")
    if request_log.get("runWorkflowId") != "wf-browser" or request_log.get("runVersionId") != "wfv-browser-2":
        raise AssertionError(f"workflow run target mismatch: {request_log}")
    if request_log.get("runMode") != "sync":
        raise AssertionError(f"workflow run mode mismatch: {request_log}")
    if request_log.get("runEntryTool") != "workflow_run" or request_log.get("runEntryArgument") != "input":
        raise AssertionError(f"workflow run entry mismatch: {request_log}")
    if request_log.get("runExitField") != "output":
        raise AssertionError(f"workflow run exit mismatch: {request_log}")
    run_input = request_log.get("runInput") or {}
    if run_input.get("message") != "Browser explicit entry message":
        raise AssertionError(f"workflow run input did not include chat message: {request_log}")
    if run_input.get("topic") != "browser-selected-entry" or run_input.get("query") != "explicit chat query":
        raise AssertionError(f"workflow run input did not merge explicit input: {request_log}")


def run_chat_selected_entry(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-chat-workflow-entry-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + CHAT_SELECTED_ENTRY_SMOKE_PATH)
        wait_for_text(client, "workflow chat selected entry smoke", timeout=60)
        click_testid(client, "codex-send-selected-workflow-chat", timeout=30)
        evidence = wait_until(
            lambda: item
            if (item := selected_entry_evidence(client)).get("sendState") == "streamed"
            and item.get("hasWorkflowPart")
            and item.get("hasOutputText")
            and item.get("hasRenderedWorkflowResult")
            else None,
            timeout=45,
            interval=0.5,
        )
        request_log = wait_until(
            lambda: item
            if (item := request_log_evidence(client)).get("runEntryTool") == "workflow_run"
            and item.get("runExitField") == "output"
            else None,
            timeout=30,
            interval=0.5,
        )
        assert_selected_entry(evidence, request_log)

        screenshot_path = out_dir / f"workflow-chat-selected-entry-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": CHAT_SELECTED_ENTRY_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "evidence": evidence,
            "request_log": request_log,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-chat-selected-entry-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "selected_workflow_id": request_log["selectedWorkflowId"],
                    "run_entry_tool": request_log["runEntryTool"],
                    "run_exit_field": request_log["runExitField"],
                    "has_output_text": evidence["hasOutputText"],
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

    response = requests.get(base_url + CHAT_SELECTED_ENTRY_SMOKE_PATH, timeout=2)
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
        run_chat_selected_entry(base_url, chrome_path, out_dir)
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
