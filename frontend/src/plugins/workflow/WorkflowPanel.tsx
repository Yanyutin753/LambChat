import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type ReactFlowInstance,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertTriangle,
  CheckCircle2,
  Crosshair,
  FileJson,
  GitBranch,
  KeyRound,
  Loader2,
  Maximize2,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Square,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  workflowApi,
  type WorkflowInputSchemaResponse,
  type WorkflowIoContractResponse,
  type WorkflowNodeTypesResponse,
  type WorkflowDetailResponse,
  type WorkflowCredentialResponse,
  type WorkflowImportReport,
  type WorkflowImportResponse,
  type WorkflowRunEvent,
  type WorkflowRunMode,
  type WorkflowRunResponse,
  type WorkflowSummary,
  type WorkflowValidationResponse,
  type WorkflowVersionSummary,
} from "./api";
import {
  sampleWorkflowInputFromSchema,
  sampleWorkflowInputValue,
  workflowInputDraftMessage,
  workflowOutputPathValue,
  workflowInputDraftStatus,
} from "./contractUtils";

type WorkflowDefaultText = {
  importedWorkflowName: string;
  blankWorkflowName: string;
  startTitle: string;
  answerTitle: string;
  entryMessageDescription: string;
  answerTextDescription: string;
  workflowOutputDescription: string;
  sampleAnswer: string;
  sampleMessage: string;
  nodeTitle: (index: number) => string;
  approveInstruction: string;
  generalClass: string;
  supportClass: string;
  listOperatorTitle: string;
};

type WorkflowTranslator = (key: string, values?: Record<string, unknown>) => string;

function translatedWorkflowLabel(t: WorkflowTranslator, key: string, fallback: string) {
  const value = t(key, { defaultValue: fallback });
  return value && value !== key ? value : fallback;
}

function workflowDefaultText(t: (key: string, values?: Record<string, unknown>) => string): WorkflowDefaultText {
  return {
    importedWorkflowName: t("workflowPlugin.defaults.importedWorkflowName"),
    blankWorkflowName: t("workflowPlugin.defaults.blankWorkflowName"),
    startTitle: t("workflowPlugin.defaults.startTitle"),
    answerTitle: t("workflowPlugin.defaults.answerTitle"),
    entryMessageDescription: t("workflowPlugin.defaults.entryMessageDescription"),
    answerTextDescription: t("workflowPlugin.defaults.answerTextDescription"),
    workflowOutputDescription: t("workflowPlugin.defaults.workflowOutputDescription"),
    sampleAnswer: t("workflowPlugin.defaults.sampleAnswer"),
    sampleMessage: t("workflowPlugin.defaults.sampleMessage"),
    nodeTitle: (index: number) => t("workflowPlugin.defaults.nodeTitle", { index }),
    approveInstruction: t("workflowPlugin.defaults.approveInstruction"),
    generalClass: t("workflowPlugin.defaults.generalClass"),
    supportClass: t("workflowPlugin.defaults.supportClass"),
    listOperatorTitle: t("workflowPlugin.defaults.listOperatorTitle"),
  };
}

function sampleWorkflowDsl(defaultText: WorkflowDefaultText) {
  return JSON.stringify({
    version: "0.3.0",
    workflow: {
      nodes: [
        { id: "start", type: "start", data: { title: defaultText.startTitle } },
        {
          id: "answer",
          type: "answer",
          data: { title: defaultText.answerTitle, answer: defaultText.sampleAnswer },
        },
      ],
      edges: [{ id: "e1", source: "start", target: "answer" }],
    },
  }, null, 2);
}

function buildBlankWorkflowPluginDsl(name: string, defaultText: WorkflowDefaultText) {
  return {
    version: "0.3.0",
    app: {
      name,
      mode: "workflow",
    },
    workflow: {
      nodes: [
        {
          id: "start",
          type: "start",
          data: {
            title: defaultText.startTitle,
            variables: [{ name: "message", type: "string", required: true, description: defaultText.entryMessageDescription }],
            input_schema: {
              type: "object",
              properties: {
                message: { type: "string", description: defaultText.entryMessageDescription },
              },
              required: ["message"],
              additionalProperties: true,
            },
          },
          position: { x: 80, y: 120 },
        },
        {
          id: "answer",
          type: "answer",
          data: {
            title: defaultText.answerTitle,
            answer: "{{message}}",
            output_schema: {
              type: "object",
              properties: {
                answer: { type: "string", description: defaultText.answerTextDescription },
              },
              required: ["answer"],
              additionalProperties: true,
            },
          },
          position: { x: 420, y: 120 },
        },
      ],
      edges: [{ id: "start-answer", source: "start", target: "answer" }],
    },
  };
}

