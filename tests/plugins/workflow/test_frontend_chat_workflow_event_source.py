from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def read_frontend_source(*parts: str) -> str:
    return (FRONTEND_SRC.joinpath(*parts)).read_text(encoding="utf-8")


def test_chat_workflow_run_event_is_a_first_class_message_part() -> None:
    message_source = read_frontend_source("types", "message.ts")
    types_source = read_frontend_source("hooks", "useAgent", "types.ts")
    processor_source = read_frontend_source("hooks", "useAgent", "eventProcessor.ts")
    handlers_source = read_frontend_source("hooks", "useAgent", "eventHandlers.ts")

    assert "| WorkflowPart" in message_source
    assert 'type: "workflow";' in message_source
    assert "interface?: WorkflowInterfaceContract | null;" in message_source
    assert "next_action?: Record<string, unknown> | null;" in message_source
    assert '  | "workflow:run"' in types_source
    assert 'case "workflow:run":' in processor_source
    assert 'type: "workflow"' in processor_source
    assert "interface: data.interface" in processor_source
    assert "next_action: data.next_action" in processor_source
    assert "output_contract: data.output_contract" in processor_source
    assert '"workflow:run",' in handlers_source


def test_chat_workflow_part_renders_entry_exit_and_debug_interface() -> None:
    renderer_source = read_frontend_source(
        "components",
        "chat",
        "ChatMessage",
        "MessagePartRenderer.tsx",
    )
    tool_item_source = read_frontend_source(
        "components",
        "chat",
        "ChatMessage",
        "ToolCallItem.tsx",
    )
    workflow_item_source = read_frontend_source(
        "components",
        "chat",
        "ChatMessage",
        "items",
        "WorkflowItem.tsx",
    )
    mcp_result_source = read_frontend_source(
        "components",
        "chat",
        "ChatMessage",
        "items",
        "McpBlockPreview.tsx",
    )

    assert "WorkflowItem" in tool_item_source
    assert 'if (part.type === "workflow")' in renderer_source
    assert "<WorkflowItem part={part} />" in renderer_source
    assert "function workflowPartFromToolResult" in mcp_result_source
    assert "function looksLikeWorkflowRunResult" in mcp_result_source
    assert 'data.plugin_id !== "workflow"' in mcp_result_source
    assert "nonEmptyString(data.status)" in mcp_result_source
    assert 'typeof data.error === "string"' in mcp_result_source
    assert "isRecord(data.next_action)" in mcp_result_source
    assert "const runId = nonEmptyString(data.run_id)" in mcp_result_source
    assert "if (!runId || !workflowId) return null" not in mcp_result_source
    assert "return <WorkflowItem part={workflowPart} />" in mcp_result_source
    assert "function InterfaceRows" in workflow_item_source
    assert 't("chat.message.workflowEntry", "Entry")' in workflow_item_source
    assert 't("chat.message.workflowExit", "Exit")' in workflow_item_source
    assert 't("chat.message.workflowDebug", "Debug")' in workflow_item_source
    assert 'data-testid="workflow-result-interface"' in workflow_item_source
    assert "data-testid={`workflow-result-interface-${row.key}`}" in workflow_item_source
    assert 'key: "entry"' in workflow_item_source
    assert 'key: "exit"' in workflow_item_source
    assert 'key: "debug"' in workflow_item_source
    assert 't("chat.message.workflowNextAction", "Next action")' in workflow_item_source
    assert "toolField(entry?.tool, entry?.argument)" in workflow_item_source
    assert "toolField(exit?.schema_tool, exit?.schema_field)" in workflow_item_source
    assert "toolField(debug?.tool, debug?.events_field)" in workflow_item_source
    assert "const actionType = stringValue(action?.type)" in workflow_item_source
    assert (
        'actionType !== "await_human_approval" && actionType !== "wait_for_human_approval"'
        in workflow_item_source
    )
    assert 'resumeTool: stringValue(resume?.tool) || "workflow_resume"' in workflow_item_source
    assert "updatePersistentToolPanel" in workflow_item_source
    assert "function WorkflowResumeResultPanel" in workflow_item_source
    assert "<WorkflowResumeResultPanel part={nextPart} />" in workflow_item_source
    assert "status: workflowStatus(nextPart.status, nextPart.error)" in workflow_item_source
    assert (
        'const panelKey = `workflow:${workflowId || "unknown"}:${runId || "latest"}`;'
        in workflow_item_source
    )
    assert "children: detailContent" in workflow_item_source
    assert "panelKey," in workflow_item_source
    assert (
        "`/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`"
        in workflow_item_source
    )
    assert 't("chat.message.workflowOpenRun", "Open run")' in workflow_item_source


