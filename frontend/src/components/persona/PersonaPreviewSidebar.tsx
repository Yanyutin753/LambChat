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
import { IconButton } from "../common";
import { MarkdownContent } from "../chat/ChatMessage/MarkdownContent";
import { PersonaAvatarWithLoading } from "./PersonaAvatarWithLoading";
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

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={preset.name}
      icon={
        <PersonaAvatarWithLoading
          key={preset.avatar}
          preset={preset}
          className="flex h-7 w-7 items-center justify-center rounded-lg"
          imgClassName="h-5 w-5 rounded object-cover"
          style={{
            background: `linear-gradient(135deg, ${gradient[0]}, ${gradient[1]})`,
          }}
        />
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
        <div className="flex min-w-0 items-center gap-3">
          <PersonaAvatarWithLoading
            key={preset.avatar}
            preset={preset}
            className="pps-card__avatar !h-14 !w-14 shrink-0"
            imgClassName="pps-card__avatar-img"
            iconSize={28}
          />
          <div className="min-w-0 flex flex-col gap-1 text-13 text-theme-text-secondary">
            <span>
              {preset.scope === "global"
                ? t("personaPresets.official")
                : t("personaPresets.mine")}
            </span>
            {preset.usage_count > 0 && (
              <span className="text-12">
                {preset.usage_count} {t("personaPresets.usageCount")}
              </span>
            )}
          </div>
        </div>

        {/* Description */}
        <div className="min-w-0 [overflow-wrap:anywhere]">
          {preset.description ? (
            <p
              className="text-13 leading-relaxed"
              style={{ color: "var(--theme-text-secondary)" }}
            >
              {preset.description}
            </p>
          ) : (
            <p
              className="text-13"
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
          <div className="es-field">
            <h3 className="es-label flex items-center gap-1.5">
              <Tag size={14} className="shrink-0" />
              {t("personaPresets.tags", "标签")}
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {preset.tags.map((tag) => (
                <span
                  key={tag}
                  className="es-chip max-w-full [overflow-wrap:anywhere]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* System Prompt section */}
        <div className="es-field min-w-0">
          <div className="flex min-w-0 items-center justify-between gap-2">
            <h3 className="es-label min-w-0 flex items-center gap-1.5 [overflow-wrap:anywhere]">
              <FileText size={14} className="shrink-0" />
              {t("personaPresets.systemPrompt", "系统提示词")}
            </h3>
            <div className="flex shrink-0 items-center gap-1">
              <IconButton
                icon={viewSource ? <Eye size={14} /> : <Code2 size={14} />}
                onClick={() => setViewSource(!viewSource)}
                size="sm"
                aria-pressed={viewSource}
                aria-label={
                  viewSource
                    ? t("personaPresets.previewMarkdown")
                    : t("personaPresets.viewSource")
                }
                title={
                  viewSource
                    ? t("personaPresets.previewMarkdown", "预览 Markdown")
                    : t("personaPresets.viewSource", "查看原文")
                }
              />
              <CopyButton text={preset.system_prompt} size={14} />
            </div>
          </div>
          <div
            className="min-w-0 rounded-lg bg-[var(--theme-bg-subtle)]/60 p-3 text-13"
            style={{ color: "var(--theme-text)" }}
          >
            {viewSource ? (
              <pre className="whitespace-pre-wrap [overflow-wrap:anywhere] font-mono text-12 leading-[1.6]">
                {preset.system_prompt}
              </pre>
            ) : (
              <MarkdownContent content={preset.system_prompt} />
            )}
          </div>
        </div>

        {/* Skills section */}
        {preset.skill_names.length > 0 && (
          <div className="es-field">
            <h3 className="es-label flex items-center gap-1.5">
              <Zap size={14} />
              {t("personaPresets.skills", "技能")}
              <span className="ml-auto font-mono text-10 opacity-60">
                {preset.skill_names.length}
              </span>
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {preset.skill_names.map((name) => (
                <span key={name} className="es-chip min-w-0 max-w-full">
                  <Sparkles size={10} className="shrink-0 opacity-50" />
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    {name}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </EditorSidebar>
  );
}