function blankWorkflowNameFromDraft(draftName: string, defaultText: WorkflowDefaultText) {
  const trimmed = draftName.trim();
  return trimmed && trimmed !== defaultText.importedWorkflowName ? trimmed : defaultText.blankWorkflowName;
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function workflowEditorPath(workflowId: string) {
  return `/workflows/${encodeURIComponent(workflowId)}/editor`;
}

function workflowRunTracePath(workflowId: string, runId: string) {
  return `/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function StatusIcon({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle2 className="text-emerald-500" size={16} />
  ) : (
    <AlertTriangle className="text-amber-500" size={16} />
  );
}

function runEventDuration(event: WorkflowRunEvent) {
  const duration = event.payload?.duration_ms;
  return typeof duration === "number" && Number.isFinite(duration) ? duration : null;
}

function runEventPayloadByteValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function formatRunEventPayloadBytes(value: number | null) {
  if (value === null) return "unknown";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function workflowEventPayloadTruncation(payload: Record<string, unknown>) {
  if (payload.truncated !== true || payload.reason !== "workflow_event_payload_too_large") {
    return null;
  }
  return {
    originalBytes: runEventPayloadByteValue(payload.original_bytes),
    maxBytes: runEventPayloadByteValue(payload.max_bytes),
    keys: Array.isArray(payload.keys) ? payload.keys.filter((key): key is string => typeof key === "string") : [],
  };
}

function runEventNodeIds(events: WorkflowRunEvent[]) {
  return Array.from(
    new Set(
      events
        .map((event) => event.node_id)
        .filter((nodeId): nodeId is string => typeof nodeId === "string" && nodeId.trim().length > 0),
    ),
  );
}

function workflowRunEvents(value: unknown): WorkflowRunEvent[] {
  return Array.isArray(value) ? value as WorkflowRunEvent[] : [];
}

function mergeWorkflowRunEvents(current: WorkflowRunEvent[], incoming: WorkflowRunEvent[]) {
  if (incoming.length === 0) return current;
  const seen = new Set(current.map((event) => event.event_id));
  const additions = incoming.filter((event) => {
    if (seen.has(event.event_id)) return false;
    seen.add(event.event_id);
    return true;
  });
  if (additions.length === 0) return current;
  return [...current, ...additions].sort(
    (left, right) => left.sequence - right.sequence || left.event_id.localeCompare(right.event_id),
  );
}

type WorkflowNodeRunStatus = "idle" | "running" | "succeeded" | "failed" | "paused";

type WorkflowNodeRunState = {
  status: WorkflowNodeRunStatus;
  eventCount: number;
  durationMs: number | null;
  lastEventType: string | null;
  focused: boolean;
};

function emptyWorkflowNodeRunState(focused = false): WorkflowNodeRunState {
  return {
    status: "idle",
    eventCount: 0,
    durationMs: null,
    lastEventType: null,
    focused,
  };
}

function workflowNodeRunStatusFromEvents(events: WorkflowRunEvent[]): WorkflowNodeRunStatus {
  if (events.some((event) => event.event_type.includes("failed") || event.event_type.includes("error"))) {
    return "failed";
  }
  if (events.some((event) => event.event_type.includes("paused") || event.event_type.includes("approval"))) {
    return "paused";
  }
  if (events.some((event) => event.event_type.includes("running") || event.event_type.includes("started"))) {
    const finished = events.some((event) =>
      event.event_type.includes("finished") ||
      event.event_type.includes("succeeded") ||
      event.event_type.includes("completed")
    );
    return finished ? "succeeded" : "running";
  }
  if (events.some((event) =>
    event.event_type.includes("finished") ||
    event.event_type.includes("succeeded") ||
    event.event_type.includes("completed")
  )) {
    return "succeeded";
  }
  return events.length > 0 ? "running" : "idle";
}

function workflowNodeRunStates(
  events: WorkflowRunEvent[],
  focusedNodeId: string | null,
): Record<string, WorkflowNodeRunState> {
  const grouped = new Map<string, WorkflowRunEvent[]>();
  for (const event of events) {
    if (!event.node_id) continue;
    grouped.set(event.node_id, [...(grouped.get(event.node_id) ?? []), event]);
  }
  const states: Record<string, WorkflowNodeRunState> = Object.fromEntries(
    Array.from(grouped.entries()).map<[string, WorkflowNodeRunState]>(([nodeId, nodeEvents]) => {
      const durations = nodeEvents
        .map(runEventDuration)
        .filter((value): value is number => value !== null);
      return [
        nodeId,
        {
          status: workflowNodeRunStatusFromEvents(nodeEvents),
          eventCount: nodeEvents.length,
          durationMs: durations.length > 0 ? durations.reduce((sum, value) => sum + value, 0) : null,
          lastEventType: nodeEvents[nodeEvents.length - 1]?.event_type ?? null,
          focused: focusedNodeId === nodeId,
        },
      ];
    }),
  );
  if (focusedNodeId && !states[focusedNodeId]) {
    states[focusedNodeId] = emptyWorkflowNodeRunState(true);
  }
  return states;
}

function workflowNodeRunStateClass(runState?: WorkflowNodeRunState) {
  if (!runState) return "border-[var(--theme-border)]";
  if (runState.focused) return "border-[var(--theme-primary)] ring-2 ring-[color-mix(in_srgb,var(--theme-primary)_22%,transparent)]";
  if (runState.status === "failed") return "border-red-500/60";
  if (runState.status === "paused") return "border-amber-500/60";
  if (runState.status === "running") return "border-sky-500/60";
  if (runState.status === "succeeded") return "border-emerald-500/60";
  return "border-[var(--theme-border)]";
}

function workflowNodeRunStatusClass(status: WorkflowNodeRunStatus) {
  if (status === "failed") return "border-red-500/30 bg-red-500/5 text-red-600";
  if (status === "paused") return "border-amber-500/30 bg-amber-500/5 text-amber-700";
  if (status === "running") return "border-sky-500/30 bg-sky-500/5 text-sky-700";
  if (status === "succeeded") return "border-emerald-500/30 bg-emerald-500/5 text-emerald-700";
  return "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] text-[var(--theme-text-secondary)]";
}

function runEventTone(eventType: string) {
  if (eventType.includes("failed")) {
    return {
      icon: <XCircle className="text-red-500" size={14} />,
      className: "border-red-500/40 bg-red-500/5",
    };
  }
  if (eventType.includes("finished")) {
    return {
      icon: <CheckCircle2 className="text-emerald-500" size={14} />,
      className: "border-emerald-500/30 bg-emerald-500/5",
    };
  }
  return {
    icon: <Play className="text-[var(--theme-text-secondary)]" size={14} />,
    className: "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)]",
  };
}

function compatibilityTone(status: string) {
  if (status === "blocked") {
    return "border-red-500/30 bg-red-500/5 text-red-600";
  }
  if (status === "guarded") {
    return "border-amber-500/30 bg-amber-500/5 text-amber-600";
  }
  return "border-emerald-500/30 bg-emerald-500/5 text-emerald-600";
}

function isWorkflowRunWaiting(status: WorkflowRunResponse["status"]) {
  return status === "queued" || status === "running";
}

function workflowRunStatusTone(status: WorkflowRunResponse["status"]) {
  if (status === "failed") return "text-red-500";
  if (status === "paused") return "text-amber-600";
  if (status === "succeeded") return "text-emerald-600";
  return "text-[var(--theme-text-secondary)]";
}

const WORKFLOW_RUN_OUTPUT_PREVIEW_LIMIT = 360;

function compactWorkflowValue(value: unknown) {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function truncatedWorkflowText(value: string, limit = WORKFLOW_RUN_OUTPUT_PREVIEW_LIMIT) {
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function isWorkflowOutputSummaryValue(value: unknown) {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function workflowRunOutputSummary(
  run: WorkflowRunResponse | null,
  outputFields: WorkflowInputField[] = [],
) {
  if (!run) return "";
  const rawOutput = run.output && typeof run.output === "object" && !Array.isArray(run.output)
    ? (run.output as Record<string, unknown>)
    : {};
  for (const field of outputFields) {
    const value = workflowOutputPathValue(rawOutput, field.field);
    if (isWorkflowOutputSummaryValue(value)) {
      return truncatedWorkflowText(compactWorkflowValue(value));
    }
  }
  const answer = workflowOutputPathValue(rawOutput, "answer");
  const raw = isWorkflowOutputSummaryValue(answer)
    ? compactWorkflowValue(answer)
    : compactWorkflowValue(run.output) || run.error || "";
  return truncatedWorkflowText(raw);
}

type WorkflowRunOutputEntry = {
  key: string;
  value: string;
  type: string;
  declared: boolean;
  present: boolean;
  description?: string;
};

type WorkflowRunOutputContractStatus = {
  valid: boolean;
  label: string;
  title: string;
  detail: string;
};

type WorkflowRunOutputContractStatusLabels = {
  declared: string;
  issue: string;
  missing: string;
  ok: string;
  satisfied: string;
  type: string;
  unknown: string;
};

type WorkflowRunInterfaceItem = {
  label: string;
  value: string;
  detail: string;
};

type WorkflowRunNextActionSummary = {
  label: string;
  detail: string;
  type: string;
};

function workflowOutputContractMissingFields(
  contract: WorkflowRunResponse["output_contract"],
) {
  if (!contract) return [];
  const missing = Array.isArray(contract.missing_required)
    ? contract.missing_required.filter((field) => typeof field === "string" && field.length > 0)
    : [];
  const requiredPaths = Array.isArray(contract.required_field_paths)
    ? contract.required_field_paths.filter((field) => typeof field === "string" && field.length > 0)
    : [];
  if (missing.length === 0 || requiredPaths.length === 0) {
    return missing;
  }
  const missingRoots = new Set(missing);
  const missingPaths = requiredPaths.filter((path) => {
    const root = (path.split(".", 1)[0] || "").replace(/\[\]$/, "");
    return missingRoots.has(root);
  });
  return missingPaths.length > 0 ? missingPaths : missing;
}

function workflowRunOutputContractStatus(
  run: WorkflowRunResponse | null,
  labels: WorkflowRunOutputContractStatusLabels,
): WorkflowRunOutputContractStatus | null {
  const contract = run?.output_contract;
  if (!contract || typeof contract.valid !== "boolean") return null;
  const missing = workflowOutputContractMissingFields(contract);
  const mismatches = Array.isArray(contract.type_mismatches)
    ? contract.type_mismatches
        .map((item) => {
          const field = typeof item.field === "string" ? item.field : "";
          const expected = compactWorkflowValue(item.expected);
          const actual = typeof item.actual === "string" ? item.actual : "";
          return field
            ? `${field}: ${actual || labels.unknown} -> ${expected || labels.declared}`
            : "";
        })
        .filter(Boolean)
    : [];
  const titleParts = [
    missing.length > 0 ? `${labels.missing}: ${missing.join(", ")}` : "",
    mismatches.length > 0 ? `${labels.type}: ${mismatches.join(", ")}` : "",
  ].filter(Boolean);
  return {
    valid: contract.valid,
    label: contract.valid ? labels.ok : labels.issue,
    title: titleParts.length > 0 ? titleParts.join(" | ") : labels.satisfied,
    detail: contract.valid ? "" : titleParts.join(" | "),
  };
}

function workflowRunOutputContractBadgeClass(valid: boolean) {
  return valid
    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
    : "border-amber-500/30 bg-amber-500/10 text-amber-700";
}

function workflowRunOutputEntries(
  run: WorkflowRunResponse | null,
  outputFields: WorkflowInputField[] = [],
): WorkflowRunOutputEntry[] {
  const rawOutput = run?.output && typeof run.output === "object" && !Array.isArray(run.output)
    ? (run.output as Record<string, unknown>)
    : {};
  const actualEntries = Object.entries(rawOutput).filter(([, value]) => value !== undefined);
  const contractByField = new Map(outputFields.map((field) => [field.field, field]));
  const orderedKeys = [
    ...outputFields.map((field) => field.field),
    ...actualEntries.map(([key]) => key).filter((key) => !contractByField.has(key)),
  ];
  return Array.from(new Set(orderedKeys)).slice(0, 8).map((key) => {
    const contract = contractByField.get(key);
    const value = workflowOutputPathValue(rawOutput, key);
    const present = value !== undefined;
    return {
      key,
      value: present
        ? truncatedWorkflowText(compactWorkflowValue(value), 160)
        : "Not returned by this run",
      type: contract?.type ?? "runtime",
      declared: Boolean(contract),
      present,
      description: contract?.description,
    };
  });
}

function workflowInterfaceObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function workflowInterfaceText(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function workflowInterfaceToolField(tool: unknown, field: unknown) {
  const toolName = workflowInterfaceText(tool);
  const fieldName = workflowInterfaceText(field);
  if (toolName && fieldName) return `${toolName}.${fieldName}`;
  return toolName || fieldName;
}

function workflowRunNextActionSummary(run: WorkflowRunResponse | null): WorkflowRunNextActionSummary | null {
  const nextAction = workflowInterfaceObject(run?.next_action);
  const type = workflowInterfaceText(nextAction.type);
  if (!type) return null;
  const target = workflowInterfaceText(nextAction.tool) || workflowInterfaceText(nextAction.field);
  const reason = workflowInterfaceText(nextAction.reason);
  return {
    label: type
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" "),
    detail: [target, reason].filter(Boolean).join(" | ") || "Read run status",
    type,
  };
}

function workflowRunNextActionBadgeClass(type: string) {
  if (type === "use_output") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
  if (type === "handle_terminal_error") return "border-red-500/30 bg-red-500/10 text-red-700";
  return "border-sky-500/30 bg-sky-500/10 text-sky-700";
}

function workflowRunInterfaceItems(run: WorkflowRunResponse | null): WorkflowRunInterfaceItem[] {
  const interfacePayload = workflowInterfaceObject(run?.interface);
  if (Object.keys(interfacePayload).length === 0) return [];

  const entry = workflowInterfaceObject(interfacePayload.entry);
  const exit = workflowInterfaceObject(interfacePayload.exit);
  const debug = workflowInterfaceObject(interfacePayload.debug);
  const items: WorkflowRunInterfaceItem[] = [];

  const entryValue = workflowInterfaceToolField(entry.tool, entry.argument);
  if (entryValue) {
    items.push({
      label: "Entry",
      value: entryValue,
      detail: workflowInterfaceToolField(entry.schema_tool, entry.schema_field) || "input_schema",
    });
  }

  const exitValue = workflowInterfaceText(exit.field);
  if (exitValue) {
    items.push({
      label: "Exit",
      value: exitValue,
      detail: workflowInterfaceToolField(exit.schema_tool, exit.schema_field) || "output_schema",
    });
  }

  const debugValue = workflowInterfaceText(debug.tool);
  if (debugValue) {
    items.push({
      label: "Debug",
      value: debugValue,
      detail: workflowInterfaceText(debug.run_id) || workflowInterfaceText(debug.events_field) || "events",
    });
  }

  return items;
}

function workflowContractInterfaceItems(
  workflow: WorkflowSummary | null,
  contract: WorkflowIoContractResponse | null,
): WorkflowRunInterfaceItem[] {
  if (!workflow) return [];
  const interfacePayload = workflowInterfaceObject(contract?.interface);
  const entry = workflowInterfaceObject(interfacePayload.entry);
  const exit = workflowInterfaceObject(interfacePayload.exit);
  const schema = workflowInterfaceObject(interfacePayload.schema);
  const versionId = contract?.version_id || workflow.published_version_id || workflow.latest_version_id || "";
  const versionDetail = versionId ? `version ${versionId}` : "latest available version";
  const entryValue = workflowInterfaceToolField(entry.tool, entry.argument);
  const exitValue = workflowInterfaceText(exit.field);
  const schemaValue = workflowInterfaceText(schema.tool);
  return [
    {
      label: "Entry",
      value: entryValue || "workflow_run.input",
      detail: workflowInterfaceToolField(entry.schema_tool, entry.schema_field) || contract?.input_schema_source || "input_schema",
    },
    {
      label: "Exit",
      value: exitValue || "output",
      detail: workflowInterfaceToolField(exit.schema_tool, exit.schema_field) || contract?.output_schema_source || "output_schema",
    },
    {
      label: "Schema",
      value: schemaValue || "workflow_get_schema",
      detail: workflowInterfaceText(schema.version_id) || versionDetail,
    },
  ];
}

type WorkflowStatusFilter = "all" | WorkflowSummary["status"];

function workflowStatusBadgeClass(status: WorkflowSummary["status"]) {
  if (status === "published") return "border-emerald-500/30 bg-emerald-500/5 text-emerald-700";
  if (status === "archived") return "border-stone-500/30 bg-stone-500/5 text-stone-600";
  return "border-amber-500/30 bg-amber-500/5 text-amber-700";
}

function pendingApprovalFromRun(run: WorkflowRunResponse | null) {
  const pause = run?.pause;
  if (!pause || typeof pause !== "object") return null;
  const pending = pause.pending_approval;
  return pending && typeof pending === "object" ? pending as Record<string, unknown> : null;
}

function pendingApprovalText(value: unknown) {
  return typeof value === "string" ? value : "";
}

function runInputFromSchema(
  schemaResponse: WorkflowInputSchemaResponse | null,
  defaultText: WorkflowDefaultText,
) {
  return JSON.stringify(sampleWorkflowInputFromSchema(schemaResponse?.input_schema, defaultText.sampleMessage), null, 2);
}

function inputSchemaFromIoContract(
  contract: WorkflowIoContractResponse | null | undefined,
): WorkflowInputSchemaResponse | null {
  if (!contract) return null;
  return {
    plugin_id: "workflow",
    workflow_id: contract.workflow_id,
    version_id: contract.version_id,
    version_number: contract.version_number,
    input_schema: contract.input_schema,
    status: contract.status,
    schema_source: contract.input_schema_source,
    inferred_fields: contract.inferred_input_fields,
    interface: contract.interface,
  };
}

function savedWorkflowVersionId(response: WorkflowImportResponse) {
  return (
    response.version_id
    ?? response.interface?.entry?.version_id
    ?? response.io_contract?.version_id
    ?? null
  );
}

type WorkflowInputField = {
  field: string;
  type: string;
  source: string;
  required: boolean;
  optionCount: number;
  schema: Record<string, unknown>;
  description?: string;
  inputKind?: string;
};

type SchemaFieldOptions = {
  nested?: boolean;
  prefix?: string;
};

function schemaFields(schemaResponse: WorkflowInputSchemaResponse | null): WorkflowInputField[] {
  const schema = schemaResponse?.input_schema;
  return schemaFieldsFromSchema(schema);
}

function schemaFieldType(property: Record<string, unknown>) {
  if (typeof property.type === "string") return property.type;
  if (Array.isArray(property.type)) {
    return property.type.map((item) => String(item)).filter(Boolean).join("|") || "unknown";
  }
  if (property.properties && typeof property.properties === "object" && !Array.isArray(property.properties)) {
    return "object";
  }
  if (property.items && typeof property.items === "object" && !Array.isArray(property.items)) {
    return "array";
  }
  return "unknown";
}

function schemaFieldsFromSchema(
  schema: Record<string, unknown> | null | undefined,
  options: SchemaFieldOptions = {},
): WorkflowInputField[] {
  const schemaObject = schema && typeof schema === "object" && !Array.isArray(schema)
    ? (schema as Record<string, unknown>)
    : null;
  const properties = schemaObject?.properties ?? null;
  const requiredFields = Array.isArray(schemaObject?.required) ? schemaObject.required : [];
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return [];
  }
  return Object.entries(properties as Record<string, unknown>).map(([field, rawSchema]) => {
    const property = rawSchema && typeof rawSchema === "object" && !Array.isArray(rawSchema)
      ? (rawSchema as Record<string, unknown>)
      : {};
    const fieldPath = options.prefix ? `${options.prefix}.${field}` : field;
    const type = schemaFieldType(property);
    const entry = {
      field: fieldPath,
      type,
      source: typeof property["x-lambchat-source"] === "string" ? String(property["x-lambchat-source"]) : "declared",
      required: requiredFields.includes(field),
      optionCount: Array.isArray(property.enum) ? property.enum.length : 0,
      schema: property,
      description: typeof property.description === "string" ? property.description : undefined,
      inputKind: typeof property["x-lambchat-input-kind"] === "string" ? String(property["x-lambchat-input-kind"]) : undefined,
    };
    if (!options.nested) return [entry];
    const nestedFields = type === "object"
      ? schemaFieldsFromSchema(property, { nested: true, prefix: fieldPath })
      : type === "array"
        ? schemaFieldsFromSchema(
            property.items && typeof property.items === "object" && !Array.isArray(property.items)
              ? (property.items as Record<string, unknown>)
              : null,
            { nested: true, prefix: `${fieldPath}[]` },
          )
        : [];
    return nestedFields.length > 0 ? nestedFields : [entry];
  }).flat();
}

function parseRunInputObject(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

function stringifyRunInput(input: Record<string, unknown>) {
  return JSON.stringify(input, null, 2);
}

function resolveDebugVersionId(
  detail: WorkflowDetailResponse,
  versions: WorkflowVersionSummary[],
  currentVersionId: string | null,
) {
  if (currentVersionId && versions.some((version) => version.version_id === currentVersionId)) {
    return currentVersionId;
  }
  return detail.latest_version?.version_id ?? versions[0]?.version_id ?? null;
}

function runInputFieldValue(
  runInput: string,
  field: WorkflowInputField,
) {
  const input = parseRunInputObject(runInput);
  if (Object.prototype.hasOwnProperty.call(input, field.field)) {
    return input[field.field];
  }
  return sampleWorkflowInputValue(field.field, field.schema, { fallbackText: "LambChat" });
}

function runInputWithFieldValue(
  runInput: string,
  field: string,
  value: unknown,
) {
  const input = parseRunInputObject(runInput);
  return stringifyRunInput({ ...input, [field]: value });
}

function jsonSelectValue(value: unknown) {
  return JSON.stringify(value);
}

function numericFieldValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

function stringFieldValue(value: unknown) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function complexFieldValue(value: unknown) {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function fileMetadataValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function fileMetadataListValue(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.map(fileMetadataValue);
}

function fileMetadataText(value: unknown, key: string) {
  const item = fileMetadataValue(value)[key];
  return typeof item === "string" || typeof item === "number" ? String(item) : "";
}

function runInputWithFileMetadataValue(
  runInput: string,
  field: string,
  currentValue: unknown,
  metadataKey: string,
  metadataValue: string,
) {
  return runInputWithFieldValue(runInput, field, {
    ...fileMetadataValue(currentValue),
    [metadataKey]: metadataValue,
  });
}

function runInputWithFileMetadataListItemValue(
  runInput: string,
  field: string,
  currentValue: unknown,
  itemIndex: number,
  metadataKey: string,
  metadataValue: string,
) {
  const items = fileMetadataListValue(currentValue);
  items[itemIndex] = {
    ...fileMetadataValue(items[itemIndex]),
    [metadataKey]: metadataValue,
  };
  return runInputWithFieldValue(runInput, field, items);
}

function runInputWithAddedFileMetadataItem(
  runInput: string,
  field: string,
  currentValue: unknown,
) {
  return runInputWithFieldValue(runInput, field, [
    ...fileMetadataListValue(currentValue),
    { name: "", url: "", mime_type: "" },
  ]);
}

function runInputWithRemovedFileMetadataItem(
  runInput: string,
  field: string,
  currentValue: unknown,
  itemIndex: number,
) {
  return runInputWithFieldValue(
    runInput,
    field,
    fileMetadataListValue(currentValue).filter((_, index) => index !== itemIndex),
  );
}

const FILE_METADATA_FIELDS = [
  ["name", "File name"],
  ["url", "URL"],
  ["mime_type", "MIME type"],
] as const;

function schemaNumber(schema: Record<string, unknown>, key: string) {
  const value = schema[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function WorkflowInputForm({
  fields,
  runInput,
  disabled,
  onChange,
}: {
  fields: WorkflowInputField[];
  runInput: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  if (fields.length === 0) return null;
  return (
    <div className="mb-2 grid gap-2 sm:grid-cols-2">
      {fields.map((field) => {
        const value = runInputFieldValue(runInput, field);
        const commonLabel = (
          <div className="mb-1 flex min-w-0 items-center justify-between gap-2 text-xs">
            <span className="truncate font-medium text-[var(--theme-text)]">{field.field}</span>
            {field.required && <span className="shrink-0 text-amber-500">{t("workflowPlugin.editor.common.required")}</span>}
          </div>
        );
        const baseControlClass = "h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)] disabled:opacity-50";
        const control = (() => {
          if (Array.isArray(field.schema.enum) && field.schema.enum.length > 0) {
            return (
              <select
                className={baseControlClass}
                value={jsonSelectValue(value)}
                onChange={(event) => onChange(runInputWithFieldValue(runInput, field.field, JSON.parse(event.target.value) as unknown))}
                disabled={disabled}
              >
                {field.schema.enum.map((option) => (
                  <option key={jsonSelectValue(option)} value={jsonSelectValue(option)}>
                    {String(option)}
                  </option>
                ))}
              </select>
            );
          }
          if (field.type === "boolean") {
            return (
              <label className="flex h-9 items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm">
                <input
                  type="checkbox"
                  checked={value === true}
                  onChange={(event) => onChange(runInputWithFieldValue(runInput, field.field, event.target.checked))}
                  disabled={disabled}
                  className="h-4 w-4 accent-[var(--theme-primary)]"
                />
                <span>{value === true ? "true" : "false"}</span>
              </label>
            );
          }
          if (field.type === "integer" || field.type === "number") {
            return (
              <input
                type="number"
                step={field.type === "integer" ? 1 : "any"}
                min={schemaNumber(field.schema, "minimum")}
                max={schemaNumber(field.schema, "maximum")}
                className={baseControlClass}
                value={numericFieldValue(value)}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  onChange(
                    runInputWithFieldValue(
                      runInput,
                      field.field,
                      nextValue === ""
                        ? ""
                        : field.type === "integer"
                          ? Number.parseInt(nextValue, 10)
                          : Number.parseFloat(nextValue),
                    ),
                  );
                }}
                disabled={disabled}
              />
            );
          }
          if (field.inputKind === "file" && field.type === "object") {
            return (
              <div className="grid gap-2">
                {FILE_METADATA_FIELDS.map(([metadataKey, placeholder]) => (
                  <input
                    key={metadataKey}
                    type={metadataKey === "url" ? "url" : "text"}
                    className={baseControlClass}
                    value={fileMetadataText(value, metadataKey)}
                    onChange={(event) =>
                      onChange(
                        runInputWithFileMetadataValue(
                          runInput,
                          field.field,
                          value,
                          metadataKey,
                          event.target.value,
                        ),
                      )
                    }
                    placeholder={placeholder}
                    disabled={disabled}
                  />
                ))}
              </div>
            );
          }
          if (field.inputKind === "file" && field.type === "array") {
            const items = fileMetadataListValue(value);
            return (
              <div className="space-y-2">
                {(items.length > 0 ? items : [{}]).map((item, itemIndex) => (
                  <div key={itemIndex} className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                    <div className="mb-2 flex items-center justify-between gap-2 text-xs text-[var(--theme-text-secondary)]">
                      <span>File {itemIndex + 1}</span>
                      <button
                        type="button"
                        onClick={() => onChange(runInputWithRemovedFileMetadataItem(runInput, field.field, value, itemIndex))}
                        disabled={disabled || items.length === 0}
                        className="inline-flex h-7 items-center rounded-md border border-[var(--theme-border)] px-2 hover:bg-[var(--theme-bg)] disabled:opacity-50"
                      >
                        Remove
                      </button>
                    </div>
                    <div className="grid gap-2">
                      {FILE_METADATA_FIELDS.map(([metadataKey, placeholder]) => (
                        <input
                          key={metadataKey}
                          type={metadataKey === "url" ? "url" : "text"}
                          className={baseControlClass}
                          value={fileMetadataText(item, metadataKey)}
                          onChange={(event) =>
                            onChange(
                              runInputWithFileMetadataListItemValue(
                                runInput,
                                field.field,
                                value,
                                itemIndex,
                                metadataKey,
                                event.target.value,
                              ),
                            )
                          }
                          placeholder={placeholder}
                          disabled={disabled}
                        />
                      ))}
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => onChange(runInputWithAddedFileMetadataItem(runInput, field.field, value))}
                  disabled={disabled}
                  className="inline-flex h-8 items-center justify-center rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                >
                  Add file
                </button>
              </div>
            );
          }
          if (field.type === "array" || field.type === "object") {
            return (
              <textarea
                className="min-h-20 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2 font-mono text-xs outline-none focus:border-[var(--theme-primary)] disabled:opacity-50"
                value={complexFieldValue(value)}
                onChange={(event) => {
                  try {
                    onChange(runInputWithFieldValue(runInput, field.field, JSON.parse(event.target.value) as unknown));
                  } catch {
                    onChange(runInputWithFieldValue(runInput, field.field, event.target.value));
                  }
                }}
                disabled={disabled}
                spellCheck={false}
              />
            );
          }
          return (
            <input
              type={field.schema.format === "email" ? "email" : field.schema.format === "url" || field.schema.format === "uri" ? "url" : "text"}
              minLength={schemaNumber(field.schema, "minLength")}
              maxLength={schemaNumber(field.schema, "maxLength")}
              className={baseControlClass}
              value={stringFieldValue(value)}
              onChange={(event) => onChange(runInputWithFieldValue(runInput, field.field, event.target.value))}
              disabled={disabled}
            />
          );
        })();
        return (
          <label
            key={field.field}
            className="block rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2"
            title={field.description || `${field.field}: ${field.type} (${field.source})`}
          >
            {commonLabel}
            {control}
          </label>
        );
      })}
    </div>
  );
}

function CompatibilityMatrixPanel({ catalog }: { catalog: WorkflowNodeTypesResponse | null }) {
  const { t } = useTranslation();
  if (!catalog) {
    return (
      <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
        {t("workflowPlugin.editor.compatibility.loading")}
      </div>
    );
  }
  const summary = catalog.compatibility.summary;
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3 text-sm font-medium">
        <span>{t("workflowPlugin.editor.compatibility.title")}</span>
        <span className="text-xs font-normal text-[var(--theme-text-secondary)]">{summary.total}</span>
      </div>
      <div className="mb-3 grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.supported")}</div>
          <div className="mt-1 font-medium text-emerald-600">{summary.supported}</div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.guarded")}</div>
          <div className="mt-1 font-medium text-amber-600">{summary.guarded}</div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.blocked")}</div>
          <div className="mt-1 font-medium text-red-600">{summary.blocked}</div>
        </div>
      </div>
      <div className="max-h-72 space-y-2 overflow-auto pr-1">
        {catalog.compatibility.items.map((item) => (
          <div key={item.source_type} className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2 text-xs">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-medium">{workflowNodeTypeLabel(item.source_type, t)}</div>
                <div className="mt-0.5 truncate text-[var(--theme-text-secondary)]">
                  {workflowNodeTypeLabel(item.internal_type ?? "unsupported", t)} / {workflowCompatibilityRuntimeLabel(item.runtime, t)}
                </div>
              </div>
              <span className={`shrink-0 rounded-md border px-2 py-0.5 ${compatibilityTone(item.status)}`}>
                {workflowCompatibilityStatusLabel(item.status, t)}
              </span>
            </div>
            {item.publish_requirements.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {item.publish_requirements.map((requirement) => (
                  <span key={requirement} className="rounded bg-[var(--theme-bg)] px-1.5 py-0.5 text-[var(--theme-text-secondary)]">
                    {workflowCompatibilityRequirementLabel(requirement, t)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function reportList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];
}

function reportMappingList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function reportObjectList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return [item as Record<string, unknown>];
    }
    const text = credentialText(item).trim();
    return text ? [{ type: text }] : [];
  });
}

function credentialText(value: unknown) {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function credentialMappingTitle(mapping: Record<string, unknown>) {
  return credentialText(mapping.label) || credentialText(mapping.ref) || "Credential reference";
}

function normalizeWorkflowImportReport(value: unknown): WorkflowImportReport | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const report = value as Record<string, unknown>;
  return {
    source: "workflow",
    source_version: credentialText(report.source_version),
    workflow_id: credentialText(report.workflow_id) || null,
    supported_nodes: reportList(report.supported_nodes),
    unsupported_nodes: reportObjectList(report.unsupported_nodes),
    credential_refs_required: reportList(report.credential_refs_required),
    credential_refs_resolved: reportMappingList(report.credential_refs_resolved),
    credential_refs_unresolved: reportList(report.credential_refs_unresolved),
    warnings: reportList(report.warnings),
    errors: reportList(report.errors),
    lossless: report.lossless === true,
  };
}

function uniqueWorkflowErrors(errors: string[]) {
  return Array.from(new Set(errors));
}

function boundaryPreflightErrors(report: WorkflowImportReport) {
  return reportList(report.errors).filter(
    (error) =>
      error.startsWith("workflow_boundary_edge_") ||
      error.startsWith("boundary_edge_"),
  );
}

function boundaryPreflightMessage(error: string) {
  const [, edgeId = "edge", path = ""] = error.split(":");
  if (error.includes("targets_entry")) {
    return `Edge ${edgeId} points back into the workflow entry${path ? ` (${path})` : ""}.`;
  }
  if (error.includes("starts_from_exit")) {
    return `Edge ${edgeId} starts from a workflow exit${path ? ` (${path})` : ""}.`;
  }
  return error;
}

function BoundaryPreflightPanel({ report }: { report: WorkflowImportReport }) {
  const { t } = useTranslation();
  const errors = boundaryPreflightErrors(report);
  if (errors.length === 0) return null;
  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
      <div className="mb-2 flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
        <AlertTriangle size={13} />
        <span>{t("workflowPlugin.editor.boundaryIssues.title")}</span>
      </div>
      <div className="space-y-1">
        {errors.map((error) => (
          <div key={error} className="rounded-md bg-[var(--theme-bg)] px-2 py-1 text-[var(--theme-text-secondary)]" title={error}>
            {boundaryPreflightMessage(error)}
          </div>
        ))}
      </div>
    </div>
  );
}

function CredentialPreflightPanel({ report }: { report: WorkflowImportReport }) {
  const { t } = useTranslation();
  const required = reportList(report.credential_refs_required);
  const resolved = reportMappingList(report.credential_refs_resolved);
  const unresolved = reportList(report.credential_refs_unresolved);
  if (required.length === 0 && resolved.length === 0 && unresolved.length === 0) {
    return null;
  }
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2 text-xs">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.editor.credentials.preflight")}</span>
        <span className={unresolved.length > 0 ? "text-amber-600" : "text-emerald-600"}>
          {resolved.length}/{required.length} {t("workflowPlugin.editor.common.mapped")}
        </span>
      </div>
      {resolved.length > 0 && (
        <div className="mb-2 space-y-1">
          {resolved.map((mapping) => {
            const ref = credentialText(mapping.ref);
            const target = credentialText(mapping.target);
            const type = credentialText(mapping.type);
            return (
              <div key={`${ref}:${target}`} className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-2 py-1">
                <div className="truncate font-medium text-emerald-700">{credentialMappingTitle(mapping)}</div>
                <div className="mt-0.5 truncate text-[var(--theme-text-secondary)]">
                  {type || "credential_ref"} &gt; {target || t("workflowPlugin.editor.common.mapped")}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {unresolved.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {unresolved.map((ref) => (
            <span key={ref} className="max-w-full truncate rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-amber-700" title={ref}>
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function reportWithValidationPreflight(
  report: WorkflowImportReport,
  validation: WorkflowValidationResponse,
): WorkflowImportReport {
  const normalizedReport = normalizeWorkflowImportReport(report) ?? report;
  return {
    ...normalizedReport,
    lossless: normalizedReport.lossless && validation.runnable,
    errors: uniqueWorkflowErrors([
      ...reportList(normalizedReport.errors).filter((error) => !error.startsWith("workflow_")),
      ...validation.errors,
    ]),
    credential_refs_required: validation.credential_refs_required,
    credential_refs_resolved: validation.credential_refs_resolved,
    credential_refs_unresolved: validation.credential_refs_unresolved,
  };
}

type CredentialDraft = {
  ref: string;
  type: string;
  label: string;
  description: string;
  secret: string;
};

const EMPTY_CREDENTIAL_DRAFT: CredentialDraft = {
  ref: "",
  type: "credential_ref",
  label: "",
  description: "",
  secret: "",
};

function credentialDraftFromRef(ref: string): CredentialDraft {
  return {
    ...EMPTY_CREDENTIAL_DRAFT,
    ref,
    label: ref,
  };
}

function credentialDraftFromCredential(credential: WorkflowCredentialResponse): CredentialDraft {
  return {
    ref: credential.ref,
    type: credential.type || "credential_ref",
    label: credential.label || "",
    description: credential.description || "",
    secret: "",
  };
}

function credentialRefsFromReport(report: WorkflowImportReport | null) {
  if (!report) return [];
  return reportList(report.credential_refs_unresolved);
}

function CredentialVaultPanel({
  credentials,
  unresolvedRefs,
  draft,
  isLoading,
  isSaving,
  isDeletingId,
  onDraftChange,
  onPickRef,
  onEditCredential,
  onSave,
  onReset,
  onDelete,
}: {
  credentials: WorkflowCredentialResponse[];
  unresolvedRefs: string[];
  draft: CredentialDraft;
  isLoading: boolean;
  isSaving: boolean;
  isDeletingId: string | null;
  onDraftChange: (draft: CredentialDraft) => void;
  onPickRef: (ref: string) => void;
  onEditCredential: (credential: WorkflowCredentialResponse) => void;
  onSave: () => void;
  onReset: () => void;
  onDelete: (credentialId: string) => void;
}) {
  const { t } = useTranslation();
  const canSave = Boolean(draft.ref.trim()) && !isSaving;
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3 text-sm font-medium">
        <div className="flex min-w-0 items-center gap-2">
          <KeyRound size={16} />
          <span>{t("workflowPlugin.editor.credentials.title")}</span>
        </div>
        <span className="text-xs font-normal text-[var(--theme-text-secondary)]">{credentials.length}</span>
      </div>
      {unresolvedRefs.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {unresolvedRefs.map((ref) => (
            <button
              key={ref}
              type="button"
              onClick={() => onPickRef(ref)}
              className="max-w-full truncate rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-xs text-amber-700 hover:bg-amber-500/10"
              title={ref}
            >
              {ref}
            </button>
          ))}
        </div>
      )}
      <div className="grid gap-2">
        <input
          className="h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
          value={draft.ref}
          onChange={(event) => onDraftChange({ ...draft, ref: event.target.value })}
          placeholder={t("workflowPlugin.editor.credentials.refPlaceholder")}
          disabled={isSaving}
        />
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
          <select
            className="h-9 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
            value={draft.type}
            onChange={(event) => onDraftChange({ ...draft, type: event.target.value })}
            disabled={isSaving}
            title={t("workflowPlugin.editor.credentials.typeTitle")}
          >
            <option value="credential_ref">{t("workflowPlugin.editor.credentials.types.credentialRef")}</option>
            <option value="http_auth">{t("workflowPlugin.editor.credentials.types.httpAuth")}</option>
            <option value="model">{t("workflowPlugin.editor.credentials.types.model")}</option>
            <option value="api_key">{t("workflowPlugin.editor.credentials.types.apiKey")}</option>
          </select>
          <input
            className="h-9 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
            value={draft.label}
            onChange={(event) => onDraftChange({ ...draft, label: event.target.value })}
            placeholder={t("workflowPlugin.editor.credentials.labelPlaceholder")}
            disabled={isSaving}
          />
        </div>
        <input
          className="h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
          value={draft.secret}
          onChange={(event) => onDraftChange({ ...draft, secret: event.target.value })}
          placeholder={t("workflowPlugin.editor.credentials.secretPlaceholder")}
          type="password"
          disabled={isSaving}
        />
        <textarea
          className="min-h-16 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2 text-sm outline-none focus:border-[var(--theme-primary)]"
          value={draft.description}
          onChange={(event) => onDraftChange({ ...draft, description: event.target.value })}
          placeholder={t("workflowPlugin.editor.credentials.descriptionPlaceholder")}
          disabled={isSaving}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave}
          className="inline-flex h-8 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-xs text-white disabled:opacity-50"
        >
          {isSaving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
          {t("workflowPlugin.editor.common.save")}
        </button>
        <button
          type="button"
          onClick={onReset}
          disabled={isSaving}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
        >
          <Plus size={14} />
          {t("workflowPlugin.editor.common.new")}
        </button>
      </div>
      <div className="mt-3 space-y-2">
        {isLoading ? (
          <div className="flex items-center gap-2 rounded-md border border-dashed border-[var(--theme-border)] px-3 py-6 text-sm text-[var(--theme-text-secondary)]">
            <Loader2 className="animate-spin" size={16} /> {t("workflowPlugin.editor.credentials.loading")}
          </div>
        ) : credentials.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-6 text-center text-sm text-[var(--theme-text-secondary)]">
            {t("workflowPlugin.editor.credentials.empty")}
          </div>
        ) : (
          credentials.map((credential) => (
            <div key={credential.credential_id} className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2 text-xs">
              <div className="mb-2 flex items-start justify-between gap-2">
                <button
                  type="button"
                  onClick={() => onEditCredential(credential)}
                  className="min-w-0 text-left"
                  title={credential.ref}
                >
                  <div className="truncate font-medium text-[var(--theme-text)]">{credential.label || credential.ref}</div>
                  <div className="mt-0.5 truncate text-[var(--theme-text-secondary)]">{credential.ref}</div>
                </button>
                <div className="flex shrink-0 items-center gap-1">
                  {credential.has_secret && <span className="rounded-md border border-emerald-500/30 px-1.5 py-0.5 text-emerald-600">{t("workflowPlugin.editor.common.secret")}</span>}
                  <button
                    type="button"
                    onClick={() => onDelete(credential.credential_id)}
                    disabled={isDeletingId === credential.credential_id}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                    title={t("workflowPlugin.editor.credentials.deleteTitle")}
                  >
                    {isDeletingId === credential.credential_id ? <Loader2 className="animate-spin" size={13} /> : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 text-[var(--theme-text-secondary)]">
                <span>{credential.type}</span>
                {credential.description && <span className="truncate">{credential.description}</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ReportPanel({ report }: { report: WorkflowImportReport | null }) {
  const { t } = useTranslation();
  const normalizedReport = normalizeWorkflowImportReport(report);
  if (!normalizedReport) {
    return (
      <div className="flex min-h-32 items-center justify-center rounded-md border border-dashed border-[var(--theme-border)] p-4 text-sm text-[var(--theme-text-secondary)]">
        {t("workflowPlugin.editor.report.empty")}
      </div>
    );
  }
  return (
    <div className="space-y-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <StatusIcon ok={normalizedReport.lossless} />
          <span>{normalizedReport.lossless ? t("workflowPlugin.editor.report.lossless") : t("workflowPlugin.editor.report.needsAttention")}</span>
        </div>
        <span className="text-xs text-[var(--theme-text-secondary)]">
          {t("workflowPlugin.editor.report.sourceVersion", { version: normalizedReport.source_version })}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.supported")}</div>
          <div className="mt-1 font-medium">{normalizedReport.supported_nodes.length}</div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.unsupported")}</div>
          <div className="mt-1 font-medium">{normalizedReport.unsupported_nodes.length}</div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.warnings")}</div>
          <div className="mt-1 font-medium">{normalizedReport.warnings.length}</div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg-secondary)] p-2">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.common.errors")}</div>
          <div className="mt-1 font-medium">{normalizedReport.errors.length}</div>
        </div>
      </div>
      {(normalizedReport.unsupported_nodes.length > 0 || normalizedReport.errors.length > 0) && (
        <pre className="max-h-40 overflow-auto rounded-md bg-[var(--theme-bg-secondary)] p-3 text-xs text-[var(--theme-text-secondary)]">
          {JSON.stringify(
            {
              unsupported_nodes: normalizedReport.unsupported_nodes,
              warnings: normalizedReport.warnings,
              errors: normalizedReport.errors,
            },
            null,
            2,
          )}
        </pre>
      )}
      <BoundaryPreflightPanel report={normalizedReport} />
      <CredentialPreflightPanel report={normalizedReport} />
    </div>
  );
}

type GraphNode = {
  id: string;
  type?: string;
  title?: string;
  data?: Record<string, unknown>;
  position?: WorkflowNodePosition;
  supported?: boolean;
};

type GraphEdge = {
  id?: string;
  source?: string;
  target?: string;
  source_handle?: string | null;
  target_handle?: string | null;
  valid?: boolean;
};

type EditableGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type WorkflowNodePosition = {
  x: number;
  y: number;
};

const EDITABLE_NODE_TYPES = [
  "start",
  "answer",
  "end",
  "condition",
  "human_approval",
  "variable_assign",
  "template_transform",
  "parameter_extractor",
  "question_classifier",
  "variable_aggregator",
  "list_operator",
  "iteration",
  "document_extractor",
  "knowledge_retrieval",
  "sub_workflow",
  "llm",
  "tool_call",
  "http_request",
] as const;

type EditableNodeType = typeof EDITABLE_NODE_TYPES[number];

type WorkflowNodePaletteGroup = {
  id: string;
  label: string;
  types: EditableNodeType[];
};

const WORKFLOW_NODE_PALETTE_GROUPS: WorkflowNodePaletteGroup[] = [
  { id: "io", label: "Input / Output", types: ["start", "answer", "end"] },
  {
    id: "logic",
    label: "Logic",
    types: ["condition", "human_approval", "question_classifier", "iteration", "list_operator"],
  },
  {
    id: "data",
    label: "Data",
    types: [
      "variable_assign",
      "template_transform",
      "parameter_extractor",
      "variable_aggregator",
      "document_extractor",
    ],
  },
  {
    id: "ai",
    label: "Knowledge / AI",
    types: ["knowledge_retrieval", "llm"],
  },
  {
    id: "integrations",
    label: "Integrations",
    types: ["tool_call", "http_request", "sub_workflow"],
  },
];

function workflowNodeTypeFallbackLabel(type: string) {
  return type
    .split(/[_-]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function workflowNodeTypeLabel(type: string, t?: WorkflowTranslator) {
  const fallback = workflowNodeTypeFallbackLabel(type);
  const key = type.replaceAll("-", "_").toLowerCase();
  return t ? translatedWorkflowLabel(t, `workflowPlugin.editor.nodeTypes.${key}`, fallback) : fallback;
}

function workflowNodePaletteGroupLabel(group: WorkflowNodePaletteGroup, t: WorkflowTranslator) {
  return translatedWorkflowLabel(t, `workflowPlugin.editor.palette.groups.${group.id}`, group.label);
}

function workflowNodePaletteGroups(query: string, t: WorkflowTranslator): WorkflowNodePaletteGroup[] {
  const normalizedQuery = query.trim().toLowerCase();
  const groups = WORKFLOW_NODE_PALETTE_GROUPS.map((group) => ({
    ...group,
    label: workflowNodePaletteGroupLabel(group, t),
  }));
  if (!normalizedQuery) return groups;
  return groups
    .map((group) => ({
      ...group,
      types: group.types.filter((type) => {
        const label = workflowNodeTypeLabel(type, t).toLowerCase();
        return type.includes(normalizedQuery) || label.includes(normalizedQuery);
      }),
    }))
    .filter((group) => group.types.length > 0);
}

function workflowCompatibilityStatusLabel(status: string, t: WorkflowTranslator) {
  return translatedWorkflowLabel(t, `workflowPlugin.editor.common.${status}`, workflowNodeTypeFallbackLabel(status));
}

function workflowCompatibilityRuntimeLabel(runtime: string, t: WorkflowTranslator) {
  return translatedWorkflowLabel(t, `workflowPlugin.editor.compatibility.runtime.${runtime}`, workflowNodeTypeFallbackLabel(runtime));
}

function workflowCompatibilityRequirementLabel(requirement: string, t: WorkflowTranslator) {
  const key = requirement
    .trim()
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return translatedWorkflowLabel(t, `workflowPlugin.editor.compatibility.requirements.${key}`, requirement);
}

function workflowListOperatorPresetLabel(presetId: string, fallback: string, t: WorkflowTranslator) {
  return translatedWorkflowLabel(t, `workflowPlugin.editor.palette.presets.${presetId}`, fallback);
}

const WORKFLOW_CANVAS_DRAG_TYPE = "application/x-lambchat-workflow-node";

const LIST_OPERATOR_PRESETS = [
  {
    id: "first",
    label: "First item",
    data: { variable_selector: ["items"], operation: "first", output_key: "result" },
  },
  {
    id: "sort_desc",
    label: "Sort items",
    data: { variable_selector: ["items"], operation: "sort", sort_by: "score", direction: "desc", output_key: "result" },
  },
  {
    id: "sum_field",
    label: "Sum field",
    data: { variable_selector: ["items"], operation: "sum", value_key: "score", output_key: "result" },
  },
  {
    id: "pluck_field",
    label: "Pluck field",
    data: { variable_selector: ["items"], operation: "pluck", value_key: "profile.name", output_key: "result" },
  },
  {
    id: "filter_conditions",
    label: "Filter items",
    data: {
      variable_selector: ["items"],
      operation: "filter",
      logical_operator: "and",
      conditions: [
        { variable_selector: ["item", "score"], operator: ">=", value: "{{min_score}}" },
      ],
      output_key: "result",
    },
  },
  {
    id: "find_match",
    label: "Find match",
    data: {
      variable_selector: ["items"],
      operation: "find",
      logical_operator: "and",
      conditions: [
        { variable_selector: ["item", "score"], operator: ">=", value: "{{min_score}}" },
      ],
      output_key: "result",
    },
  },
  {
    id: "count_matches",
    label: "Count matches",
    data: {
      variable_selector: ["items"],
      operation: "count_matching",
      logical_operator: "and",
      conditions: [
        { variable_selector: ["item", "score"], operator: ">=", value: "{{min_score}}" },
      ],
      output_key: "result",
    },
  },
] as const;

const LIST_OPERATOR_CONDITION_OPERATIONS = new Set([
  "filter",
  "where",
  "select",
  "keep",
  "find",
  "find_first",
  "first_match",
  "first-match",
  "first_where",
  "first-where",
  "any",
  "some",
  "has_match",
  "has-match",
  "exists_match",
  "exists-match",
  "all",
  "every",
  "none",
  "not_any",
  "not-any",
  "no_match",
  "no-match",
  "count_matching",
  "count-matching",
  "count_matches",
  "count-matches",
  "count_where",
  "count-where",
]);

const VARIABLE_AGGREGATOR_SELECTOR_KEYS = [
  "variables",
  "input_variables",
  "inputVariables",
  "selectors",
  "items",
  "variable_groups",
  "variableGroups",
  "groups",
] as const;

const VARIABLE_AGGREGATOR_WRAPPER_KEYS = ["value", "values", "variables", "selectors", "items", "children", "group"] as const;

const VARIABLE_AGGREGATOR_CLEAR_KEYS = [
  "input_variables",
  "inputVariables",
  "selectors",
  "items",
  "variable_groups",
  "variableGroups",
  "groups",
] as const;

const CONDITION_BRANCH_HANDLES = ["true", "false"] as const;

function fallbackWorkflowNodePosition(index: number): WorkflowNodePosition {
  return {
    x: (index % 3) * 280,
    y: Math.floor(index / 3) * 170,
  };
}

function nextWorkflowNodeId(graph: EditableGraph) {
  const existingIds = new Set(graph.nodes.map((node) => (node.id || "").trim()).filter(Boolean));
  const highestGeneratedNumber = graph.nodes.reduce((highest, node) => {
    const match = /^node_(\d+)$/.exec((node.id || "").trim());
    if (!match) return highest;
    return Math.max(highest, Number.parseInt(match[1], 10));
  }, 0);
  let nextNumber = Math.max(graph.nodes.length + 1, highestGeneratedNumber + 1);
  while (existingIds.has(`node_${nextNumber}`)) {
    nextNumber += 1;
  }
  return `node_${nextNumber}`;
}

function workflowNodePosition(value: unknown, index: number): WorkflowNodePosition {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const position = value as Record<string, unknown>;
    const x = position.x;
    const y = position.y;
    if (
      typeof x === "number" &&
      Number.isFinite(x) &&
      typeof y === "number" &&
      Number.isFinite(y)
    ) {
      return { x, y };
    }
  }
  return fallbackWorkflowNodePosition(index);
}

function workflowGraph(version?: WorkflowVersionSummary | null) {
  const graph = version?.internal_model?.graph;
  if (!graph || typeof graph !== "object") return { nodes: [], edges: [] };
  const data = graph as { nodes?: unknown; edges?: unknown };
  const nodes = Array.isArray(data.nodes) ? (data.nodes as GraphNode[]) : [];
  const edges = Array.isArray(data.edges) ? (data.edges as GraphEdge[]) : [];
  return { nodes, edges };
}

function graphFromVersion(version?: WorkflowVersionSummary | null): EditableGraph {
  const { nodes, edges } = workflowGraph(version);
  return {
    nodes: nodes.map((node, index) => ({
      id: node.id,
      type: node.type || "answer",
      title: node.title || node.id,
      data: node.data && typeof node.data === "object" ? node.data : {},
      position: workflowNodePosition(node.position, index),
      supported: node.supported,
    })),
    edges: edges.map((edge, index) => ({
      id: edge.id || `edge_${index + 1}`,
      source: edge.source || "",
      target: edge.target || "",
      source_handle: edge.source_handle ?? null,
      target_handle: edge.target_handle ?? null,
      valid: edge.valid !== false,
    })),
  };
}

function graphToWorkflowDsl(graph: EditableGraph) {
  return {
    version: "0.3.0",
    workflow: {
      nodes: graph.nodes.map((node, index) => ({
        id: node.id || `node_${index + 1}`,
        type: node.type || "answer",
        position: node.position || fallbackWorkflowNodePosition(index),
        data: {
          ...(node.data || {}),
          title: node.title || node.id || `Node ${index + 1}`,
        },
      })),
      edges: graph.edges.map((edge, index) => ({
        id: edge.id || `edge_${index + 1}`,
        source: edge.source || "",
        target: edge.target || "",
        sourceHandle: edge.source_handle || undefined,
        targetHandle: edge.target_handle || undefined,
      })),
    },
  };
}

function validateEditableGraph(graph: EditableGraph) {
  const issues: string[] = [];
  const nodeIds = new Set<string>();
  const nodeTypesById = new Map<string, string>();
  let startCount = 0;
  graph.nodes.forEach((node, index) => {
    const nodeId = (node.id || "").trim();
    if (!nodeId) {
      issues.push(`Node ${index + 1} is missing an id.`);
      return;
    }
    if (nodeIds.has(nodeId)) {
      issues.push(`Node id "${nodeId}" is duplicated.`);
    }
    nodeIds.add(nodeId);
    const nodeType = node.type || "answer";
    nodeTypesById.set(nodeId, nodeType);
    if (nodeType === "start") startCount += 1;
  });
  if (graph.nodes.length > 0 && startCount === 0) issues.push("Graph must include one start node.");
  if (startCount > 1) issues.push("Graph can include only one start node.");
  graph.edges.forEach((edge, index) => {
    const label = edge.id || `edge ${index + 1}`;
    const source = (edge.source || "").trim();
    const target = (edge.target || "").trim();
    if (edge.valid === false) issues.push(`Edge ${label} is marked invalid.`);
    if (!source) issues.push(`Edge ${label} is missing a source node.`);
    else if (!nodeIds.has(source)) issues.push(`Edge ${label} source "${source}" does not exist.`);
    if (!target) issues.push(`Edge ${label} is missing a target node.`);
    else if (!nodeIds.has(target)) issues.push(`Edge ${label} target "${target}" does not exist.`);
    const boundaryIssue = workflowEdgeBoundaryIssue(nodeTypesById, source, target, label);
    if (boundaryIssue) issues.push(boundaryIssue);
  });
  return issues;
}

function workflowEdgeBoundaryIssue(
  nodeTypesById: Map<string, string>,
  source: string,
  target: string,
  label: string,
) {
  if (target && nodeTypesById.get(target) === "start") {
    return `Edge ${label} targets entry node "${target}".`;
  }
  const sourceType = nodeTypesById.get(source);
  const targetType = nodeTypesById.get(target);
  if (source && (sourceType === "end" || (sourceType === "answer" && targetType !== "end"))) {
    return `Edge ${label} starts from exit node "${source}".`;
  }
  return null;
}

function nodeDataText(node: GraphNode | null) {
  return JSON.stringify(node?.data || {}, null, 2);
}

function selectorText(value: unknown) {
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim()).join(".");
  return typeof value === "string" ? value : "";
}

function selectorFromText(value: string) {
  return value.split(".").map((item) => item.trim()).filter(Boolean);
}

function stringListText(value: unknown) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()).join(", ") : "";
}

function stringListFromText(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function dataTextValue(data: Record<string, unknown> | undefined, key: string) {
  const value = data?.[key];
  return typeof value === "string" ? value : "";
}

function structuredValueText(value: unknown) {
  if (typeof value === "string") return value;
  if (value === undefined || value === null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function structuredValueFromText(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
}

function httpRequestBodyText(data: Record<string, unknown> | undefined) {
  return structuredValueText(data?.request_body ?? data?.requestBody ?? data?.body);
}

function httpRequestBodyPatch(value: string): Record<string, unknown> {
  return { request_body: structuredValueFromText(value), body: undefined, requestBody: undefined };
}

function knowledgeFilterPatch(key: "dataset_filter" | "metadata_filter", value: string): Record<string, unknown> {
  if (key === "dataset_filter") {
    return { dataset_filter: structuredValueFromText(value), datasetFilter: undefined };
  }
  return { metadata_filter: structuredValueFromText(value), metadataFilter: undefined };
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function httpAuthorizationValue(data: Record<string, unknown> | undefined) {
  return recordValue(data?.authorization ?? data?.auth);
}

function httpCredentialRefText(data: Record<string, unknown> | undefined) {
  const auth = httpAuthorizationValue(data);
  const value = data?.credential_ref ?? data?.credentialRef ?? data?.credential_id ?? data?.credentialId
    ?? auth.credential_ref ?? auth.credentialRef ?? auth.credential_id ?? auth.credentialId;
  return typeof value === "string" ? value : "";
}

function httpAuthorizationTextValue(data: Record<string, unknown> | undefined, key: string) {
  const auth = httpAuthorizationValue(data);
  const value = key === "type"
    ? auth.type ?? auth.scheme ?? auth.auth_type ?? auth.authType
    : key === "header_name"
      ? auth.header_name ?? auth.headerName ?? auth.header ?? auth.name
      : key === "prefix"
        ? auth.prefix ?? auth.value_prefix ?? auth.valuePrefix
        : auth[key];
  return typeof value === "string" ? value : "";
}

function httpCredentialRefPatch(value: string): Record<string, unknown> {
  return { credential_ref: value, credentialRef: undefined, credential_id: undefined, credentialId: undefined };
}

function httpAuthorizationPatch(data: Record<string, unknown> | undefined, patch: Record<string, unknown>): Record<string, unknown> {
  return { authorization: { ...httpAuthorizationValue(data), ...patch }, auth: undefined };
}

function llmModelValue(data: Record<string, unknown> | undefined) {
  return recordValue(data?.model);
}

function llmModelTextValue(data: Record<string, unknown> | undefined, key: string) {
  const model = llmModelValue(data);
  const value = key === "name"
    ? model.name ?? model.model ?? data?.model_name ?? data?.modelName
    : key === "provider"
      ? model.provider ?? data?.provider
      : key === "provider_credential_id"
        ? model.provider_credential_id ?? model.providerCredentialId ?? data?.provider_credential_id ?? data?.providerCredentialId
        : model[key] ?? data?.[key];
  return typeof value === "string" ? value : "";
}

function llmTextValue(data: Record<string, unknown> | undefined, key: string) {
  const value = data?.[key];
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "";
}

function llmModelPatch(data: Record<string, unknown> | undefined, patch: Record<string, unknown>): Record<string, unknown> {
  return { model: { ...llmModelValue(data), ...patch } };
}

function objectList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function descriptorRowTextValue(value: Record<string, unknown>, key: string) {
  const rowValue = value[key];
  if (key === "value_selector") return selectorText(rowValue);
  return typeof rowValue === "string" ? rowValue : "";
}

function toolConfigurationFallback(): Record<string, unknown> {
  return { name: "query", value_selector: ["message"] };
}

function httpHeaderFallback(): Record<string, unknown> {
  return { name: "X-Trace", value: "{{trace_id}}" };
}

function httpQueryFallback(): Record<string, unknown> {
  return { name: "q", value: "{{message}}" };
}

function firstObjectTextValue(value: unknown, key: string) {
  const objectValue = objectList(value)[0]?.[key];
  if (Array.isArray(objectValue)) return selectorText(objectValue);
  return typeof objectValue === "string" ? objectValue : "";
}

function objectListWithFirstValue(value: unknown, fallback: Record<string, unknown>, key: string, nextValue: unknown) {
  const objects = objectList(value);
  const firstObject = objects[0] ?? fallback;
  return [{ ...firstObject, [key]: nextValue }, ...objects.slice(1)];
}

function objectRows(value: unknown, fallback: Record<string, unknown>): Array<Record<string, unknown>> {
  const objects = objectList(value);
  return objects.length > 0 ? objects : [{ ...fallback }];
}

function objectRowTextValue(value: Record<string, unknown>, key: string) {
  const rowValue = value[key];
  return typeof rowValue === "string" ? rowValue : "";
}

function objectRowsWithValue(value: unknown, index: number, fallback: Record<string, unknown>, key: string, nextValue: unknown) {
  return objectRows(value, fallback).map((row, rowIndex) => (
    rowIndex === index ? { ...fallback, ...row, [key]: nextValue } : row
  ));
}

function objectRowsWithAddedRow(value: unknown, fallback: Record<string, unknown>) {
  return [...objectRows(value, fallback), { ...fallback }];
}

function objectRowsWithoutIndex(value: unknown, index: number, fallback: Record<string, unknown>) {
  const rows = objectRows(value, fallback).filter((_, rowIndex) => rowIndex !== index);
  return rows.length > 0 ? rows : [{ ...fallback }];
}

const WORKFLOW_CONTRACT_FIELD_TYPES = ["string", "number", "integer", "boolean", "object", "array"] as const;

function inputContractFallback(defaultText: WorkflowDefaultText): Record<string, unknown> {
  return { name: "message", type: "string", required: true, description: defaultText.entryMessageDescription };
}

function outputContractFallback(defaultText: WorkflowDefaultText): Record<string, unknown> {
  return { name: "answer", type: "string", value: "{{message}}", description: defaultText.workflowOutputDescription };
}

function contractFieldName(row: Record<string, unknown>) {
  return String(row.name ?? row.variable ?? row.key ?? row.output_key ?? row.outputKey ?? "").trim();
}

function contractFieldType(row: Record<string, unknown>) {
  const rawType = String(
    row.type
      ?? row.input_type
      ?? row.inputType
      ?? row.output_type
      ?? row.outputType
      ?? row.data_type
      ?? row.dataType
      ?? "string",
  ).trim();
  return WORKFLOW_CONTRACT_FIELD_TYPES.includes(rawType as (typeof WORKFLOW_CONTRACT_FIELD_TYPES)[number])
    ? rawType
    : "string";
}

function contractFieldBooleanValue(row: Record<string, unknown>, key: string) {
  return row[key] === true;
}

function contractFieldDefaultText(row: Record<string, unknown>) {
  return structuredValueText(row.default ?? row.default_value ?? row.defaultValue);
}

function contractFieldSchema(row: Record<string, unknown>) {
  const schema: Record<string, unknown> = { type: contractFieldType(row) };
  const description = descriptorRowTextValue(row, "description") || descriptorRowTextValue(row, "label");
  const defaultValue = row.default ?? row.default_value ?? row.defaultValue;
  if (description) schema.description = description;
  if (defaultValue !== undefined && defaultValue !== "") schema.default = defaultValue;
  if (schema.type === "object") schema.additionalProperties = true;
  if (schema.type === "array") schema.items = {};
  return schema;
}

function schemaFromContractRows(rows: Array<Record<string, unknown>>, requiredKey?: string) {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  rows.forEach((row) => {
    const name = contractFieldName(row);
    if (!name) return;
    properties[name] = contractFieldSchema(row);
    if (requiredKey && contractFieldBooleanValue(row, requiredKey)) required.push(name);
  });
  const schema: Record<string, unknown> = { type: "object", properties, additionalProperties: true };
  if (required.length > 0) schema.required = Array.from(new Set(required)).sort();
  return schema;
}

function inputContractRows(data: Record<string, unknown>, defaultText: WorkflowDefaultText) {
  return objectRows(data.variables ?? data.inputs, inputContractFallback(defaultText));
}

function outputContractRows(data: Record<string, unknown>, defaultText: WorkflowDefaultText) {
  return objectRows(data.outputs, outputContractFallback(defaultText));
}

function inputContractPatch(rows: Array<Record<string, unknown>>): Record<string, unknown> {
  return {
    variables: rows,
    input_schema: schemaFromContractRows(rows, "required"),
    inputs: undefined,
    inputSchema: undefined,
    parameters: undefined,
  };
}

function outputContractPatch(rows: Array<Record<string, unknown>>): Record<string, unknown> {
  return {
    outputs: rows,
    output_schema: schemaFromContractRows(rows),
    outputSchema: undefined,
    schema: undefined,
  };
}

function answerOutputContractRow(data: Record<string, unknown>, defaultText: WorkflowDefaultText) {
  const outputSchema = recordValue(data.output_schema ?? data.outputSchema ?? data.schema);
  const properties = recordValue(outputSchema.properties);
  const answerSchema = recordValue(properties.answer);
  return {
    name: "answer",
    type: contractFieldType(answerSchema),
    description: descriptorRowTextValue(answerSchema, "description") || defaultText.answerTextDescription,
  };
}

function answerOutputContractPatch(row: Record<string, unknown>): Record<string, unknown> {
  return {
    outputs: undefined,
    output_schema: schemaFromContractRows([{ ...row, name: "answer" }]),
    outputSchema: undefined,
    schema: undefined,
  };
}

type WorkflowBoundarySummaryItem = {
  id: string;
  label: string;
  fields: number;
  role: "Entry" | "Exit";
};

function workflowBoundarySummaryItems(graph: EditableGraph, defaultText: WorkflowDefaultText): WorkflowBoundarySummaryItem[] {
  const items: WorkflowBoundarySummaryItem[] = [];
  for (const node of graph.nodes) {
    if (node.type === "start") {
      items.push({
        id: node.id,
        label: node.title || node.id,
        fields: inputContractRows(node.data || {}, defaultText).filter((field) => contractFieldName(field)).length,
        role: "Entry",
      });
      continue;
    }
    if (node.type === "answer") {
      items.push({
        id: node.id,
        label: node.title || node.id,
        fields: contractFieldName(answerOutputContractRow(node.data || {}, defaultText)) ? 1 : 0,
        role: "Exit",
      });
      continue;
    }
    if (node.type === "end") {
      items.push({
        id: node.id,
        label: node.title || node.id,
        fields: outputContractRows(node.data || {}, defaultText).filter((field) => contractFieldName(field)).length,
        role: "Exit",
      });
    }
  }
  return items;
}

function WorkflowBoundarySummary({
  graph,
  onSelectNode,
}: {
  graph: EditableGraph;
  onSelectNode: (nodeId: string) => void;
}) {
  const { t } = useTranslation();
  const defaultText = useMemo(() => workflowDefaultText(t), [t]);
  const items = workflowBoundarySummaryItems(graph, defaultText);
  const entryItems = items.filter((item) => item.role === "Entry");
  const exitItems = items.filter((item) => item.role === "Exit");
  const inputFieldCount = entryItems.reduce((total, item) => total + item.fields, 0);
  const outputFieldCount = exitItems.reduce((total, item) => total + item.fields, 0);
  const stats = [
    [t("workflowPlugin.editor.boundaries.entries"), entryItems.length],
    [t("workflowPlugin.editor.boundaries.exits"), exitItems.length],
    [t("workflowPlugin.editor.boundaries.inputFields"), inputFieldCount],
    [t("workflowPlugin.editor.boundaries.outputFields"), outputFieldCount],
  ] as const;
  return (
    <div
      className="mb-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2"
      data-testid="workflow-boundary-summary"
    >
      <div className="mb-2 flex items-center gap-2 text-xs font-medium">
        <GitBranch size={13} className="text-[var(--theme-text-secondary)]" />
        <span>{t("workflowPlugin.editor.boundaries.title")}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-4">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1.5">
            <div className="text-[10px] uppercase text-[var(--theme-text-secondary)]">{label}</div>
            <div className="text-sm font-medium">{value}</div>
          </div>
        ))}
      </div>
      {items.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {items.map((item) => {
            const roleLabel = item.role === "Entry"
              ? t("workflowPlugin.editor.boundaries.roleEntry")
              : t("workflowPlugin.editor.boundaries.roleExit");
            return (
              <button
                key={`${item.role}-${item.id}`}
                type="button"
                onClick={() => onSelectNode(item.id)}
                className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1 text-xs hover:border-[var(--theme-primary)]"
                title={`${roleLabel}: ${item.id}`}
              >
                <span className={item.role === "Entry" ? "text-[var(--theme-primary)]" : "text-emerald-600"}>{roleLabel}</span>
                <span className="max-w-36 truncate">{item.label}</span>
                <span className="text-[var(--theme-text-secondary)]">{item.fields}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function conditionCaseFallback(index = 0): Record<string, unknown> {
  return {
    case_id: `case_${index + 1}`,
    logical_operator: "and",
    conditions: [{ variable_selector: ["message"], operator: "not_empty" }],
  };
}

function conditionCaseRows(data: Record<string, unknown> | undefined): Array<Record<string, unknown>> {
  const cases = objectList(data?.cases);
  if (cases.length > 0) return cases;
  const branches = objectList(data?.branches);
  return branches.length > 0 ? branches : [conditionCaseFallback()];
}

function conditionCaseId(conditionCase: Record<string, unknown>, index: number) {
  const rawId = conditionCase.id ?? conditionCase.case_id ?? conditionCase.caseId ?? conditionCase.handle;
  if (typeof rawId === "string" || typeof rawId === "number") {
    const text = String(rawId).trim();
    if (text) return text;
  }
  return `case_${index + 1}`;
}

function conditionCaseCondition(conditionCase: Record<string, unknown>) {
  return objectList(conditionCase.conditions)[0] ?? { variable_selector: ["message"], operator: "not_empty" };
}

function conditionCaseConditionValue(conditionCase: Record<string, unknown>, key: string) {
  const condition = conditionCaseCondition(conditionCase);
  const value = key === "operator" ? (condition.comparison_operator ?? condition.operator) : condition[key];
  if (Array.isArray(value)) return selectorText(value);
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function conditionCasesPatch(cases: Array<Record<string, unknown>>): Record<string, unknown> {
  return { cases, branches: undefined };
}

function conditionCasesWithCaseId(data: Record<string, unknown> | undefined, index: number, nextValue: string) {
  return conditionCaseRows(data).map((conditionCase, caseIndex) => (
    caseIndex === index ? { ...conditionCase, id: undefined, case_id: nextValue, handle: undefined } : conditionCase
  ));
}

function conditionCasesWithConditionValue(data: Record<string, unknown> | undefined, index: number, key: string, nextValue: unknown) {
  return conditionCaseRows(data).map((conditionCase, caseIndex) => {
    if (caseIndex !== index) return conditionCase;
    const conditions = objectList(conditionCase.conditions);
    const firstCondition = conditions[0] ?? conditionCaseCondition(conditionCase);
    const patch = key === "operator"
      ? { operator: nextValue, comparison_operator: nextValue }
      : key === "variable_selector"
        ? { variable_selector: nextValue, variable: undefined }
        : key === "value"
          ? { value: nextValue, value_selector: undefined }
          : { [key]: nextValue };
    return { ...conditionCase, conditions: [{ ...firstCondition, ...patch }, ...conditions.slice(1)] };
  });
}

function conditionCasesWithAddedCase(data: Record<string, unknown> | undefined) {
  const cases = conditionCaseRows(data);
  return [...cases, conditionCaseFallback(cases.length)];
}

function conditionCasesWithoutIndex(data: Record<string, unknown> | undefined, index: number) {
  const cases = conditionCaseRows(data).filter((_, caseIndex) => caseIndex !== index);
  return cases.length > 0 ? cases : [conditionCaseFallback()];
}

function parameterExtractorParameterFallback(): Record<string, unknown> {
  return { name: "topic", type: "string", description: "" };
}

function questionClassifierClassFallback(): Record<string, unknown> {
  return { id: "general", name: "General" };
}

function questionClassifierClassId(classifierClass: Record<string, unknown>, index: number) {
  const rawId = classifierClass.id ?? classifierClass.class_id ?? classifierClass.classId ?? classifierClass.value ?? classifierClass.name;
  if (typeof rawId === "string" || typeof rawId === "number") {
    const text = String(rawId).trim();
    if (text) return text;
  }
  return `class_${index + 1}`;
}

function normalizedBranchHandle(value: unknown) {
  return String(value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function edgeForSourceHandle(edges: GraphEdge[], source: string, sourceHandle: string) {
  const exactEdge = edges.find((edge) => edge.source === source && edge.source_handle === sourceHandle);
  if (exactEdge) return exactEdge;
  const normalizedHandle = normalizedBranchHandle(sourceHandle);
  return edges.find((edge) => edge.source === source && normalizedBranchHandle(edge.source_handle) === normalizedHandle) ?? null;
}

function variableAggregatorSelectorFallback(): Record<string, unknown> {
  return { variable_selector: ["message"] };
}

function variableAggregatorSelectorRows(data: Record<string, unknown> | undefined): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  for (const key of VARIABLE_AGGREGATOR_SELECTOR_KEYS) {
    rows.push(...variableAggregatorSelectorRowsFromValue(data?.[key]));
  }
  return rows.length > 0 ? rows : [variableAggregatorSelectorFallback()];
}

function variableAggregatorSelectorRowsFromValue(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item === "string" || typeof item === "number")) {
      return [{ variable_selector: value }];
    }
    const rows: Array<Record<string, unknown>> = [];
    for (const item of value) rows.push(...variableAggregatorSelectorRowsFromValue(item));
    return rows;
  }
  if (value && typeof value === "object") {
    const descriptor = value as Record<string, unknown>;
    const selector = descriptor.variable_selector ?? descriptor.variableSelector ?? descriptor.value_selector ?? descriptor.valueSelector ?? descriptor.input_selector ?? descriptor.inputSelector ?? descriptor.source_selector ?? descriptor.sourceSelector ?? descriptor.selector ?? descriptor.variable ?? descriptor.name;
    if (selector !== undefined && selector !== null && selector !== "") {
      return [{ ...descriptor, variable_selector: selector }];
    }
    for (const key of VARIABLE_AGGREGATOR_WRAPPER_KEYS) {
      if (key in descriptor) return variableAggregatorSelectorRowsFromValue(descriptor[key]);
    }
  }
  if (typeof value === "string" && value.trim()) return [{ variable_selector: selectorFromText(value) }];
  return [];
}

function variableAggregatorSelectorValue(selector: Record<string, unknown>) {
  return selectorText(selector.variable_selector);
}

function variableAggregatorSelectorsWithValue(data: Record<string, unknown> | undefined, index: number, nextValue: unknown) {
  return variableAggregatorSelectorRows(data).map((selector, selectorIndex) => (
    selectorIndex === index ? { ...selector, variable_selector: nextValue } : selector
  ));
}

function variableAggregatorSelectorsWithAddedSelector(data: Record<string, unknown> | undefined) {
  return [...variableAggregatorSelectorRows(data), variableAggregatorSelectorFallback()];
}

function variableAggregatorSelectorsWithoutIndex(data: Record<string, unknown> | undefined, index: number) {
  const selectors = variableAggregatorSelectorRows(data).filter((_, selectorIndex) => selectorIndex !== index);
  return selectors.length > 0 ? selectors : [variableAggregatorSelectorFallback()];
}

function variableAggregatorSelectorPatch(variables: Array<Record<string, unknown>>): Record<string, unknown> {
  const patch: Record<string, unknown> = { variables };
  for (const key of VARIABLE_AGGREGATOR_CLEAR_KEYS) patch[key] = [];
  return patch;
}

function listOperatorConditionFallback(): Record<string, unknown> {
  return { variable_selector: ["item", "score"], operator: ">=", value: "{{min_score}}" };
}

function listOperatorConditionRows(value: unknown): Array<Record<string, unknown>> {
  const conditions = objectList(value);
  return conditions.length > 0 ? conditions : [listOperatorConditionFallback()];
}

function listOperatorConditionValue(condition: Record<string, unknown>, key: string) {
  const conditionValue = condition[key];
  if (Array.isArray(conditionValue)) return selectorText(conditionValue);
  return typeof conditionValue === "string" ? conditionValue : "";
}

function listOperatorConditionsWithValue(value: unknown, index: number, key: string, nextValue: unknown) {
  return listOperatorConditionRows(value).map((condition, conditionIndex) => (
    conditionIndex === index ? { ...listOperatorConditionFallback(), ...condition, [key]: nextValue } : condition
  ));
}

function listOperatorConditionsWithAddedCondition(value: unknown) {
  return [...listOperatorConditionRows(value), listOperatorConditionFallback()];
}

function listOperatorConditionsWithoutIndex(value: unknown, index: number) {
  const conditions = listOperatorConditionRows(value).filter((_, conditionIndex) => conditionIndex !== index);
  return conditions.length > 0 ? conditions : [listOperatorConditionFallback()];
}

function assignmentEntryName(value: unknown) {
  const assignments = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  return Object.keys(assignments)[0] ?? "value";
}

function assignmentEntryRawValue(value: unknown) {
  const assignments = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  return assignments[assignmentEntryName(assignments)] ?? "";
}

function assignmentEntryTextValue(value: unknown) {
  const entryValue = assignmentEntryRawValue(value);
  return typeof entryValue === "string" ? entryValue : "";
}

function assignmentsWithEntryName(value: unknown, nextName: string) {
  const currentName = assignmentEntryName(value);
  const currentValue = assignmentEntryRawValue(value);
  const name = nextName.trim() || currentName;
  return { [name]: currentValue };
}

function assignmentsWithEntryValue(value: unknown, nextValue: string) {
  return { [assignmentEntryName(value)]: nextValue };
}

function listOperatorFieldKey(data: Record<string, unknown> | undefined) {
  return data?.operation === "sort" ? "sort_by" : "value_key";
}

function listOperatorUsesConditions(data: Record<string, unknown> | undefined) {
  return LIST_OPERATOR_CONDITION_OPERATIONS.has(dataTextValue(data, "operation"));
}

function defaultNodeData(
  type: string,
  title: string,
  defaultText: WorkflowDefaultText,
  presetId?: string,
): Record<string, unknown> {
  if (type === "start") {
    const variables = [inputContractFallback(defaultText)];
    return { title, variables, input_schema: schemaFromContractRows(variables, "required") };
  }
  if (type === "answer") {
    return {
      title,
      answer: defaultText.sampleAnswer,
      output_schema: schemaFromContractRows([{ name: "answer", type: "string", description: defaultText.answerTextDescription }]),
    };
  }
  if (type === "end") {
    const outputs = [outputContractFallback(defaultText)];
    return { title, outputs, output_schema: schemaFromContractRows(outputs) };
  }
  if (type === "condition") {
    return {
      title,
      conditions: [{ variable: "message", operator: "not_empty" }],
    };
  }
  if (type === "human_approval") {
    return {
      title,
      instructions: defaultText.approveInstruction,
      assignee: "",
      output_key: "approval",
    };
  }
  if (type === "variable_assign") return { title, assignments: { value: "{{message}}" } };
  if (type === "template_transform") return { title, template: defaultText.sampleAnswer, output_key: "result" };
  if (type === "parameter_extractor") {
    return {
      title,
      query: "{{message}}",
      parameters: [{ name: "topic", type: "string" }],
      output_key: "parameters",
    };
  }
  if (type === "question_classifier") {
    return {
      title,
      query: "{{message}}",
      classes: [
        { id: "general", name: defaultText.generalClass },
        { id: "support", name: defaultText.supportClass },
      ],
      output_key: "question_class",
    };
  }
  if (type === "variable_aggregator") {
    return {
      title,
      output_key: "result",
      variables: [{ variable_selector: ["message"] }],
    };
  }
  if (type === "list_operator") {
    const preset = LIST_OPERATOR_PRESETS.find((item) => item.id === presetId) ?? LIST_OPERATOR_PRESETS[0];
    return { title, ...preset.data };
  }
  if (type === "iteration") {
    return { title, iterator_selector: ["items"], item_template: "{{item}}", output_key: "results" };
  }
  if (type === "document_extractor") {
    return { title, variable_selector: ["attachment"], output_key: "document_text" };
  }
  if (type === "knowledge_retrieval") {
    return { title, query_variable_selector: ["message"], dataset_ids: [], output_key: "knowledge" };
  }
  if (type === "sub_workflow") {
    return { title, workflow_id: "", version_id: "", inputs: { message: "{{message}}" }, output_key: "child" };
  }
  if (type === "llm") return { title, prompt_template: defaultText.sampleAnswer };
  if (type === "tool_call") {
    return {
      title,
      tool_name: "workflow_list",
      tool_configurations: [
        { name: "scope", value: "published" },
        { name: "query", value_selector: ["message"] },
      ],
    };
  }
  if (type === "http_request") {
    return {
      title,
      request_method: "GET",
      endpoint: "https://example.com",
      header_parameters: [{ name: "X-Trace", value: "{{trace_id}}" }],
      query_parameters: [{ name: "q", value: "{{message}}" }],
      request_body: {},
    };
  }
  return { title };
}

function graphWithNodePatch(graph: EditableGraph, nodeId: string, patch: Partial<GraphNode>) {
  const nextId = patch.id ?? nodeId;
  return {
    nodes: graph.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch, id: nextId } : node)),
    edges: graph.edges.map((edge) => ({
      ...edge,
      source: edge.source === nodeId ? nextId : edge.source,
      target: edge.target === nodeId ? nextId : edge.target,
    })),
  };
}

function LlmSettingsFields({
  data,
  onPatch,
  disabled,
}: {
  data: Record<string, unknown> | undefined;
  onPatch: (patch: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={llmModelTextValue(data, "provider")}
        onChange={(event) => onPatch(llmModelPatch(data, { provider: event.target.value }))}
        placeholder={t("workflowPlugin.editor.graph.llmProvider")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.llmProviderTitle")}
      />
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={llmModelTextValue(data, "name")}
        onChange={(event) => onPatch(llmModelPatch(data, { name: event.target.value, model: undefined }))}
        placeholder={t("workflowPlugin.editor.graph.llmModelName")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.llmModelNameTitle")}
      />
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={llmModelTextValue(data, "provider_credential_id")}
        onChange={(event) => onPatch(llmModelPatch(data, { provider_credential_id: event.target.value, providerCredentialId: undefined }))}
        placeholder={t("workflowPlugin.editor.graph.providerCredentialId")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.providerCredentialIdTitle")}
      />
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={httpCredentialRefText(data)}
        onChange={(event) => onPatch(httpCredentialRefPatch(event.target.value))}
        placeholder={t("workflowPlugin.editor.graph.credentialRef")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.llmCredentialRefTitle")}
      />
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={llmTextValue(data, "temperature")}
        onChange={(event) => onPatch({ temperature: structuredValueFromText(event.target.value) })}
        placeholder={t("workflowPlugin.editor.graph.temperature")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.llmTemperatureTitle")}
      />
      <input
        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
        value={llmTextValue(data, "max_tokens")}
        onChange={(event) => onPatch({ max_tokens: structuredValueFromText(event.target.value), maxTokens: undefined })}
        placeholder={t("workflowPlugin.editor.graph.maxTokens")}
        disabled={disabled}
        title={t("workflowPlugin.editor.graph.llmMaxTokensTitle")}
      />
    </div>
  );
}

type WorkflowCanvasNodeData = {
  nodeId: string;
  label: string;
  nodeType: string;
  boundaryRole: "entry" | "exit" | null;
  supported: boolean;
  sourceHandles: string[];
  runState?: WorkflowNodeRunState;
  [key: string]: unknown;
};

function workflowNodeBoundaryRole(nodeType?: string | null): WorkflowCanvasNodeData["boundaryRole"] {
  if (nodeType === "start") return "entry";
  if (nodeType === "answer" || nodeType === "end") return "exit";
  return null;
}

function workflowCanvasSourceHandles(node: GraphNode) {
  if (node.type === "condition") return ["true", "false"];
  if (node.type === "question_classifier") {
    const classes = node.data?.classes;
    if (Array.isArray(classes)) {
      return classes
        .map((item, index) => questionClassifierClassId(item, index))
        .filter(Boolean);
    }
  }
  return ["default"];
}

function WorkflowCanvasNode({
  data,
  selected,
}: {
  data: WorkflowCanvasNodeData;
  selected?: boolean;
}) {
  const { t } = useTranslation();
  const sourceHandles = data.sourceHandles.length > 0 ? data.sourceHandles : ["default"];
  const runState = data.runState;
  const boundaryRole = data.boundaryRole;
  return (
    <div
      data-testid={`workflow-canvas-node-${data.nodeId}`}
      className={`min-w-48 max-w-56 rounded-md border bg-[var(--theme-bg)] shadow-sm transition-colors ${
        selected
          ? "border-[var(--theme-primary)] ring-2 ring-[color-mix(in_srgb,var(--theme-primary)_18%,transparent)]"
          : workflowNodeRunStateClass(runState)
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        data-testid={`workflow-canvas-target-handle-${data.nodeId}`}
        className="!h-2.5 !w-2.5 !border-2 !border-[var(--theme-bg)] !bg-[var(--theme-primary)]"
      />
      <div className="border-b border-[var(--theme-border)] px-3 py-2">
        <div className="flex items-center gap-2">
          {data.supported ? (
            <CheckCircle2 className="shrink-0 text-emerald-500" size={15} />
          ) : (
            <AlertTriangle className="shrink-0 text-amber-500" size={15} />
          )}
          <span className="truncate text-sm font-medium">{data.label}</span>
        </div>
        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-[var(--theme-text-secondary)]">
          <span className="truncate">{data.nodeType}</span>
          {boundaryRole && (
            <span className="rounded-md border border-[var(--theme-primary)]/30 bg-[var(--theme-bg-secondary)] px-1.5 py-0.5 text-[var(--theme-primary)]">
              {boundaryRole === "entry" ? t("workflowPlugin.editor.boundaries.roleEntry") : t("workflowPlugin.editor.boundaries.roleExit")}
            </span>
          )}
          {runState && runState.eventCount > 0 && (
            <span
              data-testid={`workflow-canvas-run-status-${data.nodeId}`}
              className={`rounded-md border px-1.5 py-0.5 ${workflowNodeRunStatusClass(runState.status)}`}
            >
              {runState.status}
            </span>
          )}
        </div>
      </div>
      {runState && runState.eventCount > 0 && (
        <div className="border-b border-[var(--theme-border)] px-3 py-2 text-[10px] text-[var(--theme-text-secondary)]">
          <div className="flex items-center justify-between gap-2">
            <span>{t("workflowPlugin.editor.events.count", { count: runState.eventCount })}</span>
            {runState.durationMs !== null && <span>{runState.durationMs} ms</span>}
          </div>
          {runState.lastEventType && (
            <div className="mt-1 truncate" title={runState.lastEventType}>{runState.lastEventType}</div>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-1 px-3 py-2 text-[10px] text-[var(--theme-text-secondary)]">
        {sourceHandles.map((handle) => (
          <span key={handle} className="rounded bg-[var(--theme-bg-secondary)] px-1.5 py-0.5">
            {handle}
          </span>
        ))}
      </div>
      {sourceHandles.map((handle, index) => (
        <Handle
          key={handle}
          id={handle === "default" ? undefined : handle}
          type="source"
          position={Position.Bottom}
          data-testid={`workflow-canvas-source-handle-${data.nodeId}-${handle}`}
          style={{
            left: `${((index + 1) / (sourceHandles.length + 1)) * 100}%`,
          }}
          className="!h-2.5 !w-2.5 !border-2 !border-[var(--theme-bg)] !bg-[var(--theme-primary)]"
        />
      ))}
    </div>
  );
}

const workflowCanvasNodeTypes = { workflow: WorkflowCanvasNode };

function workflowCanvasNodes(
  graph: EditableGraph,
  selectedNodeId: string | null,
  nodeRunStates: Record<string, WorkflowNodeRunState>,
  liveNodePositions: Record<string, WorkflowNodePosition>,
): Node<WorkflowCanvasNodeData>[] {
  return graph.nodes.map((node, index) => ({
    id: node.id,
    type: "workflow",
    position: liveNodePositions[node.id] || node.position || fallbackWorkflowNodePosition(index),
    selected: node.id === selectedNodeId,
      data: {
        nodeId: node.id,
        label: node.title || node.id,
        nodeType: node.type || "answer",
        boundaryRole: workflowNodeBoundaryRole(node.type || "answer"),
        supported: node.supported !== false,
      sourceHandles: workflowCanvasSourceHandles(node),
      runState: nodeRunStates[node.id],
    },
  }));
}

function workflowCanvasEdges(graph: EditableGraph): Edge[] {
  return graph.edges
    .filter((edge) => edge.source && edge.target)
    .map((edge, index) => ({
      id: edge.id || `edge_${index + 1}`,
      source: edge.source || "",
      target: edge.target || "",
      sourceHandle: edge.source_handle || undefined,
      targetHandle: edge.target_handle || undefined,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: edge.valid === false ? "#f59e0b" : "var(--theme-primary)",
        strokeWidth: 1.8,
      },
      animated: false,
    }));
}

function WorkflowCanvas({
  graph,
  selectedNodeId,
  nodeRunStates,
  disabled,
  onSelectNode,
  onUpdateNode,
  onAddEdge,
  onAddNodeAt,
}: {
  graph: EditableGraph;
  selectedNodeId: string | null;
  nodeRunStates: Record<string, WorkflowNodeRunState>;
  disabled?: boolean;
  onSelectNode: (nodeId: string) => void;
  onUpdateNode: (nodeId: string, patch: Partial<GraphNode>) => void;
  onAddEdge: (source: string, target: string, sourceHandle?: string) => void;
  onAddNodeAt: (nodeType: string, position: WorkflowNodePosition, presetId?: string) => void;
}) {
  const { t } = useTranslation();
  const reactFlowInstanceRef = useRef<ReactFlowInstance<Node<WorkflowCanvasNodeData>, Edge> | null>(null);
  const [liveNodePositions, setLiveNodePositions] = useState<Record<string, WorkflowNodePosition>>({});
  const nodes = useMemo(
    () => workflowCanvasNodes(graph, selectedNodeId, nodeRunStates, liveNodePositions),
    [graph, liveNodePositions, nodeRunStates, selectedNodeId],
  );
  const edges = useMemo(() => workflowCanvasEdges(graph), [graph]);
  const selectedGraphNode = useMemo(
    () => graph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [graph.nodes, selectedNodeId],
  );

  const handleNodeChanges = useCallback(
    (changes: NodeChange[]) => {
      if (disabled) return;
      changes.forEach((change) => {
        if (change.type === "position" && change.position) {
          if (change.dragging === false) {
            setLiveNodePositions((current) => {
              if (!(change.id in current)) return current;
              const next = { ...current };
              delete next[change.id];
              return next;
            });
            onUpdateNode(change.id, { position: change.position });
          } else {
            setLiveNodePositions((current) => ({
              ...current,
              [change.id]: change.position!,
            }));
          }
        }
        if (change.type === "select" && change.selected) {
          onSelectNode(change.id);
        }
      });
    },
    [disabled, onSelectNode, onUpdateNode],
  );

  const handleNodeDragStop = useCallback(
    (_event: unknown, node: Node<WorkflowCanvasNodeData>) => {
      if (disabled) return;
      setLiveNodePositions((current) => {
        if (!(node.id in current)) return current;
        const next = { ...current };
        delete next[node.id];
        return next;
      });
      onUpdateNode(node.id, { position: node.position });
    },
    [disabled, onUpdateNode],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (disabled || !connection.source || !connection.target) return;
      onAddEdge(connection.source, connection.target, connection.sourceHandle || undefined);
    },
    [disabled, onAddEdge],
  );

  const handleDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (!Array.from(event.dataTransfer.types).includes(WORKFLOW_CANVAS_DRAG_TYPE)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, [disabled]);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (disabled) return;
      const rawPayload = event.dataTransfer.getData(WORKFLOW_CANVAS_DRAG_TYPE);
      if (!rawPayload) return;
      event.preventDefault();
      try {
        const payload = JSON.parse(rawPayload) as { nodeType?: unknown; presetId?: unknown };
        const nodeType = typeof payload.nodeType === "string" ? payload.nodeType : "";
        if (!EDITABLE_NODE_TYPES.includes(nodeType as typeof EDITABLE_NODE_TYPES[number])) return;
        const position = reactFlowInstanceRef.current?.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        }) ?? fallbackWorkflowNodePosition(graph.nodes.length);
        onAddNodeAt(
          nodeType,
          position,
          typeof payload.presetId === "string" ? payload.presetId : undefined,
        );
      } catch {
        return;
      }
    },
    [disabled, graph.nodes.length, onAddNodeAt],
  );

  const handleFitView = useCallback(() => {
    reactFlowInstanceRef.current?.fitView({ duration: 250, padding: 0.2 });
  }, []);

  const handleCenterSelected = useCallback(() => {
    if (!selectedGraphNode?.position) return;
    reactFlowInstanceRef.current?.setCenter(
      selectedGraphNode.position.x + 100,
      selectedGraphNode.position.y + 40,
      { duration: 250, zoom: 1.05 },
    );
  }, [selectedGraphNode]);

  return (
    <div
      className="relative mb-3 h-[28rem] min-h-80 overflow-hidden rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)]"
      data-testid="workflow-canvas"
      style={{ height: "28rem", minHeight: "20rem" }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div className="absolute right-3 top-3 z-10 flex items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-1 shadow-sm">
        <button
          type="button"
          onClick={handleFitView}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)]"
          title={t("workflowPlugin.editor.canvas.fitView")}
        >
          <Maximize2 size={15} />
        </button>
        <button
          type="button"
          onClick={handleCenterSelected}
          disabled={!selectedGraphNode}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-40"
          title={t("workflowPlugin.editor.canvas.centerSelected")}
        >
          <Crosshair size={15} />
        </button>
      </div>
      <ReactFlow<Node<WorkflowCanvasNodeData>, Edge>
        className="h-full w-full"
        data-testid="workflow-react-flow"
        nodes={nodes}
        edges={edges}
        nodeTypes={workflowCanvasNodeTypes}
        nodesDraggable={!disabled}
        nodesConnectable={!disabled}
        elementsSelectable
        fitView
        onConnect={handleConnect}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        onNodeDragStop={handleNodeDragStop}
        onNodesChange={handleNodeChanges}
        onInit={(instance) => {
          reactFlowInstanceRef.current = instance;
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="var(--theme-primary)"
          className="!opacity-20"
        />
        <MiniMap
          pannable
          zoomable
          className="!border !border-[var(--theme-border)] !bg-[var(--theme-bg)]"
        />
        <Controls
          position="bottom-left"
          className="!border !border-[var(--theme-border)] !bg-[var(--theme-bg)]"
        />
      </ReactFlow>
    </div>
  );
}

