import { useState, useCallback, useEffect } from "react";
import i18n from "i18next";
import { authFetch } from "../services/api/fetch";
import { API_BASE } from "../services/api/config";
import type {
  MCPServerResponse,
  MCPServerRetestResponse,
  MCPServersResponse,
  MCPServerCreate,
  MCPServerUpdate,
  MCPServerToggleResponse,
  MCPImportRequest,
  MCPImportResponse,
  MCPExportResponse,
  MCPServerMoveResponse,
} from "../types";

const MCP_API_BASE = `${API_BASE}/api/mcp`;
const ADMIN_MCP_API_BASE = `${API_BASE}/api/admin/mcp`;

interface MCPListParams {
  skip?: number;
  limit?: number;
  q?: string;
}

function buildMCPListUrl(params: MCPListParams = {}): string {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));
  if (params.q) searchParams.set("q", params.q);
  const query = searchParams.toString();
  return `${MCP_API_BASE}/${query ? `?${query}` : ""}`;
}

export function useMCP(options?: { listParams?: MCPListParams }) {
  const listParams = options?.listParams;
  const [servers, setServers] = useState<MCPServerResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all MCP servers
  const fetchServers = useCallback(
    async (params?: MCPListParams) => {
      setIsLoading(true);
      setError(null);
      try {
        const data: MCPServersResponse = await authFetch(
          buildMCPListUrl(params ?? listParams ?? {}),
        );
        setServers(data.servers ?? []);
        setTotal(data.total);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.fetchServersFailed", "获取MCP服务器失败"),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [listParams],
  );

  // Get single server
  const getServer = useCallback(
    async (name: string): Promise<MCPServerResponse | null> => {
      try {
        return await authFetch<MCPServerResponse>(`${MCP_API_BASE}/${name}`);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.fetchServerFailed", "获取MCP服务器失败"),
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
        const baseUrl = isSystem ? ADMIN_MCP_API_BASE : MCP_API_BASE;
        const data: MCPServerResponse = await authFetch(`${baseUrl}/`, {
          method: "POST",
          body: JSON.stringify(server),
        });
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.createFailed", "创建MCP服务器失败"),
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
        const baseUrl = isSystem ? ADMIN_MCP_API_BASE : MCP_API_BASE;
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
          err instanceof Error
            ? err.message
            : i18n.t("mcp.updateFailed", "更新MCP服务器失败"),
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
        const baseUrl = isSystem ? ADMIN_MCP_API_BASE : MCP_API_BASE;
        await authFetch(`${baseUrl}/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        await fetchServers();
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.deleteFailed", "删除MCP服务器失败"),
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
          `${MCP_API_BASE}/${name}/toggle`,
          {
            method: "PATCH",
          },
        );
        await fetchServers();
        return data.server;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.toggleFailed", "切换MCP服务器失败"),
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Retest one server connection; refreshes the list so the badge updates (issue #991)
  const retestServer = useCallback(
    async (
      name: string,
      isSystem = false,
    ): Promise<MCPServerRetestResponse | null> => {
      setError(null);
      try {
        const baseUrl = isSystem ? ADMIN_MCP_API_BASE : MCP_API_BASE;
        const data: MCPServerRetestResponse = await authFetch(
          `${baseUrl}/${encodeURIComponent(name)}/retest`,
          { method: "POST" },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.retestFailed", "重测连接失败"),
        );
        return null;
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
        const data: MCPImportResponse = await authFetch(
          `${MCP_API_BASE}/import`,
          {
            method: "POST",
            body: JSON.stringify(request),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.importFailed", "导入MCP服务器失败"),
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
        return await authFetch<MCPExportResponse>(`${MCP_API_BASE}/export`);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.exportFailed", "导出MCP服务器失败"),
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
          `${ADMIN_MCP_API_BASE}/${encodeURIComponent(name)}/promote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: ownerUserId }),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.promoteFailed", "升级MCP服务器失败"),
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
          `${ADMIN_MCP_API_BASE}/${encodeURIComponent(name)}/demote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: targetUserId }),
          },
        );
        await fetchServers();
        return data;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("mcp.demoteFailed", "降级MCP服务器失败"),
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchServers],
  );

  // Initial load
  useEffect(() => {
    fetchServers(listParams);
  }, [fetchServers, listParams]);

  return {
    servers,
    total,
    isLoading,
    error,
    fetchServers,
    getServer,
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    retestServer,
    importServers,
    exportServers,
    promoteServer,
    demoteServer,
    clearError: () => setError(null),
  };
}
