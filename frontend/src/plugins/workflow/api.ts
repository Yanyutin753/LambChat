import { API_BASE } from "../../services/api/config";
import { authFetch } from "../../services/api/fetch";
import {
  getValidAccessToken,
  redirectToLogin,
  refreshAccessToken,
} from "../../services/api/tokenManager";

export type WorkflowSummary = {
  workflow_id: string;
  name: string;
  status: "draft" | "published" | "archived";
  latest_version_id?: string | null;
  published_version_id?: string | null;
  updated_at: string;
};

export type WorkflowVersionSummary = {
  version_id: string;
  workflow_id: string;
  version_number: number;
  source: "workflow";
  source_format: "json" | "yaml";
  internal_model: Record<string, unknown>;
  compatibility_report: Record<string, unknown>;
  created_at: string;
};

export type WorkflowDetailResponse = WorkflowSummary & {
  description: string;
  version_count: number;
  created_at: string;
  latest_version?: WorkflowVersionSummary | null;
};

export type WorkflowVersionListResponse = {
  workflow_id: string;
  versions: WorkflowVersionSummary[];
  skip: number;
  limit: number;
};

export type WorkflowListResponse = {
  workflows: WorkflowSummary[];
  total: number;
  skip: number;
  limit: number;
  plugin_id: "workflow";
};

export type WorkflowListOptions = {
  skip?: number;
  limit?: number;
  query?: string;
  status?: WorkflowSummary["status"] | "all";
};

export type WorkflowImportReport = {
  source: "workflow";
  source_version: string;
  workflow_id?: string | null;
  supported_nodes: string[];
  unsupported_nodes: Array<Record<string, unknown>>;
  credential_refs_required: string[];
  credential_refs_resolved: Array<Record<string, unknown>>;
  credential_refs_unresolved: string[];
  warnings: string[];
  errors: string[];
  lossless: boolean;
};

export type WorkflowImportResponse = {
  workflow_id?: string | null;
  version_id?: string | null;
  status: "stub" | "imported" | "versioned";
  dry_run: boolean;
  compatibility_report: WorkflowImportReport;
  io_contract?: WorkflowIoContractResponse | null;
  interface?: WorkflowRunInterface | null;
};

export type WorkflowLifecycleResponse = {
  workflow: WorkflowSummary;
};

export type WorkflowDeleteResponse = {
  deleted: boolean;
  workflow_id: string;
  workflow: WorkflowSummary;
};

export type WorkflowValidationResponse = {
  workflow_id: string;
  version_id: string;
  version_number: number;
  runnable: boolean;
  errors: string[];
  reachable_node_ids: string[];
  credential_refs_required: string[];
  credential_refs_resolved: Array<Record<string, unknown>>;
  credential_refs_unresolved: string[];
};

