// ============================================
// MCP Types
// ============================================

// MCP Transport Type
export type MCPTransport = "sse" | "streamable_http" | "sandbox";

// MCP Server Base
export interface MCPServerBase {
  name: string;
  transport: MCPTransport;
  enabled: boolean;
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  env_keys?: string[];
}

// MCP Server Response (from API)
export interface MCPServerResponse extends MCPServerBase {
  is_system: boolean;
  can_edit: boolean;
  allowed_roles: string[];
  role_quotas: Record<string, MCPRoleQuota>;
  created_at?: string;
  updated_at?: string;
}

export interface MCPRoleQuota {
  daily_limit?: number | null;
  weekly_limit?: number | null;
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
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  env_keys?: string[];
  allowed_roles?: string[];
  role_quotas?: Record<string, MCPRoleQuota>;
}

// MCP Server Update Request
export interface MCPServerUpdate {
  transport?: MCPTransport;
  enabled?: boolean;
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  env_keys?: string[];
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
