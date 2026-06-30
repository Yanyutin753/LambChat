"""Repeatable local CDP smoke for workflow editor drag/connect/save.

This goal-ledger harness turns the manual Task 444 browser smoke into a
scriptable acceptance check. It can either target an already-running local
Vite mock URL or start the goal-local mock server itself.
"""

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

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(__file__).resolve().parent
WORKFLOW_EDITOR_SMOKE_PATH = "/codex/workflow-editor-interaction-smoke"
DEFAULT_BASE_URL = "http://127.0.0.1:3232"
DEFAULT_NODE = (
    r"C:\Users\admin\AppData\Local\OpenAI\Codex\runtimes\cua_node\1b23c930bdf84ed6\bin\node.exe"
)


def start_vite_mock_server(node_path: Path, port: int) -> subprocess.Popen[bytes]:
    vite_script = f"""
import {{ createServer }} from './frontend/node_modules/vite/dist/node/index.js';
import {{ createWorkflowMockApiPlugin }} from './goal-1/browser_workflow_mock.mjs';

const server = await createServer({{
  root: 'frontend',
  configFile: {json.dumps(str(REPO_ROOT / "frontend" / "vite.config.ts"))},
  plugins: [createWorkflowMockApiPlugin()],
  server: {{ host: '127.0.0.1', port: {port}, strictPort: true }},
}});

await server.listen();
server.printUrls();
process.on('SIGTERM', async () => {{
  await server.close();
  process.exit(0);
}});
await new Promise(() => {{}});
"""
    return subprocess.Popen(
        [str(node_path), "--input-type=module", "-e", vite_script],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def editor_dom_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  if (typeof window.__codexWorkflowEditorEvidence !== 'function') {
    throw new Error('workflow editor evidence hook is unavailable');
  }
  return window.__codexWorkflowEditorEvidence();
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
  const body = data.last_workflow_version_body || {};
  const workflow = body.source_payload?.workflow || {};
  const nodes = Array.isArray(workflow.nodes) ? workflow.nodes : [];
  const edges = Array.isArray(workflow.edges) ? workflow.edges : [];
  const nodeIds = nodes.map((node) => node.id).filter(Boolean);
  const edgePairs = edges.map((edge) => `${edge.source}->${edge.target}`);
  return {
    saved_workflow_version_id: data.saved_workflow_version_id,
    last_workflow_version_body: body,
    nodes: nodeIds.join(','),
    edges: edgePairs.join(','),
    has_node_5: nodeIds.includes('node_5'),
    has_start_node_5: edgePairs.includes('start->node_5'),
  };
})()
""",
        timeout=15,
        await_promise=True,
    )


def workflow_interface_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const textFor = (testId) => document.querySelector(`[data-testid="${testId}"]`)?.textContent || '';
  const contractText = textFor('workflow-interface-contract');
  const entryText = textFor('workflow-interface-entry');
  const exitText = textFor('workflow-interface-exit');
  const schemaText = textFor('workflow-interface-schema');
  return {
    hasContract: contractText.includes('Workflow interface') && contractText.includes('workflow'),
    hasEntry: entryText.includes('Entry') && entryText.includes('workflow_run.input') && entryText.includes('workflow_get_schema.input_schema'),
    hasExit: exitText.includes('Exit') && exitText.includes('output') && exitText.includes('workflow_get_schema.output_schema'),
    hasSchema: schemaText.includes('Schema') && schemaText.includes('workflow_get_schema'),
    contractText,
    entryText,
    exitText,
    schemaText,
  };
})()
""",
        timeout=10,
    )


def click_editor_testid(client: CdpClient, testid: str, timeout: float = 20) -> None:
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


def run_editor_interaction(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-editor-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + WORKFLOW_EDITOR_SMOKE_PATH)
        wait_for_text(client, "Graph Editor", timeout=60)
        wait_for_text(client, "Debug version", timeout=60)

        interface_evidence = wait_until(
            lambda: evidence
            if (evidence := workflow_interface_evidence(client)).get("hasContract")
            and evidence.get("hasEntry")
            and evidence.get("hasExit")
            and evidence.get("hasSchema")
            else None,
            timeout=30,
            interval=0.5,
        )
        before_evidence = editor_dom_evidence(client)
        click_editor_testid(client, "codex-drop-answer-on-workflow-canvas", timeout=30)
        after_drop_evidence = wait_until(
            lambda: evidence if (evidence := editor_dom_evidence(client)).get("hasDroppedNode") else None,
            timeout=30,
            interval=0.5,
        )
        click_editor_testid(client, "codex-connect-start-to-dropped-node", timeout=30)
        after_connect_evidence = wait_until(
            lambda: evidence
            if (evidence := editor_dom_evidence(client)).get("hasStartToDroppedNodeEdge")
            else None,
            timeout=30,
            interval=0.5,
        )
        click_editor_testid(client, "workflow-save-graph", timeout=30)
        saved_log_evidence = wait_until(
            lambda: evidence
            if (evidence := request_log_evidence(client)).get("has_node_5")
            and evidence.get("has_start_node_5")
            else None,
            timeout=45,
            interval=0.5,
        )
        after_save_evidence = wait_until(
            lambda: evidence
            if (evidence := editor_dom_evidence(client)).get("hasDroppedNode")
            and evidence.get("hasStartToDroppedNodeEdge")
            else None,
            timeout=30,
            interval=0.5,
        )

        screenshot_path = out_dir / f"workflow-editor-interaction-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": WORKFLOW_EDITOR_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "before_evidence": before_evidence,
            "after_drop_evidence": after_drop_evidence,
            "after_connect_evidence": after_connect_evidence,
            "after_save_evidence": after_save_evidence,
            "interface_evidence": interface_evidence,
            "saved_log_evidence": saved_log_evidence,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-editor-interaction-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "nodes": saved_log_evidence["nodes"],
                    "edges": saved_log_evidence["edges"],
                    "interface": {
                        "entry": interface_evidence["entryText"],
                        "exit": interface_evidence["exitText"],
                        "schema": interface_evidence["schemaText"],
                    },
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
            wait_until(
                lambda: evaluate_health(base_url),
                timeout=60,
                interval=0.5,
            )
        run_editor_interaction(base_url, chrome_path, out_dir)
        return 0
    finally:
        if vite_proc:
            vite_proc.terminate()
            with contextlib.suppress(Exception):
                vite_proc.wait(timeout=10)
            if vite_proc.poll() is None:
                with contextlib.suppress(Exception):
                    vite_proc.kill()


def evaluate_health(base_url: str) -> bool:
    import requests

    response = requests.get(base_url + WORKFLOW_EDITOR_SMOKE_PATH, timeout=2)
    return response.ok


if __name__ == "__main__":
    raise SystemExit(main())
