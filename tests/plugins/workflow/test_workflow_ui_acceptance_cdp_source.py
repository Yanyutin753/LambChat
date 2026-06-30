from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BROWSER_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser"
CDP_SCRIPT = BROWSER_FIXTURES / "workflow_ui_acceptance_cdp.py"
INTERACTION_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_editor_interaction_cdp.py"
TOOL_APPROVAL_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_tool_approval_result_cdp.py"
CHAT_REPLAY_APPROVAL_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_chat_replay_approval_cdp.py"
AGENT_TEAM_APPROVAL_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_agent_team_approval_cdp.py"
SCHEDULED_APPROVAL_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_scheduled_approval_cdp.py"
DISABLED_CONTRIBUTIONS_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_disabled_contributions_cdp.py"
CHAT_SELECTED_ENTRY_CDP_SCRIPT = BROWSER_FIXTURES / "workflow_chat_selected_entry_cdp.py"
AGENT_TEAM_SELECTED_ENTRY_CDP_SCRIPT = (
    BROWSER_FIXTURES / "workflow_agent_team_selected_entry_cdp.py"
)
MOCK_SCRIPT = BROWSER_FIXTURES / "browser_workflow_mock.mjs"


def test_cdp_ui_acceptance_saves_graph_before_publish_and_run() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert 'click_testid(client, "workflow-save-graph", timeout=30)' in source
    assert 'saved_version_id = saved_evidence["latestVersionId"]' in source
    assert 'click_testid(client, "workflow-publish-latest", timeout=30)' in source
    assert 'click_testid(client, "workflow-run-version", timeout=30)' in source

    save_index = source.index('click_testid(client, "workflow-save-graph", timeout=30)')
    publish_index = source.index('click_testid(client, "workflow-publish-latest", timeout=30)')
    run_index = source.index(
        'click_testid(client, "workflow-run-version", timeout=30)', publish_index
    )
    assert save_index < publish_index < run_index


def test_cdp_ui_acceptance_requires_saved_version_for_publish_and_run() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "versionCount: versionsList.length" in source
    assert "versionIds: versionsList.map((version) => version.version_id).filter(Boolean)" in source
    assert "latestVersionId:" in source
    assert "latestVersionNodeTypes:" in source
    assert "latestVersionNodeIds:" in source
    assert "humanApprovalNodeData:" in source
    assert "publishedVersionId:" in source
    assert '> after_import_evidence.get("versionCount", 0)' in source
    assert (
        'evidence.get("latestVersionId") != after_import_evidence.get("latestVersionId")' in source
    )
    assert 'and "human_approval" in evidence.get("latestVersionNodeTypes", [])' in source
    assert (
        '(evidence.get("humanApprovalNodeData") or {}).get("instructions") == "Approve UI acceptance {{message}}"'
        in source
    )
    assert (
        '(evidence.get("humanApprovalNodeData") or {}).get("assignee") == "qa-reviewer"' in source
    )
    assert (
        '(evidence.get("humanApprovalNodeData") or {}).get("output_key") == "qa_approval"' in source
    )
    assert 'and evidence.get("publishedVersionId") == saved_version_id' in source
    assert 'and evidence.get("latestRun", {}).get("version_id") == saved_version_id' in source
    assert 'and "answer" in evidence.get("eventNodeIds", [])' in source
    assert '"canvas_run_status_evidence": canvas_run_status_evidence' in source
    assert '"saved_version_id": saved_version_id' in source


def test_cdp_ui_acceptance_records_node_event_evidence() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "const eventList = events?.data?.events || [];" in source
    assert "const eventNodeCounts = eventList.reduce((counts, event) =>" in source
    assert "counts[event.node_id] = (counts[event.node_id] || 0) + 1;" in source
    assert "eventCount: eventList.length" in source
    assert "eventTypes: eventList.map((event) => event.event_type)" in source
    assert (
        "eventNodeIds: Array.from(new Set(eventList.map((event) => event.node_id).filter(Boolean)))"
        in source
    )
    assert "eventNodeCounts," in source


def test_cdp_ui_acceptance_creates_and_configures_human_approval_node_before_save() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "def click_testid" in source
    assert "def set_form_field_by_title" in source
    assert "def add_human_approval_node" in source
    assert "def human_approval_editor_state" in source
    assert 'click_testid(client, "workflow-node-add-human_approval", timeout=30)' in source
    assert (
        'set_form_field_by_title(client, "Approval instructions", "Approve UI acceptance {{message}}")'
        in source
    )
    assert 'set_form_field_by_title(client, "Approval assignee", "qa-reviewer")' in source
    assert 'set_form_field_by_title(client, "Approval output key", "qa_approval")' in source
    assert "selectedNodeType: nodeTypeSelect?.value || null" in source
    assert '"human_approval_editor_evidence": human_approval_editor_evidence' in source

    add_index = source.index("human_approval_editor_evidence = add_human_approval_node(client)")
    save_index = source.index('click_testid(client, "workflow-save-graph", timeout=30)')
    publish_index = source.index('click_testid(client, "workflow-publish-latest", timeout=30)')
    assert add_index < save_index < publish_index


