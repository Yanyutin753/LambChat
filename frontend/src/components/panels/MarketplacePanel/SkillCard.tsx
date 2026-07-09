import {
  Download,
  FileText,
  Eye,
  RefreshCcw,
  Loader2 as Loader2Icon,
  Pencil,
  MoreHorizontal,
  Sparkles,
  X,
  Zap,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkillBaseCard } from "../../common/SkillBaseCard";
import { getCategoryIcon, nameToGradient } from "../../common/cardUtils";
import type { MarketplaceSkillResponse } from "../../../types";
import { formatDate } from "../../../utils/datetime";

interface SkillCardProps {
  skill: MarketplaceSkillResponse;
  index: number;
  isInstalled: boolean;
  isOwner: boolean;
  canManage: boolean;
  canWrite: boolean;
  installingSkill: string | null;
  userSkillsLoading: boolean;
  selectedTags: string[];
  openMenuName: string | null;
  onInstallClick: (skillName: string) => void;
  onPreview: () => void;
  onToggleTag: (tag: string) => void;
  onOpenMenu: (skillName: string | null) => void;
  onEdit: (skillName: string) => void;
  onActivate: (skillName: string, isActive: boolean) => void;
  onDelete: (skillName: string) => void;
}

export function SkillCard({
  skill,
  index,
  isInstalled,
  isOwner,
  canManage,
  canWrite,
  installingSkill,
  userSkillsLoading,
  selectedTags,
  openMenuName,
  onInstallClick,
  onPreview,
  onToggleTag,
  onOpenMenu,
  onEdit,
  onActivate,
  onDelete,
}: SkillCardProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(skill.skill_name);
  const primaryTag = skill.tags[0];
  const CategoryIcon = primaryTag ? getCategoryIcon(primaryTag) : Sparkles;

  return (
    <SkillBaseCard
      title={skill.skill_name}
      description={skill.description || t("marketplace.noDescription")}
      gradient={gradient}
      icon={<CategoryIcon size={20} className="text-[var(--theme-primary)]" />}
      animated
      animationDelay={index * 60}
      bannerOverlay={
        <>
          {isInstalled && (
            <span className="scb__status-pill scb__status-pill--installed">
              {t("marketplace.installed")}
            </span>
          )}
          {!skill.is_active && (
            <span className="scb__status-pill scb__status-pill--inactive">
              {t("marketplace.inactive")}
            </span>
          )}
        </>
      }
      statusPills={
        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
          {skill.updated_at && <span>{formatDate(skill.updated_at)}</span>}
          {skill.updated_at && skill.created_by_username && (
            <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
          )}
          {skill.created_by_username && (
            <span className="truncate">
              {t("marketplace.publishedBy", {
                username: skill.created_by_username,
              })}
            </span>
          )}
        </div>
      }
      tags={
        primaryTag ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="scb__mini-tag" style={{ cursor: "default" }}>
              <CategoryIcon
                size={10}
                className="text-[var(--theme-text-secondary)]"
              />
              {primaryTag}
            </span>
            {skill.tags.slice(1, 4).map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => onToggleTag(tag)}
                className={`scb__mini-tag ${
                  selectedTags.includes(tag) ? "scb__mini-tag--active" : ""
                }`}
              >
                {tag}
              </button>
            ))}
            {skill.tags.length > 4 && (
              <span className="scb__mini-tag" style={{ cursor: "default" }}>
                +{skill.tags.length - 4}
              </span>
            )}
          </div>
        ) : undefined
      }
      meta={
        <div className="flex items-center justify-between gap-2 text-[11px] text-[var(--theme-text-secondary)]">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1">
              <FileText size={11} />
              {skill.file_count}
            </span>
            <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
            <span>v{skill.version}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPreview();
              }}
              className="scb__action-btn scb__action-btn--ghost"
              title={t("marketplace.preview")}
            >
              <Eye size={16} />
            </button>
            {canWrite &&
              (installingSkill === skill.skill_name ? (
                <button
                  disabled
                  className="scb__action-btn scb__action-btn--loading"
                >
                  <Loader2Icon size={16} className="animate-spin" />
                </button>
              ) : userSkillsLoading ? (
                <span className="inline-flex items-center justify-center w-8 h-8">
                  <Loader2Icon
                    size={16}
                    className="animate-spin text-[var(--theme-text-secondary)]"
                  />
                </span>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onInstallClick(skill.skill_name);
                  }}
                  title={
                    isInstalled
                      ? t("marketplace.update")
                      : t("marketplace.install")
                  }
                  className="scb__action-btn scb__action-btn--ghost"
                >
                  {isInstalled ? (
                    <RefreshCcw size={16} />
                  ) : (
                    <Download size={16} />
                  )}
                </button>
              ))}

            {canManage && (
              <div className="relative" data-mp-menu>
                <button
                  className="scb__action-btn scb__action-btn--ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenMenu(
                      openMenuName === skill.skill_name
                        ? null
                        : skill.skill_name,
                    );
                  }}
                >
                  <MoreHorizontal size={16} />
                </button>
                {openMenuName === skill.skill_name && (
                  <div className="absolute right-0 bottom-full mb-1 z-10 w-36 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] py-1 shadow-lg">
                    {isOwner && (
                      <button
                        onClick={() => {
                          onOpenMenu(null);
                          onEdit(skill.skill_name);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-bg-subtle)]"
                      >
                        <Pencil size={12} />
                        {t("common.edit")}
                      </button>
                    )}
                    <button
                      onClick={() => {
                        onOpenMenu(null);
                        onActivate(skill.skill_name, !skill.is_active);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-bg-subtle)]"
                    >
                      {skill.is_active ? (
                        <>
                          <X size={12} />
                          {t("marketplace.inactive")}
                        </>
                      ) : (
                        <>
                          <Zap size={12} />
                          {t("marketplace.active")}
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => {
                        onOpenMenu(null);
                        onDelete(skill.skill_name);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                    >
                      <Trash2 size={12} />
                      {t("common.delete")}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      }
    />
  );
}