export type WorkflowCredentialResponse = {
  credential_id: string;
  ref: string;
  type: string;
  label: string;
  description: string;
  has_secret: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkflowCredentialListResponse = {
  credentials: WorkflowCredentialResponse[];
  skip: number;
  limit: number;
};

export type WorkflowRunResponse = {
  run_id?: string | null;
  workflow_id: string;
  version_id?: string | null;
  mode: WorkflowRunMode;
  status: "stub" | "queued" | "running" | "paused" | "succeeded" | "failed" | "cancelled";
  output: Record<string, unknown>;
  error?: string | null;
  pause?: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  events?: WorkflowRunEvent[];
  io_contract?: WorkflowIoContractResponse | null;
  interface?: WorkflowRunInterface | null;
  next_action?: WorkflowRunNextAction | null;
  output_contract?: {
    valid: boolean;
    schema_field?: string;
    declared_fields?: string[];
    declared_field_paths?: string[];
    required_fields?: string[];
    required_field_paths?: string[];
    missing_required?: string[];
    type_mismatches?: Array<Record<string, unknown>>;
    extra_fields?: string[];
  } | null;
};

export type WorkflowRunMode = "sync" | "async" | "stream";

export type WorkflowRunNextAction = {
  type?: string;
  tool?: string | null;
  field?: string | null;
  reason?: string;
};

export type WorkflowRunInterface = {
  entry?: {
    type?: string;
    tool?: string;
    argument?: string;
    workflow_id?: string | null;
    version_id?: string | null;
    schema_tool?: string;
    schema_field?: string;
  };
  exit?: {
    type?: string;
    field?: string;
    schema_tool?: string;
    schema_field?: string;
  };
  debug?: {
    tool?: string;
    workflow_id?: string | null;
    run_id?: string | null;
    run_id_field?: string;
    events_field?: string;
  };
  schema?: {
    tool?: string;
    workflow_id?: string | null;
    version_id?: string | null;
    input_schema_field?: string;
    output_schema_field?: string;
  };
  run?: {
    tool?: string;
    workflow_id?: string | null;
    version_id?: string | null;
    input_argument?: string;
    output_field?: string;
  };
};

export type WorkflowInputSchemaResponse = {
  plugin_id: "workflow";
  workflow_id: string;
  version_id: string;
  version_number: number;
  input_schema: Record<string, unknown>;
  status: "draft" | "published" | "archived";
  schema_source: string;
  inferred_fields: string[];
  interface?: WorkflowRunInterface | null;
};

export type WorkflowIoContractResponse = {
  plugin_id: "workflow";
  workflow_id: string;
  version_id: string;
  version_number: number;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  status: "draft" | "published" | "archived";
  input_schema_source: string;
  output_schema_source: string;
  inferred_input_fields: string[];
  inferred_output_fields: string[];
  interface?: WorkflowRunInterface | null;
};

export type WorkflowRunEvent = {
  event_id: string;
  run_id: string;
  workflow_id: string;
  version_id: string;
  sequence: number;
  event_type: string;
  node_id?: string | null;
  node_type?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkflowRunEventsResponse = {
  run: WorkflowRunResponse;
  events: WorkflowRunEvent[];
  skip: number;
  limit: number;
};

export type WorkflowRunEventStreamSnapshot = {
  run: WorkflowRunResponse;
  skip: number;
  limit: number;
  event_count: number;
  terminal: boolean;
  waiting?: boolean;
  error?: string | null;
};

export type WorkflowRunEventStreamError = {
  workflow_id: string;
  run_id: string;
  error: string;
};

export type WorkflowRunListResponse = {
  workflow_id: string;
  runs: WorkflowRunResponse[];
  skip: number;
  limit: number;
};

export type WorkflowPendingApprovalListResponse = {
  plugin_id: "workflow";
  runs: WorkflowRunResponse[];
  skip: number;
  limit: number;
};

export type WorkflowNodeCompatibilityStatus = "supported" | "guarded" | "blocked";

export type WorkflowNodeType = {
  type: string;
  status: WorkflowNodeCompatibilityStatus;
  runtime: string;
  source_types: string[];
  publish_requirements: string[];
};

export type WorkflowNodeCompatibility = {
  source_type: string;
  internal_type?: string | null;
  status: WorkflowNodeCompatibilityStatus;
  aliases: string[];
  runtime: string;
  publish_requirements: string[];
  notes: string[];
};

export type WorkflowNodeTypesResponse = {
  plugin_id: "workflow";
  node_types: WorkflowNodeType[];
  compatibility: {
    summary: Record<WorkflowNodeCompatibilityStatus | "total", number>;
    items: WorkflowNodeCompatibility[];
  };
};

export const workflowApi = {
  list(
    skipOrOptions: number | WorkflowListOptions = 0,
    limit = 50,
  ): Promise<WorkflowListResponse> {
    const options = typeof skipOrOptions === "number"
      ? { skip: skipOrOptions, limit }
      : skipOrOptions;
    const params = new URLSearchParams({
      skip: String(options.skip ?? 0),
      limit: String(options.limit ?? 50),
    });
    const query = options.query?.trim();
    if (query) {
      params.set("query", query);
    }
    if (options.status && options.status !== "all") {
      params.set("status", options.status);
    }
    return authFetch<WorkflowListResponse>(
      `${API_BASE}/api/plugins/workflow/workflows?${params}`,
    );
  },

  get(workflowId: string): Promise<WorkflowDetailResponse> {
    return authFetch<WorkflowDetailResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}`,
    );
  },

  versions(workflowId: string): Promise<WorkflowVersionListResponse> {
    return authFetch<WorkflowVersionListResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/versions`,
    );
  },

  inputSchema(
    workflowId: string,
    versionId?: string | null,
  ): Promise<WorkflowInputSchemaResponse> {
    const params = new URLSearchParams();
    if (versionId) {
      params.set("version_id", versionId);
    }
    const query = params.toString();
    return authFetch<WorkflowInputSchemaResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/input-schema${query ? `?${query}` : ""}`,
    );
  },

  ioContract(
    workflowId: string,
    versionId?: string | null,
  ): Promise<WorkflowIoContractResponse> {
    const params = new URLSearchParams();
    if (versionId) {
      params.set("version_id", versionId);
    }
    const query = params.toString();
    return authFetch<WorkflowIoContractResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/io-contract${query ? `?${query}` : ""}`,
    );
  },

  importWorkflow(input: {
    name: string;
    source_payload?: Record<string, unknown>;
    source_content?: string;
    source_format?: "json" | "yaml";
    dry_run: boolean;
  }): Promise<WorkflowImportResponse> {
    return authFetch<WorkflowImportResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/import`,
      {
        method: "POST",
        body: JSON.stringify({ ...input, source_format: input.source_format ?? "json" }),
      },
    );
  },

  createVersion(
    workflowId: string,
    input: {
      name?: string;
      source_payload?: Record<string, unknown>;
      source_content?: string;
      source_format?: "json" | "yaml";
    },
  ): Promise<WorkflowImportResponse> {
    return authFetch<WorkflowImportResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/versions`,
      {
        method: "POST",
        body: JSON.stringify({ ...input, source_format: input.source_format ?? "json" }),
      },
    );
  },

  publish(
    workflowId: string,
    versionId?: string | null,
  ): Promise<WorkflowLifecycleResponse> {
    return authFetch<WorkflowLifecycleResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/publish`,
      {
        method: "POST",
        body: JSON.stringify({ version_id: versionId ?? null }),
      },
    );
  },

  unpublish(workflowId: string): Promise<WorkflowLifecycleResponse> {
    return authFetch<WorkflowLifecycleResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/unpublish`,
      {
        method: "POST",
      },
    );
  },

  deleteWorkflow(workflowId: string): Promise<WorkflowDeleteResponse> {
    return authFetch<WorkflowDeleteResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}`,
      {
        method: "DELETE",
      },
    );
  },

  validate(
    workflowId: string,
    versionId?: string | null,
  ): Promise<WorkflowValidationResponse> {
    return authFetch<WorkflowValidationResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/validate`,
      {
        method: "POST",
        body: JSON.stringify({ version_id: versionId ?? null }),
      },
    );
  },

  run(
    workflowId: string,
    input: Record<string, unknown>,
    mode: WorkflowRunMode = "sync",
    versionId?: string | null,
  ): Promise<WorkflowRunResponse> {
    return authFetch<WorkflowRunResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/run`,
      {
        method: "POST",
        body: JSON.stringify({ input, mode, version_id: versionId ?? null }),
      },
    );
  },

  runs(workflowId: string, skip = 0, limit = 20): Promise<WorkflowRunListResponse> {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
    });
    return authFetch<WorkflowRunListResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs?${params}`,
    );
  },

  pendingApprovals(skip = 0, limit = 20): Promise<WorkflowPendingApprovalListResponse> {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
    });
    return authFetch<WorkflowPendingApprovalListResponse>(
      `${API_BASE}/api/plugins/workflow/approvals/pending?${params}`,
    );
  },

  runEvents(
    workflowId: string,
    runId: string,
  ): Promise<WorkflowRunEventsResponse> {
    return authFetch<WorkflowRunEventsResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs/${runId}/events`,
    );
  },

  runEventsStreamUrl(workflowId: string, runId: string): string {
    return `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs/${runId}/events/stream`;
  },

  async streamRunEvents(
    workflowId: string,
    runId: string,
    handlers: {
      onEvent?: (event: WorkflowRunEvent) => void;
      onSnapshot?: (snapshot: WorkflowRunEventStreamSnapshot) => void;
      onError?: (error: WorkflowRunEventStreamError) => void;
    },
    options: { pollMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
  ): Promise<void> {
    return streamWorkflowRunEvents(workflowId, runId, handlers, options, false);
  },

  cancelRun(workflowId: string, runId: string): Promise<WorkflowRunResponse> {
    return authFetch<WorkflowRunResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs/${runId}/cancel`,
      {
        method: "POST",
      },
    );
  },

  resumeRun(
    workflowId: string,
    runId: string,
    input: {
      approved: boolean;
      comment?: string | null;
      response?: Record<string, unknown>;
      values?: Record<string, unknown>;
    },
  ): Promise<WorkflowRunResponse> {
    return authFetch<WorkflowRunResponse>(
      `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs/${runId}/resume`,
      {
        method: "POST",
        body: JSON.stringify({
          approved: input.approved,
          comment: input.comment ?? null,
          response: input.response ?? {},
          values: input.values ?? {},
        }),
      },
    );
  },

  nodeTypes(): Promise<WorkflowNodeTypesResponse> {
    return authFetch<WorkflowNodeTypesResponse>(
      `${API_BASE}/api/plugins/workflow/node-types`,
    );
  },

  credentials(skip = 0, limit = 50): Promise<WorkflowCredentialListResponse> {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
    });
    return authFetch<WorkflowCredentialListResponse>(
      `${API_BASE}/api/plugins/workflow/credentials?${params}`,
    );
  },

  upsertCredential(input: {
    ref: string;
    type?: string;
    label?: string;
    description?: string;
    secret?: string | null;
    metadata?: Record<string, unknown>;
  }): Promise<WorkflowCredentialResponse> {
    return authFetch<WorkflowCredentialResponse>(
      `${API_BASE}/api/plugins/workflow/credentials`,
      {
        method: "PUT",
        body: JSON.stringify({
          ref: input.ref,
          type: input.type ?? "credential_ref",
          label: input.label ?? "",
          description: input.description ?? "",
          secret: input.secret ?? null,
          metadata: input.metadata ?? {},
        }),
      },
    );
  },

  deleteCredential(credentialId: string): Promise<{ deleted: boolean; credential_id: string }> {
    return authFetch<{ deleted: boolean; credential_id: string }>(
      `${API_BASE}/api/plugins/workflow/credentials/${credentialId}`,
      { method: "DELETE" },
    );
  },
};

