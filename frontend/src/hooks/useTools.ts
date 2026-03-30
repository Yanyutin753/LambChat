import { useState, useCallback, useEffect, useRef } from "react";
import { authApi } from "../services/api";
import { authenticatedRequest } from "../services/api/authenticatedRequest";
import type {
  ToolInfo,
  ToolState,
  ToolsListResponse,
  ToolCategory,
} from "../types";

const API_BASE = "/api";

export function useTools(disabledToolsVersion?: string) {
  const [tools, setTools] = useState<ToolState[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const disabledToolsRef = useRef<Set<string>>(new Set());
  const savingRef = useRef(false);
  const agentIdRef = useRef<string | undefined>(undefined);

  // 从 user metadata 同步 disabled_tools 到 ref
  const syncFromMetadata = useCallback((metadata?: Record<string, unknown>) => {
    if (metadata?.disabled_tools && Array.isArray(metadata.disabled_tools)) {
      disabledToolsRef.current = new Set(metadata.disabled_tools as string[]);
    }
  }, []);

  // 保存 disabled_tools 到 user metadata
  const saveToMetadata = useCallback(async () => {
    if (savingRef.current) return;
    savingRef.current = true;
    try {
      await authApi.updateMetadata({
        disabled_tools: [...disabledToolsRef.current],
      });
    } catch (err) {
      console.error("Failed to save disabled_tools to metadata:", err);
    } finally {
      savingRef.current = false;
    }
  }, []);

  // 获取工具列表
  const fetchTools = useCallback(
    async (metadata?: Record<string, unknown>) => {
      setIsLoading(true);
      setError(null);
      try {
        // 先从 metadata 同步
        syncFromMetadata(metadata);

        const agentId = agentIdRef.current;
        const queryParams = agentId
          ? `?agent_id=${encodeURIComponent(agentId)}`
          : "";
        const response = await authenticatedRequest(
          `${API_BASE}/tools${queryParams}`,
          {
            headers: {
              "Content-Type": "application/json",
            },
          },
        );

        if (!response.ok) {
          throw new Error("Failed to fetch tools");
        }

        const data: ToolsListResponse = await response.json();
        const disabledTools = disabledToolsRef.current;

        // 初始化工具状态，根据持久化的禁用列表设置 enabled
        const toolStates: ToolState[] = data.tools.map((tool: ToolInfo) => ({
          ...tool,
          enabled: !disabledTools.has(tool.name),
        }));

        setTools(toolStates);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch tools");
      } finally {
        setIsLoading(false);
      }
    },
    [syncFromMetadata],
  );

  // 更新禁用列表并保存到 metadata
  const updateDisabledTools = useCallback(
    (toolName: string, enabled: boolean) => {
      const disabledTools = disabledToolsRef.current;
      if (enabled) {
        disabledTools.delete(toolName);
      } else {
        disabledTools.add(toolName);
      }
      saveToMetadata();
    },
    [saveToMetadata],
  );

  // 切换单个工具
  const toggleTool = useCallback(
    (toolName: string) => {
      setTools((prev) =>
        prev.map((t) => {
          if (t.name === toolName) {
            const newEnabled = !t.enabled;
            updateDisabledTools(toolName, newEnabled);
            return { ...t, enabled: newEnabled };
          }
          return t;
        }),
      );
    },
    [updateDisabledTools],
  );

  // 切换某类别的所有工具
  const toggleCategory = useCallback(
    (category: ToolCategory, enabled: boolean) => {
      setTools((prev) => {
        prev.forEach((t) => {
          if (t.category === category) {
            updateDisabledTools(t.name, enabled);
          }
        });
        return prev.map((t) =>
          t.category === category ? { ...t, enabled } : t,
        );
      });
    },
    [updateDisabledTools],
  );

  // 全选/取消全选
  const toggleAll = useCallback(
    (enabled: boolean) => {
      setTools((prev) => {
        prev.forEach((t) => {
          updateDisabledTools(t.name, enabled);
        });
        return prev.map((t) => ({ ...t, enabled }));
      });
    },
    [updateDisabledTools],
  );

  // 获取禁用的工具列表（用于 API 请求）
  const getDisabledToolNames = useCallback(() => {
    return tools.filter((t) => !t.enabled).map((t) => t.name);
  }, [tools]);

  // 获取启用的工具数量
  const enabledCount = tools.filter((t) => t.enabled).length;

  // 初始加载 — 从 authApi 获取当前 user metadata
  // disabledToolsVersion 变化时重新获取（当 MCPServerCard 切换工具时触发）
  useEffect(() => {
    authApi
      .getCurrentUser()
      .then((user) => fetchTools(user.metadata))
      .catch(() => fetchTools());
  }, [fetchTools, disabledToolsVersion]);

  // Refresh tools with a specific agent ID (for sandbox filtering)
  const refreshToolsForAgent = useCallback(
    (agentId: string, metadata?: Record<string, unknown>) => {
      agentIdRef.current = agentId;
      return fetchTools(metadata);
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
    refreshTools: fetchTools,
    refreshToolsForAgent,
  };
}
