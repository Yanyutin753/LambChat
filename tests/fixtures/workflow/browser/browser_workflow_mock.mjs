export const nowIso = "2026-06-28T10:00:00.000Z";

export const inputSchema = {
  type: "object",
  required: ["message"],
  properties: {
    message: {
      type: "string",
      description: "Workflow entry message",
      default: "hello",
    },
  },
  additionalProperties: true,
};

export const outputSchema = {
  type: "object",
  required: ["report"],
  properties: {
    report: {
      type: "object",
      required: ["summary"],
      properties: {
        summary: {
          type: "string",
          description: "Report summary",
        },
      },
    },
    items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          summary: { type: "string" },
        },
      },
    },
  },
  additionalProperties: true,
};

export const workflow = {
  workflow_id: "wf-browser",
  name: "Browser Contract Workflow",
  status: "published",
  latest_version_id: "wfv-browser-2",
  published_version_id: "wfv-browser-2",
  description: "Browser verification workflow",
  version_count: 2,
  created_at: nowIso,
  updated_at: nowIso,
};

export const internalModel = {
  format: "lambchat.workflow.v1",
  graph: {
    nodes: [
      {
        id: "start",
        type: "start",
        title: "Start",
        data: {
          title: "Start",
          input_schema: inputSchema,
          variables: [{ name: "message", type: "string", required: true }],
        },
        position: { x: 80, y: 120 },
      },
      {
        id: "answer",
        type: "answer",
        title: "Answer",
        data: {
          title: "Answer",
          answer: "{{message}}",
          output_schema: outputSchema,
        },
        position: { x: 460, y: 120 },
      },
      {
        id: "node_4",
        type: "answer",
        title: "Imported Answer",
        data: {
          title: "Imported Answer",
          answer: "Imported fixture answer",
          output_schema: outputSchema,
        },
        position: { x: 460, y: 320 },
      },
    ],
    edges: [{ id: "start-answer", source: "start", target: "answer", valid: true }],
  },
};

export const version = {
  version_id: "wfv-browser-2",
  workflow_id: "wf-browser",
  version_number: 2,
  source: "workflow",
  source_format: "json",
  internal_model: internalModel,
  compatibility_report: {
    lossless: true,
    source_version: "workflow-0.3.0",
    supported_nodes: ["start", "answer"],
    unsupported_nodes: [],
    warnings: [],
    errors: [],
    boundary_warnings: [],
    boundary_errors: [],
    credential_refs_required: [],
    credential_refs_resolved: [],
    credential_refs_unresolved: [],
  },
  created_at: nowIso,
};

export function workflowCallableInterface(workflowId = "wf-browser", versionId = "wfv-browser-2") {
  return {
    entry: {
      type: "workflow.input",
      tool: "workflow_run",
      argument: "input",
      workflow_id: workflowId,
      version_id: versionId,
      schema_tool: "workflow_get_schema",
      schema_field: "input_schema",
    },
    exit: {
      type: "workflow.output",
      field: "output",
      schema_tool: "workflow_get_schema",
      schema_field: "output_schema",
    },
    schema: {
      tool: "workflow_get_schema",
      workflow_id: workflowId,
      version_id: versionId,
      input_schema_field: "input_schema",
      output_schema_field: "output_schema",
    },
    run: {
      tool: "workflow_run",
      workflow_id: workflowId,
      version_id: versionId,
      input_argument: "input",
      output_field: "output",
    },
    debug: {
      tool: "workflow_get_run",
      workflow_id: workflowId,
      run_id_field: "run_id",
    },
  };
}

export const ioContract = {
  plugin_id: "workflow",
  workflow_id: "wf-browser",
  version_id: "wfv-browser-2",
  version_number: 2,
  input_schema: inputSchema,
  output_schema: outputSchema,
  status: "published",
  input_schema_source: "declared",
  output_schema_source: "declared",
  inferred_input_fields: [],
  inferred_output_fields: [],
  interface: workflowCallableInterface("wf-browser", "wfv-browser-2"),
};

function ioContractForVersion(activeVersion = version) {
  return {
    ...ioContract,
    version_id: activeVersion.version_id,
    version_number: activeVersion.version_number,
    status: publishedWorkflowVersionId === activeVersion.version_id ? "published" : activeVersion.status,
    interface: workflowCallableInterface("wf-browser", activeVersion.version_id),
  };
}

export const run = {
  plugin_id: "workflow",
  run_id: "run-browser",
  workflow_id: "wf-browser",
  version_id: "wfv-browser-2",
  mode: "sync",
  status: "succeeded",
  output: {
    report: { summary: "Nested route summary" },
    items: [{ summary: "First item" }],
  },
  error: null,
  pause: {},
  started_at: nowIso,
  finished_at: nowIso,
  events: [],
  io_contract: ioContract,
  interface: {
    entry: {
      type: "workflow.input",
      tool: "workflow_run",
      argument: "input",
      workflow_id: "wf-browser",
      version_id: "wfv-browser-2",
      schema_tool: "workflow_get_schema",
      schema_field: "input_schema",
    },
    exit: {
      type: "workflow.output",
      field: "output",
      schema_tool: "workflow_get_schema",
      schema_field: "output_schema",
    },
    debug: {
      tool: "workflow_get_run",
      workflow_id: "wf-browser",
      run_id: "run-browser",
      events_field: "events",
    },
  },
  output_contract: {
    valid: true,
    schema_field: "output_schema",
    declared_fields: ["items", "report"],
    declared_field_paths: ["report.summary", "items[].summary"],
    required_fields: ["report"],
    required_field_paths: ["report.summary"],
    missing_required: [],
    type_mismatches: [],
    extra_fields: [],
  },
  next_action: {
    type: "use_output",
    field: "output",
    reason: "workflow_run_succeeded",
  },
};

export const pausedApprovalRun = {
  ...run,
  run_id: "run-approval-browser",
  mode: "async",
  status: "paused",
  output: {},
  error: "workflow_human_approval_paused:approval",
  pause: {
    kind: "human_approval",
    pending_approval: {
      node_id: "approval",
      title: "Browser approval",
      instructions: "Approve browser workflow {{message}}",
      assignee: "browser-reviewer",
      output_key: "browser_approval",
    },
    resume_state: {
      kind: "human_approval",
      node_id: "approval",
    },
  },
  started_at: nowIso,
  finished_at: null,
  events: [],
  next_action: {
    type: "wait_for_human_approval",
    reason: "workflow_human_approval_paused",
    tool: "workflow_get_run",
    field: "pause.pending_approval",
    approval: {
      kind: "human_approval",
      node_id: "approval",
      title: "Browser approval",
      assignee: "browser-reviewer",
      output_key: "browser_approval",
    },
    pending: {
      method: "GET",
      path: "/api/plugins/workflow/approvals/pending",
    },
    resume: {
      tool: "workflow_resume",
      method: "POST",
      path: "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/resume",
      body: { approved: true, comment: "", values: {} },
      arguments: {
        workflow_id: "wf-browser",
        run_id: "run-approval-browser",
        approved: true,
        comment: "",
        values: {},
      },
    },
  },
  interface: {
    ...run.interface,
    debug: {
      ...run.interface.debug,
      run_id: "run-approval-browser",
    },
  },
};

export const resumedApprovalRun = {
  ...pausedApprovalRun,
  status: "succeeded",
  output: {
    answer: "Approved via browser smoke",
    browser_approval: {
      approved: true,
      comment: "Browser approval comment",
      response: {},
    },
  },
  error: null,
  pause: {},
  finished_at: nowIso,
  next_action: {
    type: "use_output",
    field: "output",
    reason: "workflow_run_succeeded",
  },
};

export const failedRunWithoutId = {
  plugin_id: "workflow",
  workflow_id: "wf-browser",
  version_id: "wfv-browser-2",
  run_id: null,
  mode: "sync",
  status: "failed",
  output: {},
  error: "workflow_input_required_missing:message",
  interface: {
    entry: {
      type: "workflow.input",
      tool: "workflow_run",
      argument: "input",
      workflow_id: "wf-browser",
      version_id: "wfv-browser-2",
      schema_tool: "workflow_get_schema",
      schema_field: "input_schema",
    },
    exit: {
      type: "workflow.output",
      field: "output",
      schema_tool: "workflow_get_schema",
      schema_field: "output_schema",
    },
    debug: {
      tool: "workflow_get_run",
      workflow_id: "wf-browser",
      run_id: null,
      events_field: "events",
    },
  },
  next_action: {
    type: "handle_terminal_error",
    field: "error",
    reason: "workflow_run_failed",
  },
};

export const failedRunWithDebugId = {
  plugin_id: "workflow",
  workflow_id: "wf-browser",
  version_id: null,
  run_id: "run-missing-debug-browser",
  mode: null,
  status: "failed",
  output: {},
  error: "workflow_run_not_found",
  interface: {
    entry: {
      type: "workflow.input",
      tool: "workflow_run",
      argument: "input",
      workflow_id: "wf-browser",
      version_id: null,
      schema_tool: "workflow_get_schema",
      schema_field: "input_schema",
    },
    exit: {
      type: "workflow.output",
      field: "output",
      schema_tool: "workflow_get_schema",
      schema_field: "output_schema",
    },
    debug: {
      tool: "workflow_get_run",
      workflow_id: "wf-browser",
      run_id: "run-missing-debug-browser",
      events_field: "events",
    },
  },
  next_action: {
    type: "handle_terminal_error",
    field: "error",
    reason: "workflow_run_failed",
    tool: "workflow_get_run",
  },
};

const requestLog = [];
const chatSessionId = "chat-workflow-session";
const chatReplaySessionId = "chat-workflow-tool-replay-session";
const chatReplayRunId = "chat-workflow-tool-replay-run";
const chatApprovalReplaySessionId = "chat-workflow-approval-tool-replay-session";
const chatApprovalReplayRunId = "chat-workflow-approval-tool-replay-run";
const failedChatReplaySessionId = "chat-workflow-tool-failed-debug-replay-session";
const failedChatReplayRunId = "chat-workflow-tool-failed-debug-replay-run";
const agentTeamReplaySessionId = "chat-agent-team-workflow-replay-session";
const agentTeamReplayRunId = "chat-agent-team-workflow-replay-run";
const agentTeamApprovalReplaySessionId = "chat-agent-team-workflow-approval-replay-session";
const agentTeamApprovalReplayRunId = "chat-agent-team-workflow-approval-replay-run";
const agentTeamMemberId = "team-m-browser-researcher";
const chatRunId = "chat-workflow-run";
const chatTraceId = "chat-workflow-trace";
let lastChatMessage = "Browser workflow chat smoke";
let lastChatStreamBody = null;
let lastWorkflowVersionBody = null;
let lastWorkflowRunBody = null;
let lastWorkflowResumeBody = null;
let savedWorkflowVersion = null;
let publishedWorkflowVersionId = workflow.published_version_id;
let approvalRunState = "none";

function currentWorkflowVersion() {
  return savedWorkflowVersion || version;
}

function currentWorkflowSummary() {
  const latestVersion = currentWorkflowVersion();
  return {
    ...workflow,
    status: publishedWorkflowVersionId ? "published" : "draft",
    latest_version_id: latestVersion.version_id,
    published_version_id: publishedWorkflowVersionId,
  };
}

function savedInternalModelFromVersionBody(body) {
  if (body?.internal_model?.graph) {
    return body.internal_model;
  }
  const graph = body?.source_payload?.workflow;
  if (!graph || !Array.isArray(graph.nodes)) {
    return version.internal_model;
  }
  return {
    format: "lambchat.workflow.v1",
    graph: {
      nodes: graph.nodes.map((node) => ({
        ...node,
        title: node.title || node.data?.title || node.id,
        supported: node.supported ?? true,
      })),
      edges: Array.isArray(graph.edges) ? graph.edges : [],
    },
  };
}

function jsonReply(res, data, status = 200) {
  const body = JSON.stringify(data);
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(body);
}

function drainRequest(req) {
  return new Promise((resolve) => {
    req.on("data", () => {});
    req.on("end", resolve);
    req.on("error", resolve);
  });
}

function readRequestBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", () => resolve(""));
  });
}

function sseReply(res, events) {
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("Connection", "keep-alive");
  for (const event of events) {
    res.write(`id: ${event.id}\n`);
    res.write(`event: ${event.event}\n`);
    res.write(`data: ${JSON.stringify(event.data)}\n\n`);
  }
  res.end();
}

function htmlReply(res, html, status = 200) {
  res.statusCode = status;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(html);
}

function pluginContribution() {
  return {
    plugin_id: "workflow",
    enabled: true,
    executable: true,
    status: "enabled",
    frontend: {
      app_tabs: [
        {
          id: "workflow:workflows-tab",
          tab: "workflows",
          path: "/workflows",
          panel: "workflow:workflows-panel",
          insert_after: "agent-team",
          order: 700,
          permissions: ["workflow:read"],
        },
        {
          id: "workflow:workflow-editor-tab",
          tab: "workflows-editor",
          path: "/workflows/:workflowId/editor",
          panel: "workflow:workflow-editor-panel",
          insert_after: "workflows",
          order: 701,
          permissions: ["workflow:read"],
        },
        {
          id: "workflow:workflow-run-tab",
          tab: "workflows-run",
          path: "/workflows/:workflowId/runs/:runId",
          panel: "workflow:workflow-run-panel",
          insert_after: "workflows-editor",
          order: 702,
          permissions: ["workflow:read"],
        },
      ],
      app_panels: [
        { id: "workflow:workflows-panel", tab: "workflows", renderer: "workflow.WorkflowPanel" },
        { id: "workflow:workflow-editor-panel", tab: "workflows-editor", renderer: "workflow.WorkflowPanel" },
        { id: "workflow:workflow-run-panel", tab: "workflows-run", renderer: "workflow.WorkflowPanel" },
      ],
      sidebar_items: [
        {
          id: "workflow:workflows-nav",
          path: "/workflows",
          label: "workflowPlugin.nav.label",
          icon: "Workflow",
          order: 30,
          permissions: ["workflow:read"],
        },
      ],
    },
  };
}

function workflowEventsPayload(runId = "run-browser") {
  return {
    run: {
      ...run,
      run_id: runId,
      events: [],
      interface: {
        ...run.interface,
        debug: {
          ...run.interface.debug,
          run_id: runId,
        },
      },
    },
    events: [
      {
        event_id: "evt-1",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 1,
        event_type: "run_started",
        node_id: null,
        node_type: null,
        payload: { mode: "sync" },
        created_at: nowIso,
      },
      {
        event_id: "evt-2",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 2,
        event_type: "node_started",
        node_id: "start",
        node_type: "start",
        payload: { input: { message: "LambChat" } },
        started_at: nowIso,
        created_at: nowIso,
      },
      {
        event_id: "evt-3",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 3,
        event_type: "node_succeeded",
        node_id: "start",
        node_type: "start",
        payload: { output: { message: "LambChat" } },
        started_at: nowIso,
        finished_at: nowIso,
        created_at: nowIso,
      },
      {
        event_id: "evt-4",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 4,
        event_type: "node_started",
        node_id: "answer",
        node_type: "answer",
        payload: { input: { message: "LambChat" } },
        started_at: nowIso,
        created_at: nowIso,
      },
      {
        event_id: "evt-5",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 5,
        event_type: "node_succeeded",
        node_id: "answer",
        node_type: "answer",
        payload: { output: run.output },
        started_at: nowIso,
        finished_at: nowIso,
        created_at: nowIso,
      },
      {
        event_id: "evt-6",
        run_id: runId,
        workflow_id: "wf-browser",
        version_id: "wfv-browser-2",
        sequence: 6,
        event_type: "run_succeeded",
        node_id: null,
        node_type: null,
        payload: { status: "succeeded" },
        created_at: nowIso,
      },
    ],
    skip: 0,
    limit: 200,
  };
}

function approvalWorkflowRun() {
  return approvalRunState === "resumed" ? resumedApprovalRun : pausedApprovalRun;
}

function approvalWorkflowEventsPayload() {
  const currentRun = approvalWorkflowRun();
  const events = [
    {
      event_id: "evt-approval-1",
      run_id: "run-approval-browser",
      workflow_id: "wf-browser",
      version_id: currentWorkflowVersion().version_id,
      sequence: 1,
      event_type: "run_started",
      node_id: null,
      node_type: null,
      payload: { mode: "async" },
      created_at: nowIso,
    },
    {
      event_id: "evt-approval-2",
      run_id: "run-approval-browser",
      workflow_id: "wf-browser",
      version_id: currentWorkflowVersion().version_id,
      sequence: 2,
      event_type: "human_approval_required",
      node_id: "approval",
      node_type: "human_approval",
      payload: pausedApprovalRun.pause.pending_approval,
      created_at: nowIso,
    },
  ];
  if (approvalRunState === "resumed") {
    events.push(
      {
        event_id: "evt-approval-3",
        run_id: "run-approval-browser",
        workflow_id: "wf-browser",
        version_id: currentWorkflowVersion().version_id,
        sequence: 3,
        event_type: "human_approval_resumed",
        node_id: "approval",
        node_type: "human_approval",
        payload: resumedApprovalRun.output,
        created_at: nowIso,
      },
      {
        event_id: "evt-approval-4",
        run_id: "run-approval-browser",
        workflow_id: "wf-browser",
        version_id: currentWorkflowVersion().version_id,
        sequence: 4,
        event_type: "run_succeeded",
        node_id: null,
        node_type: null,
        payload: { status: "succeeded" },
        created_at: nowIso,
      },
    );
  } else {
    events.push({
      event_id: "evt-approval-3",
      run_id: "run-approval-browser",
      workflow_id: "wf-browser",
      version_id: currentWorkflowVersion().version_id,
      sequence: 3,
      event_type: "run_paused",
      node_id: "approval",
      node_type: "human_approval",
      payload: pausedApprovalRun.pause,
      created_at: nowIso,
    });
  }
  return {
    run: { ...currentRun, version_id: currentWorkflowVersion().version_id, events: [] },
    events,
    skip: 0,
    limit: 200,
  };
}

function chatWorkflowRunEvent({ runId = "run-chat-browser", summaryPrefix = "Workflow saw" } = {}) {
  return {
    ...run,
    run_id: runId,
    output: {
      report: { summary: `${summaryPrefix}: ${lastChatMessage}` },
      items: [{ summary: "Chat stream first item" }],
    },
    interface: {
      ...run.interface,
      debug: {
        ...run.interface.debug,
        run_id: runId,
      },
    },
  };
}

function failedChatWorkflowRunEvent() {
  return {
    ...failedRunWithoutId,
    timestamp: nowIso,
  };
}

function scheduledWorkflowRunResult() {
  return {
    plugin_id: "workflow",
    workflow_id: "wf-browser",
    run_id: "run-scheduled-browser",
    version_id: "wfv-browser-2",
    status: "succeeded",
    output: {
      report: { summary: "Scheduled workflow contract summary" },
      items: [{ summary: "Scheduled workflow item" }],
    },
    error: null,
    io_contract: ioContract,
    interface: {
      ...run.interface,
      debug: {
        ...run.interface.debug,
        run_id: "run-scheduled-browser",
      },
    },
    output_contract: {
      ...run.output_contract,
      valid: true,
      missing_required: [],
      type_mismatches: [],
    },
  };
}

function scheduledApprovalWorkflowRunResult() {
  return {
    ...pausedApprovalRun,
    run_id: "run-approval-browser",
    version_id: "wfv-browser-2",
    interface: {
      ...pausedApprovalRun.interface,
      debug: {
        ...pausedApprovalRun.interface.debug,
        run_id: "run-approval-browser",
      },
    },
  };
}

function toolWorkflowRunResult() {
  return {
    ...scheduledWorkflowRunResult(),
    run_id: "run-tool-browser",
    output: {
      report: { summary: "Tool workflow contract summary" },
      items: [{ summary: "Tool workflow item" }],
    },
    interface: {
      ...run.interface,
      debug: {
        ...run.interface.debug,
        run_id: "run-tool-browser",
      },
    },
  };
}

function agentTeamWorkflowRunResult() {
  return {
    ...toolWorkflowRunResult(),
    run_id: "run-agent-team-browser",
    output: {
      report: { summary: "Agent Team workflow contract summary" },
      items: [{ summary: "Agent Team workflow item" }],
    },
    interface: {
      ...run.interface,
      debug: {
        ...run.interface.debug,
        run_id: "run-agent-team-browser",
      },
    },
  };
}