def test_cdp_ui_acceptance_verifies_node_event_focus_and_rename_reset() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "def run_events_panel_state" in source
    assert "def click_run_event_node_filter" in source
    assert "def rename_selected_workflow_node" in source
    assert "document.querySelector('[data-testid=\"workflow-selected-node-id\"]')" in source
    assert "hasFocusedAnswerCount: /Run Events\\\\s+2\\\\/\\\\d+/.test(text)" in source
    assert "hasAllEventsCount: /Run Events\\\\s+\\\\d+\\\\s+All events/.test(text)" in source
    assert 'click_run_event_node_filter(client, "answer", 2, timeout=30)' in source
    assert 'rename_selected_workflow_node(client, "answer_renamed")' in source
    assert '"node_focus_evidence": node_focus_evidence' in source
    assert '"node_rename_evidence": node_rename_evidence' in source

    run_index = source.index('click_testid(client, "workflow-run-version", timeout=30)')
    focus_index = source.index('click_run_event_node_filter(client, "answer", 2, timeout=30)')
    rename_index = source.index('rename_selected_workflow_node(client, "answer_renamed")')
    mobile_index = source.index('"workflow-ui-mobile-{stamp}.png"')
    assert run_index < focus_index < rename_index < mobile_index


def test_cdp_ui_acceptance_runs_human_approval_pause_and_resume_flow() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert 'approval_workflow_name = f"UI approval acceptance {stamp}"' in source
    assert "approval_dsl_text = json.dumps" in source
    assert '"type": "human_approval"' in source
    assert '"title": "UI approval"' in source
    assert '"instructions": "Approve UI acceptance {{message}}"' in source
    assert '"assignee": "qa-reviewer"' in source
    assert '"answer": "Approved {{approval.comment}}"' in source
    assert "def set_form_field_by_placeholder" in source
    assert "def human_approval_panel_state" in source
    assert "def run_human_approval_flow" in source
    assert 'choose_run_mode(client, "async")' in source
    assert 'click_testid(client, "workflow-run-version", timeout=30)' in source
    assert (
        'set_form_field_by_placeholder(client, "Approval comment", "CDP approval comment")'
        in source
    )
    assert 'click_testid(client, "workflow-approval-approve", timeout=30)' in source
    assert ').get("latestRun", {}).get("status") == "paused"' in source
    assert 'evidence.get("pendingApprovalCount", 0) > 0' in source
    assert '"human_approval_required" in evidence.get("eventTypes", [])' in source
    assert ').get("latestRun", {}).get("status") == "succeeded"' in source
    assert '"human_approval_resumed" in evidence.get("eventTypes", [])' in source
    assert 'get("answer") == "Approved CDP approval comment"' in source
    assert (
        "human_approval_run_evidence = run_human_approval_flow(client, approval_workflow_name)"
        in source
    )
    assert (
        '"approval_after_import": str(out_dir / f"workflow-ui-approval-after-import-{stamp}.png")'
        in source
    )
    assert (
        '"approval_after_resume": str(out_dir / f"workflow-ui-approval-after-resume-{stamp}.png")'
        in source
    )
    assert '"human_approval_run_evidence": human_approval_run_evidence' in source
    assert (
        '"human_approval_run_status": human_approval_run_evidence["resumed_evidence"]["latestRun"]["status"]'
        in source
    )

    baseline_run_index = source.index(
        'click_run_event_node_filter(client, "answer", 2, timeout=30)'
    )
    approval_import_index = source.index(
        "fill_import_form(client, approval_workflow_name, approval_dsl_text)"
    )
    approval_run_index = source.index(
        "human_approval_run_evidence = run_human_approval_flow(client, approval_workflow_name)"
    )
    mobile_index = source.index('"workflow-ui-mobile-{stamp}.png"')
    assert baseline_run_index < approval_import_index < approval_run_index < mobile_index


def test_cdp_ui_acceptance_uses_stable_run_controls_and_canvas_status_selectors() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "def set_select_by_testid" in source
    assert 'set_select_by_testid(client, "workflow-run-mode", mode)' in source
    assert "def canvas_run_status_state" in source
    assert "workflow-canvas-run-status-start" in source
    assert "workflow-canvas-run-status-answer" in source
    assert "workflow-canvas-node-start" in source
    assert "workflow-canvas-node-answer" in source
    assert "canvas_run_status_evidence = wait_until" in source
    assert (
        '(state := canvas_run_status_state(client)).get("startStatus") in {"succeeded", "failed", "paused", "running"}'
        in source
    )
    assert 'state.get("answerStatus") in {"succeeded", "failed", "paused", "running"}' in source

    choose_index = source.index('choose_run_mode(client, "sync")')
    run_index = source.index(
        'click_testid(client, "workflow-run-version", timeout=30)', choose_index
    )
    canvas_index = source.index("canvas_run_status_evidence = wait_until", run_index)
    focus_index = source.index('click_run_event_node_filter(client, "answer", 2, timeout=30)')
    assert choose_index < run_index < canvas_index < focus_index


