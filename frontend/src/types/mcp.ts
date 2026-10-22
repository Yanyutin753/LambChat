// ============================================
// MCP Types
// ============================================

// MCP Transport Type
export type MCPTransport = "sse" | "streamable_http";

// MCP Server Base
export interface MCPServerBase {
  name: string;
  transport: MCPTransport;
  enabled: boolean;
  url?: string;
  headers?: Record<string, string>;
}

// MCP Server Response (from API)
export interface MCPServerResponse extends MCPServerBase {
  is_system: boolean;
  is_internal?: boolean;
  can_edit: boolean;
  allowed_roles: string[];
  role_quotas: Record<string, MCPRoleQuota>;
  created_at?: string;
  updated_at?: string;
  last_load_status?: "ok" | "failed" | null;
  consecutive_failures?: number;
  last_load_at?: string | null;
  last_load_error?: string | null;
}

// MCP Server Retest Response (from API)
export interface MCPServerRetestResponse {
  server_name: string;
  status: "ok" | "failed";
  latency_ms: number;
  tool_count: number;
  error?: string | null;
}

export interface MCPRoleQuota {
  daily_limit?: number | null;
  weekly_limit?: number | null;
}

// MCP Servers List Response
export interface MCPServersResponse {
  servers: MCPServerResponse[];
  total: number;
  skip: number;
  limit: number;
}

// MCP Server Create Request
export interface MCPServerCreate {
  name: string;
  transport: MCPTransport;
  enabled?: boolean;
  url?: string;
  headers?: Record<string, string>;
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
}

// MCP Server Update Request
export interface MCPServerUpdate {
  transport?: MCPTransport;
  enabled?: boolean;
  url?: string;
  headers?: Record<string, string>;
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
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

// MCP Tool Info (discovered from server)
export interface MCPToolInfo {
  name: string;
  description: string;
  parameters: MCPToolParamInfo[];
  system_disabled?: boolean; // Whether this tool is disabled at system level
  user_disabled?: boolean; // Whether this tool is disabled by the user
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
  policy_configured?: boolean;
  inline_exposure?: boolean;
}

// MCP Tool Parameter Info
export interface MCPToolParamInfo {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

// MCP Tool Discovery Response
export interface MCPToolDiscoveryResponse {
  server_name: string;
  tools: MCPToolInfo[];
  count: number;
  error?: string;
}

// MCP Tool Toggle Response
export interface MCPToolToggleResponse {
  server_name: string;
  tool_name: string;
  enabled: boolean;
  message: string;
}

export interface MCPToolPolicy {
  server_name?: string;
  tool_name?: string;
  disabled?: boolean;
  inline_exposure?: boolean;
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
  created_at?: string;
  updated_at?: string;
  updated_by?: string;
}

export interface MCPToolPolicyUpdate {
  disabled?: boolean;
  inline_exposure?: boolean;
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
}