function chatSessionEvents() {
  return [
    {
      id: "chat-event-user",
      event_type: "user:message",
      run_id: chatRunId,
      timestamp: nowIso,
      data: {
        content: lastChatMessage,
        message_id: `${chatRunId}:user`,
        run_id: chatRunId,
      },
    },
    {
      id: "chat-event-workflow",
      event_type: "workflow:run",
      run_id: chatRunId,
      timestamp: nowIso,
      data: chatWorkflowRunEvent(),
    },
    {
      id: "chat-event-message",
      event_type: "message:chunk",
      run_id: chatRunId,
      timestamp: nowIso,
      data: {
        content: "Agent answer after workflow.",
      },
    },
    {
      id: "chat-event-done",
      event_type: "done",
      run_id: chatRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function chatReplayWorkflowToolEvents() {
  const workflowToolResult = toolWorkflowRunResult();
  return [
    {
      id: "replay-user-message",
      event_type: "user:message",
      run_id: chatReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay workflow tool input",
        message_id: `${chatReplayRunId}:user`,
        run_id: chatReplayRunId,
      },
    },
    {
      id: "replay-tool-start",
      event_type: "tool:start",
      run_id: chatReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-replay-workflow-browser",
        tool: "workflow_run",
        args: {
          workflow_id: "wf-browser",
          version_id: "wfv-browser-2",
          input: { message: "replay workflow input" },
        },
        timestamp: nowIso,
      },
    },
    {
      id: "replay-tool-result",
      event_type: "tool:result",
      run_id: chatReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-replay-workflow-browser",
        tool: "workflow_run",
        result: workflowToolResult,
        success: true,
        timestamp: nowIso,
      },
    },
    {
      id: "replay-message-chunk",
      event_type: "message:chunk",
      run_id: chatReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay answer after workflow tool.",
      },
    },
    {
      id: "replay-done",
      event_type: "done",
      run_id: chatReplayRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function chatReplayWorkflowApprovalToolEvents() {
  return [
    {
      id: "approval-replay-user-message",
      event_type: "user:message",
      run_id: chatApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay paused workflow approval tool input",
        message_id: `${chatApprovalReplayRunId}:user`,
        run_id: chatApprovalReplayRunId,
      },
    },
    {
      id: "approval-replay-tool-start",
      event_type: "tool:start",
      run_id: chatApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-approval-replay-workflow-browser",
        tool: "workflow_run",
        args: {
          workflow_id: "wf-browser",
          version_id: "wfv-browser-2",
          input: { message: "replay paused workflow input" },
          mode: "async",
        },
        timestamp: nowIso,
      },
    },
    {
      id: "approval-replay-tool-result",
      event_type: "tool:result",
      run_id: chatApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-approval-replay-workflow-browser",
        tool: "workflow_run",
        result: pausedApprovalRun,
        success: true,
        timestamp: nowIso,
      },
    },
    {
      id: "approval-replay-message-chunk",
      event_type: "message:chunk",
      run_id: chatApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay answer waits for workflow approval.",
      },
    },
    {
      id: "approval-replay-done",
      event_type: "done",
      run_id: chatApprovalReplayRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function failedChatReplayWorkflowToolEvents() {
  return [
    {
      id: "failed-replay-user-message",
      event_type: "user:message",
      run_id: failedChatReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay failed workflow tool input",
        message_id: `${failedChatReplayRunId}:user`,
        run_id: failedChatReplayRunId,
      },
    },
    {
      id: "failed-replay-tool-start",
      event_type: "tool:start",
      run_id: failedChatReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-failed-debug-replay-workflow-browser",
        tool: "workflow_get_run",
        args: {
          workflow_id: "wf-browser",
          run_id: "run-missing-debug-browser",
        },
        timestamp: nowIso,
      },
    },
    {
      id: "failed-replay-tool-result",
      event_type: "tool:result",
      run_id: failedChatReplayRunId,
      timestamp: nowIso,
      data: {
        tool_call_id: "tool-call-failed-debug-replay-workflow-browser",
        tool: "workflow_get_run",
        result: failedRunWithDebugId,
        success: false,
        timestamp: nowIso,
      },
    },
    {
      id: "failed-replay-message-chunk",
      event_type: "message:chunk",
      run_id: failedChatReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Replay answer after failed workflow debug tool.",
      },
    },
    {
      id: "failed-replay-done",
      event_type: "done",
      run_id: failedChatReplayRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function agentTeamWorkflowReplayEvents() {
  const workflowResult = agentTeamWorkflowRunResult();
  return [
    {
      id: "agent-team-replay-user",
      event_type: "user:message",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Agent Team replay workflow input",
        message_id: `${agentTeamReplayRunId}:user`,
        run_id: agentTeamReplayRunId,
      },
    },
    {
      id: "agent-team-replay-call",
      event_type: "agent:call",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {
        agent_id: agentTeamMemberId,
        agent_name: "Workflow Researcher",
        input: "Use the selected workflow result before synthesizing.",
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-replay-workflow",
      event_type: "workflow:run",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {
        ...workflowResult,
        agent_id: agentTeamMemberId,
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-replay-result",
      event_type: "agent:result",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {
        agent_id: agentTeamMemberId,
        result: "Workflow Researcher used the workflow output contract.",
        success: true,
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-replay-message",
      event_type: "message:chunk",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Agent Team synthesis after workflow.",
      },
    },
    {
      id: "agent-team-replay-done",
      event_type: "done",
      run_id: agentTeamReplayRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function agentTeamWorkflowApprovalReplayEvents() {
  return [
    {
      id: "agent-team-approval-replay-user",
      event_type: "user:message",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Agent Team replay paused workflow approval input",
        message_id: `${agentTeamApprovalReplayRunId}:user`,
        run_id: agentTeamApprovalReplayRunId,
      },
    },
    {
      id: "agent-team-approval-replay-call",
      event_type: "agent:call",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        agent_id: agentTeamMemberId,
        agent_name: "Workflow Researcher",
        input: "Run the selected workflow asynchronously and wait for approval.",
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-approval-replay-workflow",
      event_type: "workflow:run",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        ...pausedApprovalRun,
        agent_id: agentTeamMemberId,
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-approval-replay-result",
      event_type: "agent:result",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        agent_id: agentTeamMemberId,
        result: "Workflow Researcher is waiting for workflow approval.",
        success: true,
        depth: 1,
        timestamp: nowIso,
      },
    },
    {
      id: "agent-team-approval-replay-message",
      event_type: "message:chunk",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {
        content: "Agent Team synthesis waits for workflow approval.",
      },
    },
    {
      id: "agent-team-approval-replay-done",
      event_type: "done",
      run_id: agentTeamApprovalReplayRunId,
      timestamp: nowIso,
      data: {},
    },
  ];
}

function workflowChatSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Workflow chat event smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { processMessageEvent } from "/src/hooks/useAgent/eventProcessor.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowPayload = ${JSON.stringify(chatWorkflowRunEvent())};
      let processed = processMessageEvent(
        "workflow:run",
        workflowPayload,
        [],
        "",
        [],
        0,
        [],
        false,
        "browser-smoke-message",
      );
      processed = processMessageEvent(
        "message:chunk",
        { content: "Agent answer after workflow." },
        processed.parts,
        processed.content,
        processed.toolCalls,
        0,
        [],
        false,
        "browser-smoke-message",
      );

      function SmokeTranscript() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "workflow-chat-event",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "workflow:run -> message:chunk",
              ),
              processed.parts.map((part, index) =>
                React.createElement(MessagePartRenderer, {
                  key: index,
                  part,
                  messageId: "browser-smoke-message",
                  partIndex: index,
                  isStreaming: false,
                  isLast: index === processed.parts.length - 1,
                }),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeTranscript));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function failedWorkflowChatSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Failed workflow chat event smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { processMessageEvent } from "/src/hooks/useAgent/eventProcessor.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowPayload = ${JSON.stringify(failedChatWorkflowRunEvent())};
      let processed = processMessageEvent(
        "workflow:run",
        workflowPayload,
        [],
        "",
        [],
        0,
        [],
        false,
        "failed-browser-smoke-message",
      );
      processed = processMessageEvent(
        "message:chunk",
        { content: "Agent continued after failed workflow." },
        processed.parts,
        processed.content,
        processed.toolCalls,
        0,
        [],
        false,
        "failed-browser-smoke-message",
      );
      window.__failedWorkflowEventParts = processed.parts;

      function SmokeFailedWorkflowEvent() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "failed-workflow-chat-event",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "failed workflow:run -> message:chunk",
              ),
              processed.parts.map((part, index) =>
                React.createElement(MessagePartRenderer, {
                  key: index,
                  part,
                  messageId: "failed-browser-smoke-message",
                  partIndex: index,
                  isStreaming: false,
                  isLast: index === processed.parts.length - 1,
                }),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeFailedWorkflowEvent));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function workflowPickerInputSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Workflow picker input smoke</title>
    <script type="module">
      import React, { useEffect, useMemo, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { CHAT_INPUT_PANEL_RENDERERS } from "/src/components/chat/chatInputPanelRenderers.tsx";
      import { CHAT_INPUT_SELECTED_RENDERERS } from "/src/components/chat/chatInputSelectedRenderers.tsx";

      const contribution = {
        id: "workflow:workflow-picker",
        renderer: "workflow.WorkflowPickerModal",
        createPath: "/workflows?create=blank",
        managePath: "/workflows",
        optionBinding: {
          pluginId: "workflow",
          key: "SELECTED_WORKFLOW_ID",
          scope: "session",
        },
      };

      const option = {
        id: "workflow:select-workflow",
        panel: "workflow:workflow-picker",
        selectedRenderer: "workflow.SelectedWorkflowChip",
        optionBinding: contribution.optionBinding,
      };

      const initialOptions = {
        workflow: {
          SELECTED_WORKFLOW_ID: "wf-browser",
          SELECTED_WORKFLOW_VERSION_ID: "wfv-browser-2",
        },
      };

      function SmokePicker() {
        const [activePanel, setActivePanel] = useState("workflow:workflow-picker");
        const [pluginOptions, setPluginOptions] = useState(initialOptions);
        const [sendState, setSendState] = useState("idle");
        const Panel = CHAT_INPUT_PANEL_RENDERERS["workflow.WorkflowPickerModal"];
        const selectedEntry = CHAT_INPUT_SELECTED_RENDERERS["workflow.SelectedWorkflowChip"];
        const SelectedChip = selectedEntry.Component;
        const hasSelection = selectedEntry.hasSelection({
          option,
          activePanel,
          onActivePanelChange: setActivePanel,
          pluginOptionValues: pluginOptions,
          onPluginOptionChange: handlePluginOptionChange,
          fallbackLabel: "Workflow",
        });

        function handlePluginOptionChange(pluginId, key, value) {
          const nextValue = value === undefined ? null : value;
          window.__workflowPluginChanges = [
            ...(window.__workflowPluginChanges || []),
            { pluginId, key, value: nextValue },
          ];
          setPluginOptions((current) => ({
            ...current,
            [pluginId]: {
              ...(current[pluginId] || {}),
              [key]: nextValue,
            },
          }));
        }

        async function sendChatSmoke() {
          setSendState("sending");
          const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: "Browser explicit entry message",
              agent_id: "search",
              plugin_options: pluginOptions,
            }),
          });
          if (!response.ok) {
            setSendState("failed");
            return;
          }
          const payload = await response.json();
          window.__workflowChatSendResponse = payload;
          setSendState("sent");
        }

        useEffect(() => {
          window.__workflowPickerInputState = {
            activePanel,
            hasSelection,
            pluginOptions,
            sendState,
          };
        }, [activePanel, hasSelection, pluginOptions, sendState]);

        const serializedOptions = useMemo(
          () => JSON.stringify(pluginOptions, null, 2),
          [pluginOptions],
        );

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "workflow-picker-input",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "workflow picker input smoke",
              ),
              React.createElement(
                "div",
                { className: "flex min-h-10 flex-wrap items-center gap-2", "data-smoke": "selected-chip" },
                hasSelection
                  ? React.createElement(SelectedChip, {
                      option,
                      activePanel,
                      onActivePanelChange: setActivePanel,
                      pluginOptionValues: pluginOptions,
                      onPluginOptionChange: handlePluginOptionChange,
                      fallbackLabel: "Workflow",
                    })
                  : React.createElement("span", null, "No selected workflow"),
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "rounded-md border border-theme-border px-3 py-2 text-sm",
                  onClick: () => setActivePanel("workflow:workflow-picker"),
                },
                "Open workflow picker",
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "ml-2 rounded-md border border-theme-border px-3 py-2 text-sm",
                  onClick: sendChatSmoke,
                },
                "Send chat smoke",
              ),
              React.createElement(
                "pre",
                {
                  className: "max-h-64 overflow-auto rounded-md border border-theme-border bg-theme-bg-secondary p-3 text-xs",
                  "data-smoke": "plugin-options",
                },
                serializedOptions,
              ),
              React.createElement(
                "div",
                { "data-smoke": "send-state", className: "text-xs text-theme-text-secondary" },
                sendState,
              ),
            ),
          ),
          Panel({
            contribution,
            activePanel,
            onActivePanelChange: setActivePanel,
            pluginOptionValues: pluginOptions,
            onPluginOptionChange: handlePluginOptionChange,
            onNavigate: (path) => {
              window.__workflowNavigation = path;
            },
          }),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokePicker));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function workflowChatSelectedEntrySmokeHtml(options = {}) {
  const agentTeamMode = options.agentTeamMode === true;
  const initialOptions = {
    workflow: {
      SELECTED_WORKFLOW_ID: "wf-browser",
      SELECTED_WORKFLOW_VERSION_ID: "wfv-browser-2",
      SELECTED_WORKFLOW_INPUT_JSON: {
        topic: agentTeamMode ? "agent-team-selected-entry" : "browser-selected-entry",
        query: agentTeamMode ? "agent team explicit query" : "explicit chat query",
      },
    },
    ...(agentTeamMode ? { agent_team: { SELECTED_TEAM_ID: "team-browser" } } : {}),
  };
  const smokeLabel = agentTeamMode
    ? "workflow agent team selected entry smoke"
    : "workflow chat selected entry smoke";
  const chatAgentId = agentTeamMode ? "team" : "search";
  const chatMessage = agentTeamMode ? "Agent Team explicit entry message" : "Browser explicit entry message";
  const evidenceHook = agentTeamMode
    ? "__workflowAgentTeamSelectedEntryEvidence"
    : "__workflowChatSelectedEntryEvidence";
  const responseHook = agentTeamMode
    ? "__workflowAgentTeamSelectedEntryResponse"
    : "__workflowChatSelectedEntryResponse";
  const buttonTestId = agentTeamMode
    ? "codex-send-agent-team-selected-workflow-chat"
    : "codex-send-selected-workflow-chat";
  const dataSmoke = agentTeamMode
    ? "workflow-agent-team-selected-entry"
    : "workflow-chat-selected-entry";
  const buttonLabel = agentTeamMode
    ? "Send Agent Team selected workflow chat"
    : "Send selected workflow chat";
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Workflow chat selected entry smoke</title>
    <script type="module">
      import React, { useEffect, useMemo, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { processMessageEvent } from "/src/hooks/useAgent/eventProcessor.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";
      import { CHAT_INPUT_SELECTED_RENDERERS } from "/src/components/chat/chatInputSelectedRenderers.tsx";

      const option = {
        id: "workflow:select-workflow",
        selectedRenderer: "workflow.SelectedWorkflowChip",
        optionBinding: {
          pluginId: "workflow",
          key: "SELECTED_WORKFLOW_ID",
          scope: "session",
        },
      };

      const initialOptions = ${JSON.stringify(initialOptions)};
      const chatAgentId = ${JSON.stringify(chatAgentId)};
      const chatMessage = ${JSON.stringify(chatMessage)};
      const evidenceHook = ${JSON.stringify(evidenceHook)};
      const responseHook = ${JSON.stringify(responseHook)};
      const buttonTestId = ${JSON.stringify(buttonTestId)};

      function parseSseEvents(text) {
        return text
          .split(/\\n\\n+/)
          .map((block) => block.trim())
          .filter(Boolean)
          .map((block) => {
            const eventLine = block.split("\\n").find((line) => line.startsWith("event:"));
            const dataLines = block
              .split("\\n")
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trim());
            return {
              event: eventLine ? eventLine.slice(6).trim() : "message",
              data: dataLines.length ? JSON.parse(dataLines.join("\\n")) : {},
            };
          });
      }

      function processWorkflowEvents(events) {
        let processed = {
          parts: [],
          content: "",
          toolCalls: [],
        };
        const subagentStack = [];
        for (const event of events) {
          if (!["agent:call", "agent:result", "workflow:run", "message:chunk"].includes(event.event)) continue;
          const depth = Number(event.data?.depth || 0);
          if (event.event === "agent:call") {
            subagentStack.push({
              agent_id: event.data?.agent_id || "unknown",
              depth,
              message_id: "selected-workflow-browser-message",
            });
          }
          processed = processMessageEvent(
            event.event,
            event.data,
            processed.parts,
            processed.content,
            processed.toolCalls,
            depth,
            subagentStack,
            false,
            "selected-workflow-browser-message",
          );
          if (event.event === "agent:result") {
            const agentId = event.data?.agent_id || "unknown";
            const stackIndex = subagentStack.findIndex((item) => item.agent_id === agentId);
            if (stackIndex !== -1) subagentStack.splice(stackIndex, 1);
          }
        }
        return processed;
      }

      function SmokeSelectedWorkflowChat() {
        const [activePanel, setActivePanel] = useState(null);
        const [pluginOptions, setPluginOptions] = useState(initialOptions);
        const [sendState, setSendState] = useState("idle");
        const [streamEvents, setStreamEvents] = useState([]);
        const selectedEntry = CHAT_INPUT_SELECTED_RENDERERS["workflow.SelectedWorkflowChip"];
        const SelectedChip = selectedEntry.Component;
        const hasSelection = selectedEntry.hasSelection({
          option,
          activePanel,
          onActivePanelChange: setActivePanel,
          pluginOptionValues: pluginOptions,
          onPluginOptionChange: handlePluginOptionChange,
          fallbackLabel: "Workflow",
        });
        const processed = useMemo(() => processWorkflowEvents(streamEvents), [streamEvents]);

        function handlePluginOptionChange(pluginId, key, value) {
          const nextValue = value === undefined ? null : value;
          setPluginOptions((current) => ({
            ...current,
            [pluginId]: {
              ...(current[pluginId] || {}),
              [key]: nextValue,
            },
          }));
        }

        async function sendSelectedWorkflowChat() {
          setSendState("sending");
          const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: chatMessage,
              agent_id: chatAgentId,
              plugin_options: pluginOptions,
            }),
          });
          if (!response.ok) {
            setSendState("failed");
            return;
          }
          const payload = await response.json();
          const streamResponse = await fetch("/api/chat/sessions/" + payload.session_id + "/stream");
          const streamText = await streamResponse.text();
          const events = parseSseEvents(streamText);
          setStreamEvents(events);
          window[responseHook] = payload;
          setSendState("streamed");
        }

        useEffect(() => {
          const workflowPart =
            processed.parts.find((part) => part.type === "workflow") ||
            processed.parts
              .flatMap((part) => (Array.isArray(part.parts) ? part.parts : []))
              .find((part) => part.type === "workflow") ||
            null;
          const subagentPart = processed.parts.find((part) => part.type === "subagent") || null;
          window[evidenceHook] = {
            sendState,
            hasSelection,
            pluginOptions,
            streamEvents,
            subagentPart,
            workflowPart,
            bodyText: document.body.textContent || "",
          };
        }, [sendState, hasSelection, pluginOptions, streamEvents, processed.parts]);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": ${JSON.stringify(dataSmoke)},
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                ${JSON.stringify(smokeLabel)},
              ),
              React.createElement(
                "div",
                { className: "flex min-h-10 flex-wrap items-center gap-2", "data-smoke": "selected-chip" },
                hasSelection
                  ? React.createElement(SelectedChip, {
                      option,
                      activePanel,
                      onActivePanelChange: setActivePanel,
                      pluginOptionValues: pluginOptions,
                      onPluginOptionChange: handlePluginOptionChange,
                      fallbackLabel: "Workflow",
                    })
                  : React.createElement("span", null, "No selected workflow"),
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "rounded-md border border-theme-border px-3 py-2 text-sm",
                  "data-testid": buttonTestId,
                  onClick: sendSelectedWorkflowChat,
                },
                ${JSON.stringify(buttonLabel)},
              ),
              React.createElement(
                "div",
                { "data-smoke": "send-state", className: "text-xs text-theme-text-secondary" },
                sendState,
              ),
              processed.parts.map((part, index) =>
                React.createElement(MessagePartRenderer, {
                  key: index,
                  part,
                  messageId: "selected-workflow-browser-message",
                  partIndex: index,
                  isStreaming: false,
                  isLast: index === processed.parts.length - 1,
                }),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeSelectedWorkflowChat));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function scheduledWorkflowResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Scheduled workflow result smoke</title>
    <script type="module">
      import React, { useEffect } from "react";
      import { createRoot } from "react-dom/client";
      import { MemoryRouter, useLocation } from "react-router-dom";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { TaskSessionList } from "/src/components/panels/ScheduledTaskPanel/TaskSessionList.tsx";

      function LocationProbe() {
        const location = useLocation();
        useEffect(() => {
          window.__scheduledWorkflowSmokeLocation = location.pathname;
        }, [location.pathname]);
        return React.createElement(
          "div",
          {
            "data-smoke": "scheduled-location",
            className: "sr-only",
          },
          location.pathname,
        );
      }

      function SmokeScheduledWorkflowResult() {
        return React.createElement(
          MemoryRouter,
          { initialEntries: ["/scheduled-task-smoke"] },
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg text-theme-text",
              "data-smoke": "scheduled-workflow-result",
            },
            React.createElement(LocationProbe),
            React.createElement(TaskSessionList, {
              taskId: "task-workflow-browser",
              taskName: "Browser scheduled workflow",
              onBack: () => {
                window.__scheduledWorkflowBack = true;
              },
            }),
          ),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeScheduledWorkflowResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function scheduledWorkflowApprovalResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Scheduled workflow approval result smoke</title>
    <script type="module">
      import React, { useEffect } from "react";
      import { createRoot } from "react-dom/client";
      import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { TaskSessionList } from "/src/components/panels/ScheduledTaskPanel/TaskSessionList.tsx";
      import { WorkflowPanel } from "/src/plugins/workflow/WorkflowPanel.tsx";

      function LocationProbe() {
        const location = useLocation();
        useEffect(() => {
          window.__scheduledWorkflowApprovalSmokeLocation = location.pathname;
        }, [location.pathname]);
        return React.createElement(
          "div",
          {
            "data-smoke": "scheduled-approval-location",
            className: "sr-only",
          },
          location.pathname,
        );
      }

      function SmokeScheduledWorkflowApprovalResult() {
        return React.createElement(
          MemoryRouter,
          { initialEntries: ["/scheduled-task-approval-smoke"] },
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg text-theme-text",
              "data-smoke": "scheduled-workflow-approval-result",
            },
            React.createElement(LocationProbe),
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: "/scheduled-task-approval-smoke",
                element: React.createElement(TaskSessionList, {
                  taskId: "task-workflow-approval-browser",
                  taskName: "Browser scheduled approval workflow",
                  onBack: () => {
                    window.__scheduledWorkflowApprovalBack = true;
                  },
                }),
              }),
              React.createElement(Route, {
                path: "/workflows/:workflowId/runs/:runId",
                element: React.createElement(WorkflowPanel, { activeTab: "workflows-run" }),
              }),
            ),
          ),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeScheduledWorkflowApprovalResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function toolWorkflowResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Tool workflow result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { ToolResultContent } from "/src/components/chat/ChatMessage/items/McpBlockPreview.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowToolResult = ${JSON.stringify(toolWorkflowRunResult())};

      function SmokeToolWorkflowResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "tool-workflow-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "tool workflow result smoke",
              ),
              React.createElement(ToolResultContent, { result: workflowToolResult }),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeToolWorkflowResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function toolWorkflowApprovalResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Tool workflow approval result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { ToolResultContent } from "/src/components/chat/ChatMessage/items/McpBlockPreview.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowToolResult = ${JSON.stringify(pausedApprovalRun)};

      function SmokeToolWorkflowApprovalResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "tool-workflow-approval-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "tool workflow approval result smoke",
              ),
              React.createElement(ToolResultContent, { result: workflowToolResult }),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeToolWorkflowApprovalResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function failedToolWorkflowResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Failed tool workflow result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { ToolResultContent } from "/src/components/chat/ChatMessage/items/McpBlockPreview.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowToolResult = ${JSON.stringify(failedRunWithoutId)};

      function SmokeFailedToolWorkflowResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "failed-tool-workflow-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "failed tool workflow result smoke",
              ),
              React.createElement(ToolResultContent, { result: workflowToolResult }),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeFailedToolWorkflowResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function failedToolWorkflowDebugResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Failed tool workflow debug result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { ToolResultContent } from "/src/components/chat/ChatMessage/items/McpBlockPreview.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const workflowToolResult = ${JSON.stringify(failedRunWithDebugId)};

      function SmokeFailedToolWorkflowDebugResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "failed-tool-workflow-debug-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "failed tool workflow debug result smoke",
              ),
              React.createElement(ToolResultContent, { result: workflowToolResult }),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeFailedToolWorkflowDebugResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function messageToolWorkflowResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Message tool workflow result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const toolPart = {
        type: "tool",
        id: "tool-call-workflow-browser",
        name: "workflow_run",
        args: {
          workflow_id: "wf-browser",
          version_id: "wfv-browser-2",
          input: { message: "tool-call transcript input" },
        },
        result: ${JSON.stringify(toolWorkflowRunResult())},
        success: true,
        startedAt: "${nowIso}",
        completedAt: "${nowIso}",
      };

      function SmokeMessageToolWorkflowResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "message-tool-workflow-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "message tool workflow result smoke",
              ),
              React.createElement(MessagePartRenderer, {
                part: toolPart,
                messageId: "message-tool-workflow-browser",
                partIndex: 0,
                isStreaming: false,
                isLast: true,
              }),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeMessageToolWorkflowResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function eventProcessedToolWorkflowResultSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Event processed tool workflow result smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { processMessageEvent } from "/src/hooks/useAgent/eventProcessor.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      const toolResult = ${JSON.stringify(toolWorkflowRunResult())};
      const start = processMessageEvent(
        "tool:start",
        {
          tool_call_id: "tool-call-event-workflow-browser",
          tool: "workflow_run",
          args: {
            workflow_id: "wf-browser",
            version_id: "wfv-browser-2",
            input: { message: "event processed workflow input" },
          },
          timestamp: "${nowIso}",
        },
        [],
        "",
        [],
        0,
        [],
        true,
        "event-workflow-message",
      );
      const finished = processMessageEvent(
        "tool:result",
        {
          tool_call_id: "tool-call-event-workflow-browser",
          tool: "workflow_run",
          result: toolResult,
          success: true,
          timestamp: "${nowIso}",
        },
        start.parts,
        start.content,
        start.toolCalls,
        0,
        [],
        false,
        "event-workflow-message",
      );
      window.__eventProcessedWorkflowParts = finished.parts;

      function SmokeEventProcessedToolWorkflowResult() {
        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "event-processed-tool-workflow-result",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-3" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "event processed tool workflow result smoke",
              ),
              finished.parts.map((part, index) =>
                React.createElement(MessagePartRenderer, {
                  key: index,
                  part,
                  messageId: "event-workflow-message",
                  partIndex: index,
                  isStreaming: false,
                  isLast: index === finished.parts.length - 1,
                }),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeEventProcessedToolWorkflowResult));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function chatSessionReplayWorkflowToolSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Chat session replay workflow tool smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function SmokeChatSessionReplayWorkflowTool() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${chatReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__chatReplayWorkflowMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "chat-session-replay-workflow-tool",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "chat session replay workflow tool smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading" }, "Loading replay")
                : null,
              messages.map((message) =>
                React.createElement(
                  "section",
                  {
                    key: message.id,
                    className: "space-y-2 rounded-lg border border-theme-border bg-theme-bg-card p-4",
                    "data-smoke-role": message.role,
                  },
                  React.createElement(
                    "div",
                    { className: "text-xs font-semibold uppercase text-theme-text-tertiary" },
                    message.role,
                  ),
                  message.content
                    ? React.createElement(
                        "p",
                        { className: "text-sm text-theme-text-secondary" },
                        message.content,
                      )
                    : null,
                  (message.parts || []).map((part, index) =>
                    React.createElement(MessagePartRenderer, {
                      key: index,
                      part,
                      messageId: message.id,
                      partIndex: index,
                      isStreaming: false,
                      isLast: index === (message.parts || []).length - 1,
                    }),
                  ),
                ),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeChatSessionReplayWorkflowTool));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function chatSessionReplayWorkflowApprovalToolSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Chat session replay workflow approval tool smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function SmokeChatSessionReplayWorkflowApprovalTool() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${chatApprovalReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__chatReplayWorkflowApprovalMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "chat-session-replay-workflow-approval-tool",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "chat session replay workflow approval tool smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading" }, "Loading replay")
                : null,
              messages.map((message) =>
                React.createElement(
                  "section",
                  {
                    key: message.id,
                    className: "space-y-2 rounded-lg border border-theme-border bg-theme-bg-card p-4",
                    "data-smoke-role": message.role,
                  },
                  React.createElement(
                    "div",
                    { className: "text-xs font-semibold uppercase text-theme-text-tertiary" },
                    message.role,
                  ),
                  message.content
                    ? React.createElement(
                        "p",
                        { className: "text-sm text-theme-text-secondary" },
                        message.content,
                      )
                    : null,
                  (message.parts || []).map((part, index) =>
                    React.createElement(MessagePartRenderer, {
                      key: index,
                      part,
                      messageId: message.id,
                      partIndex: index,
                      isStreaming: false,
                      isLast: index === (message.parts || []).length - 1,
                    }),
                  ),
                ),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeChatSessionReplayWorkflowApprovalTool));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function failedChatSessionReplayWorkflowToolSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Failed chat session replay workflow tool smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function SmokeFailedChatSessionReplayWorkflowTool() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${failedChatReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__failedChatReplayWorkflowMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "failed-chat-session-replay-workflow-tool",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "failed chat session replay workflow tool smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading" }, "Loading replay")
                : null,
              messages.map((message) =>
                React.createElement(
                  "section",
                  {
                    key: message.id,
                    className: "space-y-2 rounded-lg border border-theme-border bg-theme-bg-card p-4",
                    "data-smoke-role": message.role,
                  },
                  React.createElement(
                    "div",
                    { className: "text-xs font-semibold uppercase text-theme-text-tertiary" },
                    message.role,
                  ),
                  message.content
                    ? React.createElement(
                        "p",
                        { className: "text-sm text-theme-text-secondary" },
                        message.content,
                      )
                    : null,
                  (message.parts || []).map((part, index) =>
                    React.createElement(MessagePartRenderer, {
                      key: index,
                      part,
                      messageId: message.id,
                      partIndex: index,
                      isStreaming: false,
                      isLast: index === (message.parts || []).length - 1,
                    }),
                  ),
                ),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeFailedChatSessionReplayWorkflowTool));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function agentTeamReplayWorkflowSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Agent Team replay workflow smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function SmokeAgentTeamReplayWorkflow() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${agentTeamReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__agentTeamReplayWorkflowMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "agent-team-replay-workflow",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "agent team replay workflow smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading" }, "Loading replay")
                : null,
              messages.map((message) =>
                React.createElement(
                  "section",
                  {
                    key: message.id,
                    className: "space-y-2 rounded-lg border border-theme-border bg-theme-bg-card p-4",
                    "data-smoke-role": message.role,
                  },
                  React.createElement(
                    "div",
                    { className: "text-xs font-semibold uppercase text-theme-text-tertiary" },
                    message.role,
                  ),
                  message.content
                    ? React.createElement(
                        "p",
                        { className: "text-sm text-theme-text-secondary" },
                        message.content,
                      )
                    : null,
                  (message.parts || []).map((part, index) =>
                    React.createElement(MessagePartRenderer, {
                      key: index,
                      part,
                      messageId: message.id,
                      partIndex: index,
                      isStreaming: false,
                      isLast: index === (message.parts || []).length - 1,
                    }),
                  ),
                ),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeAgentTeamReplayWorkflow));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function agentTeamReplayWorkflowApprovalSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Agent Team replay workflow approval smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { MessagePartRenderer } from "/src/components/chat/ChatMessage/MessagePartRenderer.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function SmokeAgentTeamReplayWorkflowApproval() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${agentTeamApprovalReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__agentTeamReplayWorkflowApprovalMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg px-6 py-8 text-theme-text",
              "data-smoke": "agent-team-replay-workflow-approval",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-3xl space-y-4" },
              React.createElement(
                "div",
                { className: "text-xs font-medium uppercase text-theme-text-tertiary" },
                "agent team replay workflow approval smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading" }, "Loading replay")
                : null,
              messages.map((message) =>
                React.createElement(
                  "section",
                  {
                    key: message.id,
                    className: "space-y-2 rounded-lg border border-theme-border bg-theme-bg-card p-4",
                    "data-smoke-role": message.role,
                  },
                  React.createElement(
                    "div",
                    { className: "text-xs font-semibold uppercase text-theme-text-tertiary" },
                    message.role,
                  ),
                  message.content
                    ? React.createElement(
                        "p",
                        { className: "text-sm text-theme-text-secondary" },
                        message.content,
                      )
                    : null,
                  (message.parts || []).map((part, index) =>
                    React.createElement(MessagePartRenderer, {
                      key: index,
                      part,
                      messageId: message.id,
                      partIndex: index,
                      isStreaming: false,
                      isLast: index === (message.parts || []).length - 1,
                    }),
                  ),
                ),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeAgentTeamReplayWorkflowApproval));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function chatMessageAgentTeamReplayWorkflowSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ChatMessage Agent Team workflow replay smoke</title>
    <script type="module">
      import React, { useEffect, useState } from "react";
      import { createRoot } from "react-dom/client";
      import { MemoryRouter } from "react-router-dom";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import "/src/styles/chat.css";
      import { AuthProvider } from "/src/hooks/useAuth.tsx";
      import { SettingsProvider } from "/src/contexts/SettingsContext.tsx";
      import { reconstructMessagesFromEvents } from "/src/hooks/useAgent/historyLoader.ts";
      import { ChatMessage } from "/src/components/chat/ChatMessage/index.tsx";
      import { PersistentToolPanelHost } from "/src/components/chat/ChatMessage/items/persistentToolPanelState.tsx";

      function ChatMessageReplayBody() {
        const [messages, setMessages] = useState([]);
        const [error, setError] = useState("");

        useEffect(() => {
          let cancelled = false;
          async function load() {
            try {
              const response = await fetch("/api/sessions/${agentTeamReplaySessionId}/events");
              const payload = await response.json();
              const reconstructed = reconstructMessagesFromEvents(
                payload.events || [],
                new Set(),
                { activeSubagentStack: [] },
              );
              if (!cancelled) {
                window.__chatMessageAgentTeamWorkflowMessages = reconstructed;
                setMessages(reconstructed);
              }
            } catch (err) {
              if (!cancelled) setError(err?.message || String(err));
            }
          }
          load();
          return () => {
            cancelled = true;
          };
        }, []);

        return React.createElement(
          React.Fragment,
          null,
          React.createElement(
            "main",
            {
              className: "min-h-screen bg-theme-bg py-8 text-theme-text",
              "data-smoke": "chat-message-agent-team-replay-workflow",
            },
            React.createElement(
              "div",
              { className: "mx-auto max-w-4xl space-y-4" },
              React.createElement(
                "div",
                { className: "px-6 text-xs font-medium uppercase text-theme-text-tertiary" },
                "chatmessage agent team workflow replay smoke",
              ),
              error
                ? React.createElement("pre", { "data-smoke": "replay-error" }, error)
                : null,
              messages.length === 0 && !error
                ? React.createElement("div", { "data-smoke": "replay-loading", className: "px-6" }, "Loading replay")
                : null,
              messages.map((message, index) =>
                React.createElement(ChatMessage, {
                  key: message.id,
                  message,
                  sessionId: "${agentTeamReplaySessionId}",
                  runId: message.runId || "${agentTeamReplayRunId}",
                  isLastMessage: index === messages.length - 1,
                  isFirst: index === 0,
                  personaName: "Workflow Assistant",
                  showFeedbackAndShareActions: false,
                }),
              ),
            ),
          ),
          React.createElement(PersistentToolPanelHost),
        );
      }

      function SmokeChatMessageAgentTeamReplayWorkflow() {
        return React.createElement(
          MemoryRouter,
          null,
          React.createElement(
            AuthProvider,
            null,
            React.createElement(
              SettingsProvider,
              null,
              React.createElement(ChatMessageReplayBody),
            ),
          ),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeChatMessageAgentTeamReplayWorkflow));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function workflowEditorInteractionSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Workflow editor interaction smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import { MemoryRouter, Route, Routes } from "react-router-dom";
      import { Toaster } from "react-hot-toast";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import "/src/styles/components.css";
      import { WorkflowPanel } from "/src/plugins/workflow/WorkflowPanel.tsx";

      const tokenPayload = btoa(JSON.stringify({ exp: 1893456000, sub: "browser-user" })).replace(/=/g, "");
      const token = "codex." + tokenPayload + ".signature";
      localStorage.setItem("access_token", token);
      localStorage.setItem("refresh_token", token);

      const WORKFLOW_CANVAS_DRAG_TYPE = "application/x-lambchat-workflow-node";

      function createWorkflowDropEvent(type, dataTransfer, clientX, clientY) {
        if (typeof DragEvent === "function") {
          return new DragEvent(type, {
            bubbles: true,
            cancelable: true,
            clientX,
            clientY,
            dataTransfer,
          });
        }
        const event = new Event(type, { bubbles: true, cancelable: true });
        Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
        Object.defineProperty(event, "clientX", { value: clientX });
        Object.defineProperty(event, "clientY", { value: clientY });
        return event;
      }

      window.__codexDropWorkflowNode = (nodeType = "answer", presetId) => {
        const canvas = document.querySelector('[data-testid="workflow-canvas"]');
        if (!canvas) throw new Error("workflow canvas not found");
        const rect = canvas.getBoundingClientRect();
        const clientX = rect.x + rect.width * 0.55;
        const clientY = rect.y + rect.height * 0.55;
        const payload = JSON.stringify({ nodeType, presetId });
        const dataTransfer = typeof DataTransfer === "function"
          ? new DataTransfer()
          : {
              types: [WORKFLOW_CANVAS_DRAG_TYPE],
              dropEffect: "none",
              effectAllowed: "copy",
              getData: (type) => (type === WORKFLOW_CANVAS_DRAG_TYPE ? payload : ""),
              setData: () => undefined,
            };
        dataTransfer.setData(WORKFLOW_CANVAS_DRAG_TYPE, payload);
        dataTransfer.effectAllowed = "copy";
        canvas.dispatchEvent(createWorkflowDropEvent("dragover", dataTransfer, clientX, clientY));
        canvas.dispatchEvent(createWorkflowDropEvent("drop", dataTransfer, clientX, clientY));
        return { nodeType, presetId: presetId ?? null, clientX, clientY };
      };

      window.__codexConnectWorkflowNodes = async (sourceNodeId = "start", targetNodeId = "node_5") => {
        const sourceCard = document.querySelector('[data-testid="workflow-node-card-' + sourceNodeId + '"]');
        if (!sourceCard) throw new Error("source node card not found: " + sourceNodeId);
        sourceCard.click();
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const targetSelect = document.querySelector('[data-testid="workflow-add-edge-target-' + sourceNodeId + '"]');
        if (!(targetSelect instanceof HTMLSelectElement)) {
          throw new Error("edge target select not found: " + sourceNodeId);
        }
        if (!Array.from(targetSelect.options).some((option) => option.value === targetNodeId)) {
          throw new Error("edge target option not found: " + targetNodeId);
        }
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
        if (!setter) throw new Error("native select value setter missing");
        setter.call(targetSelect, targetNodeId);
        targetSelect.dispatchEvent(new Event("change", { bubbles: true }));
        return { sourceNodeId, targetNodeId };
      };

      window.__codexWorkflowEditorEvidence = () => {
        const nodeCards = Array.from(document.querySelectorAll('[data-testid^="workflow-node-card-"]'))
          .map((node) => node.getAttribute("data-testid"));
        const edgeCards = Array.from(document.querySelectorAll('[data-testid^="workflow-edge-card-"]'))
          .map((edge) => ({
            testId: edge.getAttribute("data-testid"),
            text: edge.textContent || "",
          }));
        return {
          path: location.pathname,
          nodeCards,
          edgeCards,
          hasDroppedNode: nodeCards.includes("workflow-node-card-node_5"),
          hasStartToDroppedNodeEdge: edgeCards.some((edge) => edge.text.includes("start") && edge.text.includes("node_5")),
        };
      };

      function SmokeWorkflowEditorInteraction() {
        return React.createElement(
          MemoryRouter,
          { initialEntries: ["/workflows/wf-browser/editor"] },
          React.createElement(
            React.Fragment,
            null,
            React.createElement(
              "main",
              {
                className: "min-h-screen bg-[var(--theme-bg)] text-[var(--theme-text)]",
                "data-smoke": "workflow-editor-interaction",
              },
              React.createElement(
                Routes,
                null,
                React.createElement(Route, {
                  path: "/workflows/:workflowId/editor",
                  element: React.createElement(WorkflowPanel, { activeTab: "workflows-editor" }),
                }),
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  "data-testid": "codex-drop-answer-on-workflow-canvas",
                  className: "fixed bottom-2 right-2 z-50 rounded bg-black px-2 py-1 text-xs text-white",
                  onClick: () => {
                    window.__codexDropWorkflowNode("answer");
                  },
                },
                "Drop answer on canvas",
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  "data-testid": "codex-drop-human-approval-on-workflow-canvas",
                  className: "fixed bottom-10 right-2 z-50 rounded bg-black px-2 py-1 text-xs text-white",
                  onClick: () => {
                    window.__codexDropWorkflowNode("human_approval");
                  },
                },
                "Drop human approval on canvas",
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  "data-testid": "codex-connect-start-to-dropped-node",
                  className: "fixed bottom-[4.5rem] right-2 z-50 rounded bg-black px-2 py-1 text-xs text-white",
                  onClick: () => {
                    window.__codexConnectWorkflowNodes("start", "node_5");
                  },
                },
                "Connect start to dropped node",
              ),
            ),
            React.createElement(Toaster),
          ),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeWorkflowEditorInteraction));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

