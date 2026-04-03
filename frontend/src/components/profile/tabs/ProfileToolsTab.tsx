import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Wrench, ToggleLeft, ToggleRight, Loader2, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";
import { authenticatedRequest } from "../../../services/api/authenticatedRequest";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import type { ToolInfo } from "../../../types";

const API_BASE = "/api";

interface GroupedTools {
  serverName: string;
  tools: ToolInfo[];
}

export function ProfileToolsTab() {
  const { t } = useTranslation();
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const fetchTools = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await authenticatedRequest(`${API_BASE}/tools`);
      if (!response.ok) throw new Error("Failed to fetch tools");
      const data = await response.json();
      setTools(data.tools || []);
    } catch {
      toast.error(t("tools.loadFailed", "Failed to load tools"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  const handleToggleTool = useCallback(
    async (tool: ToolInfo) => {
      if (tool.system_disabled) return;
      if (tool.category !== "mcp" || !tool.server) return;

      const toolKey = tool.name;
      setToggling((prev) => new Set(prev).add(toolKey));

      const baseName = tool.name.includes(":") ? tool.name.split(":")[1] : tool.name;
      const newEnabled = tool.user_disabled;

      try {
        const response = await authenticatedRequest(
          `${API_BASE}/mcp/${encodeURIComponent(tool.server)}/tools/${encodeURIComponent(baseName)}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: newEnabled }),
          },
        );
        if (!response.ok) throw new Error("Failed to toggle tool");
        // Optimistic update
        setTools((prev) =>
          prev.map((t) =>
            t.name === tool.name ? { ...t, user_disabled: !newEnabled } : t,
          ),
        );
      } catch {
        toast.error(t("mcp.card.toolToggleFailed", "Failed to toggle tool"));
      } finally {
        setToggling((prev) => {
          const next = new Set(prev);
          next.delete(toolKey);
          return next;
        });
      }
    },
    [t],
  );

  // Group MCP tools by server
  const mcpTools = tools.filter((t) => t.category === "mcp" && t.server);
  const groupedByServer: GroupedTools[] = [];
  const serverMap = new Map<string, ToolInfo[]>();
  for (const tool of mcpTools) {
    const server = tool.server!;
    if (!serverMap.has(server)) serverMap.set(server, []);
    serverMap.get(server)!.push(tool);
  }
  for (const [serverName, serverTools] of serverMap) {
    groupedByServer.push({
      serverName,
      tools: serverTools.sort((a, b) =>
        a.name.toLowerCase().localeCompare(b.name.toLowerCase()),
      ),
    });
  }
  groupedByServer.sort((a, b) =>
    a.serverName.toLowerCase().localeCompare(b.serverName.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wrench size={15} className="text-amber-500 dark:text-amber-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
            {t("profile.toolsPreferences", "MCP Tool Preferences")}
          </h3>
        </div>
        <button
          onClick={fetchTools}
          disabled={isLoading}
          className="p-1 rounded-lg text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700/60 transition-colors"
          title={t("common.refresh", "Refresh")}
        >
          <RefreshCw size={13} className={isLoading ? "animate-spin" : ""} />
        </button>
      </div>

      <p className="text-xs text-stone-400 dark:text-stone-500">
        {t(
          "profile.toolsPreferencesDesc",
          "Configure which MCP tools are enabled by default across all conversations. These settings can be overridden per conversation.",
        )}
      </p>

      {isLoading && tools.length === 0 ? (
        <div className="flex items-center justify-center py-8 gap-2 text-stone-400 dark:text-stone-500">
          <LoadingSpinner size="sm" />
          <span className="text-sm">{t("mcp.loading", "Loading...")}</span>
        </div>
      ) : groupedByServer.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-stone-400 dark:text-stone-500">
          <Wrench size={32} className="mb-2 text-stone-300 dark:text-stone-600" />
          <p className="text-sm">{t("tools.noTools", "No tools available")}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {groupedByServer.map(({ serverName, tools: serverTools }) => {
            const enabledCount = serverTools.filter(
              (t) => !t.user_disabled && !t.system_disabled,
            ).length;
            return (
              <div
                key={serverName}
                className="rounded-xl border border-stone-200/60 dark:border-stone-600/40 bg-stone-50 dark:bg-stone-700/40 overflow-hidden"
              >
                {/* Server header */}
                <div className="px-3 py-2 border-b border-stone-200/60 dark:border-stone-600/40 flex items-center justify-between bg-stone-100/60 dark:bg-stone-800/30">
                  <span className="text-xs font-semibold text-stone-600 dark:text-stone-300 truncate">
                    {serverName}
                  </span>
                  <span className="text-[10px] text-stone-400 dark:text-stone-500 tabular-nums shrink-0 ml-2">
                    {enabledCount}/{serverTools.length}
                  </span>
                </div>

                {/* Tool list */}
                <div className="divide-y divide-stone-200/40 dark:divide-stone-600/30">
                  {serverTools.map((tool) => {
                    const isSystemDisabled = tool.system_disabled || false;
                    const isUserDisabled = tool.user_disabled || false;
                    const isEnabled = !isUserDisabled && !isSystemDisabled;
                    const isPending = toggling.has(tool.name);
                    const baseName = tool.name.includes(":")
                      ? tool.name.split(":")[1]
                      : tool.name;

                    return (
                      <div
                        key={tool.name}
                        className={`flex items-center gap-2 px-3 py-2 transition-colors ${
                          isSystemDisabled || isUserDisabled ? "opacity-50" : ""
                        }`}
                      >
                        <button
                          onClick={() => handleToggleTool(tool)}
                          disabled={isSystemDisabled || isPending}
                          className="flex-shrink-0 disabled:cursor-not-allowed"
                          title={
                            isSystemDisabled
                              ? t("mcp.card.systemDisabled", "System Disabled")
                              : isEnabled
                                ? t("mcp.card.disableTool", "Disable tool")
                                : t("mcp.card.enableTool", "Enable tool")
                          }
                        >
                          {isPending ? (
                            <Loader2
                              size={16}
                              className="animate-spin text-stone-400"
                            />
                          ) : isEnabled ? (
                            <ToggleRight
                              size={16}
                              className="text-green-600 dark:text-green-500"
                            />
                          ) : (
                            <ToggleLeft
                              size={16}
                              className={
                                isSystemDisabled
                                  ? "text-red-400 dark:text-red-500"
                                  : "text-stone-400 dark:text-stone-500"
                              }
                            />
                          )}
                        </button>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <code className="text-xs font-medium text-stone-700 dark:text-stone-200 truncate">
                              {baseName}
                            </code>
                            {isSystemDisabled && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 font-medium">
                                {t("tools.systemDisabled", "System Disabled")}
                              </span>
                            )}
                          </div>
                          {tool.description && (
                            <p className="text-[11px] text-stone-400 dark:text-stone-500 truncate mt-0.5">
                              {tool.description}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
