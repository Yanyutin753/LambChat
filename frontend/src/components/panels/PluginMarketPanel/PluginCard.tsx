import {
  Bot,
  Download,
  Eye,
  Loader2 as Loader2Icon,
  MoreHorizontal,
  PackageMinus,
  Puzzle,
  RefreshCcw,
  Server,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkillBaseCard } from "../../common/SkillBaseCard";
import { nameToGradient } from "../../common/cardUtils";
import type { PluginResponse } from "../../../types";

interface PluginCardProps {
  plugin: PluginResponse;
  index: number;
  canAdmin: boolean;
  installingPlugin: string | null;
  openMenuName: string | null;
  onInstallClick: (pluginName: string) => void;
  onUninstall: (pluginName: string) => void;
  onPreview: () => void;
  onOpenMenu: (pluginName: string | null) => void;
  onActivate: (pluginName: string, isActive: boolean) => void;
  onDelete: (pluginName: string) => void;
}

export function PluginCard({
  plugin,
  index,
  canAdmin,
  installingPlugin,
  openMenuName,
  onInstallClick,
  onUninstall,
  onPreview,
  onOpenMenu,
  onActivate,
  onDelete,
}: PluginCardProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(plugin.name);
  const isBusy = installingPlugin === plugin.name;
  const menuOpen = openMenuName === plugin.name;

  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <SkillBaseCard
      title={plugin.display_name || plugin.name}
      description={plugin.description || t("plugins.noDescription")}
      gradient={gradient}
      icon={<Puzzle size={20} className="text-[var(--theme-primary)]" />}
      animated
      animationDelay={index * 60}
      bannerOverlay={
        <>
          {plugin.installed && (
            <span className="scb__status-pill scb__status-pill--installed">
              {t("plugins.installed")}
            </span>
          )}
          {plugin.status !== "active" && (
            <span className="scb__status-pill scb__status-pill--inactive">
              {plugin.status === "draft"
                ? t("plugins.draft")
                : t("plugins.inactive")}
            </span>
          )}
        </>
      }
      meta={
        <div className="flex items-center justify-between gap-2 text-11 text-[var(--theme-text-secondary)]">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1">
              <Sparkles size={11} />
              {t("plugins.capabilitySkills", { count: plugin.skills.length })}
            </span>
            {plugin.mcp_servers.length > 0 && (
              <>
                <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                <span className="inline-flex items-center gap-1">
                  <Server size={11} />
                  {t("plugins.capabilityMcp", { count: plugin.mcp_servers.length })}
                </span>
              </>
            )}
            {plugin.persona && (
              <>
                <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                <span className="inline-flex items-center gap-1">
                  <Bot size={11} />
                  {t("plugins.capabilityPersona")}
                </span>
              </>
            )}
          </div>
          <span>v{plugin.version}</span>
        </div>
      }
      tags={
        plugin.tags.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {plugin.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="scb__mini-tag"
                style={{ cursor: "default" }}
              >
                {tag}
              </span>
            ))}
          </div>
        ) : undefined
      }
      footer={
        <div className="flex items-center gap-1.5">
          <button
            onClick={(e) => {
              stop(e);
              onPreview();
            }}
            className="scb__action-btn scb__action-btn--ghost"
            title={t("plugins.preview")}
            aria-label={t("plugins.preview")}
          >
            <Eye size={16} />
          </button>
          {isBusy ? (
            <button disabled className="scb__action-btn scb__action-btn--loading">
              <Loader2Icon size={16} className="animate-spin" />
            </button>
          ) : (
            <button
              onClick={(e) => {
                stop(e);
                onInstallClick(plugin.name);
              }}
              title={
                plugin.installed
                  ? t("plugins.update")
                  : t("plugins.install")
              }
              aria-label={
                plugin.installed
                  ? t("plugins.update")
                  : t("plugins.install")
              }
              className="scb__action-btn scb__action-btn--ghost"
            >
              {plugin.installed ? (
                <RefreshCcw size={16} />
              ) : (
                <Download size={16} />
              )}
            </button>
          )}
          {plugin.installed && (
            <button
              onClick={(e) => {
                stop(e);
                onUninstall(plugin.name);
              }}
              className="scb__action-btn scb__action-btn--ghost"
              title={t("plugins.uninstall")}
              aria-label={t("plugins.uninstall")}
            >
              <PackageMinus size={16} />
            </button>
          )}
          {canAdmin && (
            <div className="relative" data-plugin-menu>
              <button
                className="scb__action-btn scb__action-btn--ghost"
                onClick={(e) => {
                  stop(e);
                  onOpenMenu(menuOpen ? null : plugin.name);
                }}
                aria-label={t("common.more")}
                aria-expanded={menuOpen}
              >
                <MoreHorizontal size={16} />
              </button>
              {menuOpen && (
                <div className="absolute right-0 bottom-full mb-1 z-10 w-40 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] py-1 shadow-lg">
                  <button
                    onClick={() => {
                      onOpenMenu(null);
                      onActivate(plugin.name, plugin.status !== "active");
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-12 text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-bg-subtle)]"
                  >
                    <Sparkles size={12} />
                    {plugin.status === "active"
                      ? t("plugins.deactivate")
                      : t("plugins.activate")}
                  </button>
                  <button
                    onClick={() => {
                      onOpenMenu(null);
                      onDelete(plugin.name);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-12 text-red-500 transition-colors hover:bg-[var(--theme-bg-subtle)]"
                  >
                    <Trash2 size={12} />
                    {t("common.delete")}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      }
    />
  );
}
