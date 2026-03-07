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
}

export interface SessionEventsResponse {
  events: SSEEventRecord[];
}
