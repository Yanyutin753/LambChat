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
