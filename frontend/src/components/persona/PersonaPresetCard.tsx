import { useTranslation } from "react-i18next";
import { Sparkles, Check, Copy, Pencil, Trash2 } from "lucide-react";
import type { PersonaPreset } from "../../types";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import { isPersonaImageAvatar } from "./personaAvatar";
import { getPersonaPresetCapabilities } from "./personaPresetAccess";
import { getCategoryIcon, nameToGradient } from "../common/cardUtils";

interface PersonaPresetCardProps {
  preset: PersonaPreset;
  selected: boolean;
  activeTag: string | null;
  canWrite: boolean;
  canAdmin: boolean;
  onUse: (preset: PersonaPreset) => void;
  onClear: () => void;
  onCopy: (preset: PersonaPreset) => void;
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
  onEdit,
  onDelete,
  onToggleTag,
}: PersonaPresetCardProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(preset.name);
  const primaryTag = preset.tags[0];
  const CategoryIcon = primaryTag ? getCategoryIcon(primaryTag) : Sparkles;
  const capabilities = getPersonaPresetCapabilities(preset, {
    canWrite,
    canAdmin,
  });

  return (
    <div className="scb group flex h-full flex-col overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm dark:shadow-none">
      {/* Gradient Banner */}
      <div
        className="scb__banner relative h-12 shrink-0"
        style={{
          background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
        }}
      >
        <div className="absolute top-2 right-2 flex gap-1.5">
          {selected && (
            <span className="scb__status-pill scb__status-pill--installed">
              {t("personaPresets.using", "使用中")}
            </span>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="flex flex-1 flex-col p-4 pt-5">
        {/* Title row with avatar or icon */}
        <div className="flex items-start gap-3">
          {isPersonaImageAvatar(preset.avatar) ? (
            <div className="scb__avatar-ring shrink-0">
              <PersonaAvatarImage
                avatar={preset.avatar}
                alt=""
                className="scb__avatar-img"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          ) : (
            <div className="scb__icon-ring shrink-0">
              <PersonaAvatarIcon
                avatar={preset.avatar}
                primaryTag={primaryTag}
                size={20}
                className="text-[var(--theme-primary)]"
              />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h3
              className="truncate text-base font-semibold text-[var(--theme-text)] leading-tight"
              title={preset.name}
            >
              {preset.name}
            </h3>
            <div className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
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
          </div>
        </div>

        {/* Description */}
        <p className="mt-3 text-[13px] leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2 min-h-[3.25em]">
          {preset.description || preset.system_prompt}
        </p>

        {/* Category tag + mini tags */}
        {(primaryTag || preset.tags.length > 1) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {primaryTag && (
              <span className="scb__mini-tag" style={{ cursor: "default" }}>
                <CategoryIcon
                  size={10}
                  className="text-[var(--theme-text-secondary)]"
                />
                {primaryTag}
              </span>
            )}
            {preset.tags.slice(primaryTag ? 1 : 0, 4).map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => onToggleTag(tag)}
                className={`scb__mini-tag ${
                  activeTag === tag ? "scb__mini-tag--active" : ""
                }`}
              >
                {tag}
              </button>
            ))}
            {preset.tags.length > 4 && (
              <span className="scb__mini-tag" style={{ cursor: "default" }}>
                +{preset.tags.length - 4}
              </span>
            )}
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Meta & Actions */}
        <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--theme-border)] pt-3">
          <div className="flex items-center gap-2 text-[11px] text-[var(--theme-text-secondary)]">
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
                <Check size={16} />
              </button>
            ) : (
              <button
                onClick={() => onUse(preset)}
                className="scb__action-btn scb__action-btn--ghost"
                title={t("personaPresets.use", "使用")}
              >
                <Sparkles size={16} />
              </button>
            )}
            {capabilities.canCopy && (
              <button
                onClick={() => onCopy(preset)}
                className="scb__action-btn scb__action-btn--ghost"
                title={t("personaPresets.copy", "复制到我的角色")}
              >
                <Copy size={16} />
              </button>
            )}
            {capabilities.canEdit && (
              <button
                onClick={() => onEdit(preset)}
                className="scb__action-btn scb__action-btn--ghost"
                title={t("personaPresets.edit", "编辑")}
              >
                <Pencil size={16} />
              </button>
            )}
            {capabilities.canDelete && (
              <button
                onClick={() => onDelete(preset)}
                className="scb__action-btn"
                title={t("common.delete", "删除")}
                style={{ color: "#dc2626" }}
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
