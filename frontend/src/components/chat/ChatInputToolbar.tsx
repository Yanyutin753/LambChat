import { useRef, useCallback, useState, useEffect } from "react";
import { ArrowUp, Cloud, Monitor, Settings2, Square, Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FeatureMenu, type FeaturePanel } from "../selectors/FeatureMenu";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import { isEmojiAvatar, getEmojiAvatarUrl } from "../persona/personaAvatar";
import { teamApi } from "../../services/api/team";
import type { AgentOption, FileCategory } from "../../types";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";
import { ToolbarChip } from "./ToolbarChip";
import { AgentIcon } from "../agent/AgentIcon";
import { subscribeTeamsChanged } from "../../hooks/teamEvents";
import { RunModePopover } from "./RunModePopover";
import { ComposerUsageChip } from "./ComposerUsageChip";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import {
  resolveSandboxPresentation,
  SANDBOX_AGENT_OPTION_KEY,
  SANDBOX_LOCAL_VALUE,
} from "./sandboxOption";

export interface ChatInputToolbarProps {
  activePanel: FeaturePanel;
  onActivePanelChange: (panel: FeaturePanel) => void;
  canSend: boolean;
  sendBlocked?: boolean;
  isLoading: boolean;
  /** 运行中是否有草稿文本：有则按钮发送插话（steer），无则保持停止 */
  hasDraft?: boolean;
  onSteer?: () => void;
  canSubmit: boolean;
  hasUploadingAttachment: boolean;
  hasFailedAttachment?: boolean;
  hasInvalidAttachment?: boolean;
  enabledToolsCount: number;
  totalToolsCount: number;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  hasPersonaSelector: boolean;
  personaName?: string | null;
  totalPersonaCount?: number;
  hasAgentSelector: boolean;
  agentName?: string;
  agentIcon?: string;
  hasThinkingOption: boolean;
  thinkingLabel?: string;
  uploadCategories: FileCategory[];
  uploadFiles: (files: FileList | File[], category?: FileCategory) => void;
  selectedPersonaName?: string | null;
  personaAvatar: { avatar?: string; primaryTag: string } | null;
  onClearPersonaPreset?: () => void;
  currentAgent?: string;
  selectedTeamId?: string | null;
  onSelectTeam?: (teamId: string | null) => void;
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
  return categories.map((category) => FILE_CATEGORY_ACCEPT[category]).join(",");
}