async function streamWorkflowRunEvents(
  workflowId: string,
  runId: string,
  handlers: {
    onEvent?: (event: WorkflowRunEvent) => void;
    onSnapshot?: (snapshot: WorkflowRunEventStreamSnapshot) => void;
    onError?: (error: WorkflowRunEventStreamError) => void;
  },
  options: { pollMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
  hasRetried: boolean,
): Promise<void> {
  const params = new URLSearchParams({
    poll_ms: String(options.pollMs ?? 500),
    timeout_ms: String(options.timeoutMs ?? 30000),
  });
  const token = await getValidAccessToken();
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(
    `${API_BASE}/api/plugins/workflow/workflows/${workflowId}/runs/${runId}/events/stream?${params}`,
    { headers, signal: options.signal },
  );
  if (response.status === 401 && !hasRetried) {
    try {
      await refreshAccessToken();
    } catch {
      redirectToLogin();
      throw new Error("Workflow event stream unauthorized");
    }
    return streamWorkflowRunEvents(workflowId, runId, handlers, options, true);
  }
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Workflow event stream unauthorized");
  }
  if (!response.ok) {
    throw new Error(await workflowStreamErrorMessage(response));
  }
  if (!response.body) {
    throw new Error("Workflow event stream is unavailable");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      handleWorkflowRunEventFrame(frame, handlers);
    }
    if (done) break;
  }
  if (buffer.trim()) {
    handleWorkflowRunEventFrame(buffer, handlers);
  }
}