function disabledWorkflowContributionsSmokeHtml() {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Disabled workflow contribution smoke</title>
    <script type="module">
      import React from "react";
      import { createRoot } from "react-dom/client";
      import "/src/i18n";
      import "/src/styles/tailwind.css";
      import "/src/styles/tokens.css";
      import "/src/styles/base.css";
      import {
        buildAppRouteContributions,
        buildChatInputOptionContributions,
        buildChatInputPanelContributions,
        buildPanelContributions,
        buildSidebarMoreNavContributions,
      } from "/src/extensions/coreContributions.ts";

      function agentTeamPlugin() {
        return {
          plugin_id: "agent_team",
          enabled: true,
          executable: true,
          status: "enabled",
          frontend: {
            app_tabs: [
              {
                id: "agent_team:team-tab",
                tab: "agent-team",
                path: "/agent-team",
                panel: "agent_team:team-panel",
                order: 600,
                permissions: ["team:read"],
              },
            ],
            app_panels: [
              { id: "agent_team:team-panel", tab: "agent-team", renderer: "agent_team.TeamBuilderPanel" },
            ],
            sidebar_items: [
              {
                id: "agent_team:team-nav",
                path: "/agent-team",
                label: "agentTeam.nav.label",
                icon: "Users",
                order: 20,
                permissions: ["team:read"],
              },
            ],
          },
        };
      }

      function workflowPluginPlugin(enabled) {
        return {
          plugin_id: "workflow",
          enabled,
          executable: enabled,
          status: enabled ? "enabled" : "disabled",
          frontend: {
            app_tabs: [
              {
                id: "workflow:workflows-tab",
                tab: "workflows",
                path: "/workflows",
                panel: "workflow:workflows-panel",
                insert_after: "agent-team",
                order: 700,
                permissions: ["workflow:read"],
              },
              {
                id: "workflow:workflow-editor-tab",
                tab: "workflows-editor",
                path: "/workflows/:workflowId/editor",
                panel: "workflow:workflow-editor-panel",
                insert_after: "workflows",
                order: 701,
                permissions: ["workflow:read"],
              },
              {
                id: "workflow:workflow-run-tab",
                tab: "workflows-run",
                path: "/workflows/:workflowId/runs/:runId",
                panel: "workflow:workflow-run-panel",
                insert_after: "workflows-editor",
                order: 702,
                permissions: ["workflow:read"],
              },
            ],
            app_panels: [
              { id: "workflow:workflows-panel", tab: "workflows", renderer: "workflow.WorkflowPanel" },
              { id: "workflow:workflow-editor-panel", tab: "workflows-editor", renderer: "workflow.WorkflowPanel" },
              { id: "workflow:workflow-run-panel", tab: "workflows-run", renderer: "workflow.WorkflowPanel" },
            ],
            sidebar_items: [
              {
                id: "workflow:workflows-nav",
                path: "/workflows",
                label: "workflowPlugin.nav.label",
                icon: "Workflow",
                order: 30,
                permissions: ["workflow:read"],
              },
            ],
            chat_input_options: [
              {
                id: "workflow:select-workflow",
                slot: "enhance",
                label: "workflowPlugin.chat.selectWorkflow",
                icon: "Workflow",
                panel: "workflow:workflow-picker",
                selected_renderer: "workflow.SelectedWorkflowChip",
                shortcut: "mod+w",
                order: 30,
                option_binding: {
                  plugin_id: "workflow",
                  key: "SELECTED_WORKFLOW_ID",
                  scope: "session",
                },
              },
            ],
            chat_input_panels: [
              {
                id: "workflow:workflow-picker",
                renderer: "workflow.WorkflowPickerModal",
                create_path: "/workflows?create=blank",
                manage_path: "/workflows",
                option_binding: {
                  plugin_id: "workflow",
                  key: "SELECTED_WORKFLOW_ID",
                  scope: "session",
                },
              },
            ],
          },
        };
      }

      function contributionEvidence(runtimePlugins) {
        return {
          routes: buildAppRouteContributions(runtimePlugins)
            .filter((route) => route.pluginId === "workflow" || route.pluginId === "agent_team")
            .map((route) => route.path),
          panels: buildPanelContributions(runtimePlugins)
            .filter((panel) => panel.pluginId === "workflow" || panel.pluginId === "agent_team")
            .map((panel) => panel.renderer || panel.id),
          nav: buildSidebarMoreNavContributions(runtimePlugins)
            .filter((item) => item.pluginId === "workflow" || item.pluginId === "agent_team")
            .map((item) => item.path),
          chatOptions: buildChatInputOptionContributions(runtimePlugins, { agentId: "default" })
            .filter((option) => option.pluginId === "workflow")
            .map((option) => option.id + ":" + option.optionBinding?.pluginId + "." + option.optionBinding?.key),
          chatPanels: buildChatInputPanelContributions(runtimePlugins, { agentId: "default" })
            .filter((panel) => panel.pluginId === "workflow")
            .map((panel) => panel.id + ":" + panel.renderer + ":" + panel.managePath),
        };
      }

      const enabledRuntimePlugins = [agentTeamPlugin(), workflowPluginPlugin(true)];
      const disabledRuntimePlugins = [agentTeamPlugin(), workflowPluginPlugin(false)];
      const evidence = {
        enabled: contributionEvidence(enabledRuntimePlugins),
        disabled: contributionEvidence(disabledRuntimePlugins),
      };
      window.__codexDisabledWorkflowContributionEvidence = () => evidence;

      function SmokeDisabledWorkflowContributions() {
        return React.createElement(
          "main",
          {
            className: "min-h-screen bg-[var(--theme-bg)] p-6 text-[var(--theme-text)]",
            "data-smoke": "disabled-workflow-contributions",
          },
          React.createElement("h1", { className: "text-base font-semibold" }, "workflow disabled contribution smoke"),
          React.createElement("h2", { className: "mt-4 text-sm font-medium" }, "Enabled Workflow"),
          React.createElement("pre", { "data-testid": "enabled-workflow-contributions" }, JSON.stringify(evidence.enabled, null, 2)),
          React.createElement("h2", { className: "mt-4 text-sm font-medium" }, "Disabled Workflow"),
          React.createElement("pre", { "data-testid": "disabled-workflow-contributions" }, JSON.stringify(evidence.disabled, null, 2)),
        );
      }

      createRoot(document.getElementById("root")).render(React.createElement(SmokeDisabledWorkflowContributions));
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;
}

