import type { ToolCall, MessagePart } from "./message";

// ============================================
// Session Types
// ============================================

export interface Session {
  id: string;
  user_id?: string;
  agent_id: string;
  workspace_dir: string;
  created_at: string;
  updated_at: string;
  status: "active" | "archived";
  messages: SessionMessage[];
  metadata: Record<string, unknown>;
}

export interface SessionMessage {
  role: "user" | "assistant" | "system" | "human" | "ai";
  content: string;
  created_at?: string;
  additional_kwargs?: {
    tool_calls?: ToolCall[];
    partial?: boolean;
    parts?: MessagePart[];
  };
}

export interface SessionSummary {
  session_id: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  status: "active" | "archived";
  message_count: number;
  metadata: Record<string, unknown>;
}

export interface SessionWithMessages {
  session: Session;
  messages: SessionMessage[];
  total_events: number;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface SSEEventRecord {
  id: string;
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
  run_id?: string;
}

export type SessionHistoryMode = "complete" | "active_user_only";

export interface SessionTraceWindow {
  /** 游标：窗口内最旧一条 trace 的 started_at（ISO 字符串） */
  oldest_trace_started_at: string;
  /** 游标决胜键：同 started_at 时按 trace_id 比较 */
  oldest_trace_id: string;
}

export interface SessionEventsResponse {
  events: SSEEventRecord[];
  history_mode?: SessionHistoryMode;
  stream_run_id?: string | null;
  /** 按 trace(run) 窗口分页时：是否还有更早的轮次 */
  has_more_traces?: boolean;
  /** 按 trace(run) 窗口分页时的游标；无窗口或已到最早时为 null */
  trace_window?: SessionTraceWindow | null;
}