def test_cdp_ui_acceptance_uses_stable_action_buttons_for_import_save_publish_and_approval() -> (
    None
):
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert 'click_testid(client, "workflow-import-submit", timeout=20)' in source
    assert 'click_testid(client, "workflow-save-graph", timeout=30)' in source
    assert 'click_testid(client, "workflow-publish-latest", timeout=30)' in source
    assert 'click_testid(client, "workflow-approval-approve", timeout=30)' in source
    assert 'click_button(client, "Import", timeout=20)' not in source
    assert 'click_button(client, "Save graph", timeout=30)' not in source
    assert 'click_button(client, "Publish latest", timeout=30)' not in source
    assert 'click_button(client, "Approve", timeout=30)' not in source

    import_index = source.index('click_testid(client, "workflow-import-submit", timeout=20)')
    save_index = source.index(
        'click_testid(client, "workflow-save-graph", timeout=30)', import_index
    )
    publish_index = source.index(
        'click_testid(client, "workflow-publish-latest", timeout=30)', save_index
    )
    run_index = source.index(
        'click_testid(client, "workflow-run-version", timeout=30)', publish_index
    )
    assert import_index < save_index < publish_index < run_index


def test_cdp_ui_acceptance_verifies_dedicated_editor_and_run_routes() -> None:
    source = CDP_SCRIPT.read_text(encoding="utf-8")

    assert "def workflow_route_panel_state" in source
    assert "hasGraphEditor: text.includes('Graph Editor')" in source
    assert "hasRunEvents: text.includes('Run Events')" in source
    assert (
        "hasCanvas: Boolean(document.querySelector('[data-testid=\"workflow-canvas\"]'))" in source
    )
    assert (
        "hasReactFlow: Boolean(document.querySelector('[data-testid=\"workflow-react-flow\"]'))"
        in source
    )
    assert (
        "hasNodePalette: Boolean(document.querySelector('[data-testid=\"workflow-node-palette\"]'))"
        in source
    )
    assert "editor_route_path = f\"/workflows/{quote(workflow_id, safe='')}/editor\"" in source
    assert "navigate(client, base_url + editor_route_path)" in source
    assert "editor_route_evidence = wait_until" in source
    assert (
        "run_route_path = f\"/workflows/{quote(workflow_id, safe='')}/runs/{quote(latest_run_id, safe='')}\""
        in source
    )
    assert "navigate(client, base_url + run_route_path)" in source
    assert "run_route_evidence = wait_until" in source
    assert '"editor_route": str(out_dir / f"workflow-ui-editor-route-{stamp}.png")' in source
    assert '"run_route": str(out_dir / f"workflow-ui-run-route-{stamp}.png")' in source
    assert '"editor_route_evidence": editor_route_evidence' in source
    assert '"run_route_evidence": run_route_evidence' in source
    assert '"editor_route_path": editor_route_evidence["path"]' in source
    assert '"run_route_path": run_route_evidence["path"]' in source

    import_evidence_index = source.index(
        "after_import_evidence = page_fetch_evidence(client, workflow_name)"
    )
    editor_nav_index = source.index("navigate(client, base_url + editor_route_path)")
    add_node_index = source.index(
        "human_approval_editor_evidence = add_human_approval_node(client)"
    )
    run_index = source.index('click_testid(client, "workflow-run-version", timeout=30)')
    run_nav_index = source.index("navigate(client, base_url + run_route_path)")
    focus_index = source.index('click_run_event_node_filter(client, "answer", 2, timeout=30)')
    assert import_evidence_index < editor_nav_index < add_node_index
    assert run_index < run_nav_index < focus_index


def test_browser_workflow_mock_uses_real_workflow_frontend_contribution_shape() -> None:
    source = MOCK_SCRIPT.read_text(encoding="utf-8")

    assert 'id: "workflow:workflows-tab"' in source
    assert 'panel: "workflow:workflows-panel"' in source
    assert 'insert_after: "agent-team"' in source
    assert 'id: "workflow:workflow-editor-tab"' in source
    assert 'path: "/workflows/:workflowId/editor"' in source
    assert 'panel: "workflow:workflow-editor-panel"' in source
    assert 'id: "workflow:workflow-run-tab"' in source
    assert 'path: "/workflows/:workflowId/runs/:runId"' in source
    assert 'panel: "workflow:workflow-run-panel"' in source
    assert (
        'id: "workflow:workflows-panel", tab: "workflows", renderer: "workflow.WorkflowPanel"'
        in source
    )
    assert (
        'id: "workflow:workflow-editor-panel", tab: "workflows-editor", renderer: "workflow.WorkflowPanel"'
        in source
    )
    assert (
        'id: "workflow:workflow-run-panel", tab: "workflows-run", renderer: "workflow.WorkflowPanel"'
        in source
    )
    assert 'id: "workflow:workflows-nav"' in source