def test_failed_workflow_tool_result_without_run_id_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "export const failedRunWithoutId" in mock_source
    assert "run_id: null" in mock_source
    assert 'error: "workflow_input_required_missing:message"' in mock_source
    assert "next_action: {" in mock_source
    assert 'reason: "workflow_run_failed"' in mock_source
    assert "function failedToolWorkflowResultSmokeHtml" in mock_source
    assert 'data-smoke": "failed-tool-workflow-result"' in mock_source
    assert "/codex/failed-tool-workflow-result-smoke" in mock_source
    assert "React.createElement(ToolResultContent, { result: workflowToolResult })" in mock_source


def test_tool_workflow_approval_result_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "function toolWorkflowApprovalResultSmokeHtml" in mock_source
    assert 'plugin_id: "workflow"' in mock_source
    assert "const workflowToolResult = ${JSON.stringify(pausedApprovalRun)};" in mock_source
    assert 'data-smoke": "tool-workflow-approval-result"' in mock_source
    assert "/codex/tool-workflow-approval-result-smoke" in mock_source
    assert "toolWorkflowApprovalResultSmokeHtml()" in mock_source
    assert "React.createElement(ToolResultContent, { result: workflowToolResult })" in mock_source
    assert 'type: "wait_for_human_approval"' in mock_source
    assert 'tool: "workflow_get_run"' in mock_source
    assert "approval: {" in mock_source
    assert "pending: {" in mock_source
    assert "resume: {" in mock_source
    assert 'tool: "workflow_resume"' in mock_source
    assert (
        'path: "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/resume"'
        in mock_source
    )


def test_chat_replay_workflow_approval_tool_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "const chatApprovalReplaySessionId" in mock_source
    assert "const chatApprovalReplayRunId" in mock_source
    assert "function chatReplayWorkflowApprovalToolEvents" in mock_source
    assert 'tool_call_id: "tool-call-approval-replay-workflow-browser"' in mock_source
    assert 'tool: "workflow_run"' in mock_source
    assert "result: pausedApprovalRun" in mock_source
    assert "function chatSessionReplayWorkflowApprovalToolSmokeHtml" in mock_source
    assert "/codex/chat-session-replay-workflow-approval-tool-smoke" in mock_source
    assert 'data-smoke": "chat-session-replay-workflow-approval-tool"' in mock_source
    assert "reconstructMessagesFromEvents" in mock_source
    assert "MessagePartRenderer" in mock_source
    assert "window.__chatReplayWorkflowApprovalMessages = reconstructed" in mock_source
    assert "chatReplayWorkflowApprovalToolEvents()" in mock_source


def test_agent_team_replay_workflow_approval_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "const agentTeamApprovalReplaySessionId" in mock_source
    assert "const agentTeamApprovalReplayRunId" in mock_source
    assert "function agentTeamWorkflowApprovalReplayEvents" in mock_source
    assert 'event_type: "agent:call"' in mock_source
    assert 'event_type: "workflow:run"' in mock_source
    assert "...pausedApprovalRun" in mock_source
    assert "agent_id: agentTeamMemberId" in mock_source
    assert "depth: 1" in mock_source
    assert "function agentTeamReplayWorkflowApprovalSmokeHtml" in mock_source
    assert "/codex/agent-team-replay-workflow-approval-smoke" in mock_source
    assert 'data-smoke": "agent-team-replay-workflow-approval"' in mock_source
    assert "reconstructMessagesFromEvents" in mock_source
    assert "MessagePartRenderer" in mock_source
    assert "window.__agentTeamReplayWorkflowApprovalMessages = reconstructed" in mock_source
    assert "agentTeamWorkflowApprovalReplayEvents()" in mock_source


