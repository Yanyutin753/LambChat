"""Production Workflow UI acceptance via local Chrome/CDP.

This is a goal-ledger audit harness, not product code. It launches an isolated
headless Chrome profile, seeds the same localStorage token keys used by the
frontend, exercises the production /workflows page, and writes screenshots plus
a JSON evidence file under goal-1.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests
import websocket

DEFAULT_BASE_URL = "http://172.18.95.15:9123"
DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until(predicate: Callable[[], Any], timeout: float, interval: float = 0.25) -> Any:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001 - keep the latest probe error for diagnostics.
            last_error = exc
        time.sleep(interval)
    if last_error:
        raise TimeoutError(str(last_error)) from last_error
    raise TimeoutError("condition timed out")


@dataclass
class CdpClient:
    websocket_url: str
    ws: websocket.WebSocket = field(init=False)
    next_id: int = 1
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ws = websocket.create_connection(self.websocket_url, timeout=10)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15) -> dict[str, Any]:
        call_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.time()))
            message = json.loads(self.ws.recv())
            if message.get("id") == call_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)
        raise TimeoutError(f"CDP {method} timed out")


def launch_chrome(chrome_path: Path, port: int, user_data_dir: Path) -> subprocess.Popen[bytes]:
    args = [
        str(chrome_path),
        "--headless=new",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-gpu",
        "--window-size=1440,1100",
        "about:blank",
    ]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def connect_tab(port: int, base_url: str) -> CdpClient:
    endpoint = f"http://127.0.0.1:{port}"
    wait_until(lambda: requests.get(f"{endpoint}/json/version", timeout=1).ok, timeout=20)
    response = requests.put(f"{endpoint}/json/new?{quote(base_url + '/', safe=':/?=&')}", timeout=5)
    response.raise_for_status()
    tab_info = response.json()
    client = CdpClient(tab_info["webSocketDebuggerUrl"])
    for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
        client.call(method)
    client.call(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 1100, "deviceScaleFactor": 1, "mobile": False},
    )
    return client


def evaluate(client: CdpClient, expression: str, *, timeout: float = 15, await_promise: bool = False) -> Any:
    result = client.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
            "userGesture": True,
        },
        timeout=timeout,
    )
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        text = details.get("text") or details.get("exception", {}).get("description") or str(details)
        raise RuntimeError(text)
    remote = result.get("result", {})
    return remote.get("value")


def navigate(client: CdpClient, url: str) -> None:
    client.call("Page.navigate", {"url": url}, timeout=10)
    wait_until(
        lambda: evaluate(client, "document.readyState === 'interactive' || document.readyState === 'complete'"),
        timeout=45,
    )


def wait_for_text(client: CdpClient, text: str, timeout: float = 45) -> bool:
    needle = json.dumps(text)
    return bool(
        wait_until(
            lambda: evaluate(client, f"document.body && document.body.innerText.includes({needle})"),
            timeout=timeout,
        )
    )


def screenshot(client: CdpClient, path: Path) -> None:
    data = client.call(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "captureBeyondViewport": True},
        timeout=20,
    )["data"]
    path.write_bytes(base64.b64decode(data))


def read_token_pair(token_file: Path) -> dict[str, str]:
    raw = token_file.read_text(encoding="utf-8-sig").strip()
    payload = json.loads(raw)
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise ValueError("token file must contain access_token and refresh_token strings")
    return {"access_token": access_token, "refresh_token": refresh_token}


def visible_snapshot(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const text = document.body?.innerText || '';
  const buttons = Array.from(document.querySelectorAll('button'))
    .map((button) => button.innerText.trim())
    .filter(Boolean)
    .slice(0, 80);
  const selects = Array.from(document.querySelectorAll('select')).map((select) => ({
    value: select.value,
    options: Array.from(select.options).map((option) => option.value || option.textContent || ''),
  }));
  return {
    path: location.pathname,
    title: document.title,
    textChecks: {
      workflowPlugin: text.includes('Workflow'),
      workflowList: text.includes('Workflows'),
      importPanel: text.includes('Import Workflow DSL'),
      graphEditor: text.includes('Graph Editor'),
      debugVersion: text.includes('Debug version'),
      runEvents: text.includes('Run Events'),
      compatibility: text.includes('Compatibility') || text.includes('Node compatibility'),
      credentialVault: text.includes('Credential Vault'),
    },
    buttons,
    selects,
    sample: text.slice(0, 1400),
  };
})()
""",
        timeout=10,
    )