def test_browser_workflow_mock_can_script_drop_connect_and_save_editor_graph() -> None:
    source = MOCK_SCRIPT.read_text(encoding="utf-8")

    assert "export function workflowCallableInterface" in source
    assert 'schema_tool: "workflow_get_schema"' in source
    assert 'schema_field: "input_schema"' in source
    assert 'schema_field: "output_schema"' in source
    assert 'interface: workflowCallableInterface("wf-browser", "wfv-browser-2")' in source
    assert "function ioContractForVersion" in source
    assert 'interface: workflowCallableInterface("wf-browser", activeVersion.version_id)' in source
    assert "jsonReply(res, ioContractForVersion(currentWorkflowVersion()))" in source
    assert 'window.__codexDropWorkflowNode = (nodeType = "answer", presetId) =>' in source
    assert (
        'window.__codexConnectWorkflowNodes = async (sourceNodeId = "start", targetNodeId = "node_5") =>'
        in source
    )
    assert "sourceCard.click();" in source
    assert "requestAnimationFrame(() => requestAnimationFrame(resolve))" in source
    assert (
        "document.querySelector('[data-testid=\"workflow-add-edge-target-' + sourceNodeId + '\"]')"
        in source
    )
    assert "setter.call(targetSelect, targetNodeId);" in source
    assert 'targetSelect.dispatchEvent(new Event("change", { bubbles: true }));' in source
    assert "window.__codexWorkflowEditorEvidence = () =>" in source
    assert 'nodeCards.includes("workflow-node-card-node_5")' in source
    assert (
        'edgeCards.some((edge) => edge.text.includes("start") && edge.text.includes("node_5"))'
        in source
    )
    assert "function savedInternalModelFromVersionBody(body)" in source
    assert "body?.source_payload?.workflow" in source
    assert 'format: "lambchat.workflow.v1"' in source
    assert "internal_model: savedInternalModelFromVersionBody(lastWorkflowVersionBody)" in source
    assert (
        "source_payload: lastWorkflowVersionBody?.source_payload ?? version.source_payload"
        in source
    )
    assert 'data-testid": "codex-connect-start-to-dropped-node"' in source
    assert 'window.__codexConnectWorkflowNodes("start", "node_5");' in source
    assert "last_workflow_version_body: lastWorkflowVersionBody" in source


def test_editor_interaction_cdp_replays_drop_connect_save_smoke() -> None:
    source = INTERACTION_CDP_SCRIPT.read_text(encoding="utf-8")

    assert 'WORKFLOW_EDITOR_SMOKE_PATH = "/codex/workflow-editor-interaction-smoke"' in source
    assert "def start_vite_mock_server" in source
    assert "createWorkflowMockApiPlugin" in source
    assert "await server.close();" in source
    assert "def editor_dom_evidence" in source
    assert "window.__codexWorkflowEditorEvidence()" in source
    assert "def request_log_evidence" in source
    assert "fetch('/api/codex/request-log')" in source
    assert "last_workflow_version_body" in source
    assert "has_node_5: nodeIds.includes('node_5')" in source
    assert "has_start_node_5: edgePairs.includes('start->node_5')" in source
    assert "def workflow_interface_evidence" in source
    assert "workflow-interface-contract" in source
    assert "workflow-interface-entry" in source
    assert "workflow-interface-exit" in source
    assert "workflow-interface-schema" in source
    assert "entryText.includes('workflow_run.input')" in source
    assert "entryText.includes('workflow_get_schema.input_schema')" in source
    assert "exitText.includes('output')" in source
    assert "exitText.includes('workflow_get_schema.output_schema')" in source
    assert "schemaText.includes('workflow_get_schema')" in source
    assert "interface_evidence = wait_until" in source
    assert '"interface_evidence": interface_evidence' in source
    assert "def click_editor_testid" in source
    assert ".find((item) => item.getAttribute('data-testid') === {testid_json})" in source
    assert (
        'click_editor_testid(client, "codex-drop-answer-on-workflow-canvas", timeout=30)' in source
    )
    assert (
        'click_editor_testid(client, "codex-connect-start-to-dropped-node", timeout=30)' in source
    )
    assert 'click_editor_testid(client, "workflow-save-graph", timeout=30)' in source
    assert 'f"workflow-editor-interaction-{stamp}.png"' in source
    assert 'f"workflow-editor-interaction-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + WORKFLOW_EDITOR_SMOKE_PATH)")
    interface_index = source.index("interface_evidence = wait_until", navigate_index)
    drop_index = source.index(
        'click_editor_testid(client, "codex-drop-answer-on-workflow-canvas", timeout=30)'
    )
    connect_index = source.index(
        'click_editor_testid(client, "codex-connect-start-to-dropped-node", timeout=30)'
    )
    save_index = source.index('click_editor_testid(client, "workflow-save-graph", timeout=30)')
    log_index = source.index("saved_log_evidence = wait_until")
    assert navigate_index < interface_index < drop_index < connect_index < save_index < log_index


