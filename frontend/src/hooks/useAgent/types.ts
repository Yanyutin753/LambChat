import type {
  Message,
  AgentInfo,
  ConnectionStatus,
  FormField,
  MessageAttachment,
} from "../../types";

// Event types from backend
export type EventType =
  | "metadata"
  | "message:chunk"
  | "user:message"
  | "thinking"
  | "tool:start"
  | "tool:result"
  | "todo:created"
  | "todo:updated"
  | "skill:loaded"
  | "skill:added"
  | "agent:call"
  | "agent:result"
  | "observation"
  | "code"
  | "file"
  | "message:complete"
  | "workflow:step_start"
  | "workflow:step_end"
  | "approval_required"
  | "sandbox:starting"
  | "sandbox:state"
  | "sandbox:ready"
  | "sandbox:error"
  | "token:usage"
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
  tool?: string;
  tool_call_id?: string;
  args?: Record<string, unknown>;
  result?: string;
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
  state?: string;
  sandbox_id?: string;
  work_dir?: string;
  // token:usage event fields
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  duration?: number;
  timestamp?: string;
  // user:message event fields
  attachments?: Array<{
    id: string;
    key: string;
    name: string;
    type: string;
    mime_type: string;
    size: number;
    url: string;
  }>;
  // skill:added event fields
  name?: string;
  description?: string;
  files_count?: number;
}

export interface UseAgentOptions {
  onApprovalRequired?: (approval: {
    id: string;
    message: string;
    type: string;
    fields?: FormField[];
  }) => void;
  onClearApprovals?: () => void;
  getEnabledTools?: () => string[];
  onSkillAdded?: (
    skillName: string,
    description: string,
    filesCount: number,
  ) => void;
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
  result?: string;
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
  attachments?: Array<{
    id: string;
    key: string;
    name: string;
    type: string;
    mime_type: string;
    size: number;
    url: string;
  }>;
}

// History event from backend
export interface HistoryEvent {
  id?: string | number;
  event_type: string;
  data: HistoryEventData | unknown;
  timestamp?: string;
}

// Return type for useAgent hook
export interface UseAgentReturn {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sessionId: string | null;
  currentRunId: string | null;
  agents: AgentInfo[];
  currentAgent: string;
  agentsLoading: boolean;
  isReconnecting: boolean;
  connectionStatus: ConnectionStatus;
  newlyCreatedSession: BackendSession | null;
  isInitializingSandbox: boolean;
  sandboxError: string | null;
  sendMessage: (
    content: string,
    agentOptions?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
  ) => Promise<void>;
  stopGeneration: () => Promise<void>;
  clearMessages: () => void;
  selectAgent: (agentId: string) => void;
  refreshAgents: () => Promise<void>;
  loadHistory: (targetSessionId: string, targetRunId?: string) => Promise<void>;
  reconnectSSE: () => Promise<void>;
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

// Constants
export const API_BASE = "/api";
export const DEFAULT_AGENT = "search";