def page_fetch_evidence(client: CdpClient, workflow_name: str) -> dict[str, Any]:
    return evaluate(
        client,
        f"""
(async () => {{
  const token = localStorage.getItem('access_token');
  const headers = {{ Authorization: `Bearer ${{token}}` }};
  const getJson = async (url) => {{
    const response = await fetch(url, {{ headers }});
    const text = await response.text();
    let data = null;
    try {{ data = text ? JSON.parse(text) : null; }} catch {{ data = text; }}
    return {{ status: response.status, data }};
  }};
  const list = await getJson('/api/plugins/workflow/workflows?skip=0&limit=100');
  const workflows = Array.isArray(list.data?.workflows) ? list.data.workflows : [];
  const workflow = workflows.find((item) => item.name === {json.dumps(workflow_name)});
  if (!workflow) {{
    return {{ found: false, listStatus: list.status, total: list.data?.total ?? workflows.length }};
  }}
  const encoded = encodeURIComponent(workflow.workflow_id);
  const [detail, versions, runs, schema, approvals, nodeTypes] = await Promise.all([
    getJson(`/api/plugins/workflow/workflows/${{encoded}}`),
    getJson(`/api/plugins/workflow/workflows/${{encoded}}/versions`),
    getJson(`/api/plugins/workflow/workflows/${{encoded}}/runs?skip=0&limit=20`),
    getJson(`/api/plugins/workflow/workflows/${{encoded}}/input-schema`),
    getJson('/api/plugins/workflow/approvals/pending?skip=0&limit=20'),
    getJson('/api/plugins/workflow/node-types'),
  ]);
  const versionsList = Array.isArray(versions.data?.versions) ? versions.data.versions : [];
  const latestVersion = detail.data?.latest_version || versionsList[0] || null;
  const latestVersionGraph = latestVersion?.internal_model?.graph || latestVersion?.source_payload?.workflow || {{}};
  const latestVersionGraphNodes = Array.isArray(latestVersionGraph.nodes) ? latestVersionGraph.nodes : [];
  const humanApprovalNode = latestVersionGraphNodes.find((node) => node?.type === 'human_approval') || null;
  const latestRun = Array.isArray(runs.data?.runs) ? runs.data.runs[0] : null;
  let events = null;
  if (latestRun?.run_id) {{
    events = await getJson(`/api/plugins/workflow/workflows/${{encoded}}/runs/${{encodeURIComponent(latestRun.run_id)}}/events`);
  }}
  const eventList = events?.data?.events || [];
  const eventNodeCounts = eventList.reduce((counts, event) => {{
    if (!event?.node_id) return counts;
    counts[event.node_id] = (counts[event.node_id] || 0) + 1;
    return counts;
  }}, {{}});
  return {{
    found: true,
    listStatus: list.status,
    total: list.data?.total ?? workflows.length,
    workflow,
    detail: detail.data,
    versionCount: versionsList.length,
    versionIds: versionsList.map((version) => version.version_id).filter(Boolean),
    latestVersion,
    latestVersionNodeTypes: latestVersionGraphNodes.map((node) => node?.type).filter(Boolean),
    latestVersionNodeIds: latestVersionGraphNodes.map((node) => node?.id).filter(Boolean),
    humanApprovalNodeData: humanApprovalNode?.data ?? null,
    latestVersionId: latestVersion?.version_id ?? detail.data?.latest_version_id ?? workflow.latest_version_id ?? null,
    latestVersionNumber: latestVersion?.version_number ?? null,
    latestVersionStatus: latestVersion?.status ?? null,
    publishedVersionId: detail.data?.published_version_id ?? workflow.published_version_id ?? null,
    runCount: runs.data?.runs?.length ?? 0,
    latestRun,
    eventCount: eventList.length,
    eventTypes: eventList.map((event) => event.event_type),
    eventNodeIds: Array.from(new Set(eventList.map((event) => event.node_id).filter(Boolean))),
    eventNodeCounts,
    inputFields: Object.keys(schema.data?.input_schema?.properties || {{}}),
    pendingApprovalCount: approvals.data?.runs?.length ?? 0,
    nodeTypeCount: nodeTypes.data?.node_types?.length ?? 0,
    compatibilityTotal: nodeTypes.data?.compatibility?.summary?.total ?? null,
  }};
}})()
""",
        timeout=30,
        await_promise=True,
    )


