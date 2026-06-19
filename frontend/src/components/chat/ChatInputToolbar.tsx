import { Fragment, useRef, useCallback, useState } from "react";
import { ArrowUp, Square, Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FeatureMenu, type FeaturePanel } from "../selectors/FeatureMenu";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import { isEmojiAvatar, getEmojiAvatarUrl } from "../persona/personaAvatar";
import type { AgentOption, FileCategory } from "../../types";
import type { UploadLimits } from "../../hooks/useFileUpload";
import { ToolbarChip } from "./ToolbarChip";
import { AgentIcon } from "../agent/AgentIcon";
import type { CoreChatInputOptionContribution } from "../../extensions/coreContributions";
import { CHAT_INPUT_SELECTED_RENDERERS } from "./chatInputSelectedRenderers";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";

export interface ChatInputToolbarProps {
  activePanel: FeaturePanel;
  onActivePanelChange: (panel: FeaturePanel) => void;
  canSend: boolean;
  isLoading: boolean;
  canSubmit: boolean;
  hasUploadingAttachment: boolean;
  enabledToolsCount: number;
  totalToolsCount: number;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  hasPersonaSelector: boolean;
  personaName?: string | null;
  hasAgentSelector: boolean;
  agentName?: string;
  agentIcon?: string;
  hasThinkingOption: boolean;
  thinkingLabel?: string;
  thinkingLevel?: string;
  uploadCategories: FileCategory[];
  uploadLimits: UploadLimits | null;
  uploadFiles: (files: FileList | File[], category?: FileCategory) => void;
  selectedPersonaName?: string | null;
  personaAvatar: { avatar?: string; primaryTag: string } | null;
  onClearPersonaPreset?: () => void;
  currentAgent?: string;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  chatInputOptions?: readonly CoreChatInputOptionContribution[];
  agentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
  onStopClick: () => void;
  onNoPermissionClick: () => void;
}

const FILE_CATEGORY_ACCEPT: Record<FileCategory, string> = {
  image:
    "image/*,.heic,.heif,.avif,.webp,.bmp,.ico,.tiff,.tif,.svg,.psd,.eps,.tga,.pcx,.jxl,.dng",
  video:
    "video/*,.mkv,.flv,.wmv,.avi,.mov,.m4v,.mpeg,.mpg,.3gp,.3g2,.ogv,.ts,.mts,.m2ts,.vob,.divx,.rm,.rmvb,.f4v",
  audio:
    "audio/*,.m4a,.mp3,.wav,.ogg,.aac,.flac,.wma,.opus,.aiff,.caf,.amr,.mid,.midi,.ape,.alac,.wv",
  document:
    ".pdf,.doc,.docx,.dot,.dotx,.docm,.xls,.xlsx,.xlsm,.csv,.xlt,.ods,.ppt,.pptx,.potx,.ppsx,.pptm,.odp,.txt,.md,.csv,.rtf,.odt,.epub,.dxf,.dwg,.log,.json,.xml,.html,.htm,.yaml,.yml,.toml,.ini,.cfg,.tex,.diff,.patch,.py,.js,.ts,.jsx,.tsx,.vue,.svelte,.go,.rs,.rb,.php,.java,.c,.cpp,.h,.cs,.swift,.kt,.scala,.dart,.lua,.r,.pl,.sql,.sh,.bash,.zsh,.fish,.ps1,.bat,.cmd,.properties,.gradle,.cmake,.env,.graphql,.proto,.zip,.rar,.7z,.tar,.gz,.bz2,.xz,.tgz",
};