def test_tool_approval_result_cdp_resumes_paused_workflow_from_result_card() -> None:
    source = TOOL_APPROVAL_CDP_SCRIPT.read_text(encoding="utf-8")

    assert 'TOOL_APPROVAL_SMOKE_PATH = "/codex/tool-workflow-approval-result-smoke"' in source
    assert "from workflow_editor_interaction_cdp import start_vite_mock_server" in source
    assert "def approval_card_evidence" in source
    assert "bodyText.includes('Awaiting approval')" in source
    assert "bodyText.includes('workflow_resume')" in source
    assert "def click_workflow_result_pill" in source
    assert "text.includes('Workflow run') && text.includes('wf-browser')" in source
    assert "workflow result pill not found" in source
    assert "def request_log_evidence" in source
    assert "fetch('/api/codex/request-log')" in source
    assert "last_workflow_resume_body" in source
    assert "def run_tool_approval_result" in source
    assert "navigate(client, base_url + TOOL_APPROVAL_SMOKE_PATH)" in source
    assert "click_workflow_result_pill(client)" in source
    assert 'click_button(client, "Approve", timeout=30)' in source
    assert (
        '(evidence := request_log_evidence(client)).get("approval_run_state") == "resumed"'
        in source
    )
    assert '(evidence.get("last_workflow_resume_body") or {}).get("approved") is True' in source
    assert 'f"workflow-tool-approval-result-{stamp}.png"' in source
    assert 'f"workflow-tool-approval-result-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + TOOL_APPROVAL_SMOKE_PATH)")
    open_index = source.index("click_workflow_result_pill(client)", navigate_index)
    before_index = source.index("before_evidence = wait_until", open_index)
    approve_index = source.index('click_button(client, "Approve", timeout=30)')
    resume_index = source.index("resume_log = wait_until", approve_index)
    after_index = source.index("after_evidence = wait_until", resume_index)
    assert navigate_index < open_index < before_index < approve_index < resume_index < after_index


def test_chat_replay_approval_cdp_resumes_replayed_paused_workflow_tool_result() -> None:
    source = CHAT_REPLAY_APPROVAL_CDP_SCRIPT.read_text(encoding="utf-8")

    assert (
        'CHAT_REPLAY_APPROVAL_SMOKE_PATH = "/codex/chat-session-replay-workflow-approval-tool-smoke"'
        in source
    )
    assert "from workflow_tool_approval_result_cdp import" in source
    assert "approval_card_evidence" in source
    assert "click_workflow_result_pill" in source
    assert "request_log_evidence" in source
    assert "def click_workflow_tool_pill" in source
    assert "workflow tool pill not found" in source
    assert "def replay_messages_evidence" in source
    assert "window.__chatReplayWorkflowApprovalMessages" in source
    assert "hasPausedWorkflowResult" in source
    assert "part.result.plugin_id === 'workflow'" in source
    assert "part.result.next_action?.resume?.tool === 'workflow_resume'" in source
    assert "def run_chat_replay_approval" in source
    assert "navigate(client, base_url + CHAT_REPLAY_APPROVAL_SMOKE_PATH)" in source
    assert "click_workflow_tool_pill(client)" in source
    assert "click_workflow_result_pill(client)" in source
    assert 'click_button(client, "Approve", timeout=30)' in source
    assert (
        '(evidence := request_log_evidence(client)).get("approval_run_state") == "resumed"'
        in source
    )
    assert 'f"workflow-chat-replay-approval-{stamp}.png"' in source
    assert 'f"workflow-chat-replay-approval-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + CHAT_REPLAY_APPROVAL_SMOKE_PATH)")
    replay_index = source.index("replay_evidence = wait_until", navigate_index)
    tool_index = source.index("click_workflow_tool_pill(client)", replay_index)
    result_index = source.index("click_workflow_result_pill(client)", tool_index)
    before_index = source.index("before_evidence = wait_until", result_index)
    approve_index = source.index('click_button(client, "Approve", timeout=30)')
    after_index = source.index("after_evidence = wait_until", approve_index)
    assert (
        navigate_index
        < replay_index
        < tool_index
        < result_index
        < before_index
        < approve_index
        < after_index
    )


