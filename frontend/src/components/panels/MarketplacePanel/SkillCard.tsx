import {
  Download,
  FileText,
  AlertTriangle,
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
import { useNavigate } from "react-router-dom";
import type { MarketplaceSkillResponse } from "../../../types";
import { getCategoryIcon, nameToGradient } from "./constants";

interface SkillCardProps {
  skill: MarketplaceSkillResponse;
  index: number;
  isInstalled: boolean;
  hasLocalManualConflict: boolean;
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
  hasLocalManualConflict,
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
  const navigate = useNavigate();
  const gradient = nameToGradient(skill.skill_name);
  const primaryTag = skill.tags[0];
  const CategoryIcon = primaryTag ? getCategoryIcon(primaryTag) : Sparkles;

  return (
    <div
      key={skill.skill_name}
      className="mp-card group flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none dark:border dark:border-[var(--theme-border)]"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Gradient Banner */}
      <div
        className="mp-card__banner relative h-12 shrink-0"
        style={{
          background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
        }}
      >
        {/* Status pills overlay on banner */}
        <div className="absolute top-2 right-2 flex gap-1.5">
          {isInstalled && (
            <span className="mp-card__status-pill mp-card__status-pill--installed">
              {t("marketplace.installed")}
            </span>
          )}
          {!skill.is_active && (
            <span className="mp-card__status-pill mp-card__status-pill--inactive">
              {t("marketplace.inactive")}
            </span>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="flex flex-1 flex-col p-4 pt-5">
        {/* Title row with icon */}
        <div className="flex items-start gap-3">
          <div className="mp-card__icon-ring shrink-0">
            <CategoryIcon size={20} className="text-[var(--theme-primary)]" />
          </div>
          <div className="min-w-0 flex-1">
            <h3
              className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight"
              title={skill.skill_name}
            >
              {skill.skill_name}
            </h3>
            <div className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
              {skill.updated_at && (
                <span>
                  {new Date(skill.updated_at).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "2-digit",
                    day: "2-digit",
                  })}
                </span>
              )}
              {skill.created_by_username && (
                <>
                  <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                  <span className="truncate">
                    {t("marketplace.publishedBy", {
                      username: skill.created_by_username,
                    })}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
          {skill.description || t("marketplace.noDescription")}
        </p>

        {/* Category tag */}
        {primaryTag && (
          <div className="mt-3 flex items-center gap-1.5">
            <CategoryIcon
              size={12}
              className="text-[var(--theme-text-secondary)]"
            />
            <span className="mp-card__category-tag">{primaryTag}</span>
          </div>
        )}

        {/* Conflict warning */}
        {hasLocalManualConflict && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/90 px-2.5 py-2 text-[11px] text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
            <div className="flex items-start gap-1.5">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>{t("marketplace.installNameConflict")}</span>
            </div>
            <button
              type="button"
              onClick={() =>
                navigate("/skills", {
                  state: { prefillSkillSearch: skill.skill_name },
                })
              }
              className="mt-1.5 inline-flex items-center gap-1 font-medium text-amber-900 underline decoration-amber-400 underline-offset-2 transition-colors hover:text-amber-950 dark:text-amber-200 dark:decoration-amber-700 dark:hover:text-amber-100"
            >
              <Pencil size={11} />
              <span>{t("marketplace.viewInMySkills")}</span>
            </button>
          </div>
        )}

        {/* Tags */}
        {skill.tags.length > 1 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {skill.tags.slice(1, 4).map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => onToggleTag(tag)}
                className={`mp-card__mini-tag ${
                  selectedTags.includes(tag) ? "mp-card__mini-tag--active" : ""
                }`}
              >
                {tag}
              </button>
            ))}
            {skill.tags.length > 4 && (
              <span className="mp-card__mini-tag">
                +{skill.tags.length - 4}
              </span>
            )}
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Meta & Actions */}
        <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
          <div className="flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
            <span className="inline-flex items-center gap-1">
              <FileText size={11} />
              {skill.file_count}
            </span>
            <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
            <span>v{skill.version}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={onPreview}
              className="mp-card__action-btn mp-card__action-btn--ghost"
              title={t("marketplace.preview")}
            >
              <Eye size={16} />
            </button>
            {canWrite &&
              (installingSkill === skill.skill_name ? (
                <button
                  disabled
                  className="mp-card__action-btn mp-card__action-btn--loading"
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
                  onClick={() => onInstallClick(skill.skill_name)}
                  disabled={hasLocalManualConflict}
                  title={
                    hasLocalManualConflict
                      ? t("marketplace.installNameConflict")
                      : isInstalled
                        ? t("marketplace.update")
                        : t("marketplace.install")
                  }
                  className={`mp-card__action-btn ${
                    hasLocalManualConflict
                      ? "mp-card__action-btn--disabled"
                      : "mp-card__action-btn--ghost"
                  }`}
                >
                  {hasLocalManualConflict ? (
                    <AlertTriangle size={16} />
                  ) : isInstalled ? (
                    <RefreshCcw size={16} />
                  ) : (
                    <Download size={16} />
                  )}
                </button>
              ))}

            {/* Admin dropdown */}
            {canManage && (
              <div className="relative" data-mp-menu>
                <button
                  className="mp-card__action-btn mp-card__action-btn--ghost"
                  onClick={() =>
                    onOpenMenu(
                      openMenuName === skill.skill_name
                        ? null
                        : skill.skill_name,
                    )
                  }
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
                        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
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
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
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
      </div>
    </div>
  );
}
