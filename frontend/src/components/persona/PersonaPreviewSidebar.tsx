import { Sparkles, Copy, Tag, FileText, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EditorSidebar } from "../common/EditorSidebar";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import { isPersonaImageAvatar } from "./personaAvatar";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import type { PersonaPreset } from "../../types";

interface PersonaPreviewSidebarProps {
  preset: PersonaPreset;
  isSelected: boolean;
  isMutating: boolean;
  onClose: () => void;
  onUsePreset: (preset: PersonaPreset) => void;
  onCopyPreset: (preset: PersonaPreset) => void;
}

export function PersonaPreviewSidebar({
  preset,
  isSelected,
  isMutating,
  onClose,
  onUsePreset,
  onCopyPreset,
}: PersonaPreviewSidebarProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(preset.name);
  const primaryTag = preset.tags[0];

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={preset.name}
      subtitle={`${
        preset.scope === "global"
          ? t("personaPresets.official", "官方")
          : t("personaPresets.mine", "我的")
      }${
        preset.usage_count > 0
          ? ` · ${preset.usage_count}${t(
              "personaPresets.usageCount",
              "次使用",
            )}`
          : ""
      }`}
      icon={
        <div
          className="flex h-7 w-7 items-center justify-center rounded-lg"
          style={{
            background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]})`,
          }}
        >
          {isPersonaImageAvatar(preset.avatar) ? (
            <PersonaAvatarImage
              avatar={preset.avatar}
              alt=""
              className="h-5 w-5 rounded object-cover"
            />
          ) : (
            <PersonaAvatarIcon
              avatar={preset.avatar}
              primaryTag={primaryTag}
              size={14}
              className="text-white"
            />
          )}
        </div>
      }
      footer={
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isMutating || isSelected}
            onClick={() => onUsePreset(preset)}
            className={`pps-card__action flex-1 justify-center py-2.5 text-xs font-semibold ${
              isSelected
                ? "pps-card__action--active"
                : "pps-card__action--primary"
            }`}
          >
            <Sparkles size={14} />
            {isSelected
              ? t("personaPresets.using", "使用中")
              : t("personaPresets.use", "使用")}
          </button>
          {preset.scope === "global" && (
            <button
              type="button"
              disabled={isMutating}
              onClick={() => onCopyPreset(preset)}
              className="pps-card__action pps-card__action--ghost flex-1 justify-center py-2.5 text-xs font-semibold"
            >
              <Copy size={14} />
              {t("personaPresets.copy", "复制")}
            </button>
          )}
        </div>
      }
    >
      <div className="es-form">
        {/* Hero banner with avatar overlay */}
        <div className="relative -mx-5 -mt-2 sm:-mx-6 sm:-mt-2">
          <div
            className="h-28"
            style={{
              background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
            }}
          />
          <div className="absolute -bottom-7 left-5 sm:left-6 flex items-end gap-3">
            <div className="pps-card__avatar relative z-10 !w-14 !h-14 !rounded-2xl !border-[2.5px] border-white dark:border-[var(--theme-bg-card)] shadow-lg">
              {isPersonaImageAvatar(preset.avatar) ? (
                <PersonaAvatarImage
                  avatar={preset.avatar}
                  alt=""
                  className="pps-card__avatar-img"
                />
              ) : (
                <PersonaAvatarIcon
                  avatar={preset.avatar}
                  primaryTag={primaryTag}
                  size={28}
                  className="pps-card__avatar-icon"
                />
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="pt-9">
          {preset.description ? (
            <p
              className="text-[13px] leading-relaxed"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {preset.description}
            </p>
          ) : (
            <p
              className="text-[13px] italic"
              style={{
                color:
                  "var(--theme-text-tertiary, var(--theme-text-secondary))",
              }}
            >
              {t("personaPresets.descriptionPlaceholder", "暂无简介")}
            </p>
          )}
        </div>

        {/* Tags section */}
        {preset.tags.length > 0 && (
          <div className="es-section">
            <div className="es-section-title">
              <Tag />
              {t("personaPresets.tags", "标签")}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {preset.tags.map((tag) => (
                <span key={tag} className="es-chip">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* System Prompt section */}
        <div className="es-section">
          <div className="es-section-title">
            <FileText />
            {t("personaPresets.systemPrompt", "系统提示词")}
          </div>
          <div
            className="rounded-lg bg-[var(--theme-bg)]/60 p-3 text-[13px] leading-[1.7] whitespace-pre-wrap break-words max-h-72 overflow-y-auto font-mono text-[12px]"
            style={{ color: "var(--theme-text)" }}
          >
            {preset.system_prompt}
          </div>
        </div>

        {/* Skills section */}
        {preset.skill_names.length > 0 && (
          <div className="es-section">
            <div className="es-section-title">
              <Zap />
              {t("personaPresets.skills", "技能")}
              <span className="ml-auto font-mono text-[10px] opacity-60">
                {preset.skill_names.length}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {preset.skill_names.map((name) => (
                <span key={name} className="es-chip">
                  <Sparkles size={10} className="opacity-50" />
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </EditorSidebar>
  );
}
