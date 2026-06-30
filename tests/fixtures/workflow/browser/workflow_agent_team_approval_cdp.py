"""Local CDP smoke for approving a paused workflow inside Agent Team replay."""

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
from workflow_tool_approval_result_cdp import (
    DEFAULT_BASE_URL,
    DEFAULT_NODE,
    approval_card_evidence,
    click_workflow_result_pill,
    request_log_evidence,
)
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

OUT_DIR = Path(__file__).resolve().parent
AGENT_TEAM_APPROVAL_SMOKE_PATH = "/codex/agent-team-replay-workflow-approval-smoke"


def click_agent_team_member_card(client: CdpClient) -> None:
    wait_until(
        lambda: evaluate(
            client,
            """
(() => {
  const card = Array.from(document.querySelectorAll('div')).find((item) => {
    const text = item.textContent || '';
    const isMember = text.includes('Workflow Researcher') || text.includes('Workflow researcher');
    return isMember && String(item.className || '').includes('cursor-pointer');
  });
  return Boolean(card);
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
  const card = Array.from(document.querySelectorAll('div')).find((item) => {
    const text = item.textContent || '';
    const isMember = text.includes('Workflow Researcher') || text.includes('Workflow researcher');
    return isMember && String(item.className || '').includes('cursor-pointer');
  });
  if (!card) throw new Error('agent team member card not found');
  card.click();
  return true;
})()
""",
    )


def click_agent_team_processing_section(client: CdpClient) -> None:
    wait_until(
        lambda: evaluate(
            client,
            """
(() => Boolean(document.querySelector('button[aria-expanded="false"]')))()
""",
        ),
        timeout=30,
        interval=0.5,
    )
    evaluate(
        client,
        """
(() => {
  const button = document.querySelector('button[aria-expanded="false"]');
  if (!button) throw new Error('agent team processing section toggle not found');
  button.click();
  return true;
})()
""",
    )


def agent_team_replay_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  const messages = window.__agentTeamReplayWorkflowApprovalMessages || [];
  const assistant = messages.find((message) => message.role === 'assistant') || {};
  const parts = assistant.parts || [];
  const subagent = parts.find((part) => part.type === 'subagent') || {};
  const nestedParts = subagent.parts || [];
  return {
    messageCount: messages.length,
    assistantPartTypes: parts.map((part) => part.type),
    subagentName: subagent.agent_name || null,
    nestedPartTypes: nestedParts.map((part) => part.type),
    hasSubagentWorkflowPart: nestedParts.some((part) =>
      part.type === 'workflow' &&
      part.plugin_id === 'workflow' &&
      part.status === 'paused' &&
      part.next_action?.resume?.tool === 'workflow_resume'
    ),
  };
})()
""",
        timeout=10,
    )


def run_agent_team_approval(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-agent-team-approval-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + AGENT_TEAM_APPROVAL_SMOKE_PATH)
        wait_for_text(client, "agent team replay workflow approval smoke", timeout=60)
        replay_evidence = wait_until(
            lambda: evidence
            if (evidence := agent_team_replay_evidence(client)).get("hasSubagentWorkflowPart")
            else None,
            timeout=45,
            interval=0.5,
        )
        click_agent_team_member_card(client)
        click_agent_team_processing_section(client)
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

        screenshot_path = out_dir / f"workflow-agent-team-approval-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": AGENT_TEAM_APPROVAL_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "replay_evidence": replay_evidence,
            "before_evidence": before_evidence,
            "after_evidence": after_evidence,
            "resume_log": resume_log,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-agent-team-approval-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "approval_run_state": resume_log["approval_run_state"],
                    "resume_body": resume_log["last_workflow_resume_body"],
                    "has_subagent_workflow_part": replay_evidence["hasSubagentWorkflowPart"],
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

    response = requests.get(base_url + AGENT_TEAM_APPROVAL_SMOKE_PATH, timeout=2)
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
        run_agent_team_approval(base_url, chrome_path, out_dir)
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