def test_agent_team_approval_cdp_resumes_nested_paused_workflow_run() -> None:
    source = AGENT_TEAM_APPROVAL_CDP_SCRIPT.read_text(encoding="utf-8")

    assert (
        'AGENT_TEAM_APPROVAL_SMOKE_PATH = "/codex/agent-team-replay-workflow-approval-smoke"'
        in source
    )
    assert "from workflow_tool_approval_result_cdp import" in source
    assert "approval_card_evidence" in source
    assert "click_workflow_result_pill" in source
    assert "request_log_evidence" in source
    assert "def click_agent_team_member_card" in source
    assert "Workflow Researcher" in source
    assert "Workflow researcher" in source
    assert "cursor-pointer" in source
    assert "agent team member card not found" in source
    assert "def click_agent_team_processing_section" in source
    assert 'button[aria-expanded="false"]' in source
    assert "agent team processing section toggle not found" in source
    assert "def agent_team_replay_evidence" in source
    assert "window.__agentTeamReplayWorkflowApprovalMessages" in source
    assert "hasSubagentWorkflowPart" in source
    assert "part.type === 'workflow'" in source
    assert "part.plugin_id === 'workflow'" in source
    assert "part.next_action?.resume?.tool === 'workflow_resume'" in source
    assert "def run_agent_team_approval" in source
    assert "navigate(client, base_url + AGENT_TEAM_APPROVAL_SMOKE_PATH)" in source
    assert "click_agent_team_member_card(client)" in source
    assert "click_agent_team_processing_section(client)" in source
    assert "click_workflow_result_pill(client)" in source
    assert 'click_button(client, "Approve", timeout=30)' in source
    assert (
        '(evidence := request_log_evidence(client)).get("approval_run_state") == "resumed"'
        in source
    )
    assert 'f"workflow-agent-team-approval-{stamp}.png"' in source
    assert 'f"workflow-agent-team-approval-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + AGENT_TEAM_APPROVAL_SMOKE_PATH)")
    replay_index = source.index("replay_evidence = wait_until", navigate_index)
    member_index = source.index("click_agent_team_member_card(client)", replay_index)
    section_index = source.index("click_agent_team_processing_section(client)", member_index)
    result_index = source.index("click_workflow_result_pill(client)", section_index)
    before_index = source.index("before_evidence = wait_until", result_index)
    approve_index = source.index('click_button(client, "Approve", timeout=30)')
    after_index = source.index("after_evidence = wait_until", approve_index)
    assert (
        navigate_index
        < replay_index
        < member_index
        < section_index
        < result_index
        < before_index
        < approve_index
        < after_index
    )


def test_scheduled_approval_cdp_exposes_resume_handoff_and_run_route() -> None:
    source = SCHEDULED_APPROVAL_CDP_SCRIPT.read_text(encoding="utf-8")

    assert (
        'SCHEDULED_APPROVAL_SMOKE_PATH = "/codex/scheduled-workflow-approval-result-smoke"'
        in source
    )
    assert "def scheduled_approval_evidence" in source
    assert "bodyText.includes('Workflow results')" in source
    assert "bodyText.includes('Browser approval')" in source
    assert "bodyText.includes('workflow_resume')" in source
    assert (
        "bodyText.includes('/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/resume')"
        in source
    )
    assert "bodyText.includes('/api/plugins/workflow/approvals/pending')" in source
    assert "window.__scheduledWorkflowApprovalSmokeLocation" in source
    assert "def workflow_run_page_approval_evidence" in source
    assert "bodyText.includes('Workflow Run Trace')" in source
    assert "bodyText.includes('Approved via browser smoke')" in source
    assert "request_log_evidence" in source
    assert "def click_scheduled_workflow_card" in source
    assert "scheduled workflow result card not found" in source
    assert "def run_scheduled_approval" in source
    assert "navigate(client, base_url + SCHEDULED_APPROVAL_SMOKE_PATH)" in source
    assert "click_scheduled_workflow_card(client)" in source
    assert '== "/workflows/wf-browser/runs/run-approval-browser"' in source
    assert 'click_button(client, "Approve", timeout=30)' in source
    assert (
        '(evidence := request_log_evidence(client)).get("approval_run_state") == "resumed"'
        in source
    )
    assert '(evidence.get("last_workflow_resume_body") or {}).get("approved") is True' in source
    assert 'f"workflow-scheduled-approval-{stamp}.png"' in source
    assert 'f"workflow-scheduled-approval-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + SCHEDULED_APPROVAL_SMOKE_PATH)")
    before_index = source.index("before_evidence = wait_until", navigate_index)
    click_index = source.index("click_scheduled_workflow_card(client)", before_index)
    route_index = source.index("navigation_evidence = wait_until", click_index)
    run_page_index = source.index("run_page_before = wait_until", route_index)
    approve_index = source.index('click_button(client, "Approve", timeout=30)', run_page_index)
    after_index = source.index("run_page_after = wait_until", approve_index)
    assert (
        navigate_index
        < before_index
        < click_index
        < route_index
        < run_page_index
        < approve_index
        < after_index
    )


