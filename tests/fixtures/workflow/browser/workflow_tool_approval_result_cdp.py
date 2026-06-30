"""Local CDP smoke for approving a paused workflow from a tool result card."""

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
from workflow_ui_acceptance_cdp import (
    DEFAULT_CHROME,
    CdpClient,
    click_button,
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
TOOL_APPROVAL_SMOKE_PATH = "/codex/tool-workflow-approval-result-smoke"
DEFAULT_BASE_URL = "http://127.0.0.1:3232"
DEFAULT_NODE = (
    r"C:\Users\admin\AppData\Local\OpenAI\Codex\runtimes\cua_node\1b23c930bdf84ed6\bin\node.exe"
)


def approval_card_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const bodyText = document.body.textContent || '';
  return {
    hasApproval: bodyText.includes('Awaiting approval') && bodyText.includes('Browser approval'),
    hasResumeTool: bodyText.includes('workflow_resume'),
    hasApproveButton: Array.from(document.querySelectorAll('button')).some((button) => button.textContent?.includes('Approve')),
    hasSucceeded: bodyText.includes('succeeded'),
    hasApprovedOutput: bodyText.includes('Approved via browser smoke'),
    bodyText,
  };
})()
""",
        timeout=10,
    )


def click_workflow_result_pill(client: CdpClient) -> None:
    wait_until(
        lambda: evaluate(
            client,
            """
(() => {
  const button = Array.from(document.querySelectorAll('button')).find((item) => {
    const text = item.textContent || '';
    return text.includes('Workflow run') && text.includes('wf-browser');
  });
  return Boolean(button && !button.disabled);
})()
""",
        ),
        timeout=30,
        interval=0.5,
    )
    evaluate(
        client,
        """
(() => {
  const button = Array.from(document.querySelectorAll('button')).find((item) => {
    const text = item.textContent || '';
    return text.includes('Workflow run') && text.includes('wf-browser');
  });
  if (!button) throw new Error('workflow result pill not found');
  if (button.disabled) throw new Error('workflow result pill disabled');
  button.click();
  return true;
})()
""",
    )


def request_log_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(async () => {
  const response = await fetch('/api/codex/request-log');
  const data = await response.json();
  return {
    approval_run_state: data.approval_run_state,
    last_workflow_resume_body: data.last_workflow_resume_body,
  };
})()
""",
        timeout=15,
        await_promise=True,
    )


def run_tool_approval_result(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-tool-approval-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + TOOL_APPROVAL_SMOKE_PATH)
        wait_for_text(client, "tool workflow approval result smoke", timeout=60)
        click_workflow_result_pill(client)
        before_evidence = wait_until(
            lambda: evidence
            if (evidence := approval_card_evidence(client)).get("hasApproval")
            and evidence.get("hasResumeTool")
            and evidence.get("hasApproveButton")
            else None,
            timeout=45,
            interval=0.5,
        )
        click_button(client, "Approve", timeout=30)
        resume_log = wait_until(
            lambda: evidence
            if (evidence := request_log_evidence(client)).get("approval_run_state") == "resumed"
            and (evidence.get("last_workflow_resume_body") or {}).get("approved") is True
            else None,
            timeout=45,
            interval=0.5,
        )
        after_evidence = wait_until(
            lambda: evidence
            if (evidence := approval_card_evidence(client)).get("hasSucceeded")
            and evidence.get("hasApprovedOutput")
            else None,
            timeout=45,
            interval=0.5,
        )

        screenshot_path = out_dir / f"workflow-tool-approval-result-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": TOOL_APPROVAL_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "before_evidence": before_evidence,
            "after_evidence": after_evidence,
            "resume_log": resume_log,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-tool-approval-result-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "approval_run_state": resume_log["approval_run_state"],
                    "resume_body": resume_log["last_workflow_resume_body"],
                    "has_approved_output": after_evidence["hasApprovedOutput"],
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

    response = requests.get(base_url + TOOL_APPROVAL_SMOKE_PATH, timeout=2)
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
        run_tool_approval_result(base_url, chrome_path, out_dir)
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