def test_scheduled_workflow_approval_result_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "function scheduledApprovalWorkflowRunResult" in mock_source
    assert "...pausedApprovalRun" in mock_source
    assert "function scheduledWorkflowApprovalResultSmokeHtml" in mock_source
    assert "/codex/scheduled-workflow-approval-result-smoke" in mock_source
    assert 'data-smoke": "scheduled-workflow-approval-result"' in mock_source
    assert "window.__scheduledWorkflowApprovalSmokeLocation = location.pathname" in mock_source
    assert 'path: "/scheduled-task-approval-smoke"' in mock_source
    assert 'path: "/workflows/:workflowId/runs/:runId"' in mock_source
    assert (
        'element: React.createElement(WorkflowPanel, { activeTab: "workflows-run" })' in mock_source
    )
    assert 'taskId: "task-workflow-approval-browser"' in mock_source
    assert "/api/scheduled-tasks/task-workflow-approval-browser/sessions" in mock_source
    assert "/api/scheduled-tasks/task-workflow-approval-browser/runs" in mock_source
    assert 'id: "task-run-workflow-approval-browser"' in mock_source
    assert 'status: "running"' in mock_source
    assert "workflow_result: workflowResult" in mock_source


def test_failed_workflow_tool_debug_result_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "export const failedRunWithDebugId" in mock_source
    assert 'run_id: "run-missing-debug-browser"' in mock_source
    assert 'error: "workflow_run_not_found"' in mock_source
    assert 'tool: "workflow_get_run"' in mock_source
    assert 'events_field: "events"' in mock_source
    assert 'data-smoke": "failed-tool-workflow-debug-result"' in mock_source
    assert "function failedToolWorkflowDebugResultSmokeHtml" in mock_source
    assert "/codex/failed-tool-workflow-debug-result-smoke" in mock_source
    assert "React.createElement(ToolResultContent, { result: workflowToolResult })" in mock_source


def test_failed_workflow_tool_debug_result_replays_from_history_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "const failedChatReplaySessionId" in mock_source
    assert "function failedChatReplayWorkflowToolEvents" in mock_source
    assert 'tool: "workflow_get_run"' in mock_source
    assert "result: failedRunWithDebugId" in mock_source
    assert "success: false" in mock_source
    assert "function failedChatSessionReplayWorkflowToolSmokeHtml" in mock_source
    assert "/codex/failed-chat-session-replay-workflow-tool-smoke" in mock_source
    assert 'data-smoke": "failed-chat-session-replay-workflow-tool"' in mock_source
    assert "reconstructMessagesFromEvents" in mock_source
    assert "MessagePartRenderer" in mock_source
    assert "window.__failedChatReplayWorkflowMessages = reconstructed" in mock_source


def test_failed_workflow_run_event_without_run_id_has_browser_smoke_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "function failedChatWorkflowRunEvent" in mock_source
    assert "function failedWorkflowChatSmokeHtml" in mock_source
    assert 'data-smoke": "failed-workflow-chat-event"' in mock_source
    assert "window.__failedWorkflowEventParts = processed.parts" in mock_source
    assert "/codex/failed-workflow-chat-event-smoke" in mock_source
    assert 'eventProcessor.ts";' in mock_source


def test_workflow_editor_browser_smoke_can_save_publish_and_run_latest_version() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")

    assert "function workflowEditorInteractionSmokeHtml" in mock_source
    assert 'data-smoke": "workflow-editor-interaction"' in mock_source
    assert "/codex/workflow-editor-interaction-smoke" in mock_source
    assert "let savedWorkflowVersion = null" in mock_source
    assert "function currentWorkflowSummary" in mock_source
    assert 'version_id: "wfv-browser-saved"' in mock_source
    assert "/api/plugins/workflow/workflows/wf-browser/publish" in mock_source
    assert "publishedWorkflowVersionId = requestedVersionId" in mock_source
    assert "saved_workflow_version_id: savedWorkflowVersion?.version_id ?? null" in mock_source
    assert "published_workflow_version_id: publishedWorkflowVersionId" in mock_source