def test_disabled_workflow_contributions_cdp_proves_runtime_filtering() -> None:
    source = DISABLED_CONTRIBUTIONS_CDP_SCRIPT.read_text(encoding="utf-8")
    mock_source = MOCK_SCRIPT.read_text(encoding="utf-8")

    assert (
        'DISABLED_CONTRIBUTIONS_SMOKE_PATH = "/codex/disabled-workflow-contributions-smoke"'
        in source
    )
    assert "def disabled_contribution_evidence" in source
    assert "window.__codexDisabledWorkflowContributionEvidence" in source
    assert "enabledHasWorkflowRoutes" in source
    assert "disabledHasNoWorkflowRoutes" in source
    assert "disabledHasNoWorkflowChatPicker" in source
    assert "disabledKeepsAgentTeamRoute" in source
    assert "def assert_disabled_contribution_evidence" in source
    assert "def run_disabled_contributions" in source
    assert "navigate(client, base_url + DISABLED_CONTRIBUTIONS_SMOKE_PATH)" in source
    assert "assert_disabled_contribution_evidence(evidence)" in source
    assert 'f"workflow-disabled-contributions-{stamp}.png"' in source
    assert 'f"workflow-disabled-contributions-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + DISABLED_CONTRIBUTIONS_SMOKE_PATH)")
    wait_index = source.index("evidence = wait_until", navigate_index)
    assert_index = source.index("assert_disabled_contribution_evidence(evidence)", wait_index)
    screenshot_index = source.index("screenshot_path = out_dir", assert_index)
    assert navigate_index < wait_index < assert_index < screenshot_index

    assert "function disabledWorkflowContributionsSmokeHtml" in mock_source
    assert "/codex/disabled-workflow-contributions-smoke" in mock_source
    assert "buildAppRouteContributions" in mock_source
    assert "buildChatInputOptionContributions" in mock_source
    assert "buildChatInputPanelContributions" in mock_source
    assert "workflowPluginPlugin(false)" in mock_source
    assert "agentTeamPlugin()" in mock_source
    assert "disabled-workflow-contributions" in mock_source


def test_chat_selected_entry_cdp_proves_chat_uses_workflow_entry_exit() -> None:
    source = CHAT_SELECTED_ENTRY_CDP_SCRIPT.read_text(encoding="utf-8")
    mock_source = MOCK_SCRIPT.read_text(encoding="utf-8")

    assert 'CHAT_SELECTED_ENTRY_SMOKE_PATH = "/codex/workflow-chat-selected-entry-smoke"' in source
    assert "def selected_entry_evidence" in source
    assert "window.__workflowChatSelectedEntryEvidence" in source
    assert "hasWorkflowRunEntry" in source
    assert "entry.tool === 'workflow_run' && entry.argument === 'input'" in source
    assert "hasWorkflowExit" in source
    assert "exit.field === 'output' && exit.schema_tool === 'workflow_get_schema'" in source
    assert "hasUseOutputAction" in source
    assert "workflow_run_succeeded" in source
    assert "hasRenderedWorkflowResult" in source
    assert "bodyText.includes('Workflow run wf-browser')" in source
    assert "def request_log_evidence" in source
    assert "last_chat_stream_body" in source
    assert "last_workflow_run_body" in source
    assert "runSource: runBody.source" in source
    assert "runEntryTool: runBody.interface?.entry?.tool" in source
    assert "runExitField: runBody.interface?.exit?.field" in source
    assert "def assert_selected_entry" in source
    assert "SELECTED_WORKFLOW_INPUT_JSON" in source
    assert 'runSource") != "chat_selected_workflow"' in source
    assert 'runEntryTool") != "workflow_run"' in source
    assert 'runExitField") != "output"' in source
    assert "def run_chat_selected_entry" in source
    assert "navigate(client, base_url + CHAT_SELECTED_ENTRY_SMOKE_PATH)" in source
    assert 'click_testid(client, "codex-send-selected-workflow-chat", timeout=30)' in source
    assert "assert_selected_entry(evidence, request_log)" in source
    assert 'f"workflow-chat-selected-entry-{stamp}.png"' in source
    assert 'f"workflow-chat-selected-entry-{stamp}.json"' in source

    navigate_index = source.index("navigate(client, base_url + CHAT_SELECTED_ENTRY_SMOKE_PATH)")
    click_index = source.index(
        'click_testid(client, "codex-send-selected-workflow-chat", timeout=30)'
    )
    evidence_index = source.index("evidence = wait_until", click_index)
    log_index = source.index("request_log = wait_until", evidence_index)
    assert_index = source.index("assert_selected_entry(evidence, request_log)", log_index)
    screenshot_index = source.index("screenshot_path = out_dir", assert_index)
    assert (
        navigate_index < click_index < evidence_index < log_index < assert_index < screenshot_index
    )

    assert "function workflowChatSelectedEntrySmokeHtml" in mock_source
    assert "/codex/workflow-chat-selected-entry-smoke" in mock_source
    assert 'SELECTED_WORKFLOW_ID: "wf-browser"' in mock_source
    assert 'SELECTED_WORKFLOW_VERSION_ID: "wfv-browser-2"' in mock_source
    assert "SELECTED_WORKFLOW_INPUT_JSON" in mock_source
    assert "const buttonTestId = agentTeamMode" in mock_source
    assert '"codex-send-selected-workflow-chat"' in mock_source
    assert '"data-testid": buttonTestId' in mock_source
    assert "processMessageEvent" in mock_source
    assert "MessagePartRenderer" in mock_source
    assert "const evidenceHook = agentTeamMode" in mock_source
    assert '"__workflowChatSelectedEntryEvidence"' in mock_source
    assert "window[evidenceHook]" in mock_source
    assert (
        'source: selectedTeamId ? "agent_team_selected_workflow" : "chat_selected_workflow"'
        in mock_source
    )
    assert "interface: workflowCallableInterface(" in mock_source


