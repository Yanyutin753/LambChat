import { InteractiveIcon } from "../common/InteractiveIcon";
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
import { SkillBaseCard } from "../common/SkillBaseCard";
import { Tooltip } from "../common/Tooltip";
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
  sse: "text-theme-success dark:text-emerald-400",
  streamable_http: "text-violet-600 dark:text-violet-400",
};

const DEFAULT_TRANSPORT_COLOR = "text-theme-text-secondary";

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
    <SkillBaseCard
      title={server.name}
      gradient={gradient}
      className="pps-card cursor-pointer"
      onClick={onClick ? () => onClick() : undefined}
      icon={<Server size={20} className="text-theme-text-secondary" />}
      statusPills={
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <span
            className={`text-11 font-medium tracking-wide ${transportColor}`}
          >
            {transportLabel}
          </span>
          {toolCount !== undefined && toolCount > 0 && (
            <span className="inline-flex items-center gap-1 text-11 text-[var(--theme-text-secondary)]">
              <Wrench size={11} />
              {toolCount}
            </span>
          )}
        </div>
      }
      bannerOverlay={
        <>
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
        </>
      }
      extraContent={
        server.url && (
          <div
            className="text-12 font-mono text-theme-text-tertiary truncate"
            title={server.url}
          >
            {server.url}
          </div>
        )
      }
      actions={[
        ...(server.can_edit && !server.is_internal && onEdit
          ? [
              {
                label: t("mcp.card.edit"),
                icon: <Edit3 size={16} />,
                onClick: () => onEdit(server),
              },
            ]
          : []),
        ...(server.can_edit && !server.is_internal && onDelete
          ? [
              {
                label: t("mcp.card.delete"),
                icon: <Trash2 size={16} />,
                danger: true,
                onClick: () => onDelete(server.name, server.is_system),
              },
            ]
          : []),
      ]}
      footer={
        <div className="flex items-center justify-end gap-2">
          <Tooltip
            content={t(server.enabled ? "mcp.card.disable" : "mcp.card.enable")}
          >
            <button
              type="button"
              role="switch"
              aria-checked={server.enabled}
              aria-label={
                server.enabled ? t("mcp.card.disable") : t("mcp.card.enable")
              }
              onClick={(e) => {
                e.stopPropagation();
                onToggle(server.name);
              }}
              className="scb__action-btn scb__action-btn--ghost"
            >
              {server.enabled ? (
                <InteractiveIcon>
                  <ToggleRight
                    size={16}
                    className="text-theme-success dark:text-green-500"
                  />
                </InteractiveIcon>
              ) : (
                <InteractiveIcon>
                  <ToggleLeft size={16} />
                </InteractiveIcon>
              )}
            </button>
          </Tooltip>
        </div>
      }
    />
  );
}
