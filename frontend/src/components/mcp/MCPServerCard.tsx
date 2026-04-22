import { useState, useCallback, useRef, useMemo } from "react";
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
  Shield,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { mcpApi } from "../../services/api/mcp";
import type { MCPServerResponse, MCPToolInfo } from "../../types";

interface MCPServerCardProps {
  server: MCPServerResponse;
  onToggle: (name: string) => void;
  onEdit: (server: MCPServerResponse) => void;
  onDelete: (name: string, isSystem: boolean) => void;
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
  onToolToggled,
}: MCPServerCardProps) {
  const { t } = useTranslation();
  const [isToolsExpanded, setIsToolsExpanded] = useState(false);
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);

  // Track pending toggle to debounce rapid clicks and avoid race conditions
  const pendingToggleRef = useRef<Promise<void> | null>(null);

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

      // Serialize toggles: wait for any in-flight toggle, then run this one
      const togglePromise = (async () => {
        if (pendingToggleRef.current) {
          await pendingToggleRef.current;
        }

        try {
          // user level: per-user preference toggle
          await mcpApi.toggleTool(server.name, toolName, newEnabled, "user");
          setTools((prev) =>
            prev.map((t) =>
              t.name === toolName ? { ...t, user_disabled: !newEnabled } : t,
            ),
          );
          onToolToggled?.();
        } catch {
          toast.error(t("mcp.card.toolToggleFailed", "Failed to toggle tool"));
          onToolToggled?.();
        }
      })();

      pendingToggleRef.current = togglePromise;
      await togglePromise;
      pendingToggleRef.current = null;
    },
    [server.name, onToolToggled, t],
  );

  // Count visible (non-disabled) tools
  const enabledToolCount = useMemo(
    () =>
      tools.length > 0
        ? tools.filter((t) => !t.system_disabled && !t.user_disabled).length
        : 0,
    [tools],
  );

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
            {server.is_system && server.allowed_roles && server.allowed_roles.length > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/50 dark:text-blue-300"
                title={t("mcp.card.allowedRolesTooltip", { roles: server.allowed_roles.join(", ") })}
              >
                <Shield size={10} />
                {server.allowed_roles.length === 1
                  ? server.allowed_roles[0]
                  : t("mcp.card.roleCount", { count: server.allowed_roles.length })}
              </span>
            )}
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

      {/* Tools section - system_disabled tools are hidden from individual users */}
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
                  const isDisabled =
                    tool.system_disabled || tool.user_disabled || false;
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
                        <div className="flex items-center gap-1.5 flex-wrap">
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
