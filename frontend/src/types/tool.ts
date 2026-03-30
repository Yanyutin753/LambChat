// ============================================
// Tool Types
// ============================================

// Tool Category
export type ToolCategory = "builtin" | "skill" | "human" | "mcp" | "sandbox";

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
