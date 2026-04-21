import type { MessageAttachment } from "./upload";

// ============================================
// Message Types
// ============================================

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  isStreaming?: boolean;
  // 有序内容块 - 用于按顺序渲染文本和工具调用
  parts?: MessagePart[];
  // Token 使用统计
  tokenUsage?: TokenUsagePart;
  // 对话耗时（毫秒）
  duration?: number;
  // 用户消息附件
  attachments?: MessageAttachment[];
  // 运行 ID - 用于反馈
  runId?: string;
  // 用户对该消息的反馈 (从 feedback API 加载)
  feedback?: import("./feedback").RatingValue;
  // 反馈 ID
  feedbackId?: string;
  // 是否被取消
  cancelled?: boolean;
}

// 消息内容块类型
export type MessagePart =
  | TextPart
  | ToolPart
  | SubagentPart
  | ThinkingPart
  | SandboxPart
  | TokenUsagePart
  | CancelledPart
  | TodoPart
  | SummaryPart;

// Sandbox 状态块类型（用于渲染沙箱初始化状态）
export interface SandboxPart {
  type: "sandbox";
  status: "starting" | "ready" | "error" | "cancelled";
  sandbox_id?: string;
  work_dir?: string;
  error?: string;
  timestamp?: string;
}

// Token 使用统计块类型
export interface TokenUsagePart {
  type: "token_usage";
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_creation_tokens?: number;
  cache_read_tokens?: number;
  model_id?: string;
  model?: string;
}

// 取消状态块类型
export interface CancelledPart {
  type: "cancelled";
}

// Todo 任务列表块类型
export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoItem {
  content: string;
  activeForm?: string;
  status: TodoStatus;
}

export interface TodoPart {
  type: "todo";
  items: TodoItem[];
  isStreaming?: boolean;
}

export interface SummaryPart {
  type: "summary";
  content: string;
  summary_id?: string;
  depth?: number;
  agent_id?: string;
  isStreaming?: boolean;
}

export interface TextPart {
  type: "text";
  content: string;
  depth?: number;
  agent_id?: string;
}

export interface ThinkingPart {
  type: "thinking";
  content: string;
  thinking_id?: string;
  depth?: number;
  agent_id?: string;
  isStreaming?: boolean;
}

export interface ToolPart {
  type: "tool";
  id?: string;
  name: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  error?: string;
  isPending?: boolean;
  cancelled?: boolean;
  depth?: number;
  agent_id?: string;
}

export interface SubagentPart {
  type: "subagent";
  agent_id: string;
  agent_name: string;
  input: string;
  result?: string;
  success?: boolean;
  error?: string; // 错误信息
  isPending?: boolean;
  cancelled?: boolean;
  depth: number;
  // 子代理内部的内容（嵌套）
  parts?: MessagePart[];
  // 时间追踪
  startedAt?: number; // Unix timestamp (ms)
  completedAt?: number; // Unix timestamp (ms)
  // 状态: pending | running | complete | error | cancelled
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
}

export interface ToolCall {
  id?: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResult {
  id?: string;
  name: string;
  result: string | Record<string, unknown>;
  success: boolean;
}

// DeepAgents event types
export interface AIMessage {
  content: string;
  tool_calls?: RawToolCall[];
  id?: string;
}

export interface RawToolCall {
  name: string;
  args: Record<string, unknown>;
  id?: string;
}

export interface ToolMessage {
  content: string;
  name: string;
  tool_call_id?: string;
}

export interface DeepAgentState {
  messages?: (AIMessage | ToolMessage)[];
}

export interface StreamEventData {
  content: string;
  metadata: Record<string, unknown>;
  session_id?: string;
}

// ============================================
// Form Field Types (Human Tool)
// ============================================

export type FormFieldType =
  | "text"
  | "textarea"
  | "number"
  | "checkbox"
  | "select"
  | "multi_select";

export interface FormField {
  name: string;
  label: string;
  type: FormFieldType;
  placeholder?: string;
  default?: unknown;
  required: boolean;
  options?: string[];
}

export interface PendingApproval {
  id: string;
  message: string;
  type: "form";
  fields: FormField[];
  status: "pending" | "approved" | "rejected";
  session_id?: string | null;
  expires_at?: string | null;
  timeout?: number;
}

export interface StreamEvent {
  type:
    | "thinking"
    | "content"
    | "tool_call"
    | "tool_result"
    | "step"
    | "complete"
    | "error";
  content: string;
  metadata: Record<string, unknown>;
}

export interface AgentResponse {
  success: boolean;
  message: string;
  steps: number;
  logs: AgentStep[];
  session_id: string;
}

export interface AgentStep {
  step: number;
  thought?: string;
  tool_calls: ToolCall[];
  tool_results: ToolResult[];
}

// ============================================
// SSE Connection Types
// ============================================

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected";

export interface ConnectionState {
  status: ConnectionStatus;
  retryCount: number;
  lastConnectedAt: Date | null;
}

// ============================================
// Run Types (Multi-turn Conversation)
// ============================================

export interface RunSummary {
  run_id: string;
  trace_id: string;
  agent_id?: string;
  started_at: string;
  completed_at?: string;
  status: "pending" | "running" | "completed" | "failed";
  event_count: number;
  user_message?: string;
}