export function createWorkflowMockApiPlugin(options = {}) {
  const includeWorkflowPluginContribution = options.includeWorkflowPluginContribution !== false;
  return {
    name: "codex-workflow-browser-mock",
    transformIndexHtml(html) {
      return html.replace(
        '<div id="root"></div>',
        `<div id="codex-browser-errors" style="position:fixed;z-index:999999;left:8px;right:8px;bottom:8px;max-height:40vh;overflow:auto;background:#fff7ed;color:#7c2d12;border:1px solid #fed7aa;padding:8px;font:12px/1.4 monospace;display:none"></div><script>
window.__codexBrowserErrors = [];
function __codexBrowserReportError(message) {
  window.__codexBrowserErrors.push(String(message));
  const box = document.getElementById("codex-browser-errors");
  if (box) {
    box.style.display = "block";
    box.textContent = window.__codexBrowserErrors.join("\\n");
  }
}
const __codexOriginalConsoleError = console.error.bind(console);
console.error = (...args) => {
  __codexOriginalConsoleError(...args);
  if (String(args[0] || "").includes("[ErrorBoundary]")) {
    __codexBrowserReportError(args.map((arg) => {
      if (arg?.stack) return arg.stack;
      try { return typeof arg === "string" ? arg : JSON.stringify(arg); }
      catch { return String(arg); }
    }).join("\\n"));
  }
};
window.addEventListener("error", (event) => __codexBrowserReportError([
  event.message || "window error",
  event.filename ? event.filename + ":" + event.lineno + ":" + event.colno : "",
  event.error?.stack || "",
].filter(Boolean).join("\\n")));
window.addEventListener("unhandledrejection", (event) => __codexBrowserReportError(event.reason?.stack || event.reason?.message || event.reason || "unhandled rejection"));
</script><div id="root"></div>`,
      );
    },
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url || "/", "http://127.0.0.1:3001");
        const path = url.pathname;
        requestLog.push({
          method: req.method || "GET",
          path,
          query: url.search,
          at: new Date().toISOString(),
        });
        if (requestLog.length > 1000) {
          requestLog.splice(0, requestLog.length - 1000);
        }
        if (path === "/auth/seed") {
          const token = url.searchParams.get("token") || "";
          const redirect = url.searchParams.get("redirect") || "/workflows";
          htmlReply(
            res,
            `<!doctype html><meta charset="utf-8"><script>
localStorage.setItem("access_token", ${JSON.stringify(token)});
localStorage.setItem("refresh_token", ${JSON.stringify(token)});
sessionStorage.setItem("redirect_after_login", ${JSON.stringify(redirect)});
location.replace(${JSON.stringify(redirect)});
</script>`,
          );
          return;
        }

        if (path === "/codex/workflow-chat-event-smoke") {
          const html = await server.transformIndexHtml(path, workflowChatSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/failed-workflow-chat-event-smoke") {
          const html = await server.transformIndexHtml(path, failedWorkflowChatSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/workflow-picker-input-smoke") {
          const html = await server.transformIndexHtml(path, workflowPickerInputSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/workflow-chat-selected-entry-smoke") {
          const html = await server.transformIndexHtml(path, workflowChatSelectedEntrySmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/workflow-agent-team-selected-entry-smoke") {
          const html = await server.transformIndexHtml(
            path,
            workflowChatSelectedEntrySmokeHtml({ agentTeamMode: true }),
          );
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/scheduled-workflow-result-smoke") {
          const html = await server.transformIndexHtml(path, scheduledWorkflowResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/scheduled-workflow-approval-result-smoke") {
          const html = await server.transformIndexHtml(path, scheduledWorkflowApprovalResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/tool-workflow-result-smoke") {
          const html = await server.transformIndexHtml(path, toolWorkflowResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/tool-workflow-approval-result-smoke") {
          const html = await server.transformIndexHtml(path, toolWorkflowApprovalResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/message-tool-workflow-result-smoke") {
          const html = await server.transformIndexHtml(path, messageToolWorkflowResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/failed-tool-workflow-result-smoke") {
          const html = await server.transformIndexHtml(path, failedToolWorkflowResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/failed-tool-workflow-debug-result-smoke") {
          const html = await server.transformIndexHtml(path, failedToolWorkflowDebugResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/event-processed-tool-workflow-result-smoke") {
          const html = await server.transformIndexHtml(path, eventProcessedToolWorkflowResultSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/chat-session-replay-workflow-tool-smoke") {
          const html = await server.transformIndexHtml(path, chatSessionReplayWorkflowToolSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/chat-session-replay-workflow-approval-tool-smoke") {
          const html = await server.transformIndexHtml(path, chatSessionReplayWorkflowApprovalToolSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/failed-chat-session-replay-workflow-tool-smoke") {
          const html = await server.transformIndexHtml(path, failedChatSessionReplayWorkflowToolSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/agent-team-replay-workflow-smoke") {
          const html = await server.transformIndexHtml(path, agentTeamReplayWorkflowSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/agent-team-replay-workflow-approval-smoke") {
          const html = await server.transformIndexHtml(path, agentTeamReplayWorkflowApprovalSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/chat-message-agent-team-replay-workflow-smoke") {
          const html = await server.transformIndexHtml(path, chatMessageAgentTeamReplayWorkflowSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/workflow-editor-interaction-smoke") {
          const html = await server.transformIndexHtml(path, workflowEditorInteractionSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/disabled-workflow-contributions-smoke") {
          const html = await server.transformIndexHtml(path, disabledWorkflowContributionsSmokeHtml());
          htmlReply(res, html);
          return;
        }

        if (path === "/codex/seed-auth") {
          const target = url.searchParams.get("to") || "/workflows";
          htmlReply(res, `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Seed auth</title>
    <script>
      const tokenPayload = btoa(JSON.stringify({ exp: 1893456000, sub: "browser-user" })).replace(/=/g, "");
      const token = "codex." + tokenPayload + ".signature";
      localStorage.setItem("access_token", token);
      localStorage.setItem("refresh_token", token);
      location.replace(${JSON.stringify(target)});
    </script>
  </head>
  <body>Seeding auth...</body>
</html>`);
          return;
        }

        if (!path.startsWith("/api/")) {
          next();
          return;
        }

        if (path === "/api/codex/request-log") {
          jsonReply(res, {
            requests: requestLog,
            last_chat_stream_body: lastChatStreamBody,
            last_workflow_version_body: lastWorkflowVersionBody,
            last_workflow_run_body: lastWorkflowRunBody,
            last_workflow_resume_body: lastWorkflowResumeBody,
            saved_workflow_version_id: savedWorkflowVersion?.version_id ?? null,
            published_workflow_version_id: publishedWorkflowVersionId,
            approval_run_state: approvalRunState,
          });
          return;
        }

        if (path === "/api/auth/me") {
          jsonReply(res, {
            id: "user-1",
            username: "Browser Tester",
            email: "browser@example.test",
            roles: ["user"],
            permissions: [
              "workflow:read",
              "workflow:write",
              "workflow:run",
              "workflow:credential:manage",
              "chat:read",
              "chat:write",
              "marketplace:read",
              "scheduled_task:read",
              "channel:read",
              "skill:read",
            ],
            metadata: {},
          });
          return;
        }

        if (path === "/api/auth/profile") {
          jsonReply(res, {
            id: "user-1",
            username: "Browser Tester",
            email: "browser@example.test",
            permissions: ["workflow:read", "workflow:write", "workflow:run", "chat:read", "chat:write"],
            metadata: { pinned_model_ids: [] },
          });
          return;
        }

        if (path === "/api/auth/profile/metadata") {
          await drainRequest(req);
          jsonReply(res, { metadata: { pinned_model_ids: [] } });
          return;
        }

        if (path === "/api/auth/oauth/providers") {
          jsonReply(res, {
            providers: [],
            registration_enabled: true,
            turnstile: {
              enabled: false,
              site_key: null,
              require_on_login: false,
              require_on_register: false,
              require_on_password_change: false,
            },
          });
          return;
        }

        if (path === "/api/agent/models/available") {
          jsonReply(res, {
            models: [],
            count: 0,
            enabled_count: 0,
            default_model_id: null,
          });
          return;
        }

        if (path === "/api/agents") {
          jsonReply(res, {
            agents: [
              {
                id: "search",
                name: "Search Agent",
                description: "Browser fixture chat agent",
                icon: "Search",
                avatar: "",
                category: "general",
                enabled: true,
              },
            ],
            default_agent: "search",
            allowed_model_ids: [],
          });
          return;
        }

        if (path === "/api/settings/" || path === "/api/settings") {
          jsonReply(res, {
            settings: {
              general: [],
              model: [],
              agent: [],
              ui: [],
            },
          });
          return;
        }

        if (path === "/api/projects") {
          jsonReply(res, []);
          return;
        }

        if (path === "/api/sessions") {
          jsonReply(res, {
            sessions: [],
            total: 0,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 50),
            has_more: false,
          });
          return;
        }

        if (path === `/api/sessions/${chatSessionId}`) {
          jsonReply(res, {
            id: chatSessionId,
            user_id: "user-1",
            agent_id: "search",
            created_at: nowIso,
            updated_at: nowIso,
            is_active: true,
            metadata: {
              current_run_id: chatRunId,
              agent_id: "search",
              plugin_options: {
                workflow: {
                  SELECTED_WORKFLOW_ID: "wf-browser",
                  SELECTED_WORKFLOW_VERSION_ID: "wfv-browser-2",
                },
              },
            },
            name: "Workflow chat smoke",
          });
          return;
        }

        if (path === `/api/sessions/${chatSessionId}/events`) {
          const events = chatSessionEvents();
          jsonReply(res, {
            session_id: chatSessionId,
            run_id: chatRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${chatReplaySessionId}/events`) {
          const events = chatReplayWorkflowToolEvents();
          jsonReply(res, {
            session_id: chatReplaySessionId,
            run_id: chatReplayRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${chatApprovalReplaySessionId}/events`) {
          const events = chatReplayWorkflowApprovalToolEvents();
          jsonReply(res, {
            session_id: chatApprovalReplaySessionId,
            run_id: chatApprovalReplayRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${failedChatReplaySessionId}/events`) {
          const events = failedChatReplayWorkflowToolEvents();
          jsonReply(res, {
            session_id: failedChatReplaySessionId,
            run_id: failedChatReplayRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${agentTeamReplaySessionId}/events`) {
          const events = agentTeamWorkflowReplayEvents();
          jsonReply(res, {
            session_id: agentTeamReplaySessionId,
            run_id: agentTeamReplayRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${agentTeamApprovalReplaySessionId}/events`) {
          const events = agentTeamWorkflowApprovalReplayEvents();
          jsonReply(res, {
            session_id: agentTeamApprovalReplaySessionId,
            run_id: agentTeamApprovalReplayRunId,
            events,
            total: events.length,
            skip: 0,
            limit: 200,
          });
          return;
        }

        if (path === `/api/sessions/${chatSessionId}/generate-title`) {
          await drainRequest(req);
          jsonReply(res, { title: "Workflow chat smoke", session_id: chatSessionId });
          return;
        }

        if (path === `/api/sessions/${chatSessionId}/mark-read`) {
          await drainRequest(req);
          jsonReply(res, { status: "ok" });
          return;
        }

        if (path === "/api/chat/stream" && req.method === "POST") {
          const rawBody = await readRequestBody(req);
          try {
            const parsed = JSON.parse(rawBody);
            lastChatStreamBody = parsed;
            if (typeof parsed.message === "string" && parsed.message.trim()) {
              lastChatMessage = parsed.message.trim();
            }
            const workflowOptions = parsed?.plugin_options?.workflow || {};
            if (workflowOptions.SELECTED_WORKFLOW_ID) {
              const teamOptions = parsed?.plugin_options?.agent_team || {};
              const selectedTeamId = teamOptions.SELECTED_TEAM_ID ?? null;
              lastWorkflowRunBody = {
                source: selectedTeamId ? "agent_team_selected_workflow" : "chat_selected_workflow",
                agent_id: parsed?.agent_id ?? null,
                team_id: selectedTeamId,
                caller_plugin_id: selectedTeamId ? "agent_team" : "chat",
                workflow_id: workflowOptions.SELECTED_WORKFLOW_ID,
                version_id: workflowOptions.SELECTED_WORKFLOW_VERSION_ID ?? null,
                mode: "sync",
                input: {
                  message: lastChatMessage,
                  input: lastChatMessage,
                  query: lastChatMessage,
                  ...(typeof workflowOptions.SELECTED_WORKFLOW_INPUT_JSON === "object"
                    && workflowOptions.SELECTED_WORKFLOW_INPUT_JSON !== null
                    ? workflowOptions.SELECTED_WORKFLOW_INPUT_JSON
                    : {}),
                },
                interface: workflowCallableInterface(
                  workflowOptions.SELECTED_WORKFLOW_ID,
                  workflowOptions.SELECTED_WORKFLOW_VERSION_ID ?? null,
                ),
                output_field: "output",
              };
            }
          } catch {
            lastChatStreamBody = null;
            lastChatMessage = "Browser workflow chat smoke";
          }
          jsonReply(res, {
            session_id: chatSessionId,
            run_id: chatRunId,
            trace_id: chatTraceId,
            status: "running",
          });
          return;
        }

        if (path === `/api/chat/sessions/${chatSessionId}/status`) {
          jsonReply(res, {
            session_id: chatSessionId,
            run_id: chatRunId,
            status: "completed",
          });
          return;
        }

        if (path === `/api/chat/sessions/${chatSessionId}/stream`) {
          const teamOptions = lastChatStreamBody?.plugin_options?.agent_team || {};
          const isAgentTeamSelectedWorkflow =
            lastChatStreamBody?.agent_id === "team" && Boolean(teamOptions.SELECTED_TEAM_ID);
          const workflowRunEvent = isAgentTeamSelectedWorkflow
            ? chatWorkflowRunEvent({
                runId: "run-agent-team-live-browser",
                summaryPrefix: "Agent Team workflow saw",
              })
            : chatWorkflowRunEvent();
          const streamEvents = [
            {
              id: "chat-event-user",
              event: "user:message",
              data: {
                content: lastChatMessage,
                message_id: `${chatRunId}:user`,
                run_id: chatRunId,
                _timestamp: nowIso,
              },
            },
            ...(isAgentTeamSelectedWorkflow
              ? [
                  {
                    id: "chat-event-agent-team-call",
                    event: "agent:call",
                    data: {
                      agent_id: agentTeamMemberId,
                      agent_name: "Workflow Researcher",
                      input: "Use selected workflow before team synthesis.",
                      depth: 1,
                      _timestamp: nowIso,
                    },
                  },
                ]
              : []),
            {
              id: "chat-event-workflow",
              event: "workflow:run",
              data: {
                ...workflowRunEvent,
                ...(isAgentTeamSelectedWorkflow
                  ? {
                      agent_id: agentTeamMemberId,
                      depth: 1,
                    }
                  : {}),
                _timestamp: nowIso,
              },
            },
            ...(isAgentTeamSelectedWorkflow
              ? [
                  {
                    id: "chat-event-agent-team-result",
                    event: "agent:result",
                    data: {
                      agent_id: agentTeamMemberId,
                      result: "Workflow Researcher used the selected workflow output.",
                      success: true,
                      depth: 1,
                      _timestamp: nowIso,
                    },
                  },
                ]
              : []),
            {
              id: "chat-event-message",
              event: "message:chunk",
              data: {
                content: isAgentTeamSelectedWorkflow
                  ? "Agent Team synthesis after selected workflow."
                  : "Agent answer after workflow.",
                _timestamp: nowIso,
              },
            },
            {
              id: "chat-event-done",
              event: "done",
              data: { _timestamp: nowIso },
            },
          ];
          sseReply(res, streamEvents);
          return;
        }

        if (path === "/api/scheduled-tasks/task-workflow-browser/sessions") {
          jsonReply(res, {
            items: [],
            sessions: [],
            total: 0,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 10),
          });
          return;
        }

        if (path === "/api/scheduled-tasks/task-workflow-approval-browser/sessions") {
          jsonReply(res, {
            items: [],
            sessions: [],
            total: 0,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 10),
          });
          return;
        }

        if (path === "/api/scheduled-tasks/task-workflow-browser/runs") {
          const workflowResult = scheduledWorkflowRunResult();
          jsonReply(res, {
            items: [
              {
                id: "task-run-workflow-browser",
                task_id: "task-workflow-browser",
                agent_id: "search",
                trigger_type: "interval",
                status: "success",
                session_id: "scheduled-session-browser",
                trace_id: "scheduled-trace-browser",
                input_snapshot: {
                  message: "scheduled workflow input",
                  plugin_options: {
                    workflow: {
                      WORKFLOW_ID: "wf-browser",
                      WORKFLOW_VERSION_ID: "wfv-browser-2",
                      WORKFLOW_INPUT_JSON: {
                        message: "scheduled workflow input",
                      },
                    },
                  },
                },
                output_result: {
                  plugin_results: {
                    workflow: workflowResult,
                  },
                  workflow_result: workflowResult,
                },
                error_message: null,
                retry_count: 0,
                started_at: nowIso,
                finished_at: nowIso,
                duration_ms: 1234,
                created_at: nowIso,
              },
            ],
            total: 1,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 5),
          });
          return;
        }

        if (path === "/api/scheduled-tasks/task-workflow-approval-browser/runs") {
          const workflowResult = scheduledApprovalWorkflowRunResult();
          jsonReply(res, {
            items: [
              {
                id: "task-run-workflow-approval-browser",
                task_id: "task-workflow-approval-browser",
                agent_id: "search",
                trigger_type: "interval",
                status: "running",
                session_id: "scheduled-approval-session-browser",
                trace_id: "scheduled-approval-trace-browser",
                input_snapshot: {
                  message: "scheduled approval workflow input",
                  plugin_options: {
                    workflow: {
                      WORKFLOW_ID: "wf-browser",
                      WORKFLOW_VERSION_ID: "wfv-browser-2",
                      WORKFLOW_INPUT_JSON: {
                        message: "scheduled approval workflow input",
                      },
                    },
                  },
                },
                output_result: {
                  plugin_results: {
                    workflow: workflowResult,
                  },
                  workflow_result: workflowResult,
                },
                error_message: null,
                retry_count: 0,
                started_at: nowIso,
                finished_at: null,
                duration_ms: 1234,
                created_at: nowIso,
              },
            ],
            total: 1,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 5),
          });
          return;
        }

        if (path === "/api/scheduled-tasks/") {
          jsonReply(res, {
            items: [],
            tasks: [],
            total: 0,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 10),
          });
          return;
        }

        if (path === "/api/notifications/active") {
          jsonReply(res, []);
          return;
        }

        if (path === "/api/version") {
          jsonReply(res, {
            app_version: "browser-fixture",
            latest_version: null,
            has_update: false,
            github_url: "https://github.com/QiuShi5/LambChat",
            release_url: null,
          });
          return;
        }

        if (
          path === "/api/extensions/plugins/contributions" ||
          path === "/api/extensions/contributions"
        ) {
          const plugins = includeWorkflowPluginContribution ? [pluginContribution()] : [];
          jsonReply(res, { plugins, total: plugins.length });
          return;
        }

        if (path === "/api/plugins/workflow/workflows") {
          jsonReply(res, {
            workflows: [currentWorkflowSummary()],
            total: 1,
            skip: 0,
            limit: 50,
            plugin_id: "workflow",
          });
          return;
        }

        if (path === "/api/plugins/workflow/node-types") {
          jsonReply(res, {
            plugin_id: "workflow",
            node_types: [
              { type: "start", status: "supported", runtime: "local", source_types: ["start"], publish_requirements: [] },
              { type: "answer", status: "supported", runtime: "local", source_types: ["answer"], publish_requirements: [] },
              { type: "llm", status: "supported", runtime: "local", source_types: ["llm"], publish_requirements: [] },
            ],
            compatibility: { summary: { supported: 3, guarded: 0, blocked: 0, total: 3 }, items: [] },
          });
          return;
        }

        if (path === "/api/plugins/workflow/approvals/pending") {
          jsonReply(res, {
            plugin_id: "workflow",
            runs: approvalRunState === "paused" ? [{ ...pausedApprovalRun, version_id: currentWorkflowVersion().version_id }] : [],
            skip: 0,
            limit: 20,
          });
          return;
        }

        if (path === "/api/plugins/workflow/credentials") {
          if (req.method === "POST" || req.method === "PUT") {
            await drainRequest(req);
            jsonReply(res, {
              credential_id: "cred-browser",
              ref: "browser-ref",
              type: "credential_ref",
              label: "Browser credential",
              description: "",
              has_secret: true,
            });
            return;
          }
          jsonReply(res, {
            plugin_id: "workflow",
            credentials: [],
            total: 0,
            skip: Number(url.searchParams.get("skip") || 0),
            limit: Number(url.searchParams.get("limit") || 50),
          });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser") {
          jsonReply(res, { ...currentWorkflowSummary(), latest_version: currentWorkflowVersion() });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/versions") {
          if (req.method === "POST") {
            const rawBody = await readRequestBody(req);
            try {
              lastWorkflowVersionBody = JSON.parse(rawBody || "{}");
            } catch {
              lastWorkflowVersionBody = { raw: rawBody };
            }
            savedWorkflowVersion = {
              ...version,
              version_id: "wfv-browser-saved",
              version_number: 3,
              status: "draft",
              internal_model: savedInternalModelFromVersionBody(lastWorkflowVersionBody),
              source_payload: lastWorkflowVersionBody?.source_payload ?? version.source_payload,
            };
            jsonReply(res, savedWorkflowVersion);
            return;
          }
          jsonReply(res, { workflow_id: "wf-browser", versions: [currentWorkflowVersion()], skip: 0, limit: 50 });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/publish") {
          const rawBody = await readRequestBody(req);
          let requestedVersionId = currentWorkflowVersion().version_id;
          try {
            const body = JSON.parse(rawBody || "{}");
            requestedVersionId = body.version_id || requestedVersionId;
          } catch {}
          publishedWorkflowVersionId = requestedVersionId;
          jsonReply(res, {
            plugin_id: "workflow",
            workflow: currentWorkflowSummary(),
          });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/input-schema") {
          const activeVersion = currentWorkflowVersion();
          jsonReply(res, {
            plugin_id: "workflow",
            workflow_id: "wf-browser",
            version_id: activeVersion.version_id,
            version_number: activeVersion.version_number,
            input_schema: inputSchema,
            status: publishedWorkflowVersionId === activeVersion.version_id ? "published" : activeVersion.status,
            schema_source: "declared",
            inferred_fields: [],
            interface: workflowCallableInterface("wf-browser", activeVersion.version_id),
          });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/io-contract") {
          jsonReply(res, ioContractForVersion(currentWorkflowVersion()));
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/runs") {
          const runs = approvalRunState === "none"
            ? [run]
            : [{ ...approvalWorkflowRun(), version_id: currentWorkflowVersion().version_id }, run];
          jsonReply(res, { workflow_id: "wf-browser", runs, skip: 0, limit: 20 });
          return;
        }

        if (
          path === "/api/plugins/workflow/workflows/wf-browser/runs/run-browser/events" ||
          path === "/api/plugins/workflow/workflows/wf-browser/runs/run-inline/events" ||
          path === "/api/plugins/workflow/workflows/wf-browser/runs/run-scheduled-browser/events" ||
          path === "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/events"
        ) {
          if (path.includes("run-approval-browser")) {
            jsonReply(res, approvalWorkflowEventsPayload());
            return;
          }
          const eventRunId = path.includes("run-inline") ? "run-inline" : "run-browser";
          const payload = workflowEventsPayload(eventRunId);
          if (path.includes("run-scheduled-browser")) {
            const scheduledRun = scheduledWorkflowRunResult();
            jsonReply(res, {
              ...payload,
              run: { ...run, ...scheduledRun, events: [] },
              events: payload.events.map((event) => ({
                ...event,
                run_id: "run-scheduled-browser",
              })),
            });
            return;
          }
          jsonReply(res, payload);
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/validate") {
          jsonReply(res, {
            workflow_id: "wf-browser",
            version_id: "wfv-browser-2",
            version_number: 2,
            runnable: true,
            errors: [],
            reachable_node_ids: ["start", "answer"],
            credential_refs_required: [],
            credential_refs_resolved: [],
            credential_refs_unresolved: [],
          });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/run") {
          const rawBody = await readRequestBody(req);
          try {
            lastWorkflowRunBody = JSON.parse(rawBody || "{}");
          } catch {
            lastWorkflowRunBody = { raw: rawBody };
          }
          if (lastWorkflowRunBody?.mode === "async") {
            approvalRunState = "paused";
            jsonReply(res, { ...pausedApprovalRun, version_id: currentWorkflowVersion().version_id, events: [] });
            return;
          }
          jsonReply(res, { ...run, version_id: currentWorkflowVersion().version_id, run_id: "run-inline", events: [] });
          return;
        }

        if (path === "/api/plugins/workflow/workflows/wf-browser/runs/run-approval-browser/resume") {
          const rawBody = await readRequestBody(req);
          try {
            lastWorkflowResumeBody = JSON.parse(rawBody || "{}");
          } catch {
            lastWorkflowResumeBody = { raw: rawBody };
          }
          approvalRunState = lastWorkflowResumeBody?.approved === false ? "rejected" : "resumed";
          if (approvalRunState === "rejected") {
            jsonReply(res, {
              ...pausedApprovalRun,
              version_id: currentWorkflowVersion().version_id,
              status: "failed",
              output: {},
              error: "workflow_human_approval_rejected:approval",
              pause: {},
              events: approvalWorkflowEventsPayload().events,
            });
            return;
          }
          jsonReply(res, {
            ...resumedApprovalRun,
            version_id: currentWorkflowVersion().version_id,
            output: {
              ...resumedApprovalRun.output,
              browser_approval: {
                ...resumedApprovalRun.output.browser_approval,
                comment: lastWorkflowResumeBody?.comment ?? "",
              },
            },
            events: approvalWorkflowEventsPayload().events,
          });
          return;
        }

        jsonReply(res, {});
      });
    },
  };
}
