import { useRef, useCallback, useState } from "react";
import { ArrowUp, Square, Lock, Settings2 } from "lucide-react";
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
import { RunModePopover } from "./RunModePopover";

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
  // Run mode
  autoModeEnabled?: boolean;
  goalModeEnabled?: boolean;
  onToggleAutoMode?: (enabled: boolean) => void;
  onToggleGoalMode?: (enabled: boolean) => void;
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
const FILE_ACCEPT_ALL = Object.values(FILE_CATEGORY_ACCEPT).join(",");

function getFileAccept(categories: FileCategory[]): string {
  if (categories.length === 0) return FILE_ACCEPT_ALL;
  return categories
    .map((category) => FILE_CATEGORY_ACCEPT[category])
    .filter(Boolean)
    .join(",");
}

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
  autoModeEnabled = false,
  goalModeEnabled = false,
  onToggleAutoMode,
  onToggleGoalMode,
}: ChatInputToolbarProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [modePopoverOpen, setModePopoverOpen] = useState(false);

  const hasActiveMode = autoModeEnabled || goalModeEnabled;

  const booleanAgentOptions = agentOptions
    ? Object.fromEntries(
        Object.entries(agentOptions).filter(
          ([, option]) => option.type === "boolean",
        ),
      )
    : undefined;

  const handleUploadFiles = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.accept = getFileAccept(uploadCategories);
      fileInputRef.current.click();
    }
  }, [uploadCategories]);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      uploadFiles(files);
      e.target.value = "";
    },
    [uploadFiles],
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
          uploadCategories={uploadCategories}
          onUploadFiles={handleUploadFiles}
          thinkingLabel={thinkingLabel}
          thinkingLevel={thinkingLevel}
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
          const SelectedRenderer = entry.Component;
          return (
            <SelectedRenderer
              key={option.id}
              {...selectedPluginRendererProps(option)}
              option={option}
            />
          );
        })}
      </div>

      <div className="flex shrink-0 items-center gap-3 self-end">
        {/* Mode labels — desktop only (sm:) */}
        {autoModeEnabled && (
          <button
            type="button"
            onClick={() => onToggleAutoMode?.(false)}
            className="hidden sm:inline-flex items-center gap-1 shrink-0 cursor-pointer rounded-full h-9 px-2.5 text-[11px] font-medium transition-colors duration-200"
            style={{
              color: "var(--theme-text-secondary)",
              background: "var(--theme-bg-card)",
              border: "1px solid var(--theme-border)",
            }}
            title={t("mode.auto", "Auto Mode")}
          >
            {t("mode.auto", "Auto")}
          </button>
        )}
        {goalModeEnabled && (
          <button
            type="button"
            onClick={() => onToggleGoalMode?.(false)}
            className="hidden sm:inline-flex items-center gap-1 shrink-0 cursor-pointer rounded-full h-9 px-2.5 text-[11px] font-medium transition-colors duration-200"
            style={{
              color: "var(--theme-text-secondary)",
              background: "var(--theme-bg-card)",
              border: "1px solid var(--theme-border)",
            }}
            title={t("mode.goal", "Goal Mode")}
          >
            {t("mode.goal", "Goal")}
          </button>
        )}

        {/* Settings / Run Mode button */}
        <button
          type="button"
          data-run-mode-trigger
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setModePopoverOpen((v) => !v);
          }}
          className="chat-tool-btn group shrink-0 relative"
          style={{
            color: hasActiveMode
              ? "var(--theme-text-secondary)"
              : "var(--theme-text-tertiary)",
          }}
          title={t("mode.title", "Run Mode")}
        >
          <Settings2 size={16} />
          {/* Status dot when modes are active */}
          {hasActiveMode && (
            <span
              className="absolute -top-0 -right-0.5"
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--theme-text)",
              }}
            />
          )}
        </button>

        <RunModePopover
          open={modePopoverOpen}
          onClose={() => setModePopoverOpen(false)}
          autoModeEnabled={autoModeEnabled}
          goalModeEnabled={goalModeEnabled}
          onToggleAutoMode={onToggleAutoMode ?? (() => {})}
          onToggleGoalMode={onToggleGoalMode ?? (() => {})}
          hasAgentSelector={hasAgentSelector}
          agentName={agentName}
          onOpenAgentPanel={() => onActivePanelChange("agent")}
          hasThinkingOption={hasThinkingOption}
          thinkingLabel={thinkingLabel}
          thinkingLevel={thinkingLevel}
          onOpenThinkingPanel={() => onActivePanelChange("thinking")}
          booleanAgentOptions={booleanAgentOptions}
          agentOptionValues={agentOptionValues}
          onToggleAgentOption={onToggleAgentOption}
        />

        {!canSend ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onNoPermissionClick();
            }}
            className="flex items-center justify-center rounded-full h-9 w-9 cursor-pointer transition-all duration-200 hover:scale-105"
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
            className="chat-tool-btn-active flex items-center justify-center rounded-full h-9 w-9 transition-all duration-300 hover:scale-105 active:scale-95"
            style={{
              borderColor:
                "color-mix(in srgb, var(--theme-primary) 40%, transparent)",
              background:
                "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
              color: "var(--theme-primary)",
            }}
            title={t("chat.stop")}
          >
            <Square size={16} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSubmit}
            className={`flex items-center justify-center rounded-full h-9 w-9 transition-all duration-300`}
            style={
              canSubmit
                ? {
                    backgroundColor: "var(--theme-primary)",
                    border: "1px solid var(--theme-primary)",
                    color: "var(--theme-bg-card)",
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
