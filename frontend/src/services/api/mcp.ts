/**
 * MCP API - MCP Server Management
 */

import type {
  MCPServerResponse,
  MCPServersResponse,
  MCPServerCreate,
  MCPServerUpdate,
  MCPServerToggleResponse,
  MCPImportRequest,
  MCPImportResponse,
  MCPExportResponse,
  MCPToolDiscoveryResponse,
  MCPToolToggleResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const mcpApi = {
  /**
   * List all visible MCP servers
   */
  async list(): Promise<MCPServersResponse> {
    return authFetch<MCPServersResponse>(`${API_BASE}/api/mcp`);
  },

  /**
   * Get a single MCP server
   */
  async get(name: string): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}`,
    );
  },

  /**
   * Create a new MCP server
   */
  async create(data: MCPServerCreate): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(`${API_BASE}/api/mcp`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Update an MCP server (user server only)
   */
  async update(
    name: string,
    data: MCPServerUpdate,
  ): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Update a system MCP server (admin only)
   */
  async updateSystem(
    name: string,
    data: MCPServerUpdate,
  ): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/admin/mcp/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete an MCP server (user server only)
   */
  async delete(name: string): Promise<void> {
    return authFetch<void>(`${API_BASE}/api/mcp/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
  },

  /**
   * Delete a system MCP server (admin only)
   */
  async deleteSystem(name: string): Promise<void> {
    return authFetch<void>(
      `${API_BASE}/api/admin/mcp/${encodeURIComponent(name)}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Toggle MCP server enabled status
   */
  async toggle(name: string): Promise<MCPServerToggleResponse> {
    return authFetch<MCPServerToggleResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}/toggle`,
      {
        method: "PATCH",
      },
    );
  },

  /**
   * Import MCP servers from JSON
   */
  async import(data: MCPImportRequest): Promise<MCPImportResponse> {
    return authFetch<MCPImportResponse>(`${API_BASE}/api/mcp/import`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Export MCP servers
   */
  async export(): Promise<MCPExportResponse> {
    return authFetch<MCPExportResponse>(`${API_BASE}/api/mcp/export`);
  },

  /**
   * Discover tools from a specific MCP server
   */
  async discoverTools(name: string): Promise<MCPToolDiscoveryResponse> {
    return authFetch<MCPToolDiscoveryResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}/tools`,
    );
  },

  /**
   * Toggle a specific tool's enabled status
   */
  async toggleTool(
    serverName: string,
    toolName: string,
    enabled: boolean,
    level: "system" | "user" = "system",
  ): Promise<MCPToolToggleResponse> {
    return authFetch<MCPToolToggleResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(serverName)}/tools/${encodeURIComponent(toolName)}`,
      {
        method: "PATCH",
        body: JSON.stringify({ enabled, level }),
      },
    );
  },
};
