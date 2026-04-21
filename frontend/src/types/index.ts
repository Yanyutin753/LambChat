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

// ============================================
// Message Types
// ============================================
export type {
  Message,
  MessagePart,
  SandboxPart,
  TokenUsagePart,
  TextPart,
  ThinkingPart,
  ToolPart,
  SubagentPart,
  TodoPart,
  TodoItem,
  TodoStatus,
  ToolCall,
  ToolResult,
  AIMessage,
  RawToolCall,
  ToolMessage,
  DeepAgentState,
  StreamEventData,
  FormFieldType,
  FormField,
  PendingApproval,
  StreamEvent,
  AgentResponse,
  AgentStep,
  ConnectionStatus,
  ConnectionState,
  RunSummary,
  SummaryPart,
} from "./message";

// ============================================
// Skills Types
// ============================================
export type {
  SkillSource,
  UserSkill,
  UserSkillDetail,
  SkillFileResponse,
  SkillToggleResponse,
  SkillResponse,
  SkillsResponse,
  SkillCreate,
  MarketplaceSkillResponse,
  MarketplaceCreateRequest,
  MarketplaceSkillFilesResponse,
  MarketplaceSkillFileResponse,
  MarketplaceInstallResponse,
  MarketplaceUpdateResponse,
  TagsResponse,
  PublishToMarketplaceRequest,
} from "./skill";

// ============================================
// Agent Types
// ============================================
export type {
  AgentOption,
  AgentInfo,
  AgentListResponse,
  WorkflowStepData,
  AgentConfig,
  GlobalAgentConfigResponse,
  RoleAgentAssignment,
  RoleAgentAssignmentResponse,
  RoleModelAssignment,
  UserAgentPreference,
  UserAgentPreferenceResponse,
} from "./agent";

// ============================================
// Session Types
// ============================================
export type {
  Session,
  SessionMessage,
  SessionSummary,
  SessionWithMessages,
  SessionListResponse,
  SSEEventRecord,
  SessionEventsResponse,
} from "./session";

// ============================================
// Authentication & Authorization Types
// ============================================
export {
  Permission,
  type User,
  type UserCreate,
  type UserUpdate,
  type UserListResponse,
  type RegisterResponse,
  type Role,
  type RoleCreate,
  type RoleUpdate,
  type RoleLimits,
  type LoginRequest,
  type TokenResponse,
  type TokenPayload,
  type AuthState,
  type PermissionInfo,
  type PermissionGroup,
  type PermissionsResponse,
} from "./auth";

// ============================================
// MCP Types
// ============================================
export type {
  MCPTransport,
  MCPServerBase,
  MCPServerResponse,
  MCPServersResponse,
  MCPServerCreate,
  MCPServerUpdate,
  MCPServerToggleResponse,
  MCPImportRequest,
  MCPImportResponse,
  MCPExportResponse,
  MCPServerMoveRequest,
  MCPServerMoveResponse,
  MCPToolInfo,
  MCPToolParamInfo,
  MCPToolDiscoveryResponse,
  MCPToolToggleResponse,
} from "./mcp";

// ============================================
// Tool Types
// ============================================
export type {
  ToolCategory,
  ToolParamInfo,
  ToolInfo,
  ToolsListResponse,
  ToolState,
} from "./tool";

// ============================================
// Settings Types
// ============================================
export type {
  SettingType,
  SettingCategory,
  SettingDependsOn,
  SettingItem,
  SettingsResponse,
  SettingUpdate,
  SettingResetResponse,
} from "./settings";

// ============================================
// File Upload Types
// ============================================
export type {
  FileCategory,
  MessageAttachment,
  UploadState,
  UploadConfig,
  UploadResult,
  FileCheckResult,
} from "./upload";

// ============================================
// Share Types
// ============================================
export type {
  ShareType,
  ShareVisibility,
  SharedSession,
  ShareCreate,
  ShareResponse,
  ShareListResponse,
  SharedContentOwner,
  SharedContentResponse,
} from "./share";

// ============================================
// Version Types
// ============================================
export type { VersionInfo } from "./common";

// ============================================
// Project Types
// ============================================

export interface Project {
  id: string;
  user_id: string;
  name: string;
  type: "favorites" | "custom";
  icon?: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  type?: "custom";
  icon?: string;
  sort_order?: number;
}

export interface ProjectUpdate {
  name?: string;
  icon?: string;
  sort_order?: number;
}
