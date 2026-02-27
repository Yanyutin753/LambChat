import { Server, ToggleLeft, ToggleRight, Edit3, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MCPServerResponse } from "../../types";

interface MCPServerCardProps {
  server: MCPServerResponse;
  onToggle: (name: string) => void;
  onEdit: (server: MCPServerResponse) => void;
  onDelete: (name: string, isSystem: boolean) => void;
}

const TRANSPORT_LABELS: Record<string, string> = {
  stdio: "STDIO",
  sse: "SSE",
  streamable_http: "HTTP",
};

const TRANSPORT_COLORS: Record<string, string> = {
  stdio: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  sse: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  streamable_http:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
};

const DEFAULT_TRANSPORT_COLOR =
  "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300";

export function MCPServerCard({
  server,
  onToggle,
  onEdit,
  onDelete,
}: MCPServerCardProps) {
  const { t } = useTranslation();
  const transportLabel =
    TRANSPORT_LABELS[server.transport] || server.transport.toUpperCase();
  const transportColor =
    TRANSPORT_COLORS[server.transport] || DEFAULT_TRANSPORT_COLOR;

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
            {server.transport === "stdio" && server.command && (
              <div className="font-mono text-xs bg-stone-50 dark:bg-stone-800 rounded px-2 py-1 truncate">
                <span className="text-stone-500 dark:text-stone-500">$</span>{" "}
                {server.command}
                {server.args &&
                  server.args.length > 0 &&
                  ` ${server.args.join(" ")}`}
              </div>
            )}
            {server.transport !== "stdio" && server.url && (
              <div className="font-mono text-xs bg-stone-50 dark:bg-stone-800 rounded px-2 py-1 truncate">
                {server.url}
              </div>
            )}
          </div>

          {/* Environment variables or headers info */}
          {server.env && Object.keys(server.env).length > 0 && (
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-500">
              {t("mcp.card.envVarsCount", {
                count: Object.keys(server.env).length,
              })}
            </div>
          )}
          {server.headers && Object.keys(server.headers).length > 0 && (
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-500">
              {t("mcp.card.headersCount", {
                count: Object.keys(server.headers).length,
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
    </div>
  );
}