export function ChatInputToolbar({
  activePanel,
  onActivePanelChange,
  canSend,
  isLoading,
  canSubmit,
  hasUploadingAttachment,
  enabledToolsCount,
  totalToolsCount,
  enabledSkillsCount,
  totalSkillsCount,
  hasPersonaSelector,
  personaName,
  hasAgentSelector,
  agentName,
  agentIcon,
  hasThinkingOption,
  thinkingLabel,
  thinkingLevel,
  uploadCategories,
  uploadLimits,
  uploadFiles,
  selectedPersonaName,
  personaAvatar,
  onClearPersonaPreset,
  currentAgent,
  pluginOptionValues,
  onPluginOptionChange,
  chatInputOptions = [],
  agentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
  onStopClick,
  onNoPermissionClick,
}: ChatInputToolbarProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFileCategory, setSelectedFileCategory] =
    useState<FileCategory | null>(null);

  const booleanAgentOptions = agentOptions
    ? Object.fromEntries(
        Object.entries(agentOptions).filter(
          ([, option]) => option.type === "boolean",
        ),
      )
    : undefined;

  const handleFileCategorySelect = useCallback((category: FileCategory) => {
    setSelectedFileCategory(category);
    if (fileInputRef.current) {
      fileInputRef.current.accept = FILE_CATEGORY_ACCEPT[category];
      fileInputRef.current.click();
    }
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      uploadFiles(files, selectedFileCategory || undefined);
      e.target.value = "";
    },
    [uploadFiles, selectedFileCategory],
  );
  const selectedPluginOptions = chatInputOptions.filter(
    (option) => option.selectedRenderer,
  );
  const selectedPluginRendererProps = (option: CoreChatInputOptionContribution) => ({
    option,
    activePanel,
    onActivePanelChange,
    pluginOptionValues,
    onPluginOptionChange,
    fallbackLabel: t("chat.teamSelected"),
  });
  const hasSelectedPluginOption = selectedPluginOptions.some((option) => {
    const rendererId = option.selectedRenderer;
    const entry = rendererId ? CHAT_INPUT_SELECTED_RENDERERS[rendererId] : null;
    return Boolean(entry?.hasSelection(selectedPluginRendererProps(option)));
  });
  const corePersonaSelectorSuppressed = chatInputOptions.some(
    (option) => option.suppressesCorePersonaSelector,
  );
  const corePersonaSelectorVisible =
    hasPersonaSelector && !corePersonaSelectorSuppressed;

  return (
    <div className="flex max-w-full flex-nowrap justify-between gap-2 px-2 pb-3 pt-3 mx-0.5">
      <div className="flex min-h-10 min-w-0 flex-1 items-center gap-1 overflow-x-auto no-scrollbar sm:gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileInputChange}
        />
        <FeatureMenu
          activePanel={activePanel}
          onOpen={onActivePanelChange}
          enabledToolsCount={enabledToolsCount}
          totalToolsCount={totalToolsCount}
          enabledSkillsCount={enabledSkillsCount}
          totalSkillsCount={totalSkillsCount}
          hasPersonaSelector={corePersonaSelectorVisible}
          personaName={personaName}
          pluginOptions={chatInputOptions}
          hasAgentSelector={hasAgentSelector}
          agentName={agentName}
          hasThinkingOption={hasThinkingOption}
          uploadCategories={uploadCategories}
          uploadLimits={uploadLimits}
          onFileCategorySelect={handleFileCategorySelect}
          thinkingLabel={thinkingLabel}
          thinkingLevel={thinkingLevel}
          booleanAgentOptions={booleanAgentOptions}
          agentOptionValues={agentOptionValues}
          onToggleAgentOption={onToggleAgentOption}
        />
        {hasAgentSelector &&
          !selectedPersonaName &&
          !hasSelectedPluginOption && (
            <ToolbarChip
              icon={<AgentIcon icon={agentIcon || "Bot"} size={18} />}
              label={t(`agents.${currentAgent}.name`) || agentName || ""}
              onClick={() => onActivePanelChange("agent")}
            />
          )}
        {selectedPersonaName && corePersonaSelectorVisible && (
          <ToolbarChip
            icon={
              personaAvatar?.avatar &&
              (personaAvatar.avatar.startsWith("http") ||
                personaAvatar.avatar.startsWith("/") ||
                isEmojiAvatar(personaAvatar.avatar)) ? (
                <PersonaAvatarImage
                  avatar={
                    isEmojiAvatar(personaAvatar.avatar)
                      ? getEmojiAvatarUrl(personaAvatar.avatar)
                      : personaAvatar.avatar
                  }
                  alt=""
                  className="w-[18px] h-[18px] rounded-full object-cover group-hover:opacity-0 transition-opacity"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <PersonaAvatarIcon
                  avatar={personaAvatar?.avatar}
                  primaryTag={personaAvatar?.primaryTag ?? ""}
                  size={18}
                  className="transition-transform duration-200 group-hover:opacity-0"
                />
              )
            }
            label={selectedPersonaName}
            onClick={() => onActivePanelChange("persona")}
            onClear={onClearPersonaPreset}
          />
        )}
        {selectedPluginOptions.map((option) => {
          const rendererId = option.selectedRenderer;
          const entry = rendererId ? CHAT_INPUT_SELECTED_RENDERERS[rendererId] : null;
          if (!entry) return null;
          const rendered = entry.render({
            ...selectedPluginRendererProps(option),
            option,
          });
          return rendered ? <Fragment key={option.id}>{rendered}</Fragment> : null;
        })}
      </div>

      <div className="flex shrink-0 items-center gap-1.5 self-end">
        {!canSend ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onNoPermissionClick();
            }}
            className="flex items-center justify-center rounded-full p-2 cursor-pointer transition-all duration-200 hover:scale-105"
            style={{
              backgroundColor: "var(--theme-primary-light)",
              color: "var(--theme-text-secondary)",
            }}
            title={t("chat.noPermission")}
          >
            <Lock size={18} />
          </button>
        ) : isLoading ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onStopClick();
            }}
            className="chat-tool-btn-active flex items-center justify-center rounded-full p-2 transition-all duration-300 hover:scale-105 active:scale-95"
            style={{
              borderColor: "color-mix(in srgb, #fbbf24 40%, transparent)",
              background: "color-mix(in srgb, #fbbf24 10%, transparent)",
              color: "#fbbf24",
            }}
            title={t("chat.stop")}
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSubmit}
            className={`flex items-center justify-center rounded-full p-2 transition-all duration-300`}
            style={
              canSubmit
                ? {
                    backgroundColor: "var(--theme-primary)",
                    border: "1px solid var(--theme-primary)",
                    color: "var(--theme-bg, #fff)",
                  }
                : {
                    backgroundColor: "transparent",
                    border: "1px solid var(--theme-border)",
                    color: "var(--theme-text-secondary)",
                  }
            }
            title={
              hasUploadingAttachment
                ? t("chat.waitingForUpload", "请等待文件上传完成")
                : t("chat.send")
            }
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
