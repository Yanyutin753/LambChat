// ============================================
// Authentication & Authorization Types
// ============================================

// 权限枚举
export enum Permission {
  SYSTEM_ADMIN = "system:admin",
  USER_CREATE = "user:create",
  USER_STATUS = "user:status",
  USER_RESET_PASSWORD = "user:reset_password",
  USER_ASSIGN_ROLES = "user:assign_roles",
  ROLE_READ = "role:read",
  ROLE_WRITE = "role:write",
  ROLE_DELETE = "role:delete",
  ROLE_GRANT = "role:grant",
  SETTINGS_READ = "settings:read",
  SETTINGS_SECURITY = "settings:security",
  SETTINGS_RESET = "settings:reset",
  MCP_SYSTEM_READ = "mcp:system_read",
  MCP_SYSTEM_DELETE = "mcp:system_delete",
  MCP_POLICY_MANAGE = "mcp:policy_manage",
  MCP_EXPORT = "mcp:export",
  FILE_READ = "file:read",
  FILE_DELETE = "file:delete",
  AGENT_CONFIG_READ = "agent:config_read",
  AGENT_ASSIGN = "agent:assign",
  MODEL_READ = "model:read",
  MODEL_DELETE = "model:delete",
  MODEL_ASSIGN = "model:assign",
  PRICING_MANAGE = "pricing:manage",
  PROJECT_READ = "project:read",
  PROJECT_WRITE = "project:write",
  PROJECT_DELETE = "project:delete",
  MEMORY_READ = "memory:read",
  MEMORY_WRITE = "memory:write",
  MEMORY_DELETE = "memory:delete",
  MEMORY_EXPORT = "memory:export",
  SANDBOX_READ = "sandbox:read",
  SANDBOX_EXECUTE = "sandbox:execute",
  SANDBOX_MANAGE = "sandbox:manage",
  PERSONA_PRESET_DELETE = "persona_preset:delete",
  ENVVAR_REVEAL = "envvar:reveal",
  NOTIFICATION_READ = "notification:read",
  NOTIFICATION_DELETE = "notification:delete",
  USAGE_QUOTA_MANAGE = "usage:quota_manage",

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
  // Channel
  CHANNEL_READ = "channel:read",
  CHANNEL_WRITE = "channel:write",
  CHANNEL_DELETE = "channel:delete",
  // Agent
  AGENT_READ = "agent:read",
  AGENT_ADMIN = "agent:admin",
  // Model
  MODEL_ADMIN = "model:admin",
  // Marketplace
  MARKETPLACE_READ = "marketplace:read",
  MARKETPLACE_PUBLISH = "marketplace:publish",
  MARKETPLACE_ADMIN = "marketplace:admin",
  // Persona Preset
  PERSONA_PRESET_READ = "persona_preset:read",
  PERSONA_PRESET_WRITE = "persona_preset:write",
  PERSONA_PRESET_ADMIN = "persona_preset:admin",
  // Scheduled Task
  SCHEDULED_TASK_READ = "scheduled_task:read",
  SCHEDULED_TASK_WRITE = "scheduled_task:write",
  SCHEDULED_TASK_DELETE = "scheduled_task:delete",
  // Environment Variables
  ENVVAR_READ = "envvar:read",
  ENVVAR_WRITE = "envvar:write",
  ENVVAR_DELETE = "envvar:delete",
  // Team
  TEAM_READ = "team:read",
  TEAM_WRITE = "team:write",
  TEAM_DELETE = "team:delete",
  // Notification
  NOTIFICATION_MANAGE = "notification:manage",
  // Usage
  USAGE_READ = "usage:read",
  USAGE_ADMIN = "usage:admin",
}

// 用户信息
export interface User {
  id: string;
  username: string;
  email: string;
  avatar_url?: string;
  roles: string[];
  permissions?: string[];
  grantable_permissions?: Permission[];
  assignable_role_ids?: string[];
  is_active: boolean;
  two_factor_enabled?: boolean;
  metadata?: {
    language?: string;
    theme?: string;
    [key: string]: unknown;
  };
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

// 注册响应
export interface RegisterResponse {
  user: User;
  requires_verification: boolean;
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

// 角色限制配置
export interface RoleLimits {
  five_hour_budget_usd?: number | null; // 5 小时模型费用额度（USD），null = 无限制
  weekly_budget_usd?: number | null; // 每周模型费用额度（USD），null = 无限制
  max_channels?: number | null; // 最大渠道数量，null = 无限制
  max_concurrent_chats?: number | null; // 每用户最大并发聊天数，null = 无限制
  max_queued_chats?: number | null; // 每用户最大排队数，null = 无限制
  max_file_size_image?: number | null; // 图片上传大小限制（MB），null = 使用全局默认
  max_file_size_video?: number | null; // 视频上传大小限制（MB）
  max_file_size_audio?: number | null; // 音频上传大小限制（MB）
  max_file_size_document?: number | null; // 文档上传大小限制（MB）
  max_files?: number | null; // 最大上传文件数，null = 使用全局默认
  [key: string]: number | null | undefined; // 允许扩展
}

// 角色信息
export interface Role {
  id: string;
  name: string;
  description?: string;
  permissions: Permission[];
  grantable_permissions?: Permission[];
  assignable_role_ids?: string[];
  unrestricted_models?: boolean;
  limits?: RoleLimits;
  is_system: boolean; // 系统角色不可删除
  created_at: string;
  updated_at: string;
}

export interface RoleListResponse {
  roles: Role[];
  total: number;
  skip: number;
  limit: number;
}

// 角色创建请求
export interface RoleCreate {
  name: string;
  description?: string;
  permissions: Permission[];
  grantable_permissions?: Permission[];
  assignable_role_ids?: string[];
  unrestricted_models?: boolean;
  limits?: RoleLimits;
}

// 角色更新请求
export interface RoleUpdate {
  name?: string;
  description?: string;
  permissions?: Permission[];
  grantable_permissions?: Permission[];
  assignable_role_ids?: string[];
  unrestricted_models?: boolean;
  limits?: RoleLimits;
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
  grantable_permissions?: Permission[];
  assignable_role_ids?: string[];
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
