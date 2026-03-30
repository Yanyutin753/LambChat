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
  MCP_WRITE_SSE = "mcp:write_sse",
  MCP_WRITE_HTTP = "mcp:write_http",
  MCP_WRITE_SANDBOX = "mcp:write_sandbox",
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
  // Marketplace
  MARKETPLACE_READ = "marketplace:read",
  MARKETPLACE_PUBLISH = "marketplace:publish",
  MARKETPLACE_ADMIN = "marketplace:admin",
  // Environment Variables
  ENVVAR_READ = "envvar:read",
  ENVVAR_WRITE = "envvar:write",
  ENVVAR_DELETE = "envvar:delete",
}

// 用户信息
export interface User {
  id: string;
  username: string;
  email: string;
  avatar_url?: string;
  roles: string[];
  permissions?: string[];
  is_active: boolean;
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
  limits?: RoleLimits;
  is_system: boolean; // 系统角色不可删除
  created_at: string;
  updated_at: string;
}

// 角色创建请求
export interface RoleCreate {
  name: string;
  description?: string;
  permissions: Permission[];
  limits?: RoleLimits;
}

// 角色更新请求
export interface RoleUpdate {
  name?: string;
  description?: string;
  permissions?: Permission[];
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