def test_agent_team_selected_entry_cdp_proves_live_team_uses_workflow_entry_exit() -> None:
    source = AGENT_TEAM_SELECTED_ENTRY_CDP_SCRIPT.read_text(encoding="utf-8")
    mock_source = MOCK_SCRIPT.read_text(encoding="utf-8")

    assert (
        'AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH = "/codex/workflow-agent-team-selected-entry-smoke"'
        in source
    )
    assert "def agent_team_selected_entry_evidence" in source
    assert "window.__workflowAgentTeamSelectedEntryEvidence" in source
    assert "hasSubagentPart" in source
    assert "hasNestedWorkflowPart" in source
    assert "workflowPart.depth === 1" in source
    assert "workflowPart.agent_id === 'team-m-browser-researcher'" in source
    assert "hasWorkflowRunEntry" in source
    assert "entry.tool === 'workflow_run' && entry.argument === 'input'" in source
    assert "hasWorkflowExit" in source
    assert "exit.field === 'output' && exit.schema_tool === 'workflow_get_schema'" in source
    assert "hasUseOutputAction" in source
    assert "Agent Team workflow saw: Agent Team explicit entry message" in source
    assert "def request_log_evidence" in source
    assert "selectedTeamId: teamOptions.SELECTED_TEAM_ID" in source
    assert "runSource: runBody.source" in source
    assert "callerPluginId: runBody.caller_plugin_id" in source
    assert "runEntryTool: runBody.interface?.entry?.tool" in source
    assert "def assert_agent_team_selected_entry" in source
    assert 'runSource") != "agent_team_selected_workflow"' in source
    assert 'callerPluginId") != "agent_team"' in source
    assert 'runEntryTool") != "workflow_run"' in source
    assert 'runExitField") != "output"' in source
    assert "def run_agent_team_selected_entry" in source
    assert "navigate(client, base_url + AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH)" in source
    assert (
        'click_testid(client, "codex-send-agent-team-selected-workflow-chat", timeout=30)' in source
    )
    assert "assert_agent_team_selected_entry(evidence, request_log)" in source
    assert 'f"workflow-agent-team-selected-entry-{stamp}.png"' in source
    assert 'f"workflow-agent-team-selected-entry-{stamp}.json"' in source

    navigate_index = source.index(
        "navigate(client, base_url + AGENT_TEAM_SELECTED_ENTRY_SMOKE_PATH)"
    )
    click_index = source.index(
        'click_testid(client, "codex-send-agent-team-selected-workflow-chat", timeout=30)'
    )
    evidence_index = source.index("evidence = wait_until", click_index)
    log_index = source.index("request_log = wait_until", evidence_index)
    assert_index = source.index(
        "assert_agent_team_selected_entry(evidence, request_log)", log_index
    )
    screenshot_index = source.index("screenshot_path = out_dir", assert_index)
    assert (
        navigate_index < click_index < evidence_index < log_index < assert_index < screenshot_index
    )

    assert "workflowChatSelectedEntrySmokeHtml({ agentTeamMode: true })" in mock_source
    assert "/codex/workflow-agent-team-selected-entry-smoke" in mock_source
    assert 'SELECTED_TEAM_ID: "team-browser"' in mock_source
    assert "agent_team_selected_workflow" in mock_source
    assert 'caller_plugin_id: selectedTeamId ? "agent_team" : "chat"' in mock_source
    assert 'event: "agent:call"' in mock_source
    assert 'event: "agent:result"' in mock_source
    assert "run-agent-team-live-browser" in mock_source
    assert "Agent Team workflow saw" in mock_source