def click_button(client: CdpClient, label: str, timeout: float = 20) -> None:
    label_json = json.dumps(label)
    wait_until(
        lambda: evaluate(
            client,
            f"""
(() => {{
  const button = Array.from(document.querySelectorAll('button')).find((item) => item.innerText.trim() === {label_json});
  return Boolean(button && !button.disabled);
}})()
""",
        ),
        timeout=timeout,
    )
    evaluate(
        client,
        f"""
(() => {{
  const button = Array.from(document.querySelectorAll('button')).find((item) => item.innerText.trim() === {label_json});
  if (!button) throw new Error('button not found: ' + {label_json});
  if (button.disabled) throw new Error('button disabled: ' + {label_json});
  button.click();
  return true;
}})()
""",
    )


def click_testid(client: CdpClient, testid: str, timeout: float = 20) -> None:
    testid_json = json.dumps(testid)
    wait_until(
        lambda: evaluate(
            client,
            f"""
(() => {{
  const element = document.querySelector(`[data-testid="${{${testid_json}}}"]`);
  return Boolean(element && !element.disabled);
}})()
""",
        ),
        timeout=timeout,
    )
    evaluate(
        client,
        f"""
(() => {{
  const element = document.querySelector(`[data-testid="${{${testid_json}}}"]`);
  if (!element) throw new Error('test id not found: ' + {testid_json});
  if (element.disabled) throw new Error('test id disabled: ' + {testid_json});
  element.click();
  return true;
}})()
""",
        timeout=10,
    )


def set_select_by_testid(client: CdpClient, testid: str, value: str, timeout: float = 20) -> None:
    testid_json = json.dumps(testid)
    value_json = json.dumps(value)
    wait_until(
        lambda: evaluate(
            client,
            f"""
(() => {{
  const element = document.querySelector(`[data-testid="${{${testid_json}}}"]`);
  return Boolean(element && element instanceof HTMLSelectElement && !element.disabled);
}})()
""",
        ),
        timeout=timeout,
    )
    evaluate(
        client,
        f"""
(() => {{
  const element = document.querySelector(`[data-testid="${{${testid_json}}}"]`);
  if (!element) throw new Error('test id not found: ' + {testid_json});
  if (!(element instanceof HTMLSelectElement)) throw new Error('test id is not a select: ' + {testid_json});
  if (element.disabled) throw new Error('test id disabled: ' + {testid_json});
  element.value = {value_json};
  element.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
""",
        timeout=10,
    )


def set_form_field_by_title(client: CdpClient, title: str, value: str) -> None:
    title_json = json.dumps(title)
    value_json = json.dumps(value)
    evaluate(
        client,
        f"""
(() => {{
  const element = Array.from(document.querySelectorAll('input, textarea, select')).find((item) => item.title === {title_json});
  if (!element) throw new Error('form field not found: ' + {title_json});
  const prototype = element instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : element instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (!setter) throw new Error('native value setter missing: ' + {title_json});
  setter.call(element, {value_json});
  element.dispatchEvent(new Event('input', {{ bubbles: true }}));
  element.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
""",
        timeout=10,
    )


def set_form_field_by_placeholder(client: CdpClient, placeholder: str, value: str) -> None:
    placeholder_json = json.dumps(placeholder)
    value_json = json.dumps(value)
    evaluate(
        client,
        f"""
(() => {{
  const element = Array.from(document.querySelectorAll('input, textarea')).find((item) => item.placeholder === {placeholder_json});
  if (!element) throw new Error('form field not found: ' + {placeholder_json});
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (!setter) throw new Error('native value setter missing: ' + {placeholder_json});
  setter.call(element, {value_json});
  element.dispatchEvent(new Event('input', {{ bubbles: true }}));
  element.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
""",
        timeout=10,
    )


def add_human_approval_node(client: CdpClient) -> dict[str, Any]:
    click_testid(client, "workflow-node-add-human_approval", timeout=30)
    wait_until(
        lambda: evaluate(client, "Boolean(document.querySelector('[title=\"Approval instructions\"]'))"),
        timeout=20,
    )
    set_form_field_by_title(client, "Approval instructions", "Approve UI acceptance {{message}}")
    set_form_field_by_title(client, "Approval assignee", "qa-reviewer")
    set_form_field_by_title(client, "Approval output key", "qa_approval")
    return wait_until(
        lambda: (
            state
            if (state := human_approval_editor_state(client)).get("selectedNodeType") == "human_approval"
            and state.get("instructions") == "Approve UI acceptance {{message}}"
            and state.get("assignee") == "qa-reviewer"
            and state.get("outputKey") == "qa_approval"
            else None
        ),
        timeout=20,
    )