function WorkflowNodePalette({
  addNodeType,
  addNodePreset,
  disabled,
  onAddNodeTypeChange,
  onAddNodePresetChange,
  onAddNode,
}: {
  addNodeType: string;
  addNodePreset: string;
  disabled?: boolean;
  onAddNodeTypeChange: (type: string) => void;
  onAddNodePresetChange: (preset: string) => void;
  onAddNode: (nodeType?: string, position?: WorkflowNodePosition, presetId?: string) => void;
}) {
  const { t } = useTranslation();
  const [paletteQuery, setPaletteQuery] = useState("");
  const groupedNodeTypes = useMemo(
    () => workflowNodePaletteGroups(paletteQuery, t),
    [paletteQuery, t],
  );

  const handleDragStart = (
    event: DragEvent<HTMLElement>,
    nodeType: string,
    presetId?: string,
  ) => {
    if (disabled) return;
    event.dataTransfer.setData(
      WORKFLOW_CANVAS_DRAG_TYPE,
      JSON.stringify({ nodeType, presetId }),
    );
    event.dataTransfer.effectAllowed = "copy";
  };

  return (
    <aside
      className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2"
      data-testid="workflow-node-palette"
    >
      <div className="mb-2 px-1 text-xs font-medium text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.palette.title")}</div>
      <div className="mb-2 grid gap-2">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[var(--theme-text-secondary)]" size={13} />
          <input
            className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] pl-7 pr-2 text-xs outline-none focus:border-[var(--theme-primary)] disabled:opacity-50"
            value={paletteQuery}
            onChange={(event) => setPaletteQuery(event.target.value)}
            placeholder={t("workflowPlugin.editor.palette.searchPlaceholder")}
            disabled={disabled}
          />
        </label>
        <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1.5 text-xs">
          <div className="text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.palette.selected")}</div>
          <div className="mt-0.5 truncate font-medium">{workflowNodeTypeLabel(addNodeType, t)}</div>
        </div>
        {addNodeType === "list_operator" && (
          <select
            className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)] disabled:opacity-50"
            value={addNodePreset}
            onChange={(event) => onAddNodePresetChange(event.target.value)}
            disabled={disabled}
            title={t("workflowPlugin.editor.palette.listOperatorPresetTitle")}
          >
            {LIST_OPERATOR_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>{workflowListOperatorPresetLabel(preset.id, preset.label, t)}</option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => onAddNode(addNodeType, undefined, addNodePreset)}
          disabled={disabled}
          className="inline-flex h-8 items-center justify-center gap-2 rounded-md border border-[var(--theme-border)] px-2 text-xs hover:bg-[var(--theme-bg)] disabled:opacity-50"
        >
          <Plus size={14} /> {t("workflowPlugin.editor.palette.addNode")}
        </button>
      </div>
      <div className="max-h-[24rem] space-y-3 overflow-auto pr-1">
        {groupedNodeTypes.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--theme-border)] px-2 py-6 text-center text-xs text-[var(--theme-text-secondary)]">
            {t("workflowPlugin.editor.palette.noMatches")}
          </div>
        ) : (
          groupedNodeTypes.map((group) => (
            <div key={group.id}>
              <div className="mb-1 px-1 text-[11px] font-medium uppercase text-[var(--theme-text-secondary)]">
                {group.label}
              </div>
              <div className="grid gap-1.5">
                {group.types.map((type) => {
                  const selected = addNodeType === type;
                  const presetId = type === "list_operator" ? addNodePreset : undefined;
                  return (
                    <div
                      key={type}
                      data-testid={`workflow-node-palette-item-${type}`}
                      draggable={!disabled}
                      onDragStart={(event) => handleDragStart(event, type, presetId)}
                      className={`grid grid-cols-[minmax(0,1fr)_2rem] overflow-hidden rounded-md border bg-[var(--theme-bg)] text-xs ${
                        selected
                          ? "border-[var(--theme-primary)]"
                          : "border-[var(--theme-border)] hover:border-[var(--theme-primary)]"
                      } ${disabled ? "opacity-50" : ""}`}
                      title={type}
                    >
                      <button
                        type="button"
                        onClick={() => onAddNodeTypeChange(type)}
                        disabled={disabled}
                        className="flex min-h-8 min-w-0 items-center gap-2 px-2 py-1.5 text-left disabled:opacity-50"
                      >
                        <GitBranch className="shrink-0 text-[var(--theme-text-secondary)]" size={13} />
                        <span className="min-w-0 truncate">{workflowNodeTypeLabel(type, t)}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => onAddNode(type, undefined, presetId)}
                        disabled={disabled}
                        className="inline-flex min-h-8 items-center justify-center border-l border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        data-testid={`workflow-node-add-${type}`}
                        title={t("workflowPlugin.editor.palette.addNodeTitle", { type: workflowNodeTypeLabel(type, t) })}
                      >
                        <Plus size={13} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

function GraphEditor({
  graph,
  selectedNodeId,
  nodeRunStates,
  nodeDataDraft,
  graphIssues,
  addNodeType,
  addNodePreset,
  onSelectNode,
  onNodeDataDraftChange,
  onUpdateNode,
  onResetNodeData,
  onAddNodeTypeChange,
  onAddNodePresetChange,
  onAddNode,
  onRemoveNode,
  onAddEdge,
  onUpdateEdge,
  onRemoveEdge,
  onSave,
  workflowOptions,
  currentWorkflowId,
  disabled,
}: {
  graph: EditableGraph;
  selectedNodeId: string | null;
  nodeRunStates: Record<string, WorkflowNodeRunState>;
  nodeDataDraft: string;
  graphIssues: string[];
  addNodeType: string;
  addNodePreset: string;
  onSelectNode: (nodeId: string) => void;
  onNodeDataDraftChange: (value: string) => void;
  onUpdateNode: (nodeId: string, patch: Partial<GraphNode>) => void;
  onResetNodeData: (nodeId: string) => void;
  onAddNodeTypeChange: (type: string) => void;
  onAddNodePresetChange: (preset: string) => void;
  onAddNode: (nodeType?: string, position?: WorkflowNodePosition, presetId?: string) => void;
  onRemoveNode: (nodeId: string) => void;
  onAddEdge: (source: string, target: string, sourceHandle?: string) => void;
  onUpdateEdge: (edgeId: string, patch: Partial<GraphEdge>) => void;
  onRemoveEdge: (edgeId: string) => void;
  onSave: () => void;
  workflowOptions: WorkflowSummary[];
  currentWorkflowId?: string | null;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const defaultText = useMemo(() => workflowDefaultText(t), [t]);
  const { nodes, edges } = graph;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedNodeData = selectedNode?.data || {};
  const childWorkflowOptions = workflowOptions.filter((workflow) => workflow.workflow_id !== currentWorkflowId);
  const patchSelectedNodeData = (patch: Record<string, unknown>) => {
    if (!selectedNode) return;
    onUpdateNode(selectedNode.id, { data: { ...selectedNodeData, ...patch } });
  };
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">{t("workflowPlugin.editor.graph.title")}</div>
          <div className="text-xs text-[var(--theme-text-secondary)]">
            {t("workflowPlugin.editor.graph.summary", { nodes: nodes.length, edges: edges.length })}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onSave}
            disabled={disabled}
            data-testid="workflow-save-graph"
            className="inline-flex h-8 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-xs text-white disabled:opacity-50"
          >
            <Save size={14} /> {t("workflowPlugin.editor.common.save")}
          </button>
        </div>
      </div>

      <WorkflowBoundarySummary graph={graph} onSelectNode={onSelectNode} />

      {graphIssues.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300">
          <div className="mb-1 font-medium">{t("workflowPlugin.editor.graph.issues", "Graph issues")}</div>
          <ul className="list-disc space-y-1 pl-4">
            {graphIssues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-[12rem_minmax(0,1fr)]">
        <WorkflowNodePalette
          addNodeType={addNodeType}
          addNodePreset={addNodePreset}
          disabled={disabled}
          onAddNodeTypeChange={onAddNodeTypeChange}
          onAddNodePresetChange={onAddNodePresetChange}
          onAddNode={onAddNode}
        />
        <div className="min-w-0">
          <ReactFlowProvider>
            <WorkflowCanvas
              graph={graph}
              selectedNodeId={selectedNodeId}
              nodeRunStates={nodeRunStates}
              disabled={disabled}
              onSelectNode={onSelectNode}
              onUpdateNode={onUpdateNode}
              onAddEdge={onAddEdge}
              onAddNodeAt={(nodeType, position, presetId) => onAddNode(nodeType, position, presetId)}
            />
          </ReactFlowProvider>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-2">
          {nodes.map((node, index) => {
            const outgoing = edges.filter((edge) => edge.source === node.id);
            const selected = node.id === selectedNodeId;
            return (
              <button
                key={`${node.id}-${index}`}
                type="button"
                data-testid={`workflow-node-card-${node.id || index}`}
                onClick={() => onSelectNode(node.id)}
                className={`w-full rounded-md border p-3 text-left transition-colors ${
                  selected
                    ? "border-[var(--theme-primary)] bg-[var(--theme-bg-secondary)]"
                    : "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] hover:border-[var(--theme-primary)]"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{node.title || node.id}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                      <span>{node.id}</span>
                      <span className="rounded bg-[var(--theme-bg)] px-1.5 py-0.5">{node.type || t("workflowPlugin.editor.run.unknown")}</span>
                    </div>
                  </div>
                  {node.supported === false ? (
                    <AlertTriangle className="shrink-0 text-amber-500" size={16} />
                  ) : (
                    <CheckCircle2 className="shrink-0 text-emerald-500" size={16} />
                  )}
                </div>
                {outgoing.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-[var(--theme-text-secondary)]">
                    {outgoing.map((edge) => (
                      <span key={edge.id || `${edge.source}-${edge.target}`} className={`rounded px-2 py-1 ${edge.valid === false ? "bg-amber-500/10 text-amber-600" : "bg-[var(--theme-bg)]"}`}>
                        {edge.source_handle ? `${edge.source_handle} ->` : "->"} {edge.target || "missing"}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>

        <div className="space-y-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-3">
          {selectedNode ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{t("workflowPlugin.editor.graph.node")}</div>
                <button
                  type="button"
                  onClick={() => onRemoveNode(selectedNode.id)}
                  disabled={disabled}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                  title={t("workflowPlugin.editor.graph.removeNode")}
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <input
                className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                data-testid="workflow-selected-node-id"
                value={selectedNode.id}
                onChange={(event) => onUpdateNode(selectedNode.id, { id: event.target.value })}
                disabled={disabled}
                title={t("workflowPlugin.editor.graph.nodeId")}
              />
              <input
                className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                value={selectedNode.title || ""}
                onChange={(event) => onUpdateNode(selectedNode.id, { title: event.target.value })}
                placeholder={t("workflowPlugin.editor.graph.titlePlaceholder")}
                disabled={disabled}
              />
              <select
                className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                value={selectedNode.type || "answer"}
                onChange={(event) => {
                  const nextType = event.target.value;
                  const nextTitle = selectedNode.title || selectedNode.id || nextType;
                  onUpdateNode(selectedNode.id, {
                    type: nextType,
                    data: defaultNodeData(nextType, nextTitle, defaultText, nextType === "list_operator" ? addNodePreset : undefined),
                  });
                }}
                disabled={disabled}
              >
                {EDITABLE_NODE_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
              {selectedNode.type === "start" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <div className="flex items-center justify-between gap-2 text-xs text-[var(--theme-text-secondary)]">
                    <span>{t("workflowPlugin.editor.graph.inputContract")}</span>
                    <button
                      type="button"
                      onClick={() => patchSelectedNodeData(inputContractPatch(objectRowsWithAddedRow(selectedNodeData.variables ?? selectedNodeData.inputs, inputContractFallback(defaultText))))}
                      disabled={disabled}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      title={t("workflowPlugin.editor.graph.addInputField")}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                  {inputContractRows(selectedNodeData, defaultText).map((field, fieldIndex) => (
                    <div key={`input-contract-${fieldIndex}`} className="grid gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_4rem_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={contractFieldName(field)}
                          onChange={(event) => patchSelectedNodeData(inputContractPatch(
                            objectRowsWithValue(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText), "name", event.target.value),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.inputName")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.inputName")}
                        />
                        <select
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={contractFieldType(field)}
                          onChange={(event) => patchSelectedNodeData(inputContractPatch(
                            objectRowsWithValue(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText), "type", event.target.value),
                          ))}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.inputType")}
                        >
                          {WORKFLOW_CONTRACT_FIELD_TYPES.map((fieldType) => (
                            <option key={fieldType} value={fieldType}>{fieldType}</option>
                          ))}
                        </select>
                        <label className="inline-flex h-8 items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                          <input
                            type="checkbox"
                            checked={contractFieldBooleanValue(field, "required")}
                            onChange={(event) => patchSelectedNodeData(inputContractPatch(
                              objectRowsWithValue(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText), "required", event.target.checked),
                            ))}
                            disabled={disabled}
                          />
                          {t("workflowPlugin.editor.graph.required")}
                        </label>
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData(inputContractPatch(
                            objectRowsWithoutIndex(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText)),
                          ))}
                          disabled={disabled || inputContractRows(selectedNodeData, defaultText).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeInputField")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={contractFieldDefaultText(field)}
                          onChange={(event) => patchSelectedNodeData(inputContractPatch(
                            objectRowsWithValue(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText), "default", structuredValueFromText(event.target.value)),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.defaultValue")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.defaultValue")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(field, "description")}
                          onChange={(event) => patchSelectedNodeData(inputContractPatch(
                            objectRowsWithValue(selectedNodeData.variables ?? selectedNodeData.inputs, fieldIndex, inputContractFallback(defaultText), "description", event.target.value),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.description")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.description")}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selectedNode.type === "condition" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={firstObjectTextValue(selectedNodeData.conditions, "variable")}
                    onChange={(event) => patchSelectedNodeData({
                      conditions: objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "variable", event.target.value),
                    })}
                    placeholder={t("workflowPlugin.editor.graph.variable")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.conditionVariable")}
                  />
                  <select
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={firstObjectTextValue(selectedNodeData.conditions, "operator") || "not_empty"}
                    onChange={(event) => patchSelectedNodeData({
                      conditions: objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "operator", event.target.value),
                    })}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.conditionOperator")}
                  >
                    <option value="not_empty">{t("workflowPlugin.editor.graph.operators.notEmpty")}</option>
                    <option value="empty">{t("workflowPlugin.editor.graph.operators.empty")}</option>
                    <option value="equals">{t("workflowPlugin.editor.graph.operators.equals")}</option>
                    <option value="not_equals">{t("workflowPlugin.editor.graph.operators.notEquals")}</option>
                    <option value="contains">{t("workflowPlugin.editor.graph.operators.contains")}</option>
                    <option value="not_contains">{t("workflowPlugin.editor.graph.operators.notContains")}</option>
                    <option value="greater_than">{t("workflowPlugin.editor.graph.operators.greaterThan")}</option>
                    <option value="less_than">{t("workflowPlugin.editor.graph.operators.lessThan")}</option>
                  </select>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={firstObjectTextValue(selectedNodeData.conditions, "value")}
                    onChange={(event) => patchSelectedNodeData({
                      conditions: objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "value", event.target.value),
                    })}
                    placeholder={t("workflowPlugin.editor.graph.compareValue")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.compareValue")}
                  />
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    {CONDITION_BRANCH_HANDLES.map((branchHandle) => {
                      const branchEdge = edgeForSourceHandle(edges, selectedNode.id, branchHandle);
                      return (
                        <select
                          key={`condition-branch-${branchHandle}`}
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={branchEdge?.target || ""}
                          onChange={(event) => {
                            const target = event.target.value;
                            if (!target) return;
                            if (branchEdge?.id) {
                              onUpdateEdge(branchEdge.id, { target, source_handle: branchHandle });
                            } else {
                              onAddEdge(selectedNode.id, target, branchHandle);
                            }
                          }}
                          disabled={disabled || nodes.length < 2}
                          title={t("workflowPlugin.editor.graph.branchTargetFor", { handle: branchHandle })}
                        >
                          <option value="">{t("workflowPlugin.editor.graph.branchFor", { handle: branchHandle })}</option>
                          {nodes.filter((node) => node.id !== selectedNode.id).map((node) => (
                            <option key={node.id} value={node.id}>{node.id}</option>
                          ))}
                        </select>
                      );
                    })}
                  </div>
                  <div className="space-y-2 border-t border-[var(--theme-border)] pt-2">
                    <div className="flex items-center justify-between gap-2 text-xs text-[var(--theme-text-secondary)]">
                      <span>{t("workflowPlugin.editor.graph.caseBranches")}</span>
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData(conditionCasesPatch(conditionCasesWithAddedCase(selectedNodeData)))}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addCaseBranch")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {conditionCaseRows(selectedNodeData).map((conditionCase, caseIndex) => {
                      const caseId = conditionCaseId(conditionCase, caseIndex);
                      const caseEdge = edgeForSourceHandle(edges, selectedNode.id, caseId);
                      return (
                        <div key={`condition-case-${caseIndex}`} className="grid gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] lg:grid-cols-1">
                            <input
                              className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                              value={caseId}
                              onChange={(event) => patchSelectedNodeData(conditionCasesPatch(conditionCasesWithCaseId(selectedNodeData, caseIndex, event.target.value)))}
                              placeholder={t("workflowPlugin.editor.graph.caseHandle")}
                              disabled={disabled}
                              title={t("workflowPlugin.editor.graph.caseHandle")}
                            />
                            <select
                              className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                              value={caseEdge?.target || ""}
                              onChange={(event) => {
                                const target = event.target.value;
                                if (!target) return;
                                if (caseEdge?.id) {
                                  onUpdateEdge(caseEdge.id, { target, source_handle: caseId });
                                } else {
                                  onAddEdge(selectedNode.id, target, caseId);
                                }
                              }}
                              disabled={disabled || nodes.length < 2}
                              title={t("workflowPlugin.editor.graph.caseBranchTarget")}
                            >
                              <option value="">{t("workflowPlugin.editor.graph.caseTarget")}</option>
                              {nodes.filter((node) => node.id !== selectedNode.id).map((node) => (
                                <option key={node.id} value={node.id}>{node.id}</option>
                              ))}
                            </select>
                            <button
                              type="button"
                              onClick={() => patchSelectedNodeData(conditionCasesPatch(conditionCasesWithoutIndex(selectedNodeData, caseIndex)))}
                              disabled={disabled || conditionCaseRows(selectedNodeData).length <= 1}
                              className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                              title={t("workflowPlugin.editor.graph.removeCaseBranch")}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)] lg:grid-cols-1">
                            <input
                              className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                              value={conditionCaseConditionValue(conditionCase, "variable_selector")}
                              onChange={(event) => patchSelectedNodeData(conditionCasesPatch(
                                conditionCasesWithConditionValue(selectedNodeData, caseIndex, "variable_selector", selectorFromText(event.target.value)),
                              ))}
                              placeholder={t("workflowPlugin.editor.graph.variablePath")}
                              disabled={disabled}
                              title={t("workflowPlugin.editor.graph.caseVariablePath")}
                            />
                            <select
                              className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                              value={conditionCaseConditionValue(conditionCase, "operator") || "not_empty"}
                              onChange={(event) => patchSelectedNodeData(conditionCasesPatch(
                                conditionCasesWithConditionValue(selectedNodeData, caseIndex, "operator", event.target.value),
                              ))}
                              disabled={disabled}
                              title={t("workflowPlugin.editor.graph.caseOperator")}
                            >
                              <option value="not_empty">{t("workflowPlugin.editor.graph.operators.notEmpty")}</option>
                              <option value="empty">{t("workflowPlugin.editor.graph.operators.empty")}</option>
                              <option value="equals">{t("workflowPlugin.editor.graph.operators.equals")}</option>
                              <option value="not_equals">{t("workflowPlugin.editor.graph.operators.notEquals")}</option>
                              <option value="contains">{t("workflowPlugin.editor.graph.operators.contains")}</option>
                              <option value="not_contains">{t("workflowPlugin.editor.graph.operators.notContains")}</option>
                              <option value="greater_than">{t("workflowPlugin.editor.graph.operators.greaterThan")}</option>
                              <option value="less_than">{t("workflowPlugin.editor.graph.operators.lessThan")}</option>
                              <option value={">="}>{t("workflowPlugin.editor.graph.operators.greaterOrEqual")}</option>
                              <option value={"<="}>{t("workflowPlugin.editor.graph.operators.lessOrEqual")}</option>
                            </select>
                            <input
                              className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                              value={conditionCaseConditionValue(conditionCase, "value")}
                              onChange={(event) => patchSelectedNodeData(conditionCasesPatch(
                                conditionCasesWithConditionValue(selectedNodeData, caseIndex, "value", event.target.value),
                              ))}
                              placeholder={t("workflowPlugin.editor.graph.compareValue")}
                              disabled={disabled}
                              title={t("workflowPlugin.editor.graph.caseCompareValue")}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {selectedNode.type === "human_approval" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <textarea
                    className="min-h-24 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "instructions")}
                    onChange={(event) => patchSelectedNodeData({ instructions: event.target.value })}
                    placeholder={t("workflowPlugin.editor.approval.instructionsPlaceholder")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.approval.instructionsTitle")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "assignee")}
                    onChange={(event) => patchSelectedNodeData({ assignee: event.target.value })}
                    placeholder={t("workflowPlugin.editor.approval.assigneePlaceholder")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.approval.assigneeTitle")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.approval.outputKeyPlaceholder")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.approval.outputKeyTitle")}
                  />
                </div>
              )}
              {selectedNode.type === "variable_assign" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={assignmentEntryName(selectedNodeData.assignments)}
                    onChange={(event) => patchSelectedNodeData({ assignments: assignmentsWithEntryName(selectedNodeData.assignments, event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.variableName")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.variableName")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={assignmentEntryTextValue(selectedNodeData.assignments)}
                    onChange={(event) => patchSelectedNodeData({ assignments: assignmentsWithEntryValue(selectedNodeData.assignments, event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.valueTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.valueTemplate")}
                  />
                </div>
              )}
              {selectedNode.type === "variable_aggregator" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData(variableAggregatorSelectorPatch(variableAggregatorSelectorsWithAddedSelector(selectedNodeData)))}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addSelector")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {variableAggregatorSelectorRows(selectedNodeData).map((selector, selectorIndex) => (
                      <div key={`variable-aggregator-selector-${selectorIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={variableAggregatorSelectorValue(selector)}
                          onChange={(event) => patchSelectedNodeData(variableAggregatorSelectorPatch(
                            variableAggregatorSelectorsWithValue(selectedNodeData, selectorIndex, selectorFromText(event.target.value)),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.variableSelector")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.variableSelector")}
                        />
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData(variableAggregatorSelectorPatch(variableAggregatorSelectorsWithoutIndex(selectedNodeData, selectorIndex)))}
                          disabled={disabled || variableAggregatorSelectorRows(selectedNodeData).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeSelector")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <select
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "mode") || "first_non_empty"}
                    onChange={(event) => patchSelectedNodeData({ mode: event.target.value })}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.aggregationMode")}
                  >
                    <option value="first_non_empty">{t("workflowPlugin.editor.graph.options.firstNonEmpty")}</option>
                    <option value="array">{t("workflowPlugin.editor.graph.options.array")}</option>
                  </select>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "parameter_extractor" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "query")}
                    onChange={(event) => patchSelectedNodeData({ query: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.queryTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.queryTemplate")}
                  />
                  <LlmSettingsFields data={selectedNodeData} onPatch={patchSelectedNodeData} disabled={disabled} />
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData({ parameters: objectRowsWithAddedRow(selectedNodeData.parameters, parameterExtractorParameterFallback()) })}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addParameter")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {objectRows(selectedNodeData.parameters, parameterExtractorParameterFallback()).map((parameter, parameterIndex) => (
                      <div key={`parameter-extractor-parameter-${parameterIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_minmax(0,1fr)_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={objectRowTextValue(parameter, "name")}
                          onChange={(event) => patchSelectedNodeData({
                            parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "name", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.parameterName")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.parameterName")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={objectRowTextValue(parameter, "type") || "string"}
                          onChange={(event) => patchSelectedNodeData({
                            parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "type", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.type")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.parameterType")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={objectRowTextValue(parameter, "description")}
                          onChange={(event) => patchSelectedNodeData({
                            parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "description", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.description")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.parameterDescription")}
                        />
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData({ parameters: objectRowsWithoutIndex(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback()) })}
                          disabled={disabled || objectRows(selectedNodeData.parameters, parameterExtractorParameterFallback()).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeParameter")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "question_classifier" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "query")}
                    onChange={(event) => patchSelectedNodeData({ query: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.queryTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.queryTemplate")}
                  />
                  <LlmSettingsFields data={selectedNodeData} onPatch={patchSelectedNodeData} disabled={disabled} />
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData({ classes: objectRowsWithAddedRow(selectedNodeData.classes, questionClassifierClassFallback()) })}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addClass")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {objectRows(selectedNodeData.classes, questionClassifierClassFallback()).map((classifierClass, classIndex) => {
                      const classId = questionClassifierClassId(classifierClass, classIndex);
                      const classEdge = edgeForSourceHandle(edges, selectedNode.id, classId);
                      return (
                        <div key={`question-classifier-class-${classIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_2rem] lg:grid-cols-1">
                          <input
                            className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                            value={classId}
                            onChange={(event) => patchSelectedNodeData({
                              classes: objectRowsWithValue(selectedNodeData.classes, classIndex, questionClassifierClassFallback(), "id", event.target.value),
                            })}
                            placeholder={t("workflowPlugin.editor.graph.classId")}
                            disabled={disabled}
                            title={t("workflowPlugin.editor.graph.classId")}
                          />
                          <input
                            className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                            value={objectRowTextValue(classifierClass, "name")}
                            onChange={(event) => patchSelectedNodeData({
                              classes: objectRowsWithValue(selectedNodeData.classes, classIndex, questionClassifierClassFallback(), "name", event.target.value),
                            })}
                            placeholder={t("workflowPlugin.editor.graph.className")}
                            disabled={disabled}
                            title={t("workflowPlugin.editor.graph.className")}
                          />
                          <select
                            className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                            value={classEdge?.target || ""}
                            onChange={(event) => {
                              const target = event.target.value;
                              if (!target) return;
                              if (classEdge?.id) {
                                onUpdateEdge(classEdge.id, { target, source_handle: classId });
                              } else {
                                onAddEdge(selectedNode.id, target, classId);
                              }
                            }}
                            disabled={disabled || nodes.length < 2}
                            title={t("workflowPlugin.editor.graph.classBranchTarget")}
                          >
                            <option value="">{t("workflowPlugin.editor.graph.branchTarget")}</option>
                            {nodes.filter((node) => node.id !== selectedNode.id).map((node) => (
                              <option key={node.id} value={node.id}>{node.id}</option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => patchSelectedNodeData({ classes: objectRowsWithoutIndex(selectedNodeData.classes, classIndex, questionClassifierClassFallback()) })}
                            disabled={disabled || objectRows(selectedNodeData.classes, questionClassifierClassFallback()).length <= 1}
                            className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                            title={t("workflowPlugin.editor.graph.removeClass")}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "answer" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <textarea
                    className="min-h-24 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "answer")}
                    onChange={(event) => patchSelectedNodeData({ answer: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.answerText")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.answerText")}
                  />
                  <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                    <div className="text-xs text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.run.outputContract")}</div>
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem] lg:grid-cols-1">
                      <input
                        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none"
                        value="answer"
                        readOnly
                        disabled
                        title={t("workflowPlugin.editor.graph.outputName")}
                      />
                      <select
                        className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        value={contractFieldType(answerOutputContractRow(selectedNodeData, defaultText))}
                        onChange={(event) => patchSelectedNodeData(answerOutputContractPatch({
                          ...answerOutputContractRow(selectedNodeData, defaultText),
                          type: event.target.value,
                        }))}
                        disabled={disabled}
                        title={t("workflowPlugin.editor.graph.outputType")}
                      >
                        {WORKFLOW_CONTRACT_FIELD_TYPES.map((fieldType) => (
                          <option key={fieldType} value={fieldType}>{fieldType}</option>
                        ))}
                      </select>
                    </div>
                    <input
                      className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={descriptorRowTextValue(answerOutputContractRow(selectedNodeData, defaultText), "description")}
                      onChange={(event) => patchSelectedNodeData(answerOutputContractPatch({
                        ...answerOutputContractRow(selectedNodeData, defaultText),
                        description: event.target.value,
                      }))}
                      placeholder={t("workflowPlugin.editor.graph.description")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.description")}
                    />
                  </div>
                </div>
              )}
              {selectedNode.type === "end" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <div className="flex items-center justify-between gap-2 text-xs text-[var(--theme-text-secondary)]">
                    <span>{t("workflowPlugin.editor.run.outputContract")}</span>
                    <button
                      type="button"
                      onClick={() => patchSelectedNodeData(outputContractPatch(objectRowsWithAddedRow(selectedNodeData.outputs, outputContractFallback(defaultText))))}
                      disabled={disabled}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      title={t("workflowPlugin.editor.graph.addOutputField")}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                  {outputContractRows(selectedNodeData, defaultText).map((field, fieldIndex) => (
                    <div key={`output-contract-${fieldIndex}`} className="grid gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={contractFieldName(field)}
                          onChange={(event) => patchSelectedNodeData(outputContractPatch(
                            objectRowsWithValue(selectedNodeData.outputs, fieldIndex, outputContractFallback(defaultText), "name", event.target.value),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.outputName")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.outputName")}
                        />
                        <select
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={contractFieldType(field)}
                          onChange={(event) => patchSelectedNodeData(outputContractPatch(
                            objectRowsWithValue(selectedNodeData.outputs, fieldIndex, outputContractFallback(defaultText), "type", event.target.value),
                          ))}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.outputType")}
                        >
                          {WORKFLOW_CONTRACT_FIELD_TYPES.map((fieldType) => (
                            <option key={fieldType} value={fieldType}>{fieldType}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData(outputContractPatch(
                            objectRowsWithoutIndex(selectedNodeData.outputs, fieldIndex, outputContractFallback(defaultText)),
                          ))}
                          disabled={disabled || outputContractRows(selectedNodeData, defaultText).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeOutputField")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(field, "value")}
                          onChange={(event) => patchSelectedNodeData(outputContractPatch(
                            objectRowsWithValue(selectedNodeData.outputs, fieldIndex, outputContractFallback(defaultText), "value", event.target.value),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.valueTemplate")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.valueTemplate")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(field, "description")}
                          onChange={(event) => patchSelectedNodeData(outputContractPatch(
                            objectRowsWithValue(selectedNodeData.outputs, fieldIndex, outputContractFallback(defaultText), "description", event.target.value),
                          ))}
                          placeholder={t("workflowPlugin.editor.graph.description")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.description")}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selectedNode.type === "llm" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <textarea
                    className="min-h-24 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "prompt_template")}
                    onChange={(event) => patchSelectedNodeData({ prompt_template: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.promptTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.promptTemplate")}
                  />
                  <LlmSettingsFields data={selectedNodeData} onPatch={patchSelectedNodeData} disabled={disabled} />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "template_transform" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <textarea
                    className="min-h-24 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "template")}
                    onChange={(event) => patchSelectedNodeData({ template: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.template")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.template")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "knowledge_retrieval" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={selectorText(selectedNodeData.query_variable_selector)}
                    onChange={(event) => patchSelectedNodeData({ query_variable_selector: selectorFromText(event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.querySelector")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.querySelector")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={stringListText(selectedNodeData.dataset_ids)}
                    onChange={(event) => patchSelectedNodeData({ dataset_ids: stringListFromText(event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.datasetIds")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.datasetIds")}
                  />
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    <input
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={llmTextValue(selectedNodeData, "top_k")}
                      onChange={(event) => patchSelectedNodeData({ top_k: structuredValueFromText(event.target.value), topK: undefined })}
                      placeholder={t("workflowPlugin.editor.graph.topK")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.knowledgeTopK")}
                    />
                    <input
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={llmTextValue(selectedNodeData, "score_threshold")}
                      onChange={(event) => patchSelectedNodeData({ score_threshold: structuredValueFromText(event.target.value), scoreThreshold: undefined })}
                      placeholder={t("workflowPlugin.editor.graph.scoreThreshold")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.knowledgeScoreThreshold")}
                    />
                  </div>
                  <textarea
                    className="min-h-20 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 font-mono text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={structuredValueText(selectedNodeData.dataset_filter ?? selectedNodeData.datasetFilter)}
                    onChange={(event) => patchSelectedNodeData(knowledgeFilterPatch("dataset_filter", event.target.value))}
                    placeholder={t("workflowPlugin.editor.graph.datasetFilterJson")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.knowledgeDatasetFilter")}
                    spellCheck={false}
                  />
                  <textarea
                    className="min-h-20 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 font-mono text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={structuredValueText(selectedNodeData.metadata_filter ?? selectedNodeData.metadataFilter)}
                    onChange={(event) => patchSelectedNodeData(knowledgeFilterPatch("metadata_filter", event.target.value))}
                    placeholder={t("workflowPlugin.editor.graph.metadataFilterJson")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.knowledgeMetadataFilter")}
                    spellCheck={false}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "sub_workflow" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <select
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "workflow_id")}
                    onChange={(event) => patchSelectedNodeData({ workflow_id: event.target.value })}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.childWorkflow")}
                  >
                    <option value="">{t("workflowPlugin.editor.graph.selectChildWorkflow")}</option>
                    {childWorkflowOptions.map((workflow) => (
                      <option key={workflow.workflow_id} value={workflow.workflow_id}>
                        {workflow.name} ({workflow.status})
                      </option>
                    ))}
                  </select>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "workflow_id")}
                    onChange={(event) => patchSelectedNodeData({ workflow_id: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.childWorkflowId")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.childWorkflowId")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "version_id")}
                    onChange={(event) => patchSelectedNodeData({ version_id: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.pinnedVersionId")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.pinnedVersionId")}
                  />
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    <input
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={assignmentEntryName(selectedNodeData.inputs)}
                      onChange={(event) => patchSelectedNodeData({ inputs: assignmentsWithEntryName(selectedNodeData.inputs, event.target.value) })}
                      placeholder={t("workflowPlugin.editor.graph.inputKey")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.inputKey")}
                    />
                    <input
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={assignmentEntryTextValue(selectedNodeData.inputs)}
                      onChange={(event) => patchSelectedNodeData({ inputs: assignmentsWithEntryValue(selectedNodeData.inputs, event.target.value) })}
                      placeholder={t("workflowPlugin.editor.graph.inputValueTemplate")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.inputValueTemplate")}
                    />
                  </div>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "list_operator" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <select
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={addNodePreset}
                    onChange={(event) => {
                      const nextPreset = event.target.value;
                      onAddNodePresetChange(nextPreset);
                      onUpdateNode(selectedNode.id, {
                        data: defaultNodeData("list_operator", selectedNode.title || selectedNode.id || defaultText.listOperatorTitle, defaultText, nextPreset),
                      });
                    }}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.palette.listOperatorPresetTitle")}
                  >
                    {LIST_OPERATOR_PRESETS.map((preset) => (
                      <option key={preset.id} value={preset.id}>{workflowListOperatorPresetLabel(preset.id, preset.label, t)}</option>
                    ))}
                  </select>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    <input
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={dataTextValue(selectedNodeData, "operation")}
                      onChange={(event) => patchSelectedNodeData({ operation: event.target.value })}
                      placeholder={t("workflowPlugin.editor.graph.operation")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.listOperation")}
                    />
                    <input
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={selectorText(selectedNodeData.variable_selector)}
                      onChange={(event) => patchSelectedNodeData({ variable_selector: selectorFromText(event.target.value) })}
                      placeholder={t("workflowPlugin.editor.graph.inputPath")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.inputVariablePath")}
                    />
                    <input
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={dataTextValue(selectedNodeData, "output_key")}
                      onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                      placeholder={t("workflowPlugin.editor.graph.outputKey")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.outputKey")}
                    />
                    {selectedNodeData.operation === "sort" && (
                      <select
                        className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        value={dataTextValue(selectedNodeData, "direction") || "asc"}
                        onChange={(event) => patchSelectedNodeData({ direction: event.target.value })}
                        disabled={disabled}
                        title={t("workflowPlugin.editor.graph.sortDirection")}
                      >
                        <option value="asc">{t("workflowPlugin.editor.graph.options.ascending")}</option>
                        <option value="desc">{t("workflowPlugin.editor.graph.options.descending")}</option>
                      </select>
                    )}
                    {(selectedNodeData.operation === "sort" || selectedNodeData.operation === "sum" || selectedNodeData.operation === "pluck") && (
                      <input
                        className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        value={dataTextValue(selectedNodeData, listOperatorFieldKey(selectedNodeData))}
                        onChange={(event) => patchSelectedNodeData({ [listOperatorFieldKey(selectedNodeData)]: event.target.value })}
                        placeholder={selectedNodeData.operation === "sort" ? t("workflowPlugin.editor.graph.sortField") : t("workflowPlugin.editor.graph.valueField")}
                        disabled={disabled}
                        title={selectedNodeData.operation === "sort" ? t("workflowPlugin.editor.graph.sortField") : t("workflowPlugin.editor.graph.valueField")}
                      />
                    )}
                    {listOperatorUsesConditions(selectedNodeData) && (
                      <>
                        <select
                          className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={dataTextValue(selectedNodeData, "logical_operator") || "and"}
                          onChange={(event) => patchSelectedNodeData({ logical_operator: event.target.value })}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.conditionJoin")}
                        >
                          <option value="and">{t("workflowPlugin.editor.graph.options.allConditions")}</option>
                          <option value="or">{t("workflowPlugin.editor.graph.options.anyCondition")}</option>
                        </select>
                        <div className="space-y-2 sm:col-span-2 lg:col-span-1">
                          <div className="flex justify-end">
                            <button
                              type="button"
                              onClick={() => patchSelectedNodeData({ conditions: listOperatorConditionsWithAddedCondition(selectedNodeData.conditions) })}
                              disabled={disabled}
                              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                              title={t("workflowPlugin.editor.graph.addCondition")}
                            >
                              <Plus size={14} />
                            </button>
                          </div>
                          {listOperatorConditionRows(selectedNodeData.conditions).map((condition, conditionIndex) => (
                            <div key={`list-condition-${conditionIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)_2rem] lg:grid-cols-1">
                              <input
                                className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                                value={listOperatorConditionValue(condition, "variable_selector")}
                                onChange={(event) => patchSelectedNodeData({
                                  conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "variable_selector", selectorFromText(event.target.value)),
                                })}
                                placeholder={t("workflowPlugin.editor.graph.itemFieldPath")}
                                disabled={disabled}
                                title={t("workflowPlugin.editor.graph.conditionItemFieldPath")}
                              />
                              <select
                                className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                                value={listOperatorConditionValue(condition, "operator") || ">="}
                                onChange={(event) => patchSelectedNodeData({
                                  conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "operator", event.target.value),
                                })}
                                disabled={disabled}
                                title={t("workflowPlugin.editor.graph.conditionOperator")}
                              >
                                <option value={">="}>{t("workflowPlugin.editor.graph.operators.greaterOrEqual")}</option>
                                <option value={">"}>{t("workflowPlugin.editor.graph.operators.greaterThan")}</option>
                                <option value={"<="}>{t("workflowPlugin.editor.graph.operators.lessOrEqual")}</option>
                                <option value={"<"}>{t("workflowPlugin.editor.graph.operators.lessThan")}</option>
                                <option value="equals">{t("workflowPlugin.editor.graph.operators.equals")}</option>
                                <option value="not_equals">{t("workflowPlugin.editor.graph.operators.notEquals")}</option>
                                <option value="contains">{t("workflowPlugin.editor.graph.operators.contains")}</option>
                                <option value="not_contains">{t("workflowPlugin.editor.graph.operators.notContains")}</option>
                                <option value="is true">{t("workflowPlugin.editor.graph.operators.isTrue")}</option>
                                <option value="is false">{t("workflowPlugin.editor.graph.operators.isFalse")}</option>
                                <option value="not_empty">{t("workflowPlugin.editor.graph.operators.notEmpty")}</option>
                              </select>
                              <input
                                className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                                value={listOperatorConditionValue(condition, "value")}
                                onChange={(event) => patchSelectedNodeData({
                                  conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "value", event.target.value),
                                })}
                                placeholder={t("workflowPlugin.editor.graph.compareValue")}
                                disabled={disabled}
                                title={t("workflowPlugin.editor.graph.conditionCompareValue")}
                              />
                              <button
                                type="button"
                                onClick={() => patchSelectedNodeData({ conditions: listOperatorConditionsWithoutIndex(selectedNodeData.conditions, conditionIndex) })}
                                disabled={disabled || listOperatorConditionRows(selectedNodeData.conditions).length <= 1}
                                className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                                title={t("workflowPlugin.editor.graph.removeCondition")}
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
              {selectedNode.type === "iteration" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={selectorText(selectedNodeData.iterator_selector)}
                    onChange={(event) => patchSelectedNodeData({ iterator_selector: selectorFromText(event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.iteratorPath")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.iteratorVariablePath")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "item_template")}
                    onChange={(event) => patchSelectedNodeData({ item_template: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.itemTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.itemTemplate")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "document_extractor" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={selectorText(selectedNodeData.variable_selector)}
                    onChange={(event) => patchSelectedNodeData({ variable_selector: selectorFromText(event.target.value) })}
                    placeholder={t("workflowPlugin.editor.graph.documentPath")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.documentVariablePath")}
                  />
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "output_key")}
                    onChange={(event) => patchSelectedNodeData({ output_key: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.outputKey")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.outputKey")}
                  />
                </div>
              )}
              {selectedNode.type === "tool_call" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "tool_name")}
                    onChange={(event) => patchSelectedNodeData({ tool_name: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.toolName")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.toolName")}
                  />
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData({ tool_configurations: objectRowsWithAddedRow(selectedNodeData.tool_configurations, toolConfigurationFallback()) })}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addArgument")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {objectRows(selectedNodeData.tool_configurations, toolConfigurationFallback()).map((configuration, configurationIndex) => (
                      <div key={`tool-configuration-${configurationIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(configuration, "name")}
                          onChange={(event) => patchSelectedNodeData({
                            tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "name", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.argument")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.argumentName")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(configuration, "value")}
                          onChange={(event) => patchSelectedNodeData({
                            tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "value", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.value")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.argumentValue")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(configuration, "value_selector")}
                          onChange={(event) => patchSelectedNodeData({
                            tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "value_selector", selectorFromText(event.target.value)),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.selector")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.argumentSelector")}
                        />
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData({ tool_configurations: objectRowsWithoutIndex(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback()) })}
                          disabled={disabled || objectRows(selectedNodeData.tool_configurations, toolConfigurationFallback()).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeArgument")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedNode.type === "http_request" && (
                <div className="space-y-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                  <select
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "request_method") || "GET"}
                    onChange={(event) => patchSelectedNodeData({ request_method: event.target.value })}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.requestMethod")}
                  >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="PATCH">PATCH</option>
                    <option value="DELETE">DELETE</option>
                  </select>
                  <input
                    className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={dataTextValue(selectedNodeData, "endpoint")}
                    onChange={(event) => patchSelectedNodeData({ endpoint: event.target.value })}
                    placeholder={t("workflowPlugin.editor.graph.endpointUrl")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.endpointUrl")}
                  />
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    <input
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={httpCredentialRefText(selectedNodeData)}
                      onChange={(event) => patchSelectedNodeData(httpCredentialRefPatch(event.target.value))}
                      placeholder={t("workflowPlugin.editor.graph.credentialRef")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.httpCredentialRef")}
                    />
                    <select
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={httpAuthorizationTextValue(selectedNodeData, "type") || "bearer"}
                      onChange={(event) => patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { type: event.target.value }))}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.httpAuthType")}
                    >
                      <option value="bearer">Bearer</option>
                      <option value="api_key">API key</option>
                      <option value="basic">Basic</option>
                      <option value="custom">Custom</option>
                      <option value="none">{t("workflowPlugin.editor.common.none")}</option>
                    </select>
                    <input
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={httpAuthorizationTextValue(selectedNodeData, "header_name")}
                      onChange={(event) => patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { header_name: event.target.value, headerName: undefined, header: undefined, name: undefined }))}
                      placeholder={t("workflowPlugin.editor.graph.authHeader")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.httpAuthHeader")}
                    />
                    <input
                      className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      value={httpAuthorizationTextValue(selectedNodeData, "prefix")}
                      onChange={(event) => patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { prefix: event.target.value, value_prefix: undefined, valuePrefix: undefined }))}
                      placeholder={t("workflowPlugin.editor.graph.authPrefix")}
                      disabled={disabled}
                      title={t("workflowPlugin.editor.graph.httpAuthPrefix")}
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData({ header_parameters: objectRowsWithAddedRow(selectedNodeData.header_parameters, httpHeaderFallback()) })}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addHeader")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {objectRows(selectedNodeData.header_parameters, httpHeaderFallback()).map((header, headerIndex) => (
                      <div key={`http-header-${headerIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(header, "name")}
                          onChange={(event) => patchSelectedNodeData({
                            header_parameters: objectRowsWithValue(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback(), "name", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.headerName")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.headerName")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(header, "value")}
                          onChange={(event) => patchSelectedNodeData({
                            header_parameters: objectRowsWithValue(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback(), "value", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.headerValue")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.headerValue")}
                        />
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData({ header_parameters: objectRowsWithoutIndex(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback()) })}
                          disabled={disabled || objectRows(selectedNodeData.header_parameters, httpHeaderFallback()).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeHeader")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => patchSelectedNodeData({ query_parameters: objectRowsWithAddedRow(selectedNodeData.query_parameters, httpQueryFallback()) })}
                        disabled={disabled}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        title={t("workflowPlugin.editor.graph.addQueryParameter")}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {objectRows(selectedNodeData.query_parameters, httpQueryFallback()).map((queryParameter, queryIndex) => (
                      <div key={`http-query-${queryIndex}`} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] lg:grid-cols-1">
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(queryParameter, "name")}
                          onChange={(event) => patchSelectedNodeData({
                            query_parameters: objectRowsWithValue(selectedNodeData.query_parameters, queryIndex, httpQueryFallback(), "name", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.queryName")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.queryName")}
                        />
                        <input
                          className="h-8 min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                          value={descriptorRowTextValue(queryParameter, "value")}
                          onChange={(event) => patchSelectedNodeData({
                            query_parameters: objectRowsWithValue(selectedNodeData.query_parameters, queryIndex, httpQueryFallback(), "value", event.target.value),
                          })}
                          placeholder={t("workflowPlugin.editor.graph.queryValue")}
                          disabled={disabled}
                          title={t("workflowPlugin.editor.graph.queryValue")}
                        />
                        <button
                          type="button"
                          onClick={() => patchSelectedNodeData({ query_parameters: objectRowsWithoutIndex(selectedNodeData.query_parameters, queryIndex, httpQueryFallback()) })}
                          disabled={disabled || objectRows(selectedNodeData.query_parameters, httpQueryFallback()).length <= 1}
                          className="inline-flex h-8 w-8 items-center justify-center justify-self-end rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeQueryParameter")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <textarea
                    className="min-h-24 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 font-mono text-xs outline-none focus:border-[var(--theme-primary)]"
                    value={httpRequestBodyText(selectedNodeData)}
                    onChange={(event) => patchSelectedNodeData(httpRequestBodyPatch(event.target.value))}
                    placeholder={t("workflowPlugin.editor.graph.requestBodyJsonOrTemplate")}
                    disabled={disabled}
                    title={t("workflowPlugin.editor.graph.requestBody")}
                    spellCheck={false}
                  />
                </div>
              )}
              <button
                type="button"
                onClick={() => onResetNodeData(selectedNode.id)}
                disabled={disabled}
                className="inline-flex h-8 items-center justify-center rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg)] disabled:opacity-50"
              >
                {t("workflowPlugin.editor.graph.resetNodeData")}
              </button>
              <textarea
                className="min-h-32 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 font-mono text-xs outline-none focus:border-[var(--theme-primary)]"
                value={nodeDataDraft}
                onChange={(event) => onNodeDataDraftChange(event.target.value)}
                onBlur={() => {
                  try {
                    onUpdateNode(selectedNode.id, { data: JSON.parse(nodeDataDraft) as Record<string, unknown> });
                  } catch {
                    toast.error(t("workflowPlugin.editor.toast.nodeDataInvalidJson"));
                  }
                }}
                spellCheck={false}
                disabled={disabled}
              />

              <div className="border-t border-[var(--theme-border)] pt-3">
                <div className="mb-2 text-xs font-medium text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.graph.edges")}</div>
                <div className="space-y-2">
                  {edges.map((edge) => (
                    <div
                      key={edge.id || `${edge.source}-${edge.target}`}
                      data-testid={`workflow-edge-card-${edge.id || `${edge.source}-${edge.target}`}`}
                      className="grid gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate">{edge.source || t("workflowPlugin.editor.run.missing")}</span>
                        {edge.valid === false && <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-600">{t("workflowPlugin.editor.graph.invalid")}</span>}
                        <button
                          type="button"
                          onClick={() => onRemoveEdge(edge.id || "")}
                          disabled={disabled || !edge.id}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                          title={t("workflowPlugin.editor.graph.removeEdge")}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                      <input
                        className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        data-testid={`workflow-edge-source-handle-${edge.id || `${edge.source}-${edge.target}`}`}
                        value={edge.source_handle || ""}
                        onChange={(event) => onUpdateEdge(edge.id || "", { source_handle: event.target.value || null })}
                        placeholder={t("workflowPlugin.editor.graph.sourceHandle")}
                        disabled={disabled || !edge.id}
                        title={t("workflowPlugin.editor.graph.sourceHandle")}
                      />
                      <select
                        className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        data-testid={`workflow-edge-target-${edge.id || `${edge.source}-${edge.target}`}`}
                        value={edge.target || ""}
                        onChange={(event) => onUpdateEdge(edge.id || "", { target: event.target.value })}
                        disabled={disabled || !edge.id}
                        title={t("workflowPlugin.editor.graph.targetNode")}
                      >
                        <option value="">{t("workflowPlugin.editor.graph.targetNode")}</option>
                        {nodes.filter((node) => node.id !== edge.source).map((node) => (
                          <option key={node.id} value={node.id}>{node.id}</option>
                        ))}
                      </select>
                      <input
                        className="h-8 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                        data-testid={`workflow-edge-target-handle-${edge.id || `${edge.source}-${edge.target}`}`}
                        value={edge.target_handle || ""}
                        onChange={(event) => onUpdateEdge(edge.id || "", { target_handle: event.target.value || null })}
                        placeholder={t("workflowPlugin.editor.graph.targetHandle")}
                        disabled={disabled || !edge.id}
                        title={t("workflowPlugin.editor.graph.targetHandle")}
                      />
                    </div>
                  ))}
                  {edges.length === 0 && (
                    <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-4 text-center text-xs text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.graph.noEdges")}
                    </div>
                  )}
                </div>
                {nodes.length > 1 && (
                  <div className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
                    <select
                      className="h-8 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 text-xs outline-none focus:border-[var(--theme-primary)]"
                      data-testid={`workflow-add-edge-target-${selectedNode.id}`}
                      onChange={(event) => {
                        if (event.target.value) {
                          onAddEdge(
                            selectedNode.id,
                            event.target.value,
                            selectedNode.type === "condition"
                              ? "true"
                              : selectedNode.type === "question_classifier"
                                ? "general"
                                : undefined,
                          );
                          event.target.value = "";
                        }
                      }}
                      defaultValue=""
                      disabled={disabled}
                    >
                      <option value="">{t("workflowPlugin.editor.graph.addEdge")}</option>
                      {nodes.filter((node) => node.id !== selectedNode.id).map((node) => (
                        <option key={node.id} value={node.id}>{node.id}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => onAddEdge(selectedNode.id, nodes.find((node) => node.id !== selectedNode.id)?.id || "")}
                      disabled={disabled || nodes.length < 2}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
                      title={t("workflowPlugin.editor.graph.addEdge")}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
              {t("workflowPlugin.editor.graph.selectNodeToEdit")}
            </div>
          )}
        </div>
      </div>
        </div>
      </div>
    </div>
  );
}
function RunEventsPanel({
  events,
  isLoading,
  focusedNodeId,
  onFocusNode,
}: {
  events: WorkflowRunEvent[];
  isLoading: boolean;
  focusedNodeId?: string | null;
  onFocusNode?: (nodeId: string | null) => void;
}) {
  const { t } = useTranslation();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const eventNodeIds = useMemo(() => runEventNodeIds(events), [events]);
  const visibleEvents = useMemo(
    () =>
      focusedNodeId
        ? events.filter((event) => event.node_id === focusedNodeId)
        : events,
    [events, focusedNodeId],
  );
  const selectedEvent = useMemo(
    () =>
      visibleEvents.find((event) => event.event_id === selectedEventId) ??
      visibleEvents[visibleEvents.length - 1] ??
      events.find((event) => event.event_id === selectedEventId) ??
      events[events.length - 1] ??
      null,
    [events, selectedEventId, visibleEvents],
  );
  const selectedTone = selectedEvent ? runEventTone(selectedEvent.event_type) : null;
  const selectedDuration = selectedEvent ? runEventDuration(selectedEvent) : null;
  const selectedTruncation = selectedEvent
    ? workflowEventPayloadTruncation(selectedEvent.payload)
    : null;
  const focusedNodeEventCount = focusedNodeId
    ? events.filter((event) => event.node_id === focusedNodeId).length
    : events.length;

  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3 text-sm font-medium">
        <span>{t("workflowPlugin.editor.events.title")}</span>
        <span className="inline-flex items-center gap-1 text-xs font-normal text-[var(--theme-text-secondary)]">
          {isLoading && <Loader2 size={12} className="animate-spin" />}
          {isLoading ? t("workflowPlugin.editor.events.loading") : focusedNodeId ? `${focusedNodeEventCount}/${events.length}` : events.length}
        </span>
      </div>
      {isLoading ? (
        <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
          {t("workflowPlugin.editor.events.loadingDetail")}
        </div>
      ) : events.length === 0 ? (
        <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
          {t("workflowPlugin.editor.events.empty")}
        </div>
      ) : (
        <>
        {eventNodeIds.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => onFocusNode?.(null)}
              className={`inline-flex h-7 items-center rounded-md border px-2 ${
                focusedNodeId
                  ? "border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)]"
                  : "border-[var(--theme-primary)] bg-[var(--theme-bg-secondary)] text-[var(--theme-text)]"
              }`}
            >
              {t("workflowPlugin.editor.events.all")}
            </button>
            {eventNodeIds.map((nodeId) => {
              const selected = focusedNodeId === nodeId;
              const count = events.filter((event) => event.node_id === nodeId).length;
              return (
                <button
                  key={nodeId}
                  type="button"
                  onClick={() => onFocusNode?.(nodeId)}
                  className={`inline-flex h-7 max-w-full items-center gap-1 rounded-md border px-2 ${
                    selected
                      ? "border-[var(--theme-primary)] bg-[var(--theme-bg-secondary)] text-[var(--theme-text)]"
                      : "border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)]"
                  }`}
                  title={t("workflowPlugin.editor.events.focusNode", { nodeId })}
                >
                  <span className="truncate">{nodeId}</span>
                  <span>{count}</span>
                </button>
              );
            })}
          </div>
        )}
        {visibleEvents.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
            {t("workflowPlugin.editor.events.emptySelected")}
          </div>
        ) : (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
          <div className="max-h-96 space-y-2 overflow-auto pr-1">
            {visibleEvents.map((event) => {
              const tone = runEventTone(event.event_type);
              const duration = runEventDuration(event);
              const selected = selectedEvent?.event_id === event.event_id;
              return (
                <button
                  key={event.event_id}
                  type="button"
                  onClick={() => setSelectedEventId(event.event_id)}
                  className={`relative w-full rounded-md border p-2 text-left text-xs transition-colors ${tone.className} ${
                    selected
                      ? "border-[var(--theme-primary)] ring-1 ring-[var(--theme-primary)]"
                      : "hover:border-[var(--theme-primary)]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      {tone.icon}
                      <span className="truncate font-medium">#{event.sequence} {event.event_type}</span>
                    </div>
                    {duration !== null && (
                      <span className="shrink-0 text-[var(--theme-text-secondary)]">{duration} ms</span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2 text-[var(--theme-text-secondary)]">
                    <span className="truncate">{event.node_id || t("workflowPlugin.editor.events.runScope")}</span>
                    <span className="shrink-0">{event.node_type || t("workflowPlugin.editor.events.workflowScope")}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className={`rounded-md border p-3 text-xs ${selectedTone?.className ?? "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)]"}`}>
            {selectedEvent ? (
              <>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
                      {selectedTone?.icon}
                      <span className="truncate">#{selectedEvent.sequence} {selectedEvent.event_type}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-[var(--theme-text-secondary)]">
                      {selectedEvent.node_id ? (
                        <button
                          type="button"
                          onClick={() => onFocusNode?.(selectedEvent.node_id ?? null)}
                          className="rounded-md border border-[var(--theme-border)] px-2 py-0.5 hover:bg-[var(--theme-bg)]"
                          title={t("workflowPlugin.editor.events.focusNode", { nodeId: selectedEvent.node_id })}
                        >
                          {selectedEvent.node_id}
                        </button>
                      ) : (
                        <span>{t("workflowPlugin.editor.events.runScope")}</span>
                      )}
                      <span>{selectedEvent.node_type || t("workflowPlugin.editor.events.workflowScope")}</span>
                      <span>{formatDate(selectedEvent.created_at)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {selectedDuration !== null && (
                      <span className="rounded-md bg-[var(--theme-bg)] px-2 py-1 text-[var(--theme-text-secondary)]">
                        {selectedDuration} ms
                      </span>
                    )}
                    <span className="rounded-md bg-[var(--theme-bg)] px-2 py-1 text-[var(--theme-text-secondary)]">
                      {selectedEvent.event_id}
                    </span>
                  </div>
                </div>

                {selectedTruncation && (
                  <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-amber-700">
                    <div className="flex items-center gap-2 font-medium">
                      <AlertTriangle size={13} />
                      <span>{t("workflowPlugin.editor.events.payloadTruncated")}</span>
                    </div>
                    <div className="mt-1 text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.events.payloadOriginalLimit", {
                        original: formatRunEventPayloadBytes(selectedTruncation.originalBytes),
                        limit: formatRunEventPayloadBytes(selectedTruncation.maxBytes),
                      })}
                    </div>
                    {selectedTruncation.keys.length > 0 && (
                      <div className="mt-1 text-[var(--theme-text-secondary)]">
                        {t("workflowPlugin.editor.events.payloadKeys", { keys: selectedTruncation.keys.join(", ") })}
                      </div>
                    )}
                  </div>
                )}

                <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-[var(--theme-bg)] p-3 text-[var(--theme-text-secondary)]">
                  {JSON.stringify(selectedEvent.payload, null, 2)}
                </pre>
              </>
            ) : (
              <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
                {t("workflowPlugin.editor.events.selectEvent")}
              </div>
            )}
          </div>
        </div>
        )}
        </>
      )}
    </div>
  );
}

function HumanApprovalPanel({
  run,
  comment,
  isResuming,
  onCommentChange,
  onResume,
}: {
  run: WorkflowRunResponse | null;
  comment: string;
  isResuming: boolean;
  onCommentChange: (value: string) => void;
  onResume: (approved: boolean) => void;
}) {
  const { t } = useTranslation();
  if (run?.status !== "paused") return null;
  const pending = pendingApprovalFromRun(run);
  const title = pendingApprovalText(pending?.title) || t("workflowPlugin.editor.approval.humanApproval");
  const instructions = pendingApprovalText(pending?.instructions);
  const assignee = pendingApprovalText(pending?.assignee);
  const outputKey = pendingApprovalText(pending?.output_key);

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-amber-700 dark:text-amber-300">{title}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-[var(--theme-text-secondary)]">
            {assignee && <span>{t("workflowPlugin.editor.approval.assignee", { assignee })}</span>}
            {outputKey && <span>{t("workflowPlugin.editor.approval.output", { output: outputKey })}</span>}
          </div>
        </div>
        <span className="rounded-md border border-amber-500/30 px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
          {t("workflowPlugin.editor.approval.paused")}
        </span>
      </div>
      {instructions && (
        <div className="mb-3 rounded-md border border-amber-500/20 bg-[var(--theme-bg)] px-3 py-2 text-sm text-[var(--theme-text-secondary)]">
          {instructions}
        </div>
      )}
      <textarea
        className="min-h-20 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-3 text-sm outline-none focus:border-[var(--theme-primary)]"
        value={comment}
        onChange={(event) => onCommentChange(event.target.value)}
        placeholder={t("workflowPlugin.editor.approval.commentPlaceholder")}
        disabled={isResuming}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onResume(true)}
          disabled={isResuming}
          data-testid="workflow-approval-approve"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-sm text-white disabled:opacity-50"
        >
          {isResuming ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />}
          {t("workflowPlugin.editor.approval.approve")}
        </button>
        <button
          type="button"
          onClick={() => onResume(false)}
          disabled={isResuming}
          data-testid="workflow-approval-reject"
          className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
        >
          {isResuming ? <Loader2 className="animate-spin" size={16} /> : <XCircle size={16} />}
          {t("workflowPlugin.editor.approval.reject")}
        </button>
      </div>
    </div>
  );
}

function PendingApprovalInbox({
  approvals,
  selectedRunId,
  onSelect,
  onRefresh,
}: {
  approvals: WorkflowRunResponse[];
  selectedRunId?: string | null;
  onSelect: (run: WorkflowRunResponse) => void;
  onRefresh: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3 text-sm font-medium">
        <span>{t("workflowPlugin.editor.approval.pendingTitle")}</span>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-secondary)]"
          title={t("workflowPlugin.editor.approval.refreshPending")}
        >
          <RefreshCw size={14} />
        </button>
      </div>
      {approvals.length === 0 ? (
        <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-6 text-center text-sm text-[var(--theme-text-secondary)]">
          {t("workflowPlugin.editor.approval.noPending")}
        </div>
      ) : (
        <div className="space-y-2">
          {approvals.slice(0, 8).map((run) => {
            const pending = pendingApprovalFromRun(run);
            const title = pendingApprovalText(pending?.title) || pendingApprovalText(pending?.node_id) || t("workflowPlugin.editor.approval.humanApproval");
            const selected = run.run_id && run.run_id === selectedRunId;
            return (
              <button
                key={run.run_id || `${run.workflow_id}-${run.started_at}`}
                type="button"
                onClick={() => onSelect(run)}
                disabled={!run.run_id}
                className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-colors disabled:opacity-50 ${
                  selected
                    ? "border-amber-500/60 bg-amber-500/10"
                    : "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] hover:border-amber-500/60"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium">{title}</span>
                  <span className="text-amber-600">{t("workflowPlugin.editor.approval.paused")}</span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-3 text-[var(--theme-text-secondary)]">
                  <span className="truncate">{run.workflow_id}</span>
                  <span>{run.started_at ? formatDate(run.started_at) : t("workflowPlugin.editor.run.unknown")}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

type WorkflowPanelProps = {
  activeTab?: string;
};

export function WorkflowPanel({ activeTab }: WorkflowPanelProps = {}) {
  const { t } = useTranslation();
  const defaultText = useMemo(() => workflowDefaultText(t), [t]);
  const outputContractStatusLabels = useMemo<WorkflowRunOutputContractStatusLabels>(() => ({
    declared: t("workflowPlugin.editor.run.outputContractStatus.declared"),
    issue: t("workflowPlugin.editor.run.outputContractStatus.issue"),
    missing: t("workflowPlugin.editor.run.outputContractStatus.missing"),
    ok: t("workflowPlugin.editor.run.outputContractStatus.ok"),
    satisfied: t("workflowPlugin.editor.run.outputContractStatus.satisfied"),
    type: t("workflowPlugin.editor.run.outputContractStatus.type"),
    unknown: t("workflowPlugin.editor.run.outputContractStatus.unknown"),
  }), [t]);
  const { workflowId: routeWorkflowId, runId: routeRunId } = useParams<{ workflowId?: string; runId?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const routeSelectedWorkflowId = routeWorkflowId || null;
  const routeSelectedRunId = routeRunId || null;
  const createMode = searchParams.get("create");
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [workflowTotal, setWorkflowTotal] = useState(0);
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowDetailResponse | null>(null);
  const [versions, setVersions] = useState<WorkflowVersionSummary[]>([]);
  const [inputSchema, setInputSchema] = useState<WorkflowInputSchemaResponse | null>(null);
  const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null);
  const [nodeCatalog, setNodeCatalog] = useState<WorkflowNodeTypesResponse | null>(null);
  const [credentials, setCredentials] = useState<WorkflowCredentialResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(routeSelectedWorkflowId);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingCredentials, setIsLoadingCredentials] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [isCreatingWorkflow, setIsCreatingWorkflow] = useState(false);
  const [isSavingVersion, setIsSavingVersion] = useState(false);
  const [isSavingCredential, setIsSavingCredential] = useState(false);
  const [isDeletingCredentialId, setIsDeletingCredentialId] = useState<string | null>(null);
  const [isDeletingWorkflowId, setIsDeletingWorkflowId] = useState<string | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isResumingRun, setIsResumingRun] = useState(false);
  const [isPollingRun, setIsPollingRun] = useState(false);
  const [isLoadingRunEvents, setIsLoadingRunEvents] = useState(false);
  const cancelRequestedRef = useRef(false);
  const [workflowName, setWorkflowName] = useState(() => defaultText.importedWorkflowName);
  const [sourceFormat, setSourceFormat] = useState<"json" | "yaml">("json");
  const [runMode, setRunMode] = useState<WorkflowRunMode>("async");
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [dslText, setDslText] = useState(() => sampleWorkflowDsl(defaultText));
  const [runInput, setRunInput] = useState(() => JSON.stringify({ message: defaultText.sampleMessage }));
  const [editableGraph, setEditableGraph] = useState<EditableGraph>({ nodes: [], edges: [] });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeDataDraft, setNodeDataDraft] = useState("{}");
  const [runEventFocusedNodeId, setRunEventFocusedNodeId] = useState<string | null>(null);
  const [addNodeType, setAddNodeType] = useState<string>("start");
  const [addNodePreset, setAddNodePreset] = useState<string>(LIST_OPERATOR_PRESETS[0].id);
  const [report, setReport] = useState<WorkflowImportReport | null>(null);
  const [runResult, setRunResult] = useState<WorkflowRunResponse | null>(null);
  const [approvalComment, setApprovalComment] = useState("");
  const [runEvents, setRunEvents] = useState<WorkflowRunEvent[]>([]);
  const [runs, setRuns] = useState<WorkflowRunResponse[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<WorkflowRunResponse[]>([]);
  const [credentialDraft, setCredentialDraft] = useState<CredentialDraft>(EMPTY_CREDENTIAL_DRAFT);
  const [workflowQuery, setWorkflowQuery] = useState("");
  const [workflowStatusFilter, setWorkflowStatusFilter] = useState<WorkflowStatusFilter>("all");
  const [loadError, setLoadError] = useState<string | null>(null);
  const previousDefaultTextRef = useRef(defaultText);

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.workflow_id === selectedId) ?? null,
    [selectedId, workflows],
  );
  const hasWorkflowInventoryFilter = workflowQuery.trim().length > 0 || workflowStatusFilter !== "all";
  const workflowRouteMode = createMode === "import"
    ? "import"
    : createMode === "blank"
      ? "create"
      : routeSelectedRunId || activeTab === "workflows-run"
    ? "run"
    : routeSelectedWorkflowId || activeTab === "workflows-editor"
      ? "editor"
      : "list";
  const workflowRouteTitle = workflowRouteMode === "run"
    ? t("workflowPlugin.editor.route.runTitle")
    : workflowRouteMode === "editor"
      ? t("workflowPlugin.editor.route.editorTitle")
      : workflowRouteMode === "import"
        ? t("workflowPlugin.editor.route.importTitle")
        : workflowRouteMode === "create"
          ? t("workflowPlugin.editor.route.createTitle")
          : t("workflowPlugin.editor.route.listTitle");
  const workflowRouteSubtitle = workflowRouteMode === "run"
    ? t("workflowPlugin.editor.route.runSubtitle")
    : workflowRouteMode === "editor"
      ? t("workflowPlugin.editor.route.editorSubtitle")
      : workflowRouteMode === "import"
        ? t("workflowPlugin.editor.route.importSubtitle")
        : workflowRouteMode === "create"
          ? t("workflowPlugin.editor.route.createSubtitle")
          : t("workflowPlugin.editor.route.listSubtitle");
  const workspaceGridClass = workflowRouteMode === "run"
    ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]"
    : workflowRouteMode === "editor"
      ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]"
      : "grid gap-4";
  const graphIssues = useMemo(() => validateEditableGraph(editableGraph), [editableGraph]);
  const inputFields = useMemo(() => schemaFields(inputSchema), [inputSchema]);
  const outputFields = useMemo(
    () => schemaFieldsFromSchema(ioContract?.output_schema, { nested: true }),
    [ioContract],
  );
  const contractInterfaceItems = useMemo(
    () => workflowContractInterfaceItems(selectedWorkflow, ioContract),
    [ioContract, selectedWorkflow],
  );
  const runInputDraftStatus = useMemo(
    () => workflowInputDraftStatus(runInput, inputSchema?.input_schema),
    [inputSchema, runInput],
  );
  const runInputDraftMessage = useMemo(
    () => workflowInputDraftMessage(runInputDraftStatus, t),
    [runInputDraftStatus, t],
  );
  const unresolvedCredentialRefs = useMemo(() => credentialRefsFromReport(report), [report]);
  const nodeRunStates = useMemo(
    () => workflowNodeRunStates(runEvents, runEventFocusedNodeId),
    [runEventFocusedNodeId, runEvents],
  );

  useEffect(() => {
    const previous = previousDefaultTextRef.current;
    setWorkflowName((current) => {
      if (current === previous.importedWorkflowName) return defaultText.importedWorkflowName;
      if (current === previous.blankWorkflowName) return defaultText.blankWorkflowName;
      return current;
    });
    setDslText((current) => current === sampleWorkflowDsl(previous) ? sampleWorkflowDsl(defaultText) : current);
    setRunInput((current) => {
      const previousSample = JSON.stringify({ message: previous.sampleMessage });
      return current === previousSample ? JSON.stringify({ message: defaultText.sampleMessage }) : current;
    });
    previousDefaultTextRef.current = defaultText;
  }, [defaultText]);

  const loadCredentials = useCallback(async () => {
    setIsLoadingCredentials(true);
    try {
      const response = await workflowApi.credentials(0, 100);
      setCredentials(response.credentials);
    } catch (error) {
      toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadCredentialsFailed")));
    } finally {
      setIsLoadingCredentials(false);
    }
  }, [t]);

  const loadWorkflows = useCallback(async () => {
    setIsLoading(true);
    let shouldLoadPendingApprovals = false;
    try {
      const [response, catalog] = await Promise.all([
        workflowApi.list({
          skip: 0,
          limit: 100,
          query: workflowQuery,
          status: workflowStatusFilter,
        }),
        workflowApi.nodeTypes(),
      ]);
      setWorkflows(response.workflows);
      setWorkflowTotal(response.total);
      setNodeCatalog(catalog);
      setSelectedId((current) =>
        routeSelectedWorkflowId && response.workflows.some((item) => item.workflow_id === routeSelectedWorkflowId)
          ? routeSelectedWorkflowId
          : current && response.workflows.some((item) => item.workflow_id === current)
          ? current
          : response.workflows[0]?.workflow_id ?? null,
      );
      setLoadError(null);
      shouldLoadPendingApprovals = true;
    } catch (error) {
      const message = errorMessage(error, t("workflowPlugin.editor.toast.loadWorkflowsFailed"));
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
    if (shouldLoadPendingApprovals) {
      try {
        const approvals = await workflowApi.pendingApprovals(0, 20);
        setPendingApprovals(approvals.runs);
      } catch (error) {
        toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadPendingApprovalsFailed")));
      }
    }
  }, [routeSelectedWorkflowId, t, workflowQuery, workflowStatusFilter]);

  const loadPendingApprovals = useCallback(async () => {
    try {
      const response = await workflowApi.pendingApprovals(0, 20);
      setPendingApprovals(response.runs);
    } catch (error) {
      toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadPendingApprovalsFailed")));
    }
  }, [t]);

  useEffect(() => {
    loadWorkflows();
  }, [loadWorkflows]);

  useEffect(() => {
    if (routeSelectedWorkflowId && routeSelectedWorkflowId !== selectedId) {
      setSelectedId(routeSelectedWorkflowId);
    }
  }, [routeSelectedWorkflowId, selectedId]);

  useEffect(() => {
    loadCredentials();
  }, [loadCredentials]);

  useEffect(() => {
    if (!selectedId) {
      setWorkflowDetail(null);
      setVersions([]);
      setInputSchema(null);
      setIoContract(null);
      setRuns([]);
      setRunResult(null);
      setRunEvents([]);
      setRunEventFocusedNodeId(null);
      setSelectedVersionId(null);
      return;
    }
    let cancelled = false;
    const workflowId = selectedId;
    async function loadDetail() {
      try {
        const [detail, versionList, runList] = await Promise.all([
          workflowApi.get(workflowId),
          workflowApi.versions(workflowId),
          workflowApi.runs(workflowId),
        ]);
        const nextVersionId = resolveDebugVersionId(detail, versionList.versions, selectedVersionId);
        const [schema, contract] = await Promise.all([
          workflowApi.inputSchema(workflowId, nextVersionId),
          workflowApi.ioContract(workflowId, nextVersionId),
        ]);
        const routeRunEvents = routeSelectedRunId
          ? await workflowApi.runEvents(workflowId, routeSelectedRunId).catch((error: unknown) => {
              toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadRunTraceFailed")));
              return null;
            })
          : null;
        if (!cancelled) {
          setWorkflowDetail(detail);
          setVersions(versionList.versions);
          setSelectedVersionId(nextVersionId);
          setInputSchema(schema);
          setIoContract(contract);
          setRunInput(runInputFromSchema(schema, defaultText));
          setRuns(
            routeRunEvents
              ? [
                  routeRunEvents.run,
                  ...runList.runs.filter((run) => run.run_id !== routeRunEvents.run.run_id),
                ].slice(0, 20)
              : runList.runs,
          );
          if (routeRunEvents) {
            setRunResult(routeRunEvents.run);
            setRunEvents(workflowRunEvents(routeRunEvents.events));
          }
          if (!routeRunEvents) {
            setRunEventFocusedNodeId(null);
          }
          const nextGraph = graphFromVersion(detail.latest_version);
          setEditableGraph(nextGraph);
          setRunEventFocusedNodeId((current) =>
            current && nextGraph.nodes.some((node) => node.id === current) ? current : null,
          );
          const nextSelected = nextGraph.nodes[0]?.id ?? null;
          setSelectedNodeId(nextSelected);
          setNodeDataDraft(nodeDataText(nextGraph.nodes[0] ?? null));
          const latestReport = detail.latest_version?.compatibility_report;
          if (latestReport && typeof latestReport === "object") {
            setReport(normalizeWorkflowImportReport(latestReport));
          }
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.loadWorkflowDetailFailed"));
        }
      }
    }
    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [defaultText, routeSelectedRunId, selectedId, t]);

  const applySavedVersionBoundary = useCallback((response: WorkflowImportResponse) => {
    const versionId = savedWorkflowVersionId(response);
    if (versionId) {
      setSelectedVersionId(versionId);
    }
    if (response.io_contract) {
      const schema = inputSchemaFromIoContract(response.io_contract);
      setIoContract(response.io_contract);
      if (schema) {
        setInputSchema(schema);
        setRunInput(runInputFromSchema(schema, defaultText));
      }
    }
  }, [defaultText]);

  const handleImport = async (dryRun: boolean) => {
    setIsImporting(true);
    try {
      const response = await workflowApi.importWorkflow({
        name: workflowName.trim() || defaultText.importedWorkflowName,
        source_content: dslText,
        source_format: sourceFormat,
        dry_run: dryRun,
      });
      setReport(normalizeWorkflowImportReport(response.compatibility_report));
      if (!dryRun && response.workflow_id) {
        applySavedVersionBoundary(response);
        toast.success(t("workflowPlugin.editor.toast.workflowImported"));
        await loadWorkflows();
        setSelectedId(response.workflow_id);
        navigate(workflowEditorPath(response.workflow_id));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.importFailed"));
    } finally {
      setIsImporting(false);
    }
  };

  const handleCreateBlankWorkflow = useCallback(async () => {
    const name = blankWorkflowNameFromDraft(workflowName, defaultText);
    const sourcePayload = buildBlankWorkflowPluginDsl(name, defaultText);
    setIsCreatingWorkflow(true);
    try {
      const response = await workflowApi.importWorkflow({
        name,
        source_payload: sourcePayload,
        source_format: "json",
        dry_run: false,
      });
      setReport(normalizeWorkflowImportReport(response.compatibility_report));
      setWorkflowName(name);
      setDslText(JSON.stringify(sourcePayload, null, 2));
      setSourceFormat("json");
      if (response.workflow_id) {
        applySavedVersionBoundary(response);
        toast.success(t("workflowPlugin.editor.toast.workflowCreated"));
        await loadWorkflows();
        setSelectedId(response.workflow_id);
        navigate(workflowEditorPath(response.workflow_id));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.createWorkflowFailed"));
    } finally {
      setIsCreatingWorkflow(false);
    }
  }, [applySavedVersionBoundary, defaultText, loadWorkflows, navigate, workflowName]);

  const refreshSelectedWorkflow = async (workflowId: string, preferredVersionId?: string | null) => {
    const [detail, versionList, runList] = await Promise.all([
      workflowApi.get(workflowId),
      workflowApi.versions(workflowId),
      workflowApi.runs(workflowId),
    ]);
    const nextVersionId = resolveDebugVersionId(
      detail,
      versionList.versions,
      preferredVersionId ?? selectedVersionId,
    );
    const [schema, contract] = await Promise.all([
      workflowApi.inputSchema(workflowId, nextVersionId),
      workflowApi.ioContract(workflowId, nextVersionId),
    ]);
    setWorkflowDetail(detail);
    setVersions(versionList.versions);
    setSelectedVersionId(nextVersionId);
    setInputSchema(schema);
    setIoContract(contract);
    setRunInput(runInputFromSchema(schema, defaultText));
    setRuns(runList.runs);
    setRunEventFocusedNodeId(null);
    const nextGraph = graphFromVersion(detail.latest_version);
    setEditableGraph(nextGraph);
    setRunEventFocusedNodeId((current) =>
      current && nextGraph.nodes.some((node) => node.id === current) ? current : null,
    );
    const nextSelected = nextGraph.nodes[0]?.id ?? null;
    setSelectedNodeId(nextSelected);
    setNodeDataDraft(nodeDataText(nextGraph.nodes[0] ?? null));
    const latestReport = detail.latest_version?.compatibility_report;
    if (latestReport && typeof latestReport === "object") {
      setReport(normalizeWorkflowImportReport(latestReport));
    }
  };

  const handleResetRunInput = () => {
    setRunInput(runInputFromSchema(inputSchema, defaultText));
  };

  const handleSelectDebugVersion = async (versionId: string | null) => {
    setSelectedVersionId(versionId);
    const workflowId = selectedWorkflow?.workflow_id ?? selectedId;
    if (!workflowId) return;
    try {
      const resolvedVersionId = versionId ?? workflowDetail?.latest_version?.version_id ?? null;
      const [schema, contract] = await Promise.all([
        workflowApi.inputSchema(workflowId, resolvedVersionId),
        workflowApi.ioContract(workflowId, resolvedVersionId),
      ]);
      setInputSchema(schema);
      setIoContract(contract);
      setRunInput(runInputFromSchema(schema, defaultText));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.loadInputSchemaFailed"));
    }
  };

  const handleSelectNode = (nodeId: string) => {
    const node = editableGraph.nodes.find((item) => item.id === nodeId) ?? null;
    setSelectedNodeId(nodeId);
    setRunEventFocusedNodeId(nodeId);
    setNodeDataDraft(nodeDataText(node));
  };

  const handleFocusRunEventNode = (nodeId: string | null) => {
    setRunEventFocusedNodeId(nodeId);
    if (!nodeId) return;
    const node = editableGraph.nodes.find((item) => item.id === nodeId);
    if (node) {
      setSelectedNodeId(nodeId);
      setNodeDataDraft(nodeDataText(node));
    }
  };

  const handleUpdateNode = (nodeId: string, patch: Partial<GraphNode>) => {
    setEditableGraph((current) => graphWithNodePatch(current, nodeId, patch));
    if (patch.id && patch.id !== nodeId) {
      setSelectedNodeId(patch.id);
      setRunEventFocusedNodeId((current) => (current === nodeId ? null : current));
    }
    if (patch.data) {
      setNodeDataDraft(JSON.stringify(patch.data, null, 2));
    }
  };

  const handleResetNodeData = (nodeId: string) => {
    const node = editableGraph.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const type = node.type || "answer";
    const title = node.title || node.id || type;
    handleUpdateNode(nodeId, {
      data: defaultNodeData(type, title, defaultText, type === "list_operator" ? addNodePreset : undefined),
    });
  };

  const handleAddNode = (
    requestedType?: string,
    position?: WorkflowNodePosition,
    requestedPreset?: string,
  ) => {
    setEditableGraph((current) => {
      const nextNumber = current.nodes.length + 1;
      const id = nextWorkflowNodeId(current);
      const type = requestedType || addNodeType;
      const preset = requestedPreset || addNodePreset;
      const title = type === "start" ? defaultText.startTitle : defaultText.nodeTitle(nextNumber);
      const node: GraphNode = {
        id,
        type,
        title,
        position: position || fallbackWorkflowNodePosition(current.nodes.length),
        supported: true,
        data: defaultNodeData(type, title, defaultText, type === "list_operator" ? preset : undefined),
      };
      if (current.nodes.length === 0 && type === "start") {
        setAddNodeType("answer");
      }
      setSelectedNodeId(id);
      setNodeDataDraft(nodeDataText(node));
      return { ...current, nodes: [...current.nodes, node] };
    });
  };

  const handleRemoveNode = (nodeId: string) => {
    setEditableGraph((current) => {
      const nodes = current.nodes.filter((node) => node.id !== nodeId);
      const edges = current.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId);
      const nextSelected = nodes[0]?.id ?? null;
      setRunEventFocusedNodeId((currentFocused) => currentFocused === nodeId ? null : currentFocused);
      setSelectedNodeId(nextSelected);
      setNodeDataDraft(nodeDataText(nodes[0] ?? null));
      return { nodes, edges };
    });
  };

  const handleAddEdge = (source: string, target: string, sourceHandle?: string) => {
    if (!source || !target) return;
    setEditableGraph((current) => {
      const nodeTypesById = new Map(current.nodes.map((node) => [node.id, node.type || "answer"]));
      const boundaryIssue = workflowEdgeBoundaryIssue(nodeTypesById, source, target, "connection");
      if (boundaryIssue) {
        toast.error(boundaryIssue);
        return current;
      }
      return {
        ...current,
        edges: [
          ...current.edges,
          {
            id: `edge_${Date.now()}`,
            source,
            target,
            source_handle: sourceHandle || null,
            target_handle: null,
            valid: true,
          },
        ],
      };
    });
  };

  const handleUpdateEdge = (edgeId: string, patch: Partial<GraphEdge>) => {
    if (!edgeId) return;
    setEditableGraph((current) => ({
      ...current,
      edges: current.edges.map((edge) => (edge.id === edgeId ? { ...edge, ...patch } : edge)),
    }));
  };

  const handleRemoveEdge = (edgeId: string) => {
    setEditableGraph((current) => ({
      ...current,
      edges: current.edges.filter((edge) => edge.id !== edgeId),
    }));
  };

  const handleSaveGraphVersion = async () => {
    if (!selectedWorkflow) return;
    try {
      let graphToSave = editableGraph;
      if (selectedNodeId) {
        const parsed = JSON.parse(nodeDataDraft) as Record<string, unknown>;
        graphToSave = graphWithNodePatch(editableGraph, selectedNodeId, { data: parsed });
        setEditableGraph(graphToSave);
      }
      const issues = validateEditableGraph(graphToSave);
      if (issues.length > 0) {
        toast.error(`Fix graph issues before saving: ${issues[0]}`);
        return;
      }
      const sourcePayload = graphToWorkflowDsl(graphToSave);
      const nextText = JSON.stringify(sourcePayload, null, 2);
      setDslText(nextText);
      setSourceFormat("json");
      setIsSavingVersion(true);
      const response = await workflowApi.createVersion(selectedWorkflow.workflow_id, {
        name: workflowName.trim() || selectedWorkflow.name,
        source_payload: sourcePayload,
        source_format: "json",
      });
      setReport(normalizeWorkflowImportReport(response.compatibility_report));
      applySavedVersionBoundary(response);
      toast.success(t("workflowPlugin.editor.toast.graphVersionSaved"));
      await loadWorkflows();
      setSelectedId(selectedWorkflow.workflow_id);
      await refreshSelectedWorkflow(selectedWorkflow.workflow_id, savedWorkflowVersionId(response));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.saveGraphFailed"));
    } finally {
      setIsSavingVersion(false);
    }
  };

  const handleSaveVersion = async () => {
    if (!selectedWorkflow) return;
    setIsSavingVersion(true);
    try {
      const response = await workflowApi.createVersion(selectedWorkflow.workflow_id, {
        name: workflowName.trim() || selectedWorkflow.name,
        source_content: dslText,
        source_format: sourceFormat,
      });
      setReport(normalizeWorkflowImportReport(response.compatibility_report));
      applySavedVersionBoundary(response);
      toast.success(t("workflowPlugin.editor.toast.workflowVersionSaved"));
      await loadWorkflows();
      setSelectedId(selectedWorkflow.workflow_id);
      await refreshSelectedWorkflow(selectedWorkflow.workflow_id, savedWorkflowVersionId(response));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.saveVersionFailed"));
    } finally {
      setIsSavingVersion(false);
    }
  };

  const handlePublish = async () => {
    if (!selectedWorkflow) return;
    setIsPublishing(true);
    try {
      await workflowApi.publish(
        selectedWorkflow.workflow_id,
        workflowDetail?.latest_version?.version_id,
      );
      toast.success(t("workflowPlugin.editor.toast.workflowPublished"));
      await loadWorkflows();
      setSelectedId(selectedWorkflow.workflow_id);
      await refreshSelectedWorkflow(selectedWorkflow.workflow_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.publishFailed"));
    } finally {
      setIsPublishing(false);
    }
  };

  const handleValidate = async () => {
    if (!selectedWorkflow) return;
    setIsValidating(true);
    try {
      const response = await workflowApi.validate(
        selectedWorkflow.workflow_id,
        selectedVersionId ?? workflowDetail?.latest_version?.version_id,
      );
      setReport((current) => current ? reportWithValidationPreflight(current, response) : current);
      if (response.runnable) {
        toast.success(t("workflowPlugin.editor.toast.preflightPassed", { count: response.reachable_node_ids.length }));
      } else {
        toast.error(t("workflowPlugin.editor.toast.preflightFailed", {
          reason: response.errors[0] || t("workflowPlugin.editor.toast.workflowNotRunnable"),
        }));
      }
    } catch (error) {
      toast.error(error instanceof Error
        ? error.message
        : t("workflowPlugin.editor.toast.preflightFailed", {
            reason: t("workflowPlugin.editor.toast.workflowNotRunnable"),
          }));
    } finally {
      setIsValidating(false);
    }
  };

  const handleSaveCredential = async () => {
    const ref = credentialDraft.ref.trim();
    if (!ref) {
      toast.error(t("workflowPlugin.editor.toast.credentialRefRequired"));
      return;
    }
    setIsSavingCredential(true);
    try {
      await workflowApi.upsertCredential({
        ref,
        type: credentialDraft.type.trim() || "credential_ref",
        label: credentialDraft.label.trim(),
        description: credentialDraft.description.trim(),
        secret: credentialDraft.secret || null,
      });
      toast.success(t("workflowPlugin.editor.toast.credentialSaved"));
      setCredentialDraft(EMPTY_CREDENTIAL_DRAFT);
      await loadCredentials();
      if (selectedWorkflow) {
        const response = await workflowApi.validate(
          selectedWorkflow.workflow_id,
          selectedVersionId ?? workflowDetail?.latest_version?.version_id,
        );
        setReport((current) => current ? reportWithValidationPreflight(current, response) : current);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.saveCredentialFailed"));
    } finally {
      setIsSavingCredential(false);
    }
  };

  const handleDeleteCredential = async (credentialId: string) => {
    if (!credentialId) return;
    setIsDeletingCredentialId(credentialId);
    try {
      await workflowApi.deleteCredential(credentialId);
      toast.success(t("workflowPlugin.editor.toast.credentialDeleted"));
      await loadCredentials();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.deleteCredentialFailed"));
    } finally {
      setIsDeletingCredentialId(null);
    }
  };

  const handleUnpublish = async () => {
    if (!selectedWorkflow) return;
    setIsPublishing(true);
    try {
      await workflowApi.unpublish(selectedWorkflow.workflow_id);
      toast.success(t("workflowPlugin.editor.toast.workflowReturnedToDraft"));
      await loadWorkflows();
      setSelectedId(selectedWorkflow.workflow_id);
      await refreshSelectedWorkflow(selectedWorkflow.workflow_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.unpublishFailed"));
    } finally {
      setIsPublishing(false);
    }
  };

  const handleDeleteWorkflow = async (workflow: WorkflowSummary | null) => {
    if (!workflow || workflow.status === "archived") return;
    const confirmed = typeof window === "undefined"
      ? true
      : window.confirm(t("workflowPlugin.editor.delete.confirm", { name: workflow.name }));
    if (!confirmed) return;

    setIsDeletingWorkflowId(workflow.workflow_id);
    try {
      await workflowApi.deleteWorkflow(workflow.workflow_id);
      toast.success(t("workflowPlugin.editor.toast.workflowDeleted"));
      const remainingWorkflows = workflows.filter((item) => item.workflow_id !== workflow.workflow_id);
      setWorkflows(remainingWorkflows);
      setWorkflowTotal((current) => Math.max(0, current - 1));
      if (selectedId === workflow.workflow_id) {
        setSelectedId(remainingWorkflows[0]?.workflow_id ?? null);
        setWorkflowDetail(null);
        setVersions([]);
        setInputSchema(null);
        setIoContract(null);
        setRuns([]);
        setRunResult(null);
        setRunEvents([]);
        setEditableGraph({ nodes: [], edges: [] });
        if (routeSelectedWorkflowId === workflow.workflow_id || routeSelectedRunId) {
          navigate("/workflows");
        }
      }
      await loadWorkflows();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.deleteWorkflowFailed"));
    } finally {
      setIsDeletingWorkflowId(null);
    }
  };

  const handleRun = async () => {
    if (!selectedWorkflow) return;
    if (runInputDraftStatus.message || !runInputDraftStatus.parsed) {
      toast.error(runInputDraftMessage || t("workflowPlugin.editor.toast.invalidWorkflowInput"));
      return;
    }
    setIsRunning(true);
    cancelRequestedRef.current = false;
    try {
      const response = await workflowApi.run(
        selectedWorkflow.workflow_id,
        runInputDraftStatus.parsed,
        runMode,
        selectedVersionId ?? workflowDetail?.latest_version?.version_id,
      );
      setRunResult(response);
      setRuns((current) => [response, ...current.filter((run) => run.run_id !== response.run_id)].slice(0, 20));
      const inlineRunEvents = workflowRunEvents(response.events);
      const responseRunId = typeof response.run_id === "string" && response.run_id ? response.run_id : null;
      const shouldStreamRun = runMode === "stream" && responseRunId !== null && isWorkflowRunWaiting(response.status);
      const shouldPollRun = runMode === "async" && responseRunId !== null && isWorkflowRunWaiting(response.status);
      if (inlineRunEvents.length > 0) {
        setRunEvents(inlineRunEvents);
      } else {
        setRunEvents([]);
      }
      if (inlineRunEvents.length === 0 && responseRunId && !shouldStreamRun && !shouldPollRun) {
        try {
          const eventResponse = await workflowApi.runEvents(
            selectedWorkflow.workflow_id,
            responseRunId,
          );
          setRunEvents(workflowRunEvents(eventResponse.events));
        } catch (error) {
          toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadRunEventsFailed")));
        }
      }
      if (shouldStreamRun) {
        toast.success(t("workflowPlugin.editor.toast.workflowStreamOpened"));
        await streamRunUntilFinished(selectedWorkflow.workflow_id, responseRunId);
      } else if (shouldPollRun) {
        toast.success(t("workflowPlugin.editor.toast.workflowRunQueued"));
        await pollRunUntilFinished(selectedWorkflow.workflow_id, responseRunId);
      } else if (response.status === "paused") {
        setApprovalComment("");
        toast.success(t("workflowPlugin.editor.toast.workflowPausedForApproval"));
        await loadPendingApprovals();
      } else if (response.status === "succeeded") {
        toast.success(t("workflowPlugin.editor.toast.workflowRunCompleted"));
      } else {
        toast.error(response.error || t("workflowPlugin.editor.toast.workflowRunFailed"));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.runFailed"));
    } finally {
      setIsRunning(false);
    }
  };

  const pollRunUntilFinished = async (workflowId: string, runId: string) => {
    setIsPollingRun(true);
    try {
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        if (cancelRequestedRef.current) {
          return;
        }
        const eventResponse = await workflowApi.runEvents(workflowId, runId);
        setRunResult(eventResponse.run);
        setRunEvents(workflowRunEvents(eventResponse.events));
        setRuns((current) => [eventResponse.run, ...current.filter((run) => run.run_id !== runId)].slice(0, 20));
        if (!isWorkflowRunWaiting(eventResponse.run.status)) {
          await refreshSelectedWorkflow(workflowId);
          if (eventResponse.run.status === "succeeded") {
            toast.success(t("workflowPlugin.editor.toast.workflowRunCompleted"));
          } else if (eventResponse.run.status === "failed") {
            toast.error(eventResponse.run.error || t("workflowPlugin.editor.toast.workflowRunFailed"));
          } else if (eventResponse.run.status === "cancelled") {
            toast.success(t("workflowPlugin.editor.toast.workflowRunCancelled"));
          } else if (eventResponse.run.status === "paused") {
            setApprovalComment("");
            toast.success(t("workflowPlugin.editor.toast.workflowPausedForApproval"));
            await loadPendingApprovals();
          }
          return;
        }
      }
      toast.error(t("workflowPlugin.editor.toast.workflowRunStillRunning"));
    } finally {
      setIsPollingRun(false);
    }
  };

  const streamRunUntilFinished = async (workflowId: string, runId: string) => {
    setIsPollingRun(true);
    try {
      let streamErrorMessage: string | null = null;
      await workflowApi.streamRunEvents(
        workflowId,
        runId,
        {
          onEvent: (event) => {
            setRunEvents((current) => mergeWorkflowRunEvents(current, [event]));
          },
          onSnapshot: (snapshot) => {
            setRunResult(snapshot.run);
            setRuns((current) => [snapshot.run, ...current.filter((run) => run.run_id !== runId)].slice(0, 20));
          },
          onError: (streamError) => {
            streamErrorMessage = streamError.error;
            setRunResult((current) => ({
              ...(current ?? {
                workflow_id: workflowId,
                run_id: runId,
                mode: "stream",
                output: {},
              }),
              workflow_id: workflowId,
              run_id: runId,
              status: "failed",
              error: streamError.error,
            }));
            toast.error(streamError.error || t("workflowPlugin.editor.toast.workflowStreamFailed"));
          },
        },
        { pollMs: 500, timeoutMs: 30000 },
      );
      if (streamErrorMessage) {
        return;
      }
      const eventResponse = await workflowApi.runEvents(workflowId, runId);
      setRunResult(eventResponse.run);
      setRunEvents(workflowRunEvents(eventResponse.events));
      setRuns((current) => [eventResponse.run, ...current.filter((run) => run.run_id !== runId)].slice(0, 20));
      if (!eventResponse.run || isWorkflowRunWaiting(eventResponse.run.status)) {
        toast.error(t("workflowPlugin.editor.toast.workflowStreamStillRunning"));
        return;
      }
      await refreshSelectedWorkflow(workflowId);
      if (eventResponse.run.status === "succeeded") {
        toast.success(t("workflowPlugin.editor.toast.workflowRunCompleted"));
      } else if (eventResponse.run.status === "failed") {
        toast.error(eventResponse.run.error || t("workflowPlugin.editor.toast.workflowRunFailed"));
      } else if (eventResponse.run.status === "cancelled") {
        toast.success(t("workflowPlugin.editor.toast.workflowRunCancelled"));
      } else if (eventResponse.run.status === "paused") {
        setApprovalComment("");
        toast.success(t("workflowPlugin.editor.toast.workflowPausedForApproval"));
        await loadPendingApprovals();
      }
    } catch (error) {
      if (cancelRequestedRef.current) {
        return;
      }
      await pollRunUntilFinished(workflowId, runId);
    } finally {
      setIsPollingRun(false);
    }
  };

  const handleCancelRun = async () => {
    if (!selectedWorkflow || !runResult?.run_id) return;
    cancelRequestedRef.current = true;
    try {
      const response = await workflowApi.cancelRun(selectedWorkflow.workflow_id, runResult.run_id);
      setRunResult(response);
      setRuns((current) => [response, ...current.filter((run) => run.run_id !== response.run_id)].slice(0, 20));
      const cancelEvents = workflowRunEvents(response.events);
      if (cancelEvents.length > 0) {
        setRunEvents((current) => [...current, ...cancelEvents]);
      }
      toast.success(t("workflowPlugin.editor.toast.workflowRunCancelled"));
      await refreshSelectedWorkflow(selectedWorkflow.workflow_id);
      await loadPendingApprovals();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.cancelFailed"));
    } finally {
      setIsPollingRun(false);
    }
  };

  const handleResumeRun = async (approved: boolean) => {
    if (!runResult?.workflow_id || !runResult.run_id || runResult.status !== "paused") return;
    const workflowId = runResult.workflow_id;
    setIsResumingRun(true);
    try {
      const response = await workflowApi.resumeRun(workflowId, runResult.run_id, {
        approved,
        comment: approvalComment,
      });
      setRunResult(response);
      setRuns((current) => [response, ...current.filter((run) => run.run_id !== response.run_id)].slice(0, 20));
      const resumeEvents = workflowRunEvents(response.events);
      if (resumeEvents.length > 0) {
        setRunEvents((current) => mergeWorkflowRunEvents(current, resumeEvents));
      }
      setApprovalComment("");
      if (response.status === "succeeded") {
        toast.success(t("workflowPlugin.editor.toast.workflowRunResumed"));
      } else if (response.status === "paused") {
        toast.success(t("workflowPlugin.editor.toast.workflowPausedForApproval"));
      } else if (response.status === "failed") {
        toast.error(response.error || t("workflowPlugin.editor.toast.workflowRunFailed"));
      }
      await refreshSelectedWorkflow(workflowId);
      await loadPendingApprovals();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.resumeFailed"));
    } finally {
      setIsResumingRun(false);
    }
  };

  const handleSelectRun = async (run: WorkflowRunResponse) => {
    if (!selectedWorkflow || !run.run_id) return;
    setRunResult(run);
    setRunEvents([]);
    setIsLoadingRunEvents(true);
    try {
      const eventResponse = await workflowApi.runEvents(selectedWorkflow.workflow_id, run.run_id);
      setRunResult(eventResponse.run);
      setRunEvents(workflowRunEvents(eventResponse.events));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.loadRunEventsFailed"));
    } finally {
      setIsLoadingRunEvents(false);
    }
  };

  const handleSelectPendingApproval = async (run: WorkflowRunResponse) => {
    if (!run.run_id) return;
    setSelectedId(run.workflow_id);
    setRunResult(run);
    setRunEvents([]);
    setApprovalComment("");
    setIsLoadingRunEvents(true);
    try {
      const eventResponse = await workflowApi.runEvents(run.workflow_id, run.run_id);
      setRunResult(eventResponse.run);
      setRunEvents(workflowRunEvents(eventResponse.events));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("workflowPlugin.editor.toast.loadApprovalRunFailed"));
    } finally {
      setIsLoadingRunEvents(false);
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-[var(--theme-bg)] px-3 py-3 text-[var(--theme-text)] sm:px-5 sm:py-4">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--theme-border)] px-4 py-3">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h1 className="truncate text-base font-semibold">{workflowRouteTitle}</h1>
              <span className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-0.5 text-xs text-[var(--theme-text-secondary)]">
                {workflowRouteMode}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-[var(--theme-text-secondary)]">
              {workflowRouteSubtitle}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {workflowRouteMode === "list" && (
              <>
                <Link
                  to="/workflows?create=blank"
                  className="inline-flex h-8 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-xs text-white"
                >
                  <Plus size={14} />
                  {t("workflowPlugin.editor.toolbar.newWorkflow")}
                </Link>
                <Link
                  to="/workflows?create=import"
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)]"
                >
                  <Upload size={14} />
                  {t("workflowPlugin.editor.common.import")}
                </Link>
              </>
            )}
            {workflowRouteMode === "create" && (
              <Link
                to="/workflows?create=import"
                className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)]"
              >
                <Upload size={14} />
                {t("workflowPlugin.editor.common.import")}
              </Link>
            )}
            {workflowRouteMode === "import" && (
              <Link
                to="/workflows?create=blank"
                className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)]"
              >
                <Plus size={14} />
                {t("workflowPlugin.editor.toolbar.newWorkflow")}
              </Link>
            )}
            {workflowRouteMode !== "list" && (
              <Link
                to="/workflows"
                className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)]"
              >
                {t("workflowPlugin.editor.toolbar.list")}
              </Link>
            )}
            {runResult?.workflow_id && runResult.run_id && (
              <Link
                to={workflowRunTracePath(runResult.workflow_id, runResult.run_id)}
                className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 text-xs text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)]"
              >
                {t("workflowPlugin.editor.toolbar.trace")}
              </Link>
            )}
            <button
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--theme-border)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg)] disabled:opacity-50"
              type="button"
              onClick={loadWorkflows}
              disabled={isLoading}
              title={t("workflowPlugin.editor.toolbar.refresh")}
            >
              <RefreshCw size={16} className={isLoading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {loadError && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-700">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <AlertTriangle size={16} className="shrink-0" />
                <span className="min-w-0 truncate" title={loadError}>
                  {t("workflowPlugin.editor.inventory.serviceUnavailable", { error: loadError })}
                </span>
              </div>
              <button
                type="button"
                onClick={loadWorkflows}
                disabled={isLoading}
                className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-amber-500/40 px-3 text-xs hover:bg-amber-500/10 disabled:opacity-50"
              >
                <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                {t("workflowPlugin.editor.toolbar.retry")}
              </button>
            </div>
          </div>
        )}

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden">
          <main className="min-h-0 overflow-auto p-3 sm:p-4">
            <div className={workspaceGridClass}>
              <div className={`space-y-4 ${workflowRouteMode === "run" ? "xl:order-last" : ""}`}>
                {workflowRouteMode === "list" && (
                <>
                <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{t("workflowPlugin.editor.inventory.title")}</div>
                      <div className="mt-0.5 text-xs text-[var(--theme-text-secondary)]">
                        {t("workflowPlugin.editor.inventory.visibleTotal", { visible: workflows.length, total: workflowTotal })}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="relative block min-w-0">
                        <Search className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[var(--theme-text-secondary)]" size={14} />
                        <input
                          className="h-9 w-56 max-w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] pl-8 pr-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                          value={workflowQuery}
                          onChange={(event) => setWorkflowQuery(event.target.value)}
                          placeholder={t("workflowPlugin.editor.inventory.searchPlaceholder")}
                        />
                      </label>
                      <select
                        className="h-9 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                        value={workflowStatusFilter}
                        onChange={(event) => setWorkflowStatusFilter(event.target.value as WorkflowStatusFilter)}
                      >
                        <option value="all">{t("workflowPlugin.editor.inventory.allStatuses")}</option>
                        <option value="draft">{t("workflowPlugin.editor.inventory.draft")}</option>
                        <option value="published">{t("workflowPlugin.editor.inventory.published")}</option>
                        <option value="archived">{t("workflowPlugin.editor.inventory.archived")}</option>
                      </select>
                    </div>
                  </div>

                  {isLoading ? (
                    <div className="flex items-center gap-2 rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-sm text-[var(--theme-text-secondary)]">
                      <Loader2 className="animate-spin" size={16} /> {t("workflowPlugin.editor.inventory.loadingWorkflows")}
                    </div>
                  ) : workflows.length === 0 && !hasWorkflowInventoryFilter ? (
                    <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
                      <div>{t("workflowPlugin.editor.inventory.noWorkflows")}</div>
                      <Link
                        to="/workflows?create=blank"
                        className="mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-sm text-white"
                      >
                        <Plus size={16} />
                        {t("workflowPlugin.editor.toolbar.newWorkflow")}
                      </Link>
                    </div>
                  ) : workflows.length === 0 ? (
                    <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.inventory.noMatchingWorkflows")}
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-[44rem] w-full border-separate border-spacing-0 text-left text-xs">
                        <thead className="text-[var(--theme-text-secondary)]">
                          <tr>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 font-medium">{t("workflowPlugin.editor.inventory.name")}</th>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 font-medium">{t("workflowPlugin.editor.inventory.status")}</th>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 font-medium">{t("workflowPlugin.editor.inventory.latest")}</th>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 font-medium">{t("workflowPlugin.editor.inventory.published")}</th>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 font-medium">{t("workflowPlugin.editor.inventory.updated")}</th>
                            <th className="border-b border-[var(--theme-border)] px-2 py-2 text-right font-medium">{t("workflowPlugin.editor.inventory.actions")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {workflows.map((workflow) => {
                            const selected = workflow.workflow_id === selectedId;
                            return (
                              <tr
                                key={workflow.workflow_id}
                                className={selected ? "bg-[var(--theme-bg-secondary)]" : "hover:bg-[var(--theme-bg-secondary)]"}
                              >
                                <td className="max-w-[14rem] border-b border-[var(--theme-border)] px-2 py-2">
                                  <button
                                    type="button"
                                    onClick={() => setSelectedId(workflow.workflow_id)}
                                    className="flex min-w-0 items-center gap-2 text-left hover:text-[var(--theme-primary)]"
                                  >
                                    <GitBranch size={14} className="shrink-0" />
                                    <span className="truncate font-medium">{workflow.name}</span>
                                  </button>
                                  <div className="mt-1 truncate text-[var(--theme-text-secondary)]">
                                    {workflow.workflow_id}
                                  </div>
                                </td>
                                <td className="border-b border-[var(--theme-border)] px-2 py-2">
                                  <span className={`inline-flex rounded-md border px-2 py-1 ${workflowStatusBadgeClass(workflow.status)}`}>
                                    {workflow.status}
                                  </span>
                                </td>
                                <td className="max-w-[9rem] border-b border-[var(--theme-border)] px-2 py-2">
                                  <span className="block truncate">{workflow.latest_version_id ?? t("workflowPlugin.editor.common.none")}</span>
                                </td>
                                <td className="max-w-[9rem] border-b border-[var(--theme-border)] px-2 py-2">
                                  <span className="block truncate">{workflow.published_version_id ?? t("workflowPlugin.editor.common.none")}</span>
                                </td>
                                <td className="whitespace-nowrap border-b border-[var(--theme-border)] px-2 py-2 text-[var(--theme-text-secondary)]">
                                  {formatDate(workflow.updated_at)}
                                </td>
                                <td className="border-b border-[var(--theme-border)] px-2 py-2">
                                  <div className="flex justify-end gap-2">
                                    <button
                                      type="button"
                                      onClick={() => setSelectedId(workflow.workflow_id)}
                                      className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 hover:bg-[var(--theme-bg)]"
                                    >
                                      {t("workflowPlugin.editor.inventory.select")}
                                    </button>
                                    <Link
                                      to={workflowEditorPath(workflow.workflow_id)}
                                      className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 hover:bg-[var(--theme-bg)]"
                                    >
                                      {t("workflowPlugin.editor.toolbar.editor")}
                                    </Link>
                                    <button
                                      type="button"
                                      onClick={() => handleDeleteWorkflow(workflow)}
                                      disabled={workflow.status === "archived" || isDeletingWorkflowId === workflow.workflow_id}
                                      data-testid={`workflow-delete-${workflow.workflow_id}`}
                                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-red-500/30 text-red-600 hover:bg-red-500/10 disabled:opacity-50"
                                      title={t("workflowPlugin.editor.delete.title")}
                                    >
                                      {isDeletingWorkflowId === workflow.workflow_id ? (
                                        <Loader2 className="animate-spin" size={14} />
                                      ) : (
                                        <Trash2 size={14} />
                                      )}
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                </>
                )}

                {workflowRouteMode === "create" && (
                  <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-4">
                    <div className="mb-4 flex items-center gap-2 text-sm font-medium">
                      <Plus size={16} /> {t("workflowPlugin.editor.create.title")}
                    </div>
                    <label className="block text-xs text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.import.workflowNamePlaceholder")}
                    </label>
                    <input
                      className="mt-1 h-10 w-full max-w-xl rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                      value={workflowName}
                      onChange={(event) => setWorkflowName(event.target.value)}
                      placeholder={defaultText.blankWorkflowName}
                    />
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={handleCreateBlankWorkflow}
                        disabled={isCreatingWorkflow}
                        data-testid="workflow-create-blank-submit"
                        className="inline-flex h-9 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-sm text-white disabled:opacity-50"
                      >
                        {isCreatingWorkflow ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
                        {t("workflowPlugin.editor.create.createBlank")}
                      </button>
                      <Link
                        to="/workflows?create=import"
                        className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)]"
                      >
                        <Upload size={16} />
                        {t("workflowPlugin.editor.common.import")}
                      </Link>
                      <Link
                        to="/workflows"
                        className="inline-flex h-9 items-center rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)]"
                      >
                        {t("workflowPlugin.editor.toolbar.list")}
                      </Link>
                    </div>
                  </div>
                )}

                {workflowRouteMode === "import" && (
                  <>
                    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                        <FileJson size={16} /> {t("workflowPlugin.editor.import.title")}
                      </div>
                      <input
                        className="mb-2 h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                        value={workflowName}
                        onChange={(event) => setWorkflowName(event.target.value)}
                        placeholder={t("workflowPlugin.editor.import.workflowNamePlaceholder")}
                      />
                      <select
                        className="mb-2 h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                        value={sourceFormat}
                        onChange={(event) => setSourceFormat(event.target.value as "json" | "yaml")}
                      >
                        <option value="json">JSON</option>
                        <option value="yaml">YAML</option>
                      </select>
                      <textarea
                        className="min-h-64 w-full resize-y rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-3 font-mono text-xs outline-none focus:border-[var(--theme-primary)]"
                        value={dslText}
                        onChange={(event) => setDslText(event.target.value)}
                        spellCheck={false}
                      />
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => handleImport(true)}
                          disabled={isImporting}
                          data-testid="workflow-import-dry-run"
                          className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                        >
                          {isImporting ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />}
                          {t("workflowPlugin.editor.import.dryRun")}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleImport(false)}
                          disabled={isImporting}
                          data-testid="workflow-import-submit"
                          className="inline-flex h-9 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-sm text-white disabled:opacity-50"
                        >
                          {isImporting ? <Loader2 className="animate-spin" size={16} /> : <Upload size={16} />}
                          {t("workflowPlugin.editor.common.import")}
                        </button>
                        <Link
                          to="/workflows"
                          className="inline-flex h-9 items-center rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)]"
                        >
                          {t("workflowPlugin.editor.toolbar.list")}
                        </Link>
                      </div>
                    </div>
                    <ReportPanel report={report} />
                  </>
                )}

                {workflowRouteMode === "editor" && (
                <GraphEditor
                  graph={editableGraph}
                  selectedNodeId={selectedNodeId}
                  nodeRunStates={nodeRunStates}
                  nodeDataDraft={nodeDataDraft}
                  graphIssues={graphIssues}
                  addNodeType={addNodeType}
                  addNodePreset={addNodePreset}
                  onSelectNode={handleSelectNode}
                  onNodeDataDraftChange={setNodeDataDraft}
                  onUpdateNode={handleUpdateNode}
                  onResetNodeData={handleResetNodeData}
                  onAddNodeTypeChange={setAddNodeType}
                  onAddNodePresetChange={setAddNodePreset}
                  onAddNode={handleAddNode}
                  onRemoveNode={handleRemoveNode}
                  onAddEdge={handleAddEdge}
                  onUpdateEdge={handleUpdateEdge}
                  onRemoveEdge={handleRemoveEdge}
                  onSave={handleSaveGraphVersion}
                  workflowOptions={workflows}
                  currentWorkflowId={selectedWorkflow?.workflow_id}
                  disabled={!selectedWorkflow || isSavingVersion}
                />
                )}
              </div>

              {(workflowRouteMode === "editor" || workflowRouteMode === "run") && (
              <div className={`space-y-4 ${workflowRouteMode === "run" ? "xl:order-first" : ""}`}>
                <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="min-w-0 text-sm font-medium">
                      {selectedWorkflow ? selectedWorkflow.name : t("workflowPlugin.editor.run.noWorkflowSelected")}
                    </div>
                    {selectedWorkflow && (
                      <span className="rounded-md bg-[var(--theme-bg-secondary)] px-2 py-1 text-xs text-[var(--theme-text-secondary)]">
                        {selectedWorkflow.status}
                      </span>
                    )}
                  </div>
                  {selectedWorkflow && (
                    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                      <span>{t("workflowPlugin.editor.run.latestVersion", { version: workflowDetail?.latest_version_id ?? t("workflowPlugin.editor.common.none") })}</span>
                      <span>{t("workflowPlugin.editor.run.publishedVersion", { version: workflowDetail?.published_version_id ?? t("workflowPlugin.editor.common.none") })}</span>
                    </div>
                  )}
                  {selectedWorkflow && (
                    <div className="mb-3 flex flex-wrap gap-2">
                      <Link
                        to={workflowEditorPath(selectedWorkflow.workflow_id)}
                        className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)]"
                      >
                        {t("workflowPlugin.editor.run.openEditor")}
                      </Link>
                      {runResult?.run_id && (
                        <Link
                          to={workflowRunTracePath(selectedWorkflow.workflow_id, runResult.run_id)}
                          className="inline-flex h-8 items-center rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)]"
                        >
                          {t("workflowPlugin.editor.run.openTrace")}
                        </Link>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDeleteWorkflow(selectedWorkflow)}
                        disabled={selectedWorkflow.status === "archived" || isDeletingWorkflowId === selectedWorkflow.workflow_id}
                        data-testid="workflow-delete-selected"
                        className="inline-flex h-8 items-center gap-2 rounded-md border border-red-500/30 px-3 text-xs text-red-600 hover:bg-red-500/10 disabled:opacity-50"
                      >
                        {isDeletingWorkflowId === selectedWorkflow.workflow_id ? (
                          <Loader2 className="animate-spin" size={14} />
                        ) : (
                          <Trash2 size={14} />
                        )}
                        {t("workflowPlugin.editor.delete.action")}
                      </button>
                    </div>
                  )}
                  {selectedWorkflow && versions.length > 0 && (
                    <div className="mb-3 grid gap-1.5">
                      <label className="text-xs font-medium text-[var(--theme-text-secondary)]" htmlFor="workflow-debug-version">
                        {t("workflowPlugin.editor.run.debugVersion")}
                      </label>
                      <select
                        id="workflow-debug-version"
                        className="h-9 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                        value={selectedVersionId ?? ""}
                        onChange={(event) => handleSelectDebugVersion(event.target.value || null)}
                        disabled={isRunning || isPollingRun || isValidating}
                      >
                        {versions.map((version) => (
                          <option key={version.version_id} value={version.version_id}>
                            v{version.version_number} {version.version_id === workflowDetail?.latest_version_id ? t("workflowPlugin.editor.run.latestBadge") : ""}
                            {version.version_id === workflowDetail?.published_version_id ? ` ${t("workflowPlugin.editor.run.publishedBadge")}` : ""}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  {selectedWorkflow && (
                    <div className="mb-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={handleValidate}
                        disabled={isValidating || !workflowDetail?.latest_version_id}
                        data-testid="workflow-preflight"
                        className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      >
                        {isValidating ? <Loader2 className="animate-spin" size={14} /> : <AlertTriangle size={14} />}
                        {t("workflowPlugin.editor.run.preflight")}
                      </button>
                      <button
                        type="button"
                        onClick={handleSaveVersion}
                        disabled={!selectedWorkflow || isSavingVersion}
                        data-testid="workflow-save-version"
                        className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      >
                        {isSavingVersion ? <Loader2 className="animate-spin" size={14} /> : <FileJson size={14} />}
                        {t("workflowPlugin.editor.run.saveVersion")}
                      </button>
                      <button
                        type="button"
                        onClick={handlePublish}
                        disabled={isPublishing || !workflowDetail?.latest_version_id}
                        data-testid="workflow-publish-latest"
                        className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      >
                        {isPublishing ? <Loader2 className="animate-spin" size={14} /> : <CheckCircle2 size={14} />}
                        {t("workflowPlugin.editor.run.publishLatest")}
                      </button>
                      <button
                        type="button"
                        onClick={handleUnpublish}
                        disabled={isPublishing || selectedWorkflow.status !== "published"}
                        data-testid="workflow-unpublish"
                        className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                      >
                        {isPublishing ? <Loader2 className="animate-spin" size={14} /> : <XCircle size={14} />}
                        {t("workflowPlugin.editor.run.unpublish")}
                      </button>
                    </div>
                  )}
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                      {inputFields.length === 0 ? (
                        <span className="text-xs text-[var(--theme-text-secondary)]">{t("workflowPlugin.editor.run.inputSchemaUnavailable")}</span>
                      ) : (
                        inputFields.map((item) => (
                          <span
                            key={item.field}
                            className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-2 py-1 text-xs text-[var(--theme-text-secondary)]"
                            title={`${item.field}: ${item.type} (${item.source})`}
                          >
                            <span className="truncate font-medium text-[var(--theme-text)]">{item.field}</span>
                            <span>{item.type}</span>
                            {item.required && <span className="text-amber-500">{t("workflowPlugin.editor.common.required")}</span>}
                            {item.optionCount > 0 && <span>{item.optionCount} {t("workflowPlugin.editor.common.options")}</span>}
                          </span>
                        ))
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={handleResetRunInput}
                      disabled={!selectedWorkflow || isRunning || isPollingRun}
                      className="inline-flex h-8 items-center gap-2 rounded-md border border-[var(--theme-border)] px-2 text-xs hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                    >
                      <FileJson size={14} />
                      {t("workflowPlugin.editor.run.resetInput")}
                    </button>
                  </div>
                  <WorkflowInputForm
                    fields={inputFields}
                    runInput={runInput}
                    onChange={setRunInput}
                    disabled={!selectedWorkflow || isRunning || isPollingRun}
                  />
                  {contractInterfaceItems.length > 0 && (
                    <div
                      className="mb-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2"
                      data-testid="workflow-interface-contract"
                    >
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="text-xs font-medium text-[var(--theme-text-secondary)]">
                          {t("workflowPlugin.editor.run.workflowInterface")}
                        </div>
                        <span className="rounded bg-[var(--theme-bg)] px-1.5 py-0.5 text-[10px] text-[var(--theme-text-secondary)]">
                          {t("workflowPlugin.plugin.name")}
                        </span>
                      </div>
                      <div className="grid gap-1.5 sm:grid-cols-3">
                        {contractInterfaceItems.map((item) => (
                          <div
                            key={item.label}
                            className="min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1.5"
                            data-testid={`workflow-interface-${item.label.toLowerCase()}`}
                          >
                            <div className="flex items-center justify-between gap-2 text-[10px] uppercase text-[var(--theme-text-tertiary)]">
                              <span>{item.label}</span>
                              <GitBranch size={11} />
                            </div>
                            <div className="mt-1 truncate font-mono text-xs text-[var(--theme-text)]" title={item.value}>
                              {item.value}
                            </div>
                            <div className="mt-0.5 truncate text-[10px] text-[var(--theme-text-secondary)]" title={item.detail}>
                              {item.detail}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="mb-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-2">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="text-xs font-medium text-[var(--theme-text-secondary)]">
                        {t("workflowPlugin.editor.run.outputContract")}
                      </div>
                      {ioContract && (
                        <span className="rounded bg-[var(--theme-bg)] px-1.5 py-0.5 text-[10px] text-[var(--theme-text-secondary)]">
                          {ioContract.output_schema_source}
                        </span>
                      )}
                    </div>
                    {outputFields.length === 0 ? (
                      <div className="text-xs text-[var(--theme-text-secondary)]">
                        {t("workflowPlugin.editor.run.outputSchemaUnavailable")}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {outputFields.map((item) => (
                          <span
                            key={item.field}
                            className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1 text-xs text-[var(--theme-text-secondary)]"
                            title={`${item.field}: ${item.type}`}
                          >
                            <span className="truncate font-medium text-[var(--theme-text)]">{item.field}</span>
                            <span>{item.type}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <textarea
                    className={`min-h-24 w-full resize-y rounded-md border bg-[var(--theme-bg-secondary)] p-3 font-mono text-xs outline-none focus:border-[var(--theme-primary)] ${
                      runInputDraftStatus.message ? "border-red-500/50" : "border-[var(--theme-border)]"
                    }`}
                    value={runInput}
                    onChange={(event) => setRunInput(event.target.value)}
                    spellCheck={false}
                  />
                  {runInputDraftStatus.message && (
                    <div className="mt-1 rounded-md border border-red-500/30 bg-red-500/5 px-2 py-1.5 text-xs text-red-600">
                      {runInputDraftMessage}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <select
                      className="h-9 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-3 text-sm outline-none focus:border-[var(--theme-primary)]"
                      value={runMode}
                      onChange={(event) => setRunMode(event.target.value as WorkflowRunMode)}
                      disabled={isRunning || isPollingRun}
                      data-testid="workflow-run-mode"
                    >
                      <option value="async">{t("workflowPlugin.editor.run.modes.async")}</option>
                      <option value="stream">{t("workflowPlugin.editor.run.modes.stream")}</option>
                      <option value="sync">{t("workflowPlugin.editor.run.modes.sync")}</option>
                    </select>
                    <button
                      type="button"
                      onClick={handleRun}
                      disabled={!selectedWorkflow || isRunning || isPollingRun || Boolean(runInputDraftStatus.message)}
                      data-testid="workflow-run-version"
                      className="inline-flex h-9 items-center gap-2 rounded-md bg-[var(--theme-primary)] px-3 text-sm text-white disabled:opacity-50"
                    >
                      {isRunning || isPollingRun ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
                      {isPollingRun
                        ? (runMode === "stream" ? t("workflowPlugin.editor.run.streaming") : t("workflowPlugin.editor.run.polling"))
                        : t("workflowPlugin.editor.run.runVersion")}
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelRun}
                      disabled={!selectedWorkflow || !runResult?.run_id || !(isWorkflowRunWaiting(runResult.status) || runResult.status === "paused")}
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-[var(--theme-border)] px-3 text-sm hover:bg-[var(--theme-bg-secondary)] disabled:opacity-50"
                    >
                      <Square size={15} />
                      {t("workflowPlugin.editor.run.cancel")}
                    </button>
                  </div>
                </div>

                <ReportPanel report={report} />

                <CredentialVaultPanel
                  credentials={credentials}
                  unresolvedRefs={unresolvedCredentialRefs}
                  draft={credentialDraft}
                  isLoading={isLoadingCredentials}
                  isSaving={isSavingCredential}
                  isDeletingId={isDeletingCredentialId}
                  onDraftChange={setCredentialDraft}
                  onPickRef={(ref) => setCredentialDraft(credentialDraftFromRef(ref))}
                  onEditCredential={(credential) => setCredentialDraft(credentialDraftFromCredential(credential))}
                  onSave={handleSaveCredential}
                  onReset={() => setCredentialDraft(EMPTY_CREDENTIAL_DRAFT)}
                  onDelete={handleDeleteCredential}
                />

                <CompatibilityMatrixPanel catalog={nodeCatalog} />

                <PendingApprovalInbox
                  approvals={pendingApprovals}
                  selectedRunId={runResult?.run_id}
                  onSelect={handleSelectPendingApproval}
                  onRefresh={loadPendingApprovals}
                />

                {versions.length > 0 && (
                  <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                    <div className="mb-3 text-sm font-medium">{t("workflowPlugin.editor.run.versions")}</div>
                    <div className="space-y-2">
                      {versions.slice(0, 5).map((version) => (
                        <button
                          key={version.version_id}
                          type="button"
                          onClick={() => handleSelectDebugVersion(version.version_id)}
                          className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                            selectedVersionId === version.version_id
                              ? "border-[var(--theme-primary)] bg-[var(--theme-bg-secondary)]"
                              : "border-transparent bg-[var(--theme-bg-secondary)] hover:border-[var(--theme-primary)]"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-medium">v{version.version_number}</span>
                            <span className="truncate text-[var(--theme-text-secondary)]">{version.version_id}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-2 text-[var(--theme-text-secondary)]">
                            {version.version_id === workflowDetail?.latest_version_id && <span>{t("workflowPlugin.editor.run.latestBadge")}</span>}
                            {version.version_id === workflowDetail?.published_version_id && <span>{t("workflowPlugin.editor.run.publishedBadge")}</span>}
                            <span>{formatDate(version.created_at)}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                  <div className="mb-3 flex items-center justify-between gap-3 text-sm font-medium">
                    <span>{t("workflowPlugin.editor.run.runs")}</span>
                    <span className="text-xs font-normal text-[var(--theme-text-secondary)]">{runs.length}</span>
                  </div>
                  {runs.length === 0 ? (
                    <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.run.noRuns")}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {runs.slice(0, 8).map((run) => {
                        const selected = run.run_id && run.run_id === runResult?.run_id;
                        const outputSummary = workflowRunOutputSummary(run, outputFields);
                        const outputContract = workflowRunOutputContractStatus(run, outputContractStatusLabels);
                        return (
                          <button
                            key={run.run_id || `${run.version_id}-${run.started_at}`}
                            type="button"
                            onClick={() => handleSelectRun(run)}
                            disabled={!run.run_id || isLoadingRunEvents}
                            className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-colors disabled:opacity-50 ${
                              selected
                                ? "border-[var(--theme-primary)] bg-[var(--theme-bg-secondary)]"
                                : "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] hover:border-[var(--theme-primary)]"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="truncate font-medium">{run.run_id || t("workflowPlugin.editor.run.pending")}</span>
                              <span className="inline-flex shrink-0 items-center gap-1.5">
                                {outputContract && (
                                  <span
                                    className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] ${workflowRunOutputContractBadgeClass(outputContract.valid)}`}
                                    title={outputContract.title}
                                  >
                                    {outputContract.valid ? (
                                      <CheckCircle2 size={11} />
                                    ) : (
                                      <AlertTriangle size={11} />
                                    )}
                                    {outputContract.label}
                                  </span>
                                )}
                                <span className={workflowRunStatusTone(run.status)}>{run.status}</span>
                              </span>
                            </div>
                            <div className="mt-1 flex items-center justify-between gap-3 text-[var(--theme-text-secondary)]">
                              <span className="truncate">{run.version_id ?? t("workflowPlugin.editor.run.noVersion")}</span>
                              <span>{run.started_at ? formatDate(run.started_at) : t("workflowPlugin.editor.run.unknown")}</span>
                            </div>
                            {outputSummary && (
                              <div className="mt-1 line-clamp-2 text-[var(--theme-text-secondary)]">
                                {outputSummary}
                              </div>
                            )}
                            {outputContract?.detail && (
                              <div className="mt-1 line-clamp-2 text-amber-700">
                                {outputContract.detail}
                              </div>
                            )}
                            {run.error && <div className="mt-1 truncate text-red-500">{run.error}</div>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <HumanApprovalPanel
                  run={runResult}
                  comment={approvalComment}
                  isResuming={isResumingRun}
                  onCommentChange={setApprovalComment}
                  onResume={handleResumeRun}
                />

                <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                    {runResult?.status === "failed" ? (
                      <XCircle className="text-red-500" size={16} />
                    ) : (
                      <Play size={16} />
                    )}
                    {t("workflowPlugin.editor.run.lastRun")}
                  </div>
                  {runResult ? (
                    <div className="space-y-3">
                      <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] p-3">
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                          {(() => {
                            const outputContract = workflowRunOutputContractStatus(runResult, outputContractStatusLabels);
                            return outputContract ? (
                              <>
                                <span
                                  className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] ${workflowRunOutputContractBadgeClass(outputContract.valid)}`}
                                  title={outputContract.title}
                                >
                                  {outputContract.valid ? (
                                    <CheckCircle2 size={11} />
                                  ) : (
                                    <AlertTriangle size={11} />
                                  )}
                                  {outputContract.label}
                                </span>
                                {outputContract.detail && (
                                  <span className="min-w-0 flex-1 basis-full text-amber-700 sm:basis-auto">
                                    {outputContract.detail}
                                  </span>
                                )}
                              </>
                            ) : null;
                          })()}
                          <span className={workflowRunStatusTone(runResult.status)}>{runResult.status}</span>
                          <span>{runResult.run_id || t("workflowPlugin.editor.run.pending")}</span>
                          {runResult.version_id && <span>{runResult.version_id}</span>}
                        </div>
                        {(() => {
                          const outputSummary = workflowRunOutputSummary(runResult, outputFields);
                          return outputSummary ? (
                          <div className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--theme-text)]">
                            {outputSummary}
                          </div>
                        ) : (
                          <div className="text-sm text-[var(--theme-text-secondary)]">
                            {t("workflowPlugin.editor.run.noOutput")}
                          </div>
                        );
                        })()}
                        {workflowRunOutputEntries(runResult, outputFields).length > 0 && (
                          <div className="mt-3 grid gap-2 sm:grid-cols-2">
                            {workflowRunOutputEntries(runResult, outputFields).map((entry) => (
                              <div
                                key={entry.key}
                                className="min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs"
                              >
                                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                                  <span className="truncate font-medium text-[var(--theme-text)]">
                                    {entry.key}
                                  </span>
                                  <span className="rounded bg-[var(--theme-bg-secondary)] px-1.5 py-0.5 text-[10px] text-[var(--theme-text-secondary)]">
                                    {entry.type}
                                  </span>
                                  {entry.declared && (
                                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-700">
                                      {t("workflowPlugin.editor.run.contract")}
                                    </span>
                                  )}
                                  {!entry.present && (
                                    <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700">
                                      {t("workflowPlugin.editor.run.missing")}
                                    </span>
                                  )}
                                </div>
                                {entry.description && (
                                  <div className="mt-1 line-clamp-2 text-[var(--theme-text-secondary)]">
                                    {entry.description}
                                  </div>
                                )}
                                <div className={`mt-1 line-clamp-3 ${entry.present ? "text-[var(--theme-text-secondary)]" : "text-amber-700"}`}>
                                  {entry.value}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        {workflowRunInterfaceItems(runResult).length > 0 && (
                          <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2">
                            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[var(--theme-text)]">
                              <GitBranch size={13} />
                              {t("workflowPlugin.editor.run.interface")}
                            </div>
                            <div className="grid gap-2 sm:grid-cols-3">
                              {workflowRunInterfaceItems(runResult).map((item) => (
                                <div
                                  key={item.label}
                                  className="min-w-0 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] px-2 py-1.5 text-xs"
                                  title={`${item.label}: ${item.value} (${item.detail})`}
                                >
                                  <div className="text-[10px] uppercase text-[var(--theme-text-secondary)]">
                                    {item.label}
                                  </div>
                                  <div className="truncate font-medium text-[var(--theme-text)]">
                                    {item.value}
                                  </div>
                                  <div className="truncate text-[var(--theme-text-secondary)]">
                                    {item.detail}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {(() => {
                          const nextAction = workflowRunNextActionSummary(runResult);
                          return nextAction ? (
                            <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] p-2 text-xs">
                              <span className="font-medium text-[var(--theme-text)]">{t("workflowPlugin.editor.run.nextAction")}</span>
                              <span
                                className={`inline-flex min-w-0 items-center rounded-md border px-2 py-1 text-[11px] ${workflowRunNextActionBadgeClass(nextAction.type)}`}
                                title={`${nextAction.label}: ${nextAction.detail}`}
                              >
                                {nextAction.label}
                              </span>
                              <span className="min-w-0 flex-1 truncate text-[var(--theme-text-secondary)]">
                                {nextAction.detail}
                              </span>
                            </div>
                          ) : null;
                        })()}
                      </div>
                      <details>
                        <summary className="cursor-pointer text-xs text-[var(--theme-text-secondary)]">
                          {t("workflowPlugin.editor.run.rawRunJson")}
                        </summary>
                        <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-[var(--theme-bg-secondary)] p-3 text-xs text-[var(--theme-text-secondary)]">
                          {JSON.stringify(runResult, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-[var(--theme-border)] px-3 py-8 text-center text-sm text-[var(--theme-text-secondary)]">
                      {t("workflowPlugin.editor.run.emptyHint")}
                    </div>
                  )}
                </div>

                <RunEventsPanel
                  events={runEvents}
                  isLoading={isLoadingRunEvents}
                  focusedNodeId={runEventFocusedNodeId}
                  onFocusNode={handleFocusRunEventNode}
                />
              </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </section>
  );
}
