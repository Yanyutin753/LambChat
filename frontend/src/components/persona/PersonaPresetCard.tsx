import { InteractiveIcon } from "../common/InteractiveIcon";
import { ResourceCardTags } from "../common/ResourceCardTags";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { useTranslation } from "react-i18next";
import { Sparkles, Check, Copy, Pencil, Trash2, Pin, Star } from "lucide-react";
import type { PersonaPreset } from "../../types";
import { AgentAvatar } from "../common/AgentAvatar";
import { getPersonaPresetCapabilities } from "./personaPresetAccess";
import { nameToGradient } from "../common/cardUtils";

interface PersonaPresetCardProps {
  preset: PersonaPreset;
  selected: boolean;
  activeTag: string | null;
  canWrite: boolean;
  canAdmin: boolean;
  onUse: (preset: PersonaPreset) => void;
  onClear: () => void;
  onCopy: (preset: PersonaPreset) => void;
  onTogglePreference?: (
    preset: PersonaPreset,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => void;
  onEdit: (preset: PersonaPreset) => void;
  onDelete: (preset: PersonaPreset) => void;
  onToggleTag: (tag: string) => void;
}

export function PersonaPresetCard({
  preset,
  selected,
  activeTag,
  canWrite,
  canAdmin,
  onUse,
  onClear,
  onCopy,
  onTogglePreference,
  onEdit,
  onDelete,
  onToggleTag,
}: PersonaPresetCardProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(preset.name);
  const capabilities = getPersonaPresetCapabilities(preset, {
    canWrite,
    canAdmin,
  });

  return (
    <SkillBaseCard
      title={preset.name}
      description={preset.description || preset.system_prompt}
      gradient={gradient}
      iconClassName=""
      icon={
        <AgentAvatar
          avatar={preset.avatar}
          seed={preset.id || preset.name}
          size={36}
          iconSize={20}
          className="rounded-lg"
        />
      }
      statusPills={
        <>
          <div className="mt-1.5 flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
            <span>
              {preset.scope === "global"
                ? t("personaPresets.official", "官方")
                : t("personaPresets.mine", "我的")}
            </span>
            {preset.scope === "global" && (
              <>
                <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                <span>
                  {preset.status === "published"
                    ? t("personaPresets.published", "已发布")
                    : preset.status === "archived"
                      ? t("personaPresets.archived", "已归档")
                      : t("personaPresets.draft", "草稿")}
                </span>
              </>
            )}
            {preset.usage_count > 0 && (
              <>
                <span className="inline-block h-1 w-1 rounded-full bg-[var(--theme-border)]" />
                <span>
                  {preset.usage_count}
                  {t("personaPresets.usageCount", "次使用")}
                </span>
              </>
            )}
          </div>
        </>
      }
      bannerLeadingOverlay={
        onTogglePreference ? (
          <div className="flex gap-1.5">
            <button
              type="button"
              className={`pps-card__icon-action ${
                preset.is_pinned ? "pps-card__icon-action--active-pin" : ""
              }`}
              title={t("personaPresets.pin", "置顶")}
              onClick={() =>
                onTogglePreference(preset, { is_pinned: !preset.is_pinned })
              }
            >
              <InteractiveIcon>
                <Pin size={12} />
              </InteractiveIcon>
            </button>
            <button
              type="button"
              className={`pps-card__icon-action ${
                preset.is_favorite ? "pps-card__icon-action--active-fav" : ""
              }`}
              title={t("personaPresets.favorite", "收藏")}
              onClick={() =>
                onTogglePreference(preset, {
                  is_favorite: !preset.is_favorite,
                })
              }
            >
              <InteractiveIcon>
                <Star size={12} />
              </InteractiveIcon>
            </button>
          </div>
        ) : undefined
      }
      bannerOverlay={
        selected && (
          <span className="scb__status-pill scb__status-pill--installed">
            {t("personaPresets.using")}
          </span>
        )
      }
      tags={
        preset.tags.length > 0 ? (
          <ResourceCardTags
            tags={preset.tags}
            activeTag={activeTag}
            onToggle={onToggleTag}
          />
        ) : undefined
      }
      actions={[
        {
          label: t(selected ? "personaPresets.clear" : "personaPresets.use"),
          icon: selected ? <Check size={16} /> : <Sparkles size={16} />,
          onClick: () => (selected ? onClear() : onUse(preset)),
        },
        ...(onTogglePreference
          ? [
              {
                label: t(
                  preset.is_pinned
                    ? "sidebar.unpinFromTop"
                    : "personaPresets.pin",
                ),
                icon: <Pin size={16} />,
                onClick: () =>
                  onTogglePreference(preset, { is_pinned: !preset.is_pinned }),
              },
              {
                label: t(
                  preset.is_favorite
                    ? "fileLibrary.context.unfavorite"
                    : "personaPresets.favorite",
                ),
                icon: <Star size={16} />,
                onClick: () =>
                  onTogglePreference(preset, {
                    is_favorite: !preset.is_favorite,
                  }),
              },
            ]
          : []),
        ...(capabilities.canCopy
          ? [
              {
                label: t("personaPresets.copy"),
                icon: <Copy size={16} />,
                onClick: () => onCopy(preset),
              },
            ]
          : []),
        ...(capabilities.canEdit
          ? [
              {
                label: t("personaPresets.edit"),
                icon: <Pencil size={16} />,
                onClick: () => onEdit(preset),
              },
            ]
          : []),
        ...(capabilities.canDelete
          ? [
              {
                label: t("common.delete"),
                icon: <Trash2 size={16} />,
                danger: true,
                onClick: () => onDelete(preset),
              },
            ]
          : []),
      ]}
      footer={
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-11 text-[var(--theme-text-secondary)]">
            {preset.skill_names.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <Sparkles size={11} />
                {preset.skill_names.length}{" "}
                {t("personaPresets.skillsCount", "skills")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {selected ? (
              <button
                onClick={onClear}
                className="scb__action-btn scb__action-btn--ghost"
                title={t("personaPresets.clear", "清除使用")}
              >
                <InteractiveIcon>
                  <Check size={16} />
                </InteractiveIcon>
              </button>
            ) : (
              <button
                onClick={() => onUse(preset)}
                className="scb__action-btn scb__action-btn--ghost"
                title={t("personaPresets.use", "使用")}
              >
                <InteractiveIcon>
                  <Sparkles size={16} />
                </InteractiveIcon>
              </button>
            )}
          </div>
        </div>
      }
    />
  );
}
