import { useState, useCallback, useEffect, useRef } from "react";
import { getAccessToken } from "../services/api";
import type {
  ToolInfo,
  ToolState,
  ToolsListResponse,
  ToolCategory,
} from "../types";

const API_BASE = "/api";
const DISABLED_TOOLS_KEY = "disabled_tools";

// 从 localStorage 读取禁用的工具列表
function loadDisabledTools(): Set<string> {
  try {
    const stored = localStorage.getItem(DISABLED_TOOLS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return new Set(Array.isArray(parsed) ? parsed : []);
    }
  } catch {
    // 忽略解析错误
  }
  return new Set();
}

// 保存禁用的工具列表到 localStorage
function saveDisabledTools(disabledTools: Set<string>): void {
  try {
    localStorage.setItem(
      DISABLED_TOOLS_KEY,
      JSON.stringify([...disabledTools]),
    );
  } catch {
    // 忽略存储错误
  }
}

export function useTools() {
  const [tools, setTools] = useState<ToolState[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const disabledToolsRef = useRef<Set<string>>(loadDisabledTools());

  // 获取工具列表
  const fetchTools = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = getAccessToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE}/tools`, {
        headers,
      });

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
  }, []);

  // 更新禁用列表并保存到 localStorage
  const updateDisabledTools = useCallback(
    (toolName: string, enabled: boolean) => {
      const disabledTools = disabledToolsRef.current;
      if (enabled) {
        disabledTools.delete(toolName);
      } else {
        disabledTools.add(toolName);
      }
      saveDisabledTools(disabledTools);
    },
    [],
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

  // 初始加载
  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

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
  };
}
