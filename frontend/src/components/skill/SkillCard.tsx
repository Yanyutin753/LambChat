import { ResourceCardTags } from "../common/ResourceCardTags";
import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  ShoppingBag,
  User,
  Archive,
  Sparkles,
  Upload,
  Pin,
  Star,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { Tooltip } from "../common/Tooltip";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";
import type { SkillResponse } from "../../types";
import { formatDate } from "../../utils/datetime";

interface SkillCardProps {
  skill: SkillResponse;
  onToggle: (name: string) => void;
  onTogglePreference?: (
    skill: SkillResponse,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => void;
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
  onTogglePreference,
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
      selected={selected}
      selectionMode={selectionMode}
      onSelect={onSelect ? () => onSelect(skill.name) : undefined}
      animated
      animationDelay={0}
      bannerLeadingOverlay={
        onTogglePreference ? (
          <>
            <Tooltip content={t("personaPresets.pin", "置顶")}>
              <button
                type="button"
                aria-label={t("personaPresets.pin")}
                aria-pressed={Boolean(skill.is_pinned)}
                className={`pps-card__icon-action ${
                  skill.is_pinned ? "pps-card__icon-action--active-pin" : ""
                }`}
                onClick={(event) => {
                  event.stopPropagation();
                  onTogglePreference(skill, {
                    is_pinned: !skill.is_pinned,
                  });
                }}
              >
                <Pin size={12} />
              </button>
            </Tooltip>
            <Tooltip content={t("personaPresets.favorite", "收藏")}>
              <button
                type="button"
                aria-label={t("personaPresets.favorite")}
                aria-pressed={Boolean(skill.is_favorite)}
                className={`pps-card__icon-action ${
                  skill.is_favorite ? "pps-card__icon-action--active-fav" : ""
                }`}
                onClick={(event) => {
                  event.stopPropagation();
                  onTogglePreference(skill, {
                    is_favorite: !skill.is_favorite,
                  });
                }}
              >
                <Star size={12} />
              </button>
            </Tooltip>
          </>
        ) : undefined
      }
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
          <ResourceCardTags tags={skill.tags} />
        ) : undefined
      }
      meta={
        <div className="flex flex-wrap items-center gap-2 text-12 text-[var(--theme-text-secondary)]">
          <div className="skill-meta-pill">
            <FileText size={13} />
            <span>
              {skill.file_count} {t("marketplace.files")}
            </span>
          </div>
          {skill.updated_at && (
            <div className="skill-meta-pill">
              {t("skills.card.updated")}: {formatDate(skill.updated_at)}
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
      actions={[
        {
          label: t(
            skill.enabled ? "skills.card.disable" : "skills.card.enable",
          ),
          icon: skill.enabled ? (
            <ToggleRight size={16} />
          ) : (
            <ToggleLeft size={16} />
          ),
          onClick: () => onToggle(skill.name),
        },
        ...(onTogglePreference
          ? [
              {
                label: t(
                  skill.is_pinned
                    ? "sidebar.unpinFromTop"
                    : "personaPresets.pin",
                ),
                icon: <Pin size={16} />,
                onClick: () =>
                  onTogglePreference(skill, { is_pinned: !skill.is_pinned }),
              },
              {
                label: t(
                  skill.is_favorite
                    ? "fileLibrary.context.unfavorite"
                    : "personaPresets.favorite",
                ),
                icon: <Star size={16} />,
                onClick: () =>
                  onTogglePreference(skill, {
                    is_favorite: !skill.is_favorite,
                  }),
              },
            ]
          : []),
        {
          label: t("skills.card.edit"),
          icon: <Edit3 size={16} />,
          onClick: () => onEdit(skill),
        },
        ...(skill.source === "manual" && isPublished !== undefined && onPublish
          ? [
              {
                label: t(
                  isPublished
                    ? "skills.card.republish"
                    : "skills.card.publishToMarketplace",
                ),
                icon: <Upload size={16} />,
                onClick: () => onPublish(skill),
              },
            ]
          : []),
        ...(onExportZip
          ? [
              {
                label: t("skills.exportZip"),
                icon: <Archive size={16} />,
                onClick: () => onExportZip(skill.name),
              },
            ]
          : []),
        {
          label: t("skills.card.delete"),
          icon: <Trash2 size={16} />,
          danger: true,
          onClick: () => onDelete(skill.name),
        },
      ]}
      footer={
        <div className="flex items-center gap-1">
          <Tooltip
            content={
              skill.enabled ? t("skills.card.disable") : t("skills.card.enable")
            }
          >
            <button
              aria-label={
                skill.enabled
                  ? t("skills.card.disable")
                  : t("skills.card.enable")
              }
              onClick={(e) => {
                e.stopPropagation();
                onToggle(skill.name);
              }}
              className="scb__action-btn scb__action-btn--ghost"
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
          </Tooltip>
        </div>
      }
    />
  );
}
