import {
  Server,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MCPServerResponse } from "../../types";
import { IconButton } from "../common";
import { nameToGradient } from "../common/cardUtils";

interface MCPServerCardProps {
  server: MCPServerResponse;
  onToggle: (name: string) => void;
  onEdit?: (server: MCPServerResponse) => void;
  onDelete?: (name: string, isSystem: boolean) => void;
  onClick?: () => void;
  toolCount?: number;
}

const TRANSPORT_COLORS: Record<string, string> = {
  sse: "bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:ring-emerald-800/60",
  streamable_http:
    "bg-violet-50 text-violet-600 ring-1 ring-violet-200 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-800/60",
};

const DEFAULT_TRANSPORT_COLOR =
  "bg-stone-100 text-stone-500 ring-1 ring-stone-200 dark:bg-stone-800 dark:text-stone-400 dark:ring-stone-700";

export function MCPServerCard({
  server,
  onToggle,
  onEdit,
  onDelete,
  onClick,
  toolCount,
}: MCPServerCardProps) {
  const { t } = useTranslation();

  const TRANSPORT_LABELS: Record<string, string> = {
    sse: t("mcp.form.transportSse"),
    streamable_http: t("mcp.form.transportHttp"),
  };
  const transportLabel =
    TRANSPORT_LABELS[server.transport] || server.transport.toUpperCase();
  const transportColor =
    TRANSPORT_COLORS[server.transport] || DEFAULT_TRANSPORT_COLOR;

  const gradient = nameToGradient(server.name);

  return (
    <div
      className={`pps-card group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none cursor-pointer transition-all duration-200 ${
        !server.enabled ? "opacity-50 saturate-50" : "hover:shadow-md"
      }`}
      onClick={(e) => {
        if (!(e.target as HTMLElement).closest("button")) {
          onClick?.();
        }
      }}
    >
      <div
        className="pps-card__banner relative h-12 shrink-0"
        style={{
          background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
        }}
      >
        <div className="absolute inset-0 flex items-center justify-end px-2 z-[3]">
          <div className="flex gap-1.5">
            {server.is_internal && (
              <span className="scb__status-pill scb__status-pill--installed">
                {t("mcp.card.internal", "Internal")}
              </span>
            )}
            {server.is_system && !server.is_internal && (
              <span className="scb__status-pill scb__status-pill--installed">
                {t("mcp.card.system")}
              </span>
            )}
            {!server.enabled && (
              <span className="scb__status-pill scb__status-pill--danger">
                {t("mcp.card.disabled")}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-4 pt-5">
        <div className="flex items-start gap-3">
          <div className="scb__icon-ring shrink-0">
            <Server size={16} className="text-stone-500 dark:text-stone-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h3
              className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight"
              title={server.name}
            >
              {server.name}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium tracking-wide ${transportColor}`}
              >
                {transportLabel}
              </span>
              {toolCount !== undefined && toolCount > 0 && (
                <span className="inline-flex items-center gap-1 text-[11px] text-[var(--theme-text-secondary)]">
                  <Wrench size={11} />
                  {toolCount}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-2 text-xs font-mono text-stone-400 dark:text-stone-500 truncate">
          {server.url || ""}
        </div>

        <div className="flex-1" />

        <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
          <div className="flex items-center gap-0.5">
            {server.can_edit && !server.is_internal && onEdit && (
              <IconButton
                aria-label={t("mcp.card.edit")}
                icon={<Edit3 size={14} />}
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(server);
                }}
                className="rounded-lg"
                title={t("mcp.card.edit")}
              />
            )}
            {server.can_edit && !server.is_internal && onDelete && (
              <IconButton
                aria-label={t("mcp.card.delete")}
                icon={<Trash2 size={14} />}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(server.name, server.is_system);
                }}
                className="rounded-lg hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950/30 dark:hover:text-red-400"
                title={t("mcp.card.delete")}
              />
            )}
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle(server.name);
            }}
            className={`pps-card__action ${
              server.enabled
                ? "pps-card__action--active"
                : "pps-card__action--primary"
            }`}
          >
            {server.enabled ? (
              <ToggleRight
                size={13}
                className="text-emerald-500 dark:text-emerald-400"
              />
            ) : (
              <ToggleLeft size={13} />
            )}
            {server.enabled ? t("mcp.card.enable") : t("mcp.card.disable")}
          </button>
        </div>
      </div>
    </div>
  );
}
