import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  ShoppingBag,
  User,
  Tag,
  Archive,
  Sparkles,
  Upload,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";
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
  const gradient = nameToGradient(skill.name);
  const primaryTag = skill.tags[0];
  const CategoryIcon = primaryTag ? getCategoryIcon(primaryTag) : Sparkles;
  const sourceLabel = t(`skillSelector.sources.${skill.source}`, skill.source);

  return (
    <SkillBaseCard
      title={skill.name}
      description={skill.description || t("skills.noDescription")}
      descriptionMaxLines={2}
      gradient={gradient}
      icon={<CategoryIcon size={20} className="text-[var(--theme-primary)]" />}
      muted={!skill.enabled}
      selected={selected}
      selectionMode={selectionMode}
      onSelect={onSelect ? () => onSelect(skill.name) : undefined}
      animated
      animationDelay={0}
      bannerOverlay={
        <>
          {isPublished && (
            <span className="scb__status-pill scb__status-pill--published">
              {t("skills.card.published")}
            </span>
          )}
          {!skill.enabled && (
            <span className="scb__status-pill scb__status-pill--disabled">
              {t("skills.card.disabled")}
            </span>
          )}
        </>
      }
      statusPills={
        <span className="skill-status-pill">
          {SOURCE_ICONS[skill.source]}
          {sourceLabel}
        </span>
      }
      tags={
        skill.tags.length > 0 ? (
          <div className="flex flex-wrap gap-2">
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
        ) : undefined
      }
      meta={
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
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
      }
      footer={
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle(skill.name);
            }}
            className="scb__action-btn scb__action-btn--ghost"
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
            className="scb__action-btn scb__action-btn--ghost"
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
                className="scb__action-btn scb__action-btn--ghost"
                title={
                  isPublished
                    ? t("skills.card.republish")
                    : t("skills.card.publishToMarketplace")
                }
              >
                <Upload
                  size={13}
                  className={
                    isPublished
                      ? "text-green-600 dark:text-green-500"
                      : undefined
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
              className="scb__action-btn scb__action-btn--ghost"
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
            className="scb__action-btn text-[var(--theme-text-secondary)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
            title={t("skills.card.delete")}
          >
            <Trash2 size={14} />
          </button>
        </div>
      }
    />
  );
}
