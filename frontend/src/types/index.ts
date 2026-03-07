// ============================================
// Feedback Types (re-export from feedback.ts)
// ============================================
export type {
  RatingValue,
  Feedback,
  FeedbackCreate,
  FeedbackStats,
  FeedbackListResponse,
} from "./feedback";

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
}

// 消息内容块类型
export type MessagePart =
  | TextPart
  | ToolPart
  | SubagentPart
  | ThinkingPart
  | SandboxPart
  | TokenUsagePart;

// Sandbox 状态块类型（用于渲染沙箱初始化状态）
export interface SandboxPart {
  type: "sandbox";
  status: "starting" | "ready" | "error";
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
  result?: string;
  success?: boolean;
  error?: string;
  isPending?: boolean;
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
  isPending?: boolean;
  depth: number;
  // 子代理内部的内容（嵌套）
  parts?: MessagePart[];
}

export interface ToolCall {
  id?: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResult {
  id?: string;
  name: string;
  result: string;
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
// Skills Types
// ============================================

// Skill Source Type
export type SkillSource = "builtin" | "github" | "manual";

// Skill Base
export interface SkillBase {
  name: string;
  description: string;
  content: string;
  enabled: boolean;
  files?: Record<string, string>;
}

// Skill Response (from API)
export interface SkillResponse extends SkillBase {
  source: SkillSource;
  github_url?: string;
  version?: string;
  is_system: boolean;
  can_edit: boolean;
  created_at?: string;
  updated_at?: string;
}

// Skills List Response
export interface SkillsResponse {
  skills: SkillResponse[];
  total: number;
}

// Skill Create Request
export interface SkillCreate {
  name: string;
  description: string;
  content: string;
  enabled?: boolean;
  source?: SkillSource;
  github_url?: string;
  version?: string;
  files?: Record<string, string>;
}

// Skill Update Request
export interface SkillUpdate {
  name?: string;
  description?: string;
  content?: string;
  enabled?: boolean;
  version?: string;
  files?: Record<string, string>;
  is_system?: boolean;
}

// Skill Toggle Response
export interface SkillToggleResponse {
  skill: SkillResponse;
  message: string;
}

// Skill Import Request
export interface SkillImportRequest {
  skills: Record<string, Record<string, unknown>>;
  overwrite?: boolean;
}

// Skill Import Response
export interface SkillImportResponse {
  message: string;
  imported_count: number;
  skipped_count: number;
  errors: string[];
}

// Skill Export Response
export interface SkillExportResponse {
  skills: Record<string, Record<string, unknown>>;
}

// Skill Move Request
export interface SkillMoveRequest {
  target_user_id?: string;
}

// Skill Move Response
export interface SkillMoveResponse {
  skill: SkillResponse;
  message: string;
  from_type: string;
  to_type: string;
}

// GitHub Skill Preview
export interface GitHubSkillPreview {
  name: string;
  description: string;
  path: string;
}

// GitHub Preview Response
export interface GitHubPreviewResponse {
  repo_url: string;
  skills: GitHubSkillPreview[];
}

// GitHub Install Request
export interface GitHubInstallRequest {
  repo_url: string;
  branch?: string;
  skill_names?: string[];
  as_system?: boolean;
}

// Legacy types for backwards compatibility
export interface SkillMetadata {
  name: string;
  description: string;
  path: string;
  source: "user" | "project";
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SkillContent {
  metadata: SkillMetadata;
  content: string;
}

export interface SkillListResponse {
  skills: SkillMetadata[];
  total: number;
}

export interface SkillStats {
  total_skills: number;
  enabled_skills: number;
  disabled_skills: number;
}

// Agent types
export interface AgentOption {
  type: "boolean" | "string" | "number";
  default: boolean | string | number;
  label: string;
  label_key?: string; // i18n translation key for label
  description?: string;
  description_key?: string; // i18n translation key for description
  icon?: string; // lucide-react icon name (e.g., "Brain", "Zap", "Settings")
  options?: { value: string | number; label: string }[]; // For select/dropdown type options
}

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  sort_order?: number;
  options?: Record<string, AgentOption>;
}

export interface AgentListResponse {
  agents: AgentInfo[];
  count: number;
  default_agent?: string;
}

// Workflow event types
export interface WorkflowStepData {
  step_id: string;
  step_name: string;
  agent_id?: string;
  status?: "running" | "completed" | "failed";
  result?: string;
}

// Session types for message history
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

// ============================================
// Authentication & Authorization Types
// ============================================

// 权限枚举
export enum Permission {
  // Chat
  CHAT_READ = "chat:read",
  CHAT_WRITE = "chat:write",
  // Session
  SESSION_READ = "session:read",
  SESSION_WRITE = "session:write",
  SESSION_DELETE = "session:delete",
  SESSION_ADMIN = "session:admin",
  SESSION_SHARE = "session:share",
  // Skill
  SKILL_READ = "skill:read",
  SKILL_WRITE = "skill:write",
  SKILL_DELETE = "skill:delete",
  SKILL_ADMIN = "skill:admin",
  // User (Admin)
  USER_READ = "user:read",
  USER_WRITE = "user:write",
  USER_DELETE = "user:delete",
  // Role (Admin)
  ROLE_MANAGE = "role:manage",
  // Settings (Admin)
  SETTINGS_MANAGE = "settings:manage",
  // MCP
  MCP_READ = "mcp:read",
  MCP_WRITE_STDIO = "mcp:write_stdio",
  MCP_WRITE_SSE = "mcp:write_sse",
  MCP_WRITE_HTTP = "mcp:write_http",
  MCP_DELETE = "mcp:delete",
  MCP_ADMIN = "mcp:admin",
  // File
  FILE_UPLOAD = "file:upload",
  FILE_UPLOAD_IMAGE = "file:upload:image",
  FILE_UPLOAD_VIDEO = "file:upload:video",
  FILE_UPLOAD_AUDIO = "file:upload:audio",
  FILE_UPLOAD_DOCUMENT = "file:upload:document",
  // Avatar
  AVATAR_UPLOAD = "avatar:upload",
  // Feedback
  FEEDBACK_WRITE = "feedback:write",
  FEEDBACK_READ = "feedback:read",
  FEEDBACK_ADMIN = "feedback:admin",
}

// 用户信息
export interface User {
  id: string;
  username: string;
  email: string;
  avatar_url?: string;
  roles: string[]; // 角色名称列表
  permissions?: string[]; // 动态权限
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 用户创建请求
export interface UserCreate {
  username: string;
  email: string;
  password: string;
  roles?: string[];
}

// 用户更新请求
export interface UserUpdate {
  username?: string;
  email?: string;
  password?: string;
  roles?: string[];
  is_active?: boolean;
}

// User list response (paginated)
export interface UserListResponse {
  users: User[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

// 角色信息
export interface Role {
  id: string;
  name: string;
  description?: string;
  permissions: Permission[];
  is_system: boolean; // 系统角色不可删除
  created_at: string;
  updated_at: string;
}

// 角色创建请求
export interface RoleCreate {
  name: string;
  description?: string;
  permissions: Permission[];
}

// 角色更新请求
export interface RoleUpdate {
  name?: string;
  description?: string;
  permissions?: Permission[];
}

// 登录请求
export interface LoginRequest {
  username: string;
  password: string;
}

// Token 响应
export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
}

// Token 载荷（解码后的内容）
export interface TokenPayload {
  sub: string; // user_id
  username: string;
  roles: string[];
  permissions: string[]; // 合并后的所有权限
  exp: number;
  iat: number;
}

// 认证状态
export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  permissions: Permission[];
}

// ============================================
// Permission Types
// ============================================

// 权限信息
export interface PermissionInfo {
  value: string;
  label: string;
  description: string;
}

// 权限分组
export interface PermissionGroup {
  name: string;
  permissions: PermissionInfo[];
}

// 权限列表响应
export interface PermissionsResponse {
  groups: PermissionGroup[];
  all_permissions: PermissionInfo[];
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

// ============================================
// Settings Types
// ============================================

export type SettingType = "string" | "text" | "number" | "boolean" | "json";
export type SettingCategory =
  | "frontend"
  | "agent"
  | "llm"
  | "session"
  | "skills"
  | "database"
  | "long_term_storage"
  | "security"
  | "sandbox"
  | "s3"
  | "tools"
  | "tracing"
  | "user";

// Setting dependency condition
export interface SettingDependsOn {
  key: string; // Parent setting key
  value: string | number | boolean; // Expected value for visibility
}

export interface SettingItem {
  key: string;
  value: string | number | boolean | object;
  type: SettingType;
  category: SettingCategory;
  description: string;
  default_value: string | number | boolean | object;
  requires_restart: boolean;
  is_sensitive: boolean;
  frontend_visible: boolean;
  depends_on?: string | SettingDependsOn; // Key of parent setting or condition object
  updated_at?: string;
  updated_by?: string;
}

export interface SettingsResponse {
  settings: Record<SettingCategory, SettingItem[]>;
}

export interface SettingUpdate {
  value: string | number | boolean | object;
}

export interface SettingResetResponse {
  message: string;
  reset_count: number;
}

// ============================================
// MCP Types
// ============================================

// MCP Transport Type
export type MCPTransport = "stdio" | "sse" | "streamable_http";

// MCP Server Base
export interface MCPServerBase {
  name: string;
  transport: MCPTransport;
  enabled: boolean;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}

// MCP Server Response (from API)
export interface MCPServerResponse extends MCPServerBase {
  is_system: boolean;
  can_edit: boolean;
  created_at?: string;
  updated_at?: string;
}

// MCP Servers List Response
export interface MCPServersResponse {
  servers: MCPServerResponse[];
}

// MCP Server Create Request
export interface MCPServerCreate {
  name: string;
  transport: MCPTransport;
  enabled?: boolean;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}

// MCP Server Update Request
export interface MCPServerUpdate {
  transport?: MCPTransport;
  enabled?: boolean;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}

// MCP Toggle Response
export interface MCPServerToggleResponse {
  server: MCPServerResponse;
  message: string;
}

// MCP Import Request
export interface MCPImportRequest {
  servers: Record<string, Record<string, unknown>>;
  overwrite?: boolean;
}

// MCP Import Response
export interface MCPImportResponse {
  message: string;
  imported_count: number;
  skipped_count: number;
  errors: string[];
}

// MCP Export Response
export interface MCPExportResponse {
  servers: Record<string, Record<string, unknown>>;
}

// MCP Server Move Request
export interface MCPServerMoveRequest {
  target_user_id?: string;
}

// MCP Server Move Response
export interface MCPServerMoveResponse {
  server: MCPServerResponse;
  message: string;
  from_type: string;
  to_type: string;
}

// ============================================
// Tool Types
// ============================================

// Tool Category
export type ToolCategory = "builtin" | "skill" | "human" | "mcp";

// Tool Parameter Info
export interface ToolParamInfo {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

// Tool Info (from API)
export interface ToolInfo {
  name: string;
  description: string;
  category: ToolCategory;
  server?: string; // MCP server name for MCP tools
  parameters: ToolParamInfo[];
}

// Tools List Response
export interface ToolsListResponse {
  tools: ToolInfo[];
  count: number;
}

// Tool State (with enabled status for UI)
export interface ToolState extends ToolInfo {
  enabled: boolean;
}

// ============================================
// Version Types
// ============================================

export interface VersionInfo {
  app_version: string;
  git_tag?: string;
  commit_hash?: string;
  build_time?: string;
  latest_version?: string;
  release_url?: string;
  github_url?: string;
  has_update?: boolean;
  published_at?: string;
  last_checked?: string;
}

// ============================================
// File Upload Types
// ============================================

export type FileCategory = "image" | "video" | "audio" | "document";

export interface MessageAttachment {
  id: string;
  key: string;
  name: string;
  type: FileCategory;
  mimeType: string;
  size: number;
  url?: string;
  /** Upload progress (0-100) */
  uploadProgress?: number;
  /** Whether upload is in progress */
  isUploading?: boolean;
}

// Upload state for tracking progress
export interface UploadState {
  id: string;
  file: File;
  progress: number;
  loaded: number;
  total: number;
  status: "pending" | "uploading" | "completed" | "error";
  attachment?: MessageAttachment;
  error?: string;
}

export interface UploadConfig {
  enabled: boolean;
  provider?: string;
  max_file_size?: number;
  uploadLimits: {
    image: number;
    video: number;
    audio: number;
    document: number;
    maxFiles: number;
  };
}

export interface UploadResult {
  key: string;
  url: string;
  name: string;
  type: FileCategory;
  mimeType: string;
  size: number;
}

// ============================================
// Share Types
// ============================================

export type ShareType = "full" | "partial";
export type ShareVisibility = "public" | "authenticated";

export interface SharedSession {
  id: string;
  share_id: string;
  session_id: string;
  session_name?: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
  created_at: string;
}

export interface ShareCreate {
  session_id: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
}

export interface ShareResponse {
  id: string;
  share_id: string;
  url: string;
  session_id: string;
  share_type: ShareType;
  visibility: ShareVisibility;
  run_ids?: string[];
  created_at: string;
}

export interface ShareListResponse {
  shares: SharedSession[];
  total: number;
}

export interface SharedContentOwner {
  username: string;
  avatar_url?: string;
}

export interface SharedContentOwner {
  username: string;
  avatar_url?: string;
}

export interface SharedContentResponse {
  session: {
    id: string;
    name?: string;
    agent_id: string;
    created_at?: string;
  };
  events: SSEEventRecord[];
  owner: SharedContentOwner;
  share_type: ShareType;
  run_ids?: string[];
}