async function workflowStreamErrorMessage(response: Response): Promise<string> {
  const fallback = `Workflow event stream failed: ${response.status}`;
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const detail = "detail" in payload ? (payload as { detail?: unknown }).detail : null;
  if (detail && typeof detail === "object") {
    const error = "error" in detail ? (detail as { error?: unknown }).error : null;
    return typeof error === "string" && error.trim() ? error : fallback;
  }
  const error = "error" in payload ? (payload as { error?: unknown }).error : null;
  return typeof error === "string" && error.trim() ? error : fallback;
}

function handleWorkflowRunEventFrame(
  frame: string,
  handlers: {
    onEvent?: (event: WorkflowRunEvent) => void;
    onSnapshot?: (snapshot: WorkflowRunEventStreamSnapshot) => void;
    onError?: (error: WorkflowRunEventStreamError) => void;
  },
) {
  if (!frame.trim() || frame.trimStart().startsWith(":")) {
    return;
  }
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return;
  }
  const payload = JSON.parse(dataLines.join("\n")) as unknown;
  if (eventName === "workflow_run_event") {
    handlers.onEvent?.(payload as WorkflowRunEvent);
  } else if (eventName === "workflow_run_snapshot") {
    handlers.onSnapshot?.(payload as WorkflowRunEventStreamSnapshot);
  } else if (eventName === "workflow_run_error") {
    handlers.onError?.(payload as WorkflowRunEventStreamError);
  }
}
