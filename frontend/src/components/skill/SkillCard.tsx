import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  Package,
  ShoppingBag,
  User,
  Globe,
  Tag,
  Archive,
  Check,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillResponse } from "../../types";

interface SkillCardProps {
  skill: SkillResponse;
  onToggle: (name: string) => void;
  onEdit: (skill: SkillResponse) => void;
  onDelete: (name: string) => void;
  onExportZip?: (name: string) => void;
  onPublish?: (skill: SkillResponse) => void;
  isPublished?: boolean;
  selected?: boolean;
  onSelect?: (name: string) => void;
  selectionMode?: boolean;
}

const SOURCE_COLORS: Record<string, string> = {
  builtin: "skill-status-pill",
  marketplace: "skill-status-pill skill-status-pill--active",
  manual: "skill-status-pill",
};

const DEFAULT_SOURCE_COLOR = "skill-status-pill";

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  builtin: <Package size={10} />,
  marketplace: <ShoppingBag size={10} />,
  manual: <User size={10} />,
};

export function SkillCard({
  skill,
  onToggle,
  onEdit,
  onDelete,
  onExportZip,
  onPublish,
  isPublished,
  selected = false,
  onSelect,
  selectionMode = false,
}: SkillCardProps) {
  const { t } = useTranslation();
  const sourceLabel = t(`skillSelector.sources.${skill.source}`, skill.source);
  const sourceColor = SOURCE_COLORS[skill.source] || DEFAULT_SOURCE_COLOR;

  return (
    <div
      className={`skill-surface-card skill-card group relative flex h-full flex-col rounded-[1.6rem] p-4 sm:p-5 ${
        !skill.enabled ? "skill-surface-card--muted opacity-80" : ""
      } ${selected ? "ring-2 ring-[var(--theme-primary)]" : ""}`}
      onClick={
        selectionMode && onSelect ? () => onSelect(skill.name) : undefined
      }
    >
      {/* Selection checkbox */}
      {selectionMode && onSelect && (
        <div
          className={`absolute top-3 left-3 z-10 flex h-5 w-5 items-center justify-center rounded-md border-2 transition-colors cursor-pointer ${
            selected
              ? "border-[var(--theme-primary)] bg-[var(--theme-primary)] text-white"
              : "border-[var(--theme-border)] bg-white/80 dark:bg-stone-800/80 opacity-0 group-hover:opacity-100"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(skill.name);
          }}
        >
          {selected && <Check size={12} />}
        </div>
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="truncate text-lg font-semibold text-[var(--theme-text)]">
              {skill.name}
            </h4>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${sourceColor}`}
            >
              {SOURCE_ICONS[skill.source]}
              {sourceLabel}
            </span>
            {isPublished && (
              <span className="skill-status-pill skill-status-pill--published">
                <Globe size={10} />
                {t("skills.card.published")}
              </span>
            )}
            {!skill.enabled && (
              <span className="skill-status-pill skill-status-pill--disabled">
                {t("skills.card.disabled")}
              </span>
            )}
          </div>

          <p className="mt-2 min-h-[3.75rem] text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-3">
            {skill.description || t("skills.noDescription")}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
        <div className="skill-meta-pill">
          <FileText size={13} />
          <span>
            {skill.file_count} {t("marketplace.files")}
          </span>
        </div>
        {skill.updated_at && (
          <div className="skill-meta-pill">
            {t("skills.card.updated")}:{" "}
            {new Date(skill.updated_at).toLocaleDateString()}
          </div>
        )}
        {skill.published_marketplace_name &&
          skill.published_marketplace_name !== skill.name && (
            <div className="skill-meta-pill truncate">
              {t("skills.card.storeName", {
                name: skill.published_marketplace_name,
              })}
            </div>
          )}
      </div>

      {skill.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {skill.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="skill-tag-chip skill-tag-chip--active">
              <Tag size={11} />
              {tag}
            </span>
          ))}
          {skill.tags.length > 4 && (
            <span className="skill-tag-chip">+{skill.tags.length - 4}</span>
          )}
        </div>
      )}

      <div className="skill-card-actions mt-auto flex flex-wrap items-center gap-2 border-t border-[var(--theme-border)] pt-4">
        <button
          onClick={() => onToggle(skill.name)}
          className="skill-card-action inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
          title={
            skill.enabled ? t("skills.card.disable") : t("skills.card.enable")
          }
        >
          {skill.enabled ? (
            <ToggleRight
              size={16}
              className="text-green-600 dark:text-green-500"
            />
          ) : (
            <ToggleLeft size={16} />
          )}
          <span className="hidden sm:inline">
            {skill.enabled ? t("skills.card.disable") : t("skills.card.enable")}
          </span>
        </button>

        <button
          onClick={() => onEdit(skill)}
          className="skill-card-action inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
          title={t("skills.card.edit")}
        >
          <Edit3 size={14} />
          <span className="hidden sm:inline">{t("skills.card.edit")}</span>
        </button>

        {skill.source === "manual" &&
          isPublished !== undefined &&
          onPublish && (
            <button
              onClick={() => onPublish(skill)}
              className="skill-card-action inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
              title={
                isPublished
                  ? t("skills.card.republish")
                  : t("skills.card.publishToMarketplace")
              }
            >
              <Globe
                size={14}
                className={
                  isPublished
                    ? "text-green-600 dark:text-green-500"
                    : "text-stone-400 dark:text-stone-500"
                }
              />
              <span className="hidden sm:inline">
                {isPublished
                  ? t("skills.card.republish")
                  : t("skills.card.publishToMarketplace")}
              </span>
            </button>
          )}

        {onExportZip && (
          <button
            onClick={() => onExportZip(skill.name)}
            className="skill-card-action inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
            title={t("skills.exportZip")}
          >
            <Archive size={14} />
            <span className="hidden sm:inline">{t("skills.exportZip")}</span>
          </button>
        )}

        <div className="ml-auto" />

        <button
          onClick={() => onDelete(skill.name)}
          className="skill-card-danger inline-flex h-9 w-9 items-center justify-center rounded-xl text-[var(--theme-text-secondary)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
          title={t("skills.card.delete")}
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}
