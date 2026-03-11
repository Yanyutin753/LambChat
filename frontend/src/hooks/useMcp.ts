import { useState, useCallback, useEffect, useRef } from "react";
import { authFetch } from "../services/api/fetch";
import type {
  MCPServerResponse,
  MCPServersResponse,
  MCPServerCreate,
  MCPServerUpdate,
  MCPServerToggleResponse,
  MCPImportRequest,
  MCPImportResponse,
  MCPExportResponse,
  MCPServerMoveResponse,
} from "../types";

const API_BASE = "/api/mcp";

export function useMCP(options?: { enabled?: boolean }) {
  const enabled = options?.enabled === true; // Must be explicitly true to fetch
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const [servers, setServers] = useState<MCPServerResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all MCP servers
  const fetchServers = useCallback(async () => {
    if (!enabledRef.current) return; // Skip if feature is disabled
    setIsLoading(true);
    setError(null);
    try {
      const data: MCPServersResponse = await authFetch(`${API_BASE}/`);
      setServers(data.servers ?? []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch MCP servers",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Get single server
  const getServer = useCallback(
    async (name: string): Promise<MCPServerResponse | null> => {
      try {
        return await authFetch<MCPServerResponse>(`${API_BASE}/${name}`);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to fetch MCP server",
        );
        return null;
      }
    },
    [],
  );

  // Create MCP server (auto-selects admin API for system servers)
  const createServer = useCallback(
    async (
      server: MCPServerCreate,
      isSystem: boolean = false,
    ): Promise<MCPServerResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? "/api/admin/mcp" : API_BASE;
        const data: MCPServerResponse = await authFetch(`${baseUrl}/`, {
          method: "POST",
          body: JSON.stringify(server),
        });
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to create MCP server",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Update MCP server (auto-selects admin API for system servers)
  const updateServer = useCallback(
    async (
      name: string,
      updates: MCPServerUpdate,
      isSystem: boolean = false,
    ): Promise<MCPServerResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? "/api/admin/mcp" : API_BASE;
        const data: MCPServerResponse = await authFetch(
          `${baseUrl}/${encodeURIComponent(name)}`,
          {
            method: "PUT",
            body: JSON.stringify(updates),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to update MCP server",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Delete MCP server (auto-selects admin API for system servers)
  const deleteServer = useCallback(
    async (name: string, isSystem: boolean = false): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? "/api/admin/mcp" : API_BASE;
        await authFetch(`${baseUrl}/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        await fetchServers();
        return true;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to delete MCP server",
        );
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Toggle server enabled status
  const toggleServer = useCallback(
    async (name: string): Promise<MCPServerResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: MCPServerToggleResponse = await authFetch(
          `${API_BASE}/${name}/toggle`,
          {
            method: "PATCH",
          },
        );
        await fetchServers();
        return data.server;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to toggle MCP server",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Import servers from JSON
  const importServers = useCallback(
    async (request: MCPImportRequest): Promise<MCPImportResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: MCPImportResponse = await authFetch(`${API_BASE}/import`, {
          method: "POST",
          body: JSON.stringify(request),
        });
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to import MCP servers",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Export servers to JSON
  const exportServers =
    useCallback(async (): Promise<MCPExportResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        return await authFetch<MCPExportResponse>(`${API_BASE}/export`);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to export MCP servers",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    }, []);

  // Promote user server to system server (admin only)
  const promoteServer = useCallback(
    async (
      name: string,
      ownerUserId: string,
    ): Promise<MCPServerMoveResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: MCPServerMoveResponse = await authFetch(
          `/api/admin/mcp/${encodeURIComponent(name)}/promote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: ownerUserId }),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to promote MCP server",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Demote system server to user server (admin only)
  const demoteServer = useCallback(
    async (
      name: string,
      targetUserId: string,
    ): Promise<MCPServerMoveResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: MCPServerMoveResponse = await authFetch(
          `/api/admin/mcp/${encodeURIComponent(name)}/demote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: targetUserId }),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to demote MCP server",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Initial load - only fetch when enabled
  useEffect(() => {
    if (enabled) {
      fetchServers();
    }
  }, [fetchServers, enabled]);

  return {
    servers,
    isLoading,
    error,
    fetchServers,
    getServer,
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    importServers,
    exportServers,
    promoteServer,
    demoteServer,
    clearError: () => setError(null),
  };
}
