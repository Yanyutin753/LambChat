import type {
  Message,
  AgentInfo,
  ConnectionStatus,
  FormField,
  MessageAttachment,
  PersonaPresetSnapshot,
} from "../../types";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";

// Event types from backend
export type EventType =
  | "metadata"
  | "message:chunk"
  | "user:message"
  | "user:cancel"
  | "thinking"
  | "tool:start"
  | "tool:result"
  | "artifact:result"
  | "todo:updated"
  | "summary"
  | "recommend:questions"
  | "followup:questions"
  | "agent:call"
  | "agent:result"
  | "workflow:run"
  | "approval_required"
  | "sandbox:starting"
  | "sandbox:ready"
  | "sandbox:error"
  | "token:usage"
  | "skills:changed"
  | "queue_update"
  | "goal:start"
  | "goal:end"
  | "complete"
  | "done"
  | "error";

export interface StreamEvent {
  event: EventType;
  data: string;
}

export interface EventData {
  session_id?: string;
  agent_id?: string;
  agent_name?: string;
  agent_avatar?: string;
  tool?: string;
  tool_call_id?: string;
  args?: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  artifact?: Record<string, unknown>;
  success?: boolean;
  content?: string;
  thinking_id?: string;
  error?: string;
  type?: string;
  step_name?: string;
  step_id?: string;
  input?: string;
  depth?: number;
  // approval_required event fields
  id?: string;
  message?: string;
  choices?: string[];
  default?: string;
  // sandbox event fields
  sandbox_id?: string;
  work_dir?: string;
  // token:usage event fields
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  duration?: number;
  timestamp?: string;
  cache_creation_tokens?: number;
  cache_read_tokens?: number;
  model_id?: string;
  model?: string;
  // user:message event fields
  message_id?: string;
  attachments?: Array<{
    id: string;
    key: string;
    name: string;
    type: string;
    mime_type: string;
    size: number;
    url: string;
  }>;
  // user:cancel event fields
  user_id?: string;
  run_id?: string;
  // workflow:run event fields
  plugin_id?: string;
  workflow_id?: string | null;
  version_id?: string | null;
  output?: Record<string, unknown>;
  io_contract?: Record<string, unknown> | null;
  interface?: import("../../types").WorkflowInterfaceContract | null;
  next_action?: Record<string, unknown> | null;
  output_contract?: Record<string, unknown> | null;
  // skills:changed event fields
  action?: string;
  skill_name?: string;
  files_count?: number;
  // queue_update event fields
  status?: string;
  queue_position?: number;
  // goal:start / goal:end event fields
  goal?: {
    objective: string;
    rubric?: string;
    max_iterations?: number;
  };
  started_at?: string;
  ended_at?: string;
  // todo event fields
  todos?: Array<{
    content: string;
    activeForm?: string;
    status: "pending" | "in_progress" | "completed" | "cancelled";
  }>;
  updated_index?: number;
  // summary event fields
  summary_id?: string;
  // recommend:questions / followup:questions event fields
  questions?: Array<
    | string
    | {
        content?: string;
        text?: string;
        title?: string;
        upload?: Record<string, unknown>;
        data_upload?: Record<string, unknown>;
      }
  >;
}

export interface UseAgentOptions {
  runtimePlugins?: PluginRuntimeContributionStates;
  onApprovalRequired?: (approval: {
    id: string;
    message: string;
    type: string;
    fields?: FormField[];
    expires_at?: string | null;
    timeout?: number;
    metadata?: Record<string, unknown>;
  }) => void;
  onClearApprovals?: () => void;
  getEnabledTools?: () => string[];
  getDisabledSkills?: () => string[];
  getEnabledSkills?: () => string[] | undefined;
  getPersonaPresetId?: () => string | null;
  getDisabledMcpTools?: () => string[];
  getAgentOptions?: () => Record<string, boolean | string | number>;
  onSkillAdded?: (
    skillName: string,
    description: string,
    filesCount: number,
  ) => void;
  onStreamDone?: () => void;
}