def human_approval_panel_state(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const text = document.body?.innerText || '';
  const approvalComment = Array.from(document.querySelectorAll('textarea'))
    .find((item) => item.placeholder === 'Approval comment')?.value ?? null;
  return {
    hasApprovalPanel: text.includes('Workflow paused for approval') || text.includes('Human approval') || text.includes('UI approval'),
    hasUiApprovalTitle: text.includes('UI approval'),
    hasInstructions: text.includes('Approve UI acceptance'),
    hasAssignee: text.includes('Assignee qa-reviewer'),
    hasOutputKey: text.includes('Output approval'),
    hasApproveButton: Array.from(document.querySelectorAll('button')).some((button) => button.innerText.trim() === 'Approve'),
    hasResumeEvent: text.includes('human_approval_resumed'),
    hasSucceededRun: /succeeded/.test(text),
    approvalComment,
    snippet: text.slice(Math.max(0, text.indexOf('UI approval') - 120), text.indexOf('UI approval') + 500),
  };
})()
""",
        timeout=10,
    )


def run_human_approval_flow(client: CdpClient, workflow_name: str) -> dict[str, Any]:
    choose_run_mode(client, "async")
    click_testid(client, "workflow-run-version", timeout=30)
    paused_ui = wait_until(
        lambda: (
            state
            if (state := human_approval_panel_state(client)).get("hasUiApprovalTitle")
            and state.get("hasInstructions")
            and state.get("hasApproveButton")
            else None
        ),
        timeout=60,
        interval=0.5,
    )
    paused_evidence = wait_until(
        lambda: (
            evidence
            if (evidence := page_fetch_evidence(client, workflow_name)).get("latestRun", {}).get("status") == "paused"
            and evidence.get("pendingApprovalCount", 0) > 0
            and "human_approval_required" in evidence.get("eventTypes", [])
            else None
        ),
        timeout=60,
        interval=1,
    )
    set_form_field_by_placeholder(client, "Approval comment", "CDP approval comment")
    click_testid(client, "workflow-approval-approve", timeout=30)
    resumed_ui = wait_until(
        lambda: (
            state
            if (state := human_approval_panel_state(client)).get("hasResumeEvent")
            and state.get("hasSucceededRun")
            else None
        ),
        timeout=60,
        interval=0.5,
    )
    resumed_evidence = wait_until(
        lambda: (
            evidence
            if (evidence := page_fetch_evidence(client, workflow_name)).get("latestRun", {}).get("status") == "succeeded"
            and "human_approval_resumed" in evidence.get("eventTypes", [])
            and ((evidence.get("latestRun") or {}).get("output") or {}).get("answer") == "Approved CDP approval comment"
            else None
        ),
        timeout=80,
        interval=1,
    )
    return {
        "paused_ui": paused_ui,
        "paused_evidence": paused_evidence,
        "resumed_ui": resumed_ui,
        "resumed_evidence": resumed_evidence,
    }


def human_approval_editor_state(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const selectedNodeId = document.querySelector('[data-testid="workflow-selected-node-id"]')?.value || null;
  const nodeTypeSelect = Array.from(document.querySelectorAll('select')).find((select) =>
    Array.from(select.options).some((option) => option.value === 'human_approval')
  );
  const valueByTitle = (title) => Array.from(document.querySelectorAll('input, textarea, select'))
    .find((element) => element.title === title)?.value || '';
  return {
    hasPaletteAdd: Boolean(document.querySelector('[data-testid="workflow-node-add-human_approval"]')),
    selectedNodeId,
    selectedNodeType: nodeTypeSelect?.value || null,
    instructions: valueByTitle('Approval instructions'),
    assignee: valueByTitle('Approval assignee'),
    outputKey: valueByTitle('Approval output key'),
  };
})()
""",
        timeout=10,
    )