def test_workflow_editor_browser_smoke_has_non_contiguous_node_id_fixture() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")
    panel_source = read_frontend_source("plugins", "workflow", "WorkflowPanel.tsx")

    assert 'id: "node_4"' in mock_source
    assert 'title: "Imported Answer"' in mock_source
    assert "last_workflow_version_body: lastWorkflowVersionBody" in mock_source
    assert "function nextWorkflowNodeId(graph: EditableGraph)" in panel_source
    assert "const id = nextWorkflowNodeId(current);" in panel_source


def test_workflow_editor_browser_smoke_can_dispatch_canvas_drop() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")
    panel_source = read_frontend_source("plugins", "workflow", "WorkflowPanel.tsx")

    assert (
        'const WORKFLOW_CANVAS_DRAG_TYPE = "application/x-lambchat-workflow-node";' in mock_source
    )
    assert "window.__codexDropWorkflowNode" in mock_source
    assert 'window.__codexDropWorkflowNode("human_approval")' in mock_source
    assert "createWorkflowDropEvent" in mock_source
    assert "document.querySelector('[data-testid=\"workflow-canvas\"]')" in mock_source
    assert 'canvas.dispatchEvent(createWorkflowDropEvent("dragover"' in mock_source
    assert 'canvas.dispatchEvent(createWorkflowDropEvent("drop"' in mock_source
    assert 'data-testid": "codex-drop-answer-on-workflow-canvas"' in mock_source
    assert 'data-testid": "codex-drop-human-approval-on-workflow-canvas"' in mock_source
    assert "onDragOver={handleDragOver}" in panel_source
    assert "onDrop={handleDrop}" in panel_source


def test_workflow_editor_browser_mock_supports_human_approval_pause_and_resume() -> None:
    mock_source = (
        REPO_ROOT / "tests" / "fixtures" / "workflow" / "browser" / "browser_workflow_mock.mjs"
    ).read_text(encoding="utf-8")
    panel_source = read_frontend_source("plugins", "workflow", "WorkflowPanel.tsx")

    assert "export const pausedApprovalRun" in mock_source
    assert 'run_id: "run-approval-browser"' in mock_source
    assert 'status: "paused"' in mock_source
    assert 'kind: "human_approval"' in mock_source
    assert 'instructions: "Approve browser workflow {{message}}"' in mock_source
    assert 'assignee: "browser-reviewer"' in mock_source
    assert 'output_key: "browser_approval"' in mock_source
    assert "export const resumedApprovalRun" in mock_source
    assert 'status: "succeeded"' in mock_source
    assert "let lastWorkflowRunBody = null" in mock_source
    assert "let lastWorkflowResumeBody = null" in mock_source
    assert "last_workflow_run_body: lastWorkflowRunBody" in mock_source
    assert "last_workflow_resume_body: lastWorkflowResumeBody" in mock_source
    assert "approval_run_state: approvalRunState" in mock_source
    assert 'runs: approvalRunState === "paused" ? [{ ...pausedApprovalRun' in mock_source
    assert (
        'path === "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/events"'
        in mock_source
    )
    assert 'if (lastWorkflowRunBody?.mode === "async")' in mock_source
    assert (
        'path === "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/resume"'
        in mock_source
    )
    assert 'lastWorkflowResumeBody?.comment ?? ""' in mock_source
    assert 'event_type: "human_approval_required"' in mock_source
    assert 'event_type: "human_approval_resumed"' in mock_source
    assert "function HumanApprovalPanel" in panel_source
    assert "onResume(true)" in panel_source
    assert "workflowApi.resumeRun" in panel_source
