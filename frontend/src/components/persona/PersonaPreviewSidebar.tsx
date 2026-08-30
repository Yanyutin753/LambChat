import { useState } from "react";
import {
  Sparkles,
  Copy,
  Tag,
  FileText,
  Zap,
  Loader2,
  Eye,
  Code2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { EditorSidebar } from "../common/EditorSidebar";
import { CopyButton } from "../common/CopyButton";
import { MarkdownContent } from "../chat/ChatMessage/MarkdownContent";
import { PersonaAvatarIcon, PersonaAvatarImage } from "./PersonaAvatarIcon";
import {
  isPersonaImageAvatar,
  isEmojiAvatar,
  getEmojiAvatarUrl,
} from "./personaAvatar";
import { nameToGradient } from "../panels/MarketplacePanel/constants";
import type { PersonaPreset } from "../../types";

interface PersonaPreviewSidebarProps {
  preset: PersonaPreset;
  isSelected: boolean;
  isMutating: boolean;
  isUsingPreset: boolean;
  onClose: () => void;
  onUsePreset: (preset: PersonaPreset) => Promise<void>;
  onCopyPreset: (preset: PersonaPreset) => void;
}

export function PersonaPreviewSidebar({
  preset,
  isSelected,
  isMutating,
  isUsingPreset,
  onClose,
  onUsePreset,
  onCopyPreset,
}: PersonaPreviewSidebarProps) {
  const { t } = useTranslation();
  const [viewSource, setViewSource] = useState(false);
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
          {isPersonaImageAvatar(preset.avatar) ||
          isEmojiAvatar(preset.avatar) ? (
            <PersonaAvatarImage
              avatar={
                isEmojiAvatar(preset.avatar)
                  ? getEmojiAvatarUrl(preset.avatar)
                  : preset.avatar
              }
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
            disabled={isMutating || isSelected || isUsingPreset}
            aria-busy={isUsingPreset}
            onClick={() => onUsePreset(preset)}
            className={`pps-card__action flex-1 ${
              isSelected
                ? "pps-card__action--active"
                : "pps-card__action--primary"
            } ${isUsingPreset ? "pps-card__action--loading" : ""}`}
          >
            {isUsingPreset ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            {isUsingPreset
              ? t("personaPresets.applying", "使用中...")
              : isSelected
                ? t("personaPresets.using", "使用中")
                : t("personaPresets.use", "使用")}
          </button>
          {preset.scope === "global" && (
            <button
              type="button"
              disabled={isMutating}
              onClick={() => onCopyPreset(preset)}
              className="pps-card__action pps-card__action--ghost flex-1"
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
              {isPersonaImageAvatar(preset.avatar) ||
              isEmojiAvatar(preset.avatar) ? (
                <PersonaAvatarImage
                  avatar={
                    isEmojiAvatar(preset.avatar)
                      ? getEmojiAvatarUrl(preset.avatar)
                      : preset.avatar
                  }
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
              className="text-13 leading-relaxed"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {preset.description}
            </p>
          ) : (
            <p
              className="text-13 italic"
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
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={() => setViewSource(!viewSource)}
                className="rounded-md p-1 transition-colors hover:bg-[var(--theme-bg)]/80"
                style={{ color: "var(--theme-text-secondary)" }}
                title={
                  viewSource
                    ? t("personaPresets.previewMarkdown", "预览 Markdown")
                    : t("personaPresets.viewSource", "查看原文")
                }
              >
                {viewSource ? <Eye size={14} /> : <Code2 size={14} />}
              </button>
              <CopyButton
                text={preset.system_prompt}
                size={14}
                className="rounded-md p-1 transition-colors hover:bg-[var(--theme-bg)]/80"
              />
            </div>
          </div>
          <div
            className="rounded-lg bg-[var(--theme-bg)]/60 p-2 overflow-y-auto max-h-[40rem] text-13"
            style={{ color: "var(--theme-text)" }}
          >
            {viewSource ? (
              <pre className="font-mono text-12 leading-[1.6]">
                {preset.system_prompt}
              </pre>
            ) : (
              <MarkdownContent content={preset.system_prompt} />
            )}
          </div>
        </div>

        {/* Skills section */}
        {preset.skill_names.length > 0 && (
          <div className="es-section">
            <div className="es-section-title">
              <Zap />
              {t("personaPresets.skills", "技能")}
              <span className="ml-auto font-mono text-10 opacity-60">
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
