import { useState, useCallback, useEffect } from "react";
import {
  Server,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  ChevronDown,
  ChevronRight,
  Wrench,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { mcpApi } from "../../services/api/mcp";
import { authApi } from "../../services/api";
import type { MCPServerResponse, MCPToolInfo } from "../../types";

interface MCPServerCardProps {
  server: MCPServerResponse;
  onToggle: (name: string) => void;
  onEdit: (server: MCPServerResponse) => void;
  onDelete: (name: string, isSystem: boolean) => void;
  disabledToolNames?: Set<string>;
  onToolToggled?: () => void;
}

const TRANSPORT_LABELS: Record<string, string> = {
  sse: "SSE",
  streamable_http: "HTTP",
  sandbox: "Sandbox",
};

const TRANSPORT_COLORS: Record<string, string> = {
  sse: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  streamable_http:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  sandbox:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
};

const DEFAULT_TRANSPORT_COLOR =
  "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300";

export function MCPServerCard({
  server,
  onToggle,
  onEdit,
  onDelete,
  disabledToolNames = new Set(),
  onToolToggled,
}: MCPServerCardProps) {
  const { t } = useTranslation();
  const [isToolsExpanded, setIsToolsExpanded] = useState(false);
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);

  // Sync disabled state from props (derived from disabled_tools metadata)
  const [localDisabledTools, setLocalDisabledTools] = useState<Set<string>>(
    new Set(),
  );
  useEffect(() => {
    setLocalDisabledTools(new Set(disabledToolNames));
  }, [disabledToolNames]);

  const disabledTools = localDisabledTools;

  const transportLabel =
    TRANSPORT_LABELS[server.transport] || server.transport.toUpperCase();
  const transportColor =
    TRANSPORT_COLORS[server.transport] || DEFAULT_TRANSPORT_COLOR;

  const handleToggleTools = useCallback(async () => {
    if (isToolsExpanded) {
      setIsToolsExpanded(false);
      return;
    }

    // If we haven't loaded tools yet, fetch them
    if (tools.length === 0 && !toolsLoading) {
      setIsToolsExpanded(true);
      setToolsLoading(true);
      setToolsError(null);
      try {
        const result = await mcpApi.discoverTools(server.name);
        if (result.error) {
          setToolsError(result.error);
        } else {
          // Sort tools by name
          const sortedTools = [...result.tools].sort((a, b) =>
            a.name.toLowerCase().localeCompare(b.name.toLowerCase()),
          );
          setTools(sortedTools);
        }
      } catch (err) {
        setToolsError(
          err instanceof Error ? err.message : "Failed to discover tools",
        );
      } finally {
        setToolsLoading(false);
      }
    } else {
      setIsToolsExpanded(true);
    }
  }, [isToolsExpanded, tools.length, toolsLoading, server.name]);

  const handleToggleTool = useCallback(
    async (toolName: string, currentEnabled: boolean) => {
      const newEnabled = !currentEnabled;
      const qualifiedName = `${server.name}:${toolName}`;

      // Optimistic update
      setLocalDisabledTools((prev) => {
        const next = new Set(prev);
        if (newEnabled) {
          next.delete(qualifiedName);
        } else {
          next.add(qualifiedName);
        }
        return next;
      });

      try {
        // Use the same disabled_tools metadata as ToolSelector
        const user = await authApi.getCurrentUser();
        const currentDisabled: string[] =
          (user.metadata?.disabled_tools as string[]) || [];
        const updatedDisabled = newEnabled
          ? currentDisabled.filter((n) => n !== qualifiedName)
          : [...new Set([...currentDisabled, qualifiedName])];
        await authApi.updateMetadata({ disabled_tools: updatedDisabled });

        // Notify parent to refresh ToolSelector
        onToolToggled?.();
      } catch {
        // Revert on error
        setLocalDisabledTools((prev) => {
          const next = new Set(prev);
          if (newEnabled) {
            next.add(qualifiedName);
          } else {
            next.delete(qualifiedName);
          }
          return next;
        });
      }
    },
    [server.name, onToolToggled],
  );

  const enabledToolCount =
    tools.length > 0
      ? tools.filter((t) => !disabledTools.has(`${server.name}:${t.name}`))
          .length
      : 0;

  return (
    <div
      className={`panel-card transition-opacity ${
        !server.enabled ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Server
              size={20}
              className="text-stone-400 dark:text-stone-500 flex-shrink-0"
            />
            <h4 className="font-medium text-stone-900 dark:text-stone-100 truncate">
              {server.name}
            </h4>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${transportColor}`}
            >
              {transportLabel}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                server.is_system
                  ? "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300"
                  : "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300"
              }`}
            >
              {server.is_system ? t("mcp.card.system") : t("mcp.card.user")}
            </span>
            {!server.enabled && (
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-500">
                {t("mcp.card.disabled")}
              </span>
            )}
          </div>

          {/* Transport-specific details */}
          <div className="mt-2 text-sm text-stone-600 dark:text-stone-400">
            {server.url && (
              <div className="font-mono text-xs bg-stone-50 dark:bg-stone-800 rounded px-2 py-1 truncate">
                {server.url}
              </div>
            )}
            {server.command && (
              <div className="font-mono text-xs bg-stone-50 dark:bg-stone-800 rounded px-2 py-1 truncate">
                {server.command}
              </div>
            )}
          </div>

          {/* Headers info */}
          {server.headers && Object.keys(server.headers).length > 0 && (
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-500">
              {t("mcp.card.headersCount", {
                count: Object.keys(server.headers).length,
              })}
            </div>
          )}

          {/* Env keys info (sandbox transport) */}
          {server.env_keys && server.env_keys.length > 0 && (
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-500">
              {t("mcp.card.envVarsCount", {
                count: server.env_keys.length,
              })}
            </div>
          )}

          {/* Timestamps */}
          {server.updated_at && (
            <div className="mt-2 text-xs text-stone-400 dark:text-stone-500">
              {t("mcp.card.updated", {
                date: new Date(server.updated_at).toLocaleDateString(),
              })}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          <button
            onClick={() => onToggle(server.name)}
            className="btn-icon"
            title={
              server.enabled ? t("mcp.card.disable") : t("mcp.card.enable")
            }
          >
            {server.enabled ? (
              <ToggleRight
                size={20}
                className="text-green-600 dark:text-green-500"
              />
            ) : (
              <ToggleLeft size={20} />
            )}
          </button>
          {server.can_edit && (
            <>
              <button
                onClick={() => onEdit(server)}
                className="btn-icon"
                title={t("mcp.card.edit")}
              >
                <Edit3 size={20} />
              </button>
              <button
                onClick={() => onDelete(server.name, server.is_system)}
                className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                title={t("mcp.card.delete")}
              >
                <Trash2 size={20} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tools Discovery Section - not shown for sandbox (tools are injected at runtime, not discoverable via MCP protocol) */}
      {server.enabled && server.transport !== "sandbox" && (
        <div className="mt-3 border-t border-stone-100 dark:border-stone-700/50 pt-2">
          <button
            onClick={handleToggleTools}
            className="flex items-center gap-1.5 text-xs text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 transition-colors w-full"
          >
            {isToolsExpanded ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
            <Wrench size={12} />
            <span>{t("mcp.card.tools")}</span>
            {toolsLoading && <Loader2 size={12} className="animate-spin" />}
            {tools.length > 0 && !toolsLoading && (
              <span className="text-stone-400 dark:text-stone-500 tabular-nums">
                ({enabledToolCount}/{tools.length})
              </span>
            )}
          </button>

          {isToolsExpanded && (
            <div className="mt-2 ml-4 space-y-0.5">
              {toolsLoading && (
                <div className="flex items-center gap-2 py-2 text-xs text-stone-400 dark:text-stone-500">
                  <Loader2 size={14} className="animate-spin" />
                  <span>{t("mcp.card.discovering")}</span>
                </div>
              )}

              {toolsError && (
                <div className="text-xs text-red-500 dark:text-red-400 py-1">
                  {toolsError}
                </div>
              )}

              {!toolsLoading && tools.length === 0 && !toolsError && (
                <div className="text-xs text-stone-400 dark:text-stone-500 py-1">
                  {t("mcp.card.noTools")}
                </div>
              )}

              {!toolsLoading &&
                tools.map((tool) => {
                  const qualifiedName = `${server.name}:${tool.name}`;
                  const isDisabled = disabledTools.has(qualifiedName);
                  return (
                    <div
                      key={tool.name}
                      className={`flex items-center gap-2 py-1.5 px-2 rounded-lg transition-colors ${
                        isDisabled
                          ? "opacity-50"
                          : "hover:bg-stone-50 dark:hover:bg-stone-800/50"
                      }`}
                    >
                      <button
                        onClick={() => handleToggleTool(tool.name, !isDisabled)}
                        className="flex-shrink-0"
                        title={
                          isDisabled
                            ? t("mcp.card.enableTool")
                            : t("mcp.card.disableTool")
                        }
                      >
                        {isDisabled ? (
                          <ToggleLeft
                            size={16}
                            className="text-stone-400 dark:text-stone-500"
                          />
                        ) : (
                          <ToggleRight
                            size={16}
                            className="text-green-600 dark:text-green-500"
                          />
                        )}
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <code className="text-xs font-medium text-stone-700 dark:text-stone-200 truncate">
                            {tool.name}
                          </code>
                          {tool.parameters.length > 0 && (
                            <span className="text-[9px] px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-700 text-stone-400 dark:text-stone-500 tabular-nums">
                              {tool.parameters.length} params
                            </span>
                          )}
                        </div>
                        {tool.description && (
                          <p className="text-xs text-stone-400 dark:text-stone-500 truncate mt-0.5">
                            {tool.description}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