def fill_import_form(client: CdpClient, workflow_name: str, dsl_text: str) -> None:
    evaluate(
        client,
        f"""
(() => {{
  const setNativeValue = (element, value) => {{
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
    if (!setter) throw new Error('native value setter missing');
    setter.call(element, value);
    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
    element.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const nameInput = Array.from(document.querySelectorAll('input')).find((input) => input.placeholder === 'Workflow name');
  const dslInput = document.querySelector('textarea');
  if (!nameInput) throw new Error('workflow name input not found');
  if (!dslInput) throw new Error('DSL textarea not found');
  setNativeValue(nameInput, {json.dumps(workflow_name)});
  setNativeValue(dslInput, {json.dumps(dsl_text)});
  return true;
}})()
""",
        timeout=10,
    )


def choose_run_mode(client: CdpClient, mode: str) -> None:
    set_select_by_testid(client, "workflow-run-mode", mode)


def canvas_run_status_state(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const textByTestId = (testId) => document.querySelector(`[data-testid="${testId}"]`)?.textContent?.trim() || null;
  const nodeTextByTestId = (testId) => document.querySelector(`[data-testid="${testId}"]`)?.textContent || null;
  return {
    startStatus: textByTestId('workflow-canvas-run-status-start'),
    answerStatus: textByTestId('workflow-canvas-run-status-answer'),
    startNodeText: nodeTextByTestId('workflow-canvas-node-start'),
    answerNodeText: nodeTextByTestId('workflow-canvas-node-answer'),
    hasStartHandle: Boolean(document.querySelector('[data-testid="workflow-canvas-source-handle-start-default"]')),
    hasAnswerHandle: Boolean(document.querySelector('[data-testid="workflow-canvas-source-handle-answer-default"]')),
  };
})()
""",
        timeout=10,
    )


def run_events_panel_state(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const text = document.body?.innerText || '';
  const runEventsIndex = text.indexOf('Run Events');
  const selectedNodeId = document.querySelector('[data-testid="workflow-selected-node-id"]')?.value || null;
  const eventButtons = Array.from(document.querySelectorAll('button'))
    .map((button) => button.innerText.trim())
    .filter(Boolean)
    .filter((label) => label === 'All events' || /^start\\s+\\d+$/.test(label) || /^answer\\s+\\d+$/.test(label));
  const runEventsMatch = text.match(/Run Events\\s+([^\\n]+)/);
  return {
    selectedNodeId,
    eventButtons,
    runEventsCountText: runEventsMatch ? runEventsMatch[1].trim() : null,
    hasFocusedAnswerCount: /Run Events\\s+2\\/\\d+/.test(text),
    hasAllEventsCount: /Run Events\\s+\\d+\\s+All events/.test(text),
    runEventsSnippet: runEventsIndex >= 0 ? text.slice(runEventsIndex, runEventsIndex + 700) : '',
  };
})()
""",
        timeout=10,
    )


def workflow_route_panel_state(client: CdpClient, workflow_name: str) -> dict[str, Any]:
    workflow_name_json = json.dumps(workflow_name)
    return evaluate(
        client,
        f"""
(() => {{
  const text = document.body?.innerText || '';
  const runEventsMatch = text.match(/Run Events\\s+([^\\n]+)/);
  return {{
    path: location.pathname,
    hasWorkflowName: text.includes({workflow_name_json}),
    hasGraphEditor: text.includes('Graph Editor'),
    hasDebugVersion: text.includes('Debug version'),
    hasRunEvents: text.includes('Run Events'),
    hasCanvas: Boolean(document.querySelector('[data-testid="workflow-canvas"]')),
    hasReactFlow: Boolean(document.querySelector('[data-testid="workflow-react-flow"]')),
    hasNodePalette: Boolean(document.querySelector('[data-testid="workflow-node-palette"]')),
    selectedNodeId: document.querySelector('[data-testid="workflow-selected-node-id"]')?.value || null,
    runEventsCountText: runEventsMatch ? runEventsMatch[1].trim() : null,
  }};
}})()
""",
        timeout=10,
    )


def click_run_event_node_filter(client: CdpClient, node_id: str, count: int, timeout: float = 20) -> dict[str, Any]:
    label = f"{node_id}\n{count}"
    label_json = json.dumps(label)
    wait_until(
        lambda: evaluate(
            client,
            f"""
(() => {{
  const button = Array.from(document.querySelectorAll('button')).find((item) => item.innerText.trim() === {label_json});
  return Boolean(button && !button.disabled);
}})()
""",
        ),
        timeout=timeout,
    )
    evaluate(
        client,
        f"""
(() => {{
  const button = Array.from(document.querySelectorAll('button')).find((item) => item.innerText.trim() === {label_json});
  if (!button) throw new Error('run event node filter not found: ' + {label_json});
  if (button.disabled) throw new Error('run event node filter disabled: ' + {label_json});
  button.click();
  return true;
}})()
""",
        timeout=10,
    )
    return wait_until(
        lambda: (
            state
            if (state := run_events_panel_state(client)).get("hasFocusedAnswerCount")
            and state.get("selectedNodeId") == node_id
            else None
        ),
        timeout=timeout,
    )