export function ChatInputToolbar({
  activePanel,
  onActivePanelChange,
  canSend,
  sendBlocked = false,
  isLoading,
  hasDraft = false,
  onSteer,
  canSubmit,
  hasUploadingAttachment,
  hasFailedAttachment = false,
  hasInvalidAttachment = false,
  enabledToolsCount,
  totalToolsCount,
  enabledSkillsCount,
  totalSkillsCount,
  hasPersonaSelector,
  personaName,
  totalPersonaCount,
  hasAgentSelector,
  agentName,
  agentIcon,
  hasThinkingOption,
  thinkingLabel,
  uploadCategories,
  uploadFiles,
  selectedPersonaName,
  personaAvatar,
  onClearPersonaPreset,
  currentAgent,
  selectedTeamId,
  onSelectTeam,
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
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const [totalTeamCount, setTotalTeamCount] = useState(0);
  const [modePopoverOpen, setModePopoverOpen] = useState(false);
  // Auto-reopen the RunModePopover after a full-screen selector modal closes,
  // but only if this popover was the one that triggered the modal.
  const popoverTriggeredPanel = useRef(false);
  useEffect(() => {
    if (activePanel && modePopoverOpen) {
      popoverTriggeredPanel.current = true;
    }
  }, [activePanel, modePopoverOpen]);
  const prevActivePanel = useRef(activePanel);
  useEffect(() => {
    if (
      prevActivePanel.current &&
      !activePanel &&
      popoverTriggeredPanel.current
    ) {
      setModePopoverOpen(true);
      popoverTriggeredPanel.current = false;
    }
    prevActivePanel.current = activePanel;
  }, [activePanel]);

  useEffect(() => {
    let cancelled = false;
    const loadTeams = () => {
      teamApi
        .list(0, 50)
        .then((res) => {
          if (cancelled) return;
          setTotalTeamCount(res.total);
          if (selectedTeamId) {
            const team = res.teams.find((t) => t.id === selectedTeamId);
            setSelectedTeam(team ?? null);
          }
        })
        .catch(() => {});
    };
    loadTeams();
    const unsubscribe = subscribeTeamsChanged(() => {
      loadTeams();
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [selectedTeamId]);

  useEffect(() => {
    if (!selectedTeamId) {
      setSelectedTeam(null);
    }
  }, [selectedTeamId]);

  const booleanAgentOptions = agentOptions
    ? Object.fromEntries(
        Object.entries(agentOptions).filter(
          ([, option]) => option.type === "boolean",
        ),
      )
    : undefined;

  // 沙箱选择器入口（RunModePopover 设置组）：会话存在 sandbox 选项且有切换回调时显示
  const { has: hasSandboxOption, label: sandboxLabel } =
    resolveSandboxPresentation(agentOptions, agentOptionValues, t);
  const showSandboxEntry = hasSandboxOption && !!onToggleAgentOption;

  // 沙箱 chip：拉出设置组的一等入口（与 Agent/Persona chip 同级，单击直达面板）。
  // 状态点仅本地档需要 daemon 健康；云端档不挂状态轮询，避免常驻空转。
  const sandboxTier =
    agentOptionValues[SANDBOX_AGENT_OPTION_KEY] ??
    agentOptions?.[SANDBOX_AGENT_OPTION_KEY]?.default;
  const sandboxChipLocal = sandboxTier === SANDBOX_LOCAL_VALUE;
  const { online: sandboxOnline } = useSandboxStatus({
    enabled: showSandboxEntry && sandboxChipLocal,
  });
  const sandboxChipTitle = sandboxLabel
    ? `${t("agentOptions.sandbox.label")} · ${sandboxLabel}`
    : t("agentOptions.sandbox.label");

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
  const selectedTeamName = selectedTeam?.name ?? null;

  return (
    <div className="flex max-w-full flex-nowrap justify-between gap-1 px-2 pb-3 pt-3 mx-0.5">
      {/* 左行不设横向滚动：滚动容器会在手机端裁切 chip（视觉上与右簇重叠），
          超宽时由 chip 的 shrink + truncate 优雅降级 */}
      <div className="flex min-h-10 min-w-0 flex-1 items-center gap-0.5 sm:gap-1.5">
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
          hasPersonaSelector={hasPersonaSelector && currentAgent !== "team"}
          personaName={personaName}
          totalPersonaCount={totalPersonaCount}
          hasTeamSelector={currentAgent === "team" && !!onSelectTeam}
          totalTeamCount={totalTeamCount}
          uploadCategories={uploadCategories}
          onUploadFiles={handleUploadFiles}
        />
        {hasAgentSelector &&
          !selectedPersonaName &&
          !(currentAgent === "team" && onSelectTeam && selectedTeamId) && (
            <ToolbarChip
              icon={<AgentIcon icon={agentIcon || "Bot"} size={18} />}
              label={agentName || t(`agents.${currentAgent}.name`) || ""}
              onClick={() => onActivePanelChange("agent")}
            />
          )}
        {selectedPersonaName && currentAgent !== "team" && (
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
        {currentAgent === "team" && onSelectTeam && selectedTeamId && (
          <ToolbarChip
            icon={
              <TeamAvatar
                avatar={selectedTeam?.avatar}
                fallbackAvatar={
                  selectedTeam ? getTeamFallbackAvatar(selectedTeam) : null
                }
                fallbackTag={
                  selectedTeam ? getTeamFallbackTag(selectedTeam) : ""
                }
                label={selectedTeamName ?? t("chat.teamSelected")}
                className="team-toolbar-avatar transition-opacity group-hover:opacity-0"
                iconSize={18}
              />
            }
            label={selectedTeamName ?? t("chat.teamSelected")}
            onClick={() => onActivePanelChange("team")}
            onClear={() => onSelectTeam?.(null)}
          />
        )}
      </div>

      {/* 右簇与左行同轴居中：避免贴底对齐造成发送键相对左行图标错位。
          簇内间距整体收紧（沙箱/用量/模式/发送四枚图标）。 */}
      <div className="flex shrink-0 items-center gap-1 sm:gap-1.5 self-center">
        {showSandboxEntry && (
          <ToolbarChip
            icon={
              // 手机端档位文字隐藏，档位靠图标区分：云端=云图标，本地=显示器图标
              sandboxChipLocal ? <Monitor size={18} /> : <Cloud size={18} />
            }
            label={sandboxLabel || ""}
            title={sandboxChipTitle}
            labelClassName="hidden sm:inline"
            onClick={() => onActivePanelChange("sandbox")}
            trailing={
              sandboxChipLocal ? (
                // daemon 在线状态点：绿=在线，灰=离线（与 RunModePopover 沙箱条目同源）；
                // 手机端只留纯图标，点在 sm 起显示
                <span
                  data-sandbox-status-dot
                  title={
                    sandboxOnline
                      ? t("profile.localSandbox.statusOnline")
                      : t("profile.localSandbox.statusOffline")
                  }
                  className="hidden sm:inline h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{
                    background: sandboxOnline ? "#22c55e" : "#a8a29e",
                  }}
                />
              ) : undefined
            }
          />
        )}

        {/* Today's usage — amount chip with usage card */}
        <ComposerUsageChip />

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
          title={t("mode.title", "Run Mode")}
        >
          <Settings2 size={16} />
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
          onOpenThinkingPanel={() => onActivePanelChange("thinking")}
          hasSandboxOption={showSandboxEntry}
          sandboxLabel={sandboxLabel}
          onOpenSandboxPanel={() => onActivePanelChange("sandbox")}
          onOpenMachinePanel={
            showSandboxEntry ? () => onActivePanelChange("machine") : undefined
          }
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
        ) : sendBlocked ? (
          <button
            type="submit"
            disabled
            className="flex items-center justify-center rounded-full h-9 w-9 transition-all duration-300"
            style={{
              backgroundColor: "transparent",
              color: "var(--theme-text-secondary)",
            }}
            title={t("chat.waitingForHuman", "等待人工确认后才能发送")}
          >
            <ArrowUp size={18} />
          </button>
        ) : isLoading &&
          hasDraft &&
          onSteer &&
          !hasUploadingAttachment &&
          !hasFailedAttachment &&
          !hasInvalidAttachment ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onSteer();
            }}
            className="flex items-center justify-center rounded-full h-9 w-9 transition-all duration-300 hover:scale-105 active:scale-95"
            style={{
              backgroundColor: "var(--theme-primary)",
              border: "1px solid var(--theme-primary)",
              color: "var(--theme-bg-card)",
            }}
            title={t("chat.steer", "发送插话（当前步骤后送达）")}
          >
            <ArrowUp size={18} />
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
            disabled={sendBlocked || !canSubmit}
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
