"""Local CDP smoke for disabled Workflow frontend contributions."""

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
DISABLED_CONTRIBUTIONS_SMOKE_PATH = "/codex/disabled-workflow-contributions-smoke"


def disabled_contribution_evidence(client: CdpClient) -> dict[str, Any]:
    return evaluate(
        client,
        """
(() => {
  if (typeof window.__codexDisabledWorkflowContributionEvidence !== 'function') {
    throw new Error('disabled workflow contribution evidence hook is unavailable');
  }
  const evidence = window.__codexDisabledWorkflowContributionEvidence();
  const enabled = evidence.enabled || {};
  const disabled = evidence.disabled || {};
  return {
    enabled,
    disabled,
    enabledHasWorkflowRoutes: (enabled.routes || []).includes('/workflows')
      && (enabled.routes || []).includes('/workflows/:workflowId/editor')
      && (enabled.routes || []).includes('/workflows/:workflowId/runs/:runId'),
    enabledHasWorkflowNav: (enabled.nav || []).includes('/workflows'),
    enabledHasWorkflowChatPicker: (enabled.chatOptions || []).some((item) => item.includes('workflow:select-workflow'))
      && (enabled.chatPanels || []).some((item) => item.includes('workflow.WorkflowPickerModal')),
    disabledHasNoWorkflowRoutes: !(disabled.routes || []).some((item) => item.includes('/workflows')),
    disabledHasNoWorkflowPanels: !(disabled.panels || []).some((item) => item.includes('workflow')),
    disabledHasNoWorkflowNav: !(disabled.nav || []).some((item) => item.includes('/workflows')),
    disabledHasNoWorkflowChatPicker: (disabled.chatOptions || []).length === 0 && (disabled.chatPanels || []).length === 0,
    disabledKeepsAgentTeamRoute: (disabled.routes || []).includes('/agent-team'),
    disabledKeepsAgentTeamNav: (disabled.nav || []).includes('/agent-team'),
    bodyText: document.body.textContent || '',
  };
})()
""",
        timeout=10,
    )


def assert_disabled_contribution_evidence(evidence: dict[str, Any]) -> None:
    required_flags = [
        "enabledHasWorkflowRoutes",
        "enabledHasWorkflowNav",
        "enabledHasWorkflowChatPicker",
        "disabledHasNoWorkflowRoutes",
        "disabledHasNoWorkflowPanels",
        "disabledHasNoWorkflowNav",
        "disabledHasNoWorkflowChatPicker",
        "disabledKeepsAgentTeamRoute",
        "disabledKeepsAgentTeamNav",
    ]
    missing = [flag for flag in required_flags if evidence.get(flag) is not True]
    if missing:
        raise AssertionError(f"disabled workflow contribution evidence failed: {missing}")


def run_disabled_contributions(base_url: str, chrome_path: Path, out_dir: Path) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    port = free_port()
    temp_profile = Path(tempfile.mkdtemp(prefix="lambchat-disabled-workflow-cdp-"))
    proc: subprocess.Popen[bytes] | None = None
    client: CdpClient | None = None

    try:
        proc = launch_chrome(chrome_path, port, temp_profile)
        client = connect_tab(port, base_url)
        navigate(client, base_url + DISABLED_CONTRIBUTIONS_SMOKE_PATH)
        wait_for_text(client, "workflow disabled contribution smoke", timeout=60)
        evidence = wait_until(
            lambda: item
            if (item := disabled_contribution_evidence(client)).get("disabledHasNoWorkflowRoutes")
            and item.get("disabledKeepsAgentTeamRoute")
            else None,
            timeout=45,
            interval=0.5,
        )
        assert_disabled_contribution_evidence(evidence)

        screenshot_path = out_dir / f"workflow-disabled-contributions-{stamp}.png"
        screenshot(client, screenshot_path)
        console_issues = render_console_issues(client.events)
        result = {
            "base_url": base_url,
            "path": DISABLED_CONTRIBUTIONS_SMOKE_PATH,
            "screenshot": str(screenshot_path),
            "evidence": evidence,
            "console_issues": console_issues,
        }
        result_path = out_dir / f"workflow-disabled-contributions-{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "result_path": str(result_path),
                    "screenshot": str(screenshot_path),
                    "enabled_has_workflow_routes": evidence["enabledHasWorkflowRoutes"],
                    "disabled_has_no_workflow_routes": evidence["disabledHasNoWorkflowRoutes"],
                    "disabled_has_no_workflow_chat_picker": evidence["disabledHasNoWorkflowChatPicker"],
                    "disabled_keeps_agent_team_route": evidence["disabledKeepsAgentTeamRoute"],
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

    response = requests.get(base_url + DISABLED_CONTRIBUTIONS_SMOKE_PATH, timeout=2)
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
        run_disabled_contributions(base_url, chrome_path, out_dir)
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