def rename_selected_workflow_node(client: CdpClient, next_node_id: str) -> dict[str, Any]:
    next_id_json = json.dumps(next_node_id)
    evaluate(
        client,
        f"""
(() => {{
  const input = document.querySelector('[data-testid="workflow-selected-node-id"]');
  if (!input) throw new Error('selected node id input not found');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  if (!setter) throw new Error('native input value setter missing');
  setter.call(input, {next_id_json});
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  input.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
""",
        timeout=10,
    )
    return wait_until(
        lambda: (
            state
            if (state := run_events_panel_state(client)).get("selectedNodeId") == next_node_id
            and state.get("hasAllEventsCount")
            else None
        ),
        timeout=20,
    )


def render_console_issues(events: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for event in events:
        method = event.get("method")
        params = event.get("params") or {}
        if method == "Runtime.consoleAPICalled" and params.get("type") in {"error", "warning"}:
            args = params.get("args") or []
            message = " ".join(str(arg.get("value") or arg.get("description") or "") for arg in args).strip()
            if message:
                issues.append(f"console:{params.get('type')}:{message}")
        elif method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") in {"error", "warning"}:
                message = str(entry.get("text") or "").strip()
                if message:
                    issues.append(f"log:{entry.get('level')}:{message}")
        elif method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails") or {}
            message = str(details.get("text") or details.get("exception", {}).get("description") or "").strip()
            issues.append(f"exception:{message}")
    seen: set[str] = set()
    deduped: list[str] = []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--chrome", default=DEFAULT_CHROME)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--delete-token-file", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    chrome_path = Path(args.chrome)
    token_file = Path(args.token_file)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not chrome_path.exists():
        raise FileNotFoundError(chrome_path)

    token_pair = read_token_pair(token_file)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    workflow_name = f"UI acceptance {stamp}"
    approval_workflow_name = f"UI approval acceptance {stamp}"
    dsl_text = json.dumps(
        {
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"title": "Start"}},
                    {
                        "id": "answer",
                        "type": "answer",
                        "data": {"title": "Answer", "answer": "UI acceptance {{message}}"},
                    },
                ],
                "edges": [{"id": "edge-start-answer", "source": "start", "target": "answer"}],
            },
        },
        indent=2,
    )
    approval_dsl_text = json.dumps(
        {
            "version": "0.3.0",
            "workflow": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"title": "Start"}},
                    {
                        "id": "approval",
                        "type": "human_approval",
                        "data": {
                            "title": "UI approval",
                            "instructions": "Approve UI acceptance {{message}}",
                            "assignee": "qa-reviewer",
                            "output_key": "approval",
                        },
                    },
                    {
                        "id": "answer",
                        "type": "answer",
                        "data": {
                            "title": "Answer",
                            "answer": "Approved {{approval.comment}}",
                        },
                    },
                ],
                "edges": [
                    {"id": "edge-start-approval", "source": "start", "target": "approval"},
                    {"id": "edge-approval-answer", "source": "approval", "target": "answer"},
                ],
            },
        },
        indent=2,
    )

    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-ui-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + "/")
        evaluate(
            client,
            f"""
(() => {{
  localStorage.setItem('access_token', {json.dumps(token_pair['access_token'])});
  localStorage.setItem('refresh_token', {json.dumps(token_pair['refresh_token'])});
  sessionStorage.setItem('redirect_after_login', '/workflows');
  return true;
}})()
""",
        )
        navigate(client, base_url + "/workflows")
        wait_for_text(client, "Workflow", timeout=60)
        wait_for_text(client, "Import Workflow DSL", timeout=60)
        initial_snapshot = visible_snapshot(client)
        screenshot(client, out_dir / f"workflow-ui-initial-{stamp}.png")

        fill_import_form(client, workflow_name, dsl_text)
        click_testid(client, "workflow-import-submit", timeout=20)
        wait_for_text(client, workflow_name, timeout=80)
        wait_until(lambda: (page_fetch_evidence(client, workflow_name) or {}).get("found"), timeout=80, interval=1)

        wait_for_text(client, "Graph Editor", timeout=60)
        wait_for_text(client, "Debug version", timeout=60)
        after_import_snapshot = visible_snapshot(client)
        screenshot(client, out_dir / f"workflow-ui-after-import-{stamp}.png")
        after_import_evidence = page_fetch_evidence(client, workflow_name)
        workflow_id = after_import_evidence["workflow"]["workflow_id"]
        editor_route_path = f"/workflows/{quote(workflow_id, safe='')}/editor"
        navigate(client, base_url + editor_route_path)
        editor_route_evidence = wait_until(
            lambda: (
                state
                if (state := workflow_route_panel_state(client, workflow_name)).get("path") == editor_route_path
                and state.get("hasWorkflowName")
                and state.get("hasGraphEditor")
                and state.get("hasDebugVersion")
                and state.get("hasCanvas")
                and state.get("hasReactFlow")
                and state.get("hasNodePalette")
                else None
            ),
            timeout=60,
            interval=0.5,
        )
        screenshot(client, out_dir / f"workflow-ui-editor-route-{stamp}.png")

        human_approval_editor_evidence = add_human_approval_node(client)
        click_testid(client, "workflow-save-graph", timeout=30)
        saved_evidence = wait_until(
            lambda: (
                evidence
                if (evidence := page_fetch_evidence(client, workflow_name)).get("versionCount", 0)
                > after_import_evidence.get("versionCount", 0)
                and evidence.get("latestVersionId")
                and evidence.get("latestVersionId") != after_import_evidence.get("latestVersionId")
                and "human_approval" in evidence.get("latestVersionNodeTypes", [])
                and (evidence.get("humanApprovalNodeData") or {}).get("instructions") == "Approve UI acceptance {{message}}"
                and (evidence.get("humanApprovalNodeData") or {}).get("assignee") == "qa-reviewer"
                and (evidence.get("humanApprovalNodeData") or {}).get("output_key") == "qa_approval"
                else None
            ),
            timeout=80,
            interval=1,
        )
        saved_version_id = saved_evidence["latestVersionId"]

        click_testid(client, "workflow-publish-latest", timeout=30)
        wait_until(
            lambda: (
                evidence
                if (evidence := page_fetch_evidence(client, workflow_name)).get("workflow", {}).get("status")
                == "published"
                and evidence.get("publishedVersionId") == saved_version_id
                else None
            ),
            timeout=60,
            interval=1,
        )
        choose_run_mode(client, "sync")
        click_testid(client, "workflow-run-version", timeout=30)
        final_evidence = wait_until(
            lambda: (
                evidence
                if (evidence := page_fetch_evidence(client, workflow_name)).get("latestRun", {}).get("status")
                in {"succeeded", "failed", "cancelled", "paused"}
                and evidence.get("latestRun", {}).get("version_id") == saved_version_id
                and evidence.get("eventCount", 0) > 0
                and "answer" in evidence.get("eventNodeIds", [])
                else None
            ),
            timeout=90,
            interval=1,
        )
        canvas_run_status_evidence = wait_until(
            lambda: (
                state
                if (state := canvas_run_status_state(client)).get("startStatus") in {"succeeded", "failed", "paused", "running"}
                and state.get("answerStatus") in {"succeeded", "failed", "paused", "running"}
                else None
            ),
            timeout=30,
            interval=0.5,
        )
        latest_run_id = final_evidence["latestRun"]["run_id"]
        run_route_path = f"/workflows/{quote(workflow_id, safe='')}/runs/{quote(latest_run_id, safe='')}"
        navigate(client, base_url + run_route_path)
        run_route_evidence = wait_until(
            lambda: (
                state
                if (state := workflow_route_panel_state(client, workflow_name)).get("path") == run_route_path
                and state.get("hasWorkflowName")
                and state.get("hasGraphEditor")
                and state.get("hasRunEvents")
                and state.get("hasCanvas")
                and state.get("hasReactFlow")
                else None
            ),
            timeout=60,
            interval=0.5,
        )
        screenshot(client, out_dir / f"workflow-ui-run-route-{stamp}.png")
        node_focus_evidence = click_run_event_node_filter(client, "answer", 2, timeout=30)
        node_rename_evidence = rename_selected_workflow_node(client, "answer_renamed")
        after_run_snapshot = visible_snapshot(client)
        screenshot(client, out_dir / f"workflow-ui-after-run-{stamp}.png")

        navigate(client, base_url + "/workflows")
        wait_for_text(client, "Import Workflow DSL", timeout=60)
        fill_import_form(client, approval_workflow_name, approval_dsl_text)
        click_testid(client, "workflow-import-submit", timeout=20)
        wait_for_text(client, approval_workflow_name, timeout=80)
        wait_until(lambda: (page_fetch_evidence(client, approval_workflow_name) or {}).get("found"), timeout=80, interval=1)
        wait_for_text(client, "Graph Editor", timeout=60)
        approval_after_import_snapshot = visible_snapshot(client)
        approval_after_import_evidence = page_fetch_evidence(client, approval_workflow_name)
        screenshot(client, out_dir / f"workflow-ui-approval-after-import-{stamp}.png")

        click_testid(client, "workflow-publish-latest", timeout=30)
        approval_published_evidence = wait_until(
            lambda: (
                evidence
                if (evidence := page_fetch_evidence(client, approval_workflow_name)).get("workflow", {}).get("status")
                == "published"
                and evidence.get("publishedVersionId") == evidence.get("latestVersionId")
                and "human_approval" in evidence.get("latestVersionNodeTypes", [])
                else None
            ),
            timeout=60,
            interval=1,
        )
        human_approval_run_evidence = run_human_approval_flow(client, approval_workflow_name)
        approval_after_resume_snapshot = visible_snapshot(client)
        screenshot(client, out_dir / f"workflow-ui-approval-after-resume-{stamp}.png")

        client.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
        )
        time.sleep(1)
        mobile_snapshot = visible_snapshot(client)
        screenshot(client, out_dir / f"workflow-ui-mobile-{stamp}.png")

        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "workflow_name": workflow_name,
            "screenshots": {
                "initial": str(out_dir / f"workflow-ui-initial-{stamp}.png"),
                "after_import": str(out_dir / f"workflow-ui-after-import-{stamp}.png"),
                "editor_route": str(out_dir / f"workflow-ui-editor-route-{stamp}.png"),
                "run_route": str(out_dir / f"workflow-ui-run-route-{stamp}.png"),
                "after_run": str(out_dir / f"workflow-ui-after-run-{stamp}.png"),
                "approval_after_import": str(out_dir / f"workflow-ui-approval-after-import-{stamp}.png"),
                "approval_after_resume": str(out_dir / f"workflow-ui-approval-after-resume-{stamp}.png"),
                "mobile": str(out_dir / f"workflow-ui-mobile-{stamp}.png"),
            },
            "approval_workflow_name": approval_workflow_name,
            "initial_snapshot": initial_snapshot,
            "after_import_snapshot": after_import_snapshot,
            "after_import_evidence": after_import_evidence,
            "editor_route_evidence": editor_route_evidence,
            "human_approval_editor_evidence": human_approval_editor_evidence,
            "saved_evidence": saved_evidence,
            "saved_version_id": saved_version_id,
            "run_route_evidence": run_route_evidence,
            "after_run_snapshot": after_run_snapshot,
            "approval_after_import_snapshot": approval_after_import_snapshot,
            "approval_after_import_evidence": approval_after_import_evidence,
            "approval_published_evidence": approval_published_evidence,
            "human_approval_run_evidence": human_approval_run_evidence,
            "approval_after_resume_snapshot": approval_after_resume_snapshot,
            "mobile_snapshot": mobile_snapshot,
            "final_evidence": final_evidence,
            "canvas_run_status_evidence": canvas_run_status_evidence,
            "node_focus_evidence": node_focus_evidence,
            "node_rename_evidence": node_rename_evidence,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-ui-acceptance-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "workflow_name": workflow_name,
                    "approval_workflow_name": approval_workflow_name,
                    "saved_version_id": saved_version_id,
                    "editor_route_path": editor_route_evidence["path"],
                    "run_route_path": run_route_evidence["path"],
                    "final_evidence": final_evidence,
                    "human_approval_run_status": human_approval_run_evidence["resumed_evidence"]["latestRun"]["status"],
                    "console_issue_count": len(console_issues),
                },
                indent=2,
            )
        )
        return 0
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
            import shutil

            shutil.rmtree(temp_profile)
        if args.delete_token_file:
            with contextlib.suppress(FileNotFoundError):
                token_file.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
