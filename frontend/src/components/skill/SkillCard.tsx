import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  ShoppingBag,
  User,
  Globe,
  Tag,
  Archive,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Checkbox } from "../common/Checkbox";
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
  marketplace: "skill-status-pill skill-status-pill--active",
  manual: "skill-status-pill",
};

const DEFAULT_SOURCE_COLOR = "skill-status-pill";

const SOURCE_ICONS: Record<string, React.ReactNode> = {
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
      className={`skill-surface-card skill-card group relative flex h-full flex-col rounded-[1.6rem] p-4 sm:p-5 transition-all duration-200 ${
        !skill.enabled ? "skill-surface-card--muted opacity-80" : ""
      } ${
        selected
          ? "ring-2 ring-[var(--theme-primary)] animate-[select-glow_2s_ease-in-out]"
          : ""
      } ${selectionMode ? "cursor-pointer" : ""}`}
      onClick={
        selectionMode && onSelect ? () => onSelect(skill.name) : undefined
      }
    >
      {/* Selection checkbox - top right */}
      {selectionMode && onSelect && (
        <div
          className={`absolute top-3 right-3 z-10 transition-all duration-200 ${
            selected ? "scale-110" : "scale-90 group-hover:scale-100"
          }`}
        >
          <Checkbox
            size="lg"
            checked={selected}
            onChange={() => onSelect(skill.name)}
            className="shadow-sm opacity-0 group-hover:opacity-100"
          />
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

      <div className="skill-card-actions mt-auto flex items-center gap-1 border-t border-[var(--theme-border)] pt-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle(skill.name);
          }}
          className="skill-card-action inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
          title={
            skill.enabled ? t("skills.card.disable") : t("skills.card.enable")
          }
        >
          {skill.enabled ? (
            <ToggleRight
              size={15}
              className="text-green-600 dark:text-green-500"
            />
          ) : (
            <ToggleLeft size={15} />
          )}
        </button>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onEdit(skill);
          }}
          className="skill-card-action inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
          title={t("skills.card.edit")}
        >
          <Edit3 size={13} />
        </button>

        {skill.source === "manual" &&
          isPublished !== undefined &&
          onPublish && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPublish(skill);
              }}
              className="skill-card-action inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
              title={
                isPublished
                  ? t("skills.card.republish")
                  : t("skills.card.publishToMarketplace")
              }
            >
              <Globe
                size={13}
                className={
                  isPublished ? "text-green-600 dark:text-green-500" : undefined
                }
              />
            </button>
          )}

        {onExportZip && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onExportZip(skill.name);
            }}
            className="skill-card-action inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg)] text-[var(--theme-text)] transition-colors hover:bg-[var(--theme-primary-light)]"
            title={t("skills.exportZip")}
          >
            <Archive size={13} />
          </button>
        )}

        <div className="ml-auto" />

        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(skill.name);
          }}
          className="skill-card-danger inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--theme-text-secondary)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
          title={t("skills.card.delete")}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