export interface ActiveGoalSpec {
  objective: string;
  rubric?: string;
  max_iterations?: number;
  runId?: string;
  started_at?: string;
  ended_at?: string;
}

export interface SendMessageOptions {
  retryUserMessage?: boolean;
  retryAssistantMessageId?: string;
  retryAfterUserMessageId?: string;
  enabledSkills?: string[];
}

// Subagent tracking item
export interface SubagentStackItem {
  agent_id: string;
  depth: number;
  message_id: string;
}

// History event data structure
export interface HistoryEventData {
  content?: string;
  tool?: string;
  tool_call_id?: string;
  args?: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  error?: string;
  depth?: number;
  agent_id?: string;
  agent_name?: string;
  input?: string;
  timestamp?: string;
  sandbox_id?: string;
  work_dir?: string;
  thinking_id?: string;
  todos?: Array<{
    content: string;
    activeForm?: string;
    status: "pending" | "in_progress" | "completed" | "cancelled";
  }>;
  updated_index?: number;
  questions?: Array<
    | string
    | {
        content?: string;
        text?: string;
        title?: string;
        upload?: Record<string, unknown>;
        data_upload?: Record<string, unknown>;
      }
  >;
  attachments?: Array<{
    id: string;
    key: string;
    name: string;
    type: string;
    mime_type: string;
    size: number;
    url: string;
  }>;
  message_id?: string;
  plugin_id?: string;
  workflow_id?: string | null;
  version_id?: string | null;
  status?: string;
  output?: Record<string, unknown>;
  io_contract?: Record<string, unknown> | null;
  interface?: import("../../types").WorkflowInterfaceContract | null;
  output_contract?: Record<string, unknown> | null;
}

// History event from backend
export interface HistoryEvent {
  id?: string | number;
  event_type: string;
  data: HistoryEventData | unknown;
  timestamp?: string;
  run_id?: string;
}

// Return type for useAgent hook
export interface UseAgentReturn {
  messages: Message[];
  isLoading: boolean;
  isLoadingHistory: boolean;
  error: string | null;
  sessionId: string | null;
  currentProjectId: string | null;
  currentRunId: string | null;
  agents: AgentInfo[];
  currentAgent: string;
  agentsLoading: boolean;
  allowedModelIds: string[] | null;
  isReconnecting: boolean;
  connectionStatus: ConnectionStatus;
  newlyCreatedSession: BackendSession | null;
  activeGoal: ActiveGoalSpec | null;
  goalsByRunId: Record<string, ActiveGoalSpec>;
  isInitializingSandbox: boolean;
  sandboxError: string | null;
  sendMessage: (
    content: string,
    agentOptions?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
    options?: SendMessageOptions,
  ) => Promise<void>;
  clearActiveGoal: () => void;
  stopGeneration: () => Promise<void>;
  clearMessages: () => void;
  selectAgent: (agentId: string) => void;
  switchAgent: (agentId: string) => void;
  selectedTeamId: string | null;
  sessionPluginOptions: PluginOptionsMetadata;
  setSessionPluginOption: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  refreshAgents: () => Promise<void>;
  loadHistory: (
    targetSessionId: string,
    targetRunId?: string,
  ) => Promise<SessionConfig | null>;
  reconnectSSE: () => Promise<void>;
  setPendingProjectId: (id: string | null) => void;
  autoExpandProjectId: string | null;
  clearAutoExpandProjectId: (id?: string | null) => void;
}

// Session configuration restored from metadata
export interface SessionConfig {
  agent_id?: string;
  agent_options?: Record<string, boolean | string | number>;
  disabled_tools?: string[];
  disabled_skills?: string[];
  enabled_skills?: string[];
  persona_preset_id?: string;
  persona_preset_name?: string;
  persona_snapshot?: PersonaPresetSnapshot;
  disabled_mcp_tools?: string[];
  team_id?: string;
  plugin_options?: Record<string, Record<string, unknown>>;
}

// Backend session type (simplified)
export interface BackendSession {
  id: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  metadata: Record<string, unknown>;
  name?: string;
}
