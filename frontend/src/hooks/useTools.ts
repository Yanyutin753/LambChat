import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { authenticatedRequest } from "../services/api/authenticatedRequest";
import type {
  ToolInfo,
  ToolState,
  ToolsListResponse,
  ToolCategory,
} from "../types";

const API_BASE = "/api";

export function useTools() {
  const [tools, setTools] = useState<ToolState[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const agentIdRef = useRef<string | undefined>(undefined);

  // 切换 MCP 工具的启用状态（调用 MCP API）
  const toggleMcpTool = useCallback(async (toolName: string, serverName: string, enabled: boolean) => {
    try {
      const baseName = toolName.includes(":") ? toolName.split(":")[1] : toolName;
      await authenticatedRequest(
        `${API_BASE}/mcp/${encodeURIComponent(serverName)}/tools/${encodeURIComponent(baseName)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        }
      );
    } catch (err) {
      console.error("Failed to toggle MCP tool:", err);
      throw err;
    }
  }, []);

  // 获取工具列表
  const fetchTools = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const agentId = agentIdRef.current;
      const queryParams = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
      const response = await authenticatedRequest(`${API_BASE}/tools${queryParams}`, {
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch tools");
      }

      const data: ToolsListResponse = await response.json();
      const toolStates: ToolState[] = data.tools.map((tool: ToolInfo) => ({
        ...tool,
        // 工具启用状态：未被系统禁用且未被用户禁用
        enabled: !tool.system_disabled && !tool.user_disabled,
      }));

      setTools(toolStates);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch tools");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 切换单个工具
  const toggleTool = useCallback(
    async (toolName: string) => {
      const tool = tools.find((t) => t.name === toolName);
      if (!tool) return;

      if (tool.system_disabled) {
        console.warn("Cannot toggle system-disabled tool:", toolName);
        return;
      }

      if (tool.category !== "mcp" || !tool.server) {
        console.warn("Only MCP tools can be toggled:", toolName);
        return;
      }

      try {
        await toggleMcpTool(toolName, tool.server, !tool.enabled);
        await fetchTools();
      } catch (err) {
        console.error("Failed to toggle tool:", err);
      }
    },
    [tools, toggleMcpTool, fetchTools],
  );

  // 切换某类别的所有工具
  const toggleCategory = useCallback(
    async (category: ToolCategory, enabled: boolean) => {
      // 只有 MCP 工具支持切换，且不能是系统禁用的
      const categoryTools = tools.filter(
        (t) => t.category === category && !t.system_disabled && category === "mcp" && t.server
      );
      await Promise.all(
        categoryTools.map((t) => toggleMcpTool(t.name, t.server!, enabled))
      );
      await fetchTools();
    },
    [tools, toggleMcpTool, fetchTools],
  );

  // 全选/取消全选
  const toggleAll = useCallback(
    async (enabled: boolean) => {
      const toggleableTools = tools.filter(
        (t) => !t.system_disabled && t.category === "mcp" && t.server
      );
      await Promise.all(
        toggleableTools.map((t) => toggleMcpTool(t.name, t.server!, enabled))
      );
      await fetchTools();
    },
    [tools, toggleMcpTool, fetchTools],
  );

  // 获取禁用的工具列表（用于 API 请求）
  const getDisabledToolNames = useCallback(() => {
    return tools.filter((t) => !t.enabled).map((t) => t.name);
  }, [tools]);

  /**
   * 获取禁用的 MCP 工具列表
   * 用于配置持久化（黑名单模式）
   */
  const getDisabledMcpTools = useCallback(() => {
    return tools
      .filter((t) => t.category === "mcp" && !t.enabled)
      .map((t) => t.name);
  }, [tools]);

  // 获取启用的工具数量
  const enabledCount = useMemo(() => tools.filter((t) => t.enabled).length, [tools]);

  // 初始加载
  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  // Refresh tools with a specific agent ID (for sandbox filtering)
  const refreshToolsForAgent = useCallback(
    (agentId: string) => {
      agentIdRef.current = agentId;
      return fetchTools();
    },
    [fetchTools],
  );

  return {
    tools,
    isLoading,
    error,
    enabledCount,
    totalCount: tools.length,
    toggleTool,
    toggleCategory,
    toggleAll,
    getDisabledToolNames,
    getDisabledMcpTools,
    refreshTools: fetchTools,
    refreshToolsForAgent,
  };
}
