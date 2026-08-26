import { useState, useEffect } from "react";
import { teamApi } from "../../../services/api/team";
import { subscribeTeamsChanged } from "../../../hooks/teamEvents";
import { getTeamFallbackAvatar } from "../../team/teamAvatarUtils";
import type { Team } from "../../../types/team";
import type {
  Message,
  PendingApproval,
  ToolState,
  SkillResponse,
  SkillSource,
  ToolCategory,
  AgentOption,
  AgentInfo,
  MessageAttachment,
  ConnectionStatus,
  PersonaPreset,
  PersonaPresetSnapshot,
} from "../../../types";
import type {
  ActiveGoalSpec,
  ChatSubmissionCallbacks,
} from "../../../hooks/useAgent/types";
import type { RevealPreviewRequest } from "../../chat/ChatMessage/items/revealPreviewData";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

function useCurrentTeam(currentAgent: string, selectedTeamId: string | null) {
  const [currentTeam, setCurrentTeam] = useState<Team | null>(null);

  useEffect(() => {
    if (currentAgent !== "team" || !selectedTeamId) {
      setCurrentTeam(null);
      return;
    }

    let cancelled = false;
    const loadTeam = () => {
      teamApi
        .get(selectedTeamId)
        .then((team) => {
          if (!cancelled) setCurrentTeam(team);
        })
        .catch(() => {
          if (!cancelled) setCurrentTeam(null);
        });
    };
    loadTeam();
    const unsubscribe = subscribeTeamsChanged((detail) => {
      if (!detail.teamId || detail.teamId === selectedTeamId) {
        loadTeam();
      }
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [currentAgent, selectedTeamId]);

  return currentTeam;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveChatAssistantIdentity({
  currentAgent,
  currentPersonaAvatar,
  currentTeam,
  selectedPersonaName,
  agentDisplayName,
}: {
  currentAgent: string;
  currentPersonaAvatar: string | null;
  currentTeam: Team | null;
  selectedPersonaName: string | null;
  agentDisplayName?: string | null;
}) {
  if (currentAgent === "team") {
    const fallbackAvatar = currentTeam
      ? getTeamFallbackAvatar(currentTeam)
      : null;
    return {
      avatar: currentTeam?.avatar ?? fallbackAvatar,
      name: currentTeam?.name ?? null,
    };
  }

  const agentNameFallback =
    typeof agentDisplayName === "string" && agentDisplayName.trim()
      ? agentDisplayName
      : null;

  return {
    avatar: currentPersonaAvatar,
    name: selectedPersonaName ?? agentNameFallback,
  };
}

// ---------------------------------------------------------------------------
// Props interface
// ---------------------------------------------------------------------------

export interface ChatViewProps {
  messages: Message[];
  sessionId: string | null;
  currentRunId: string | null;
  isLoading: boolean;
  isLoadingHistory: boolean;
  historyLoadGeneration: number;
  /** 历史分页：是否还有更早的轮次可加载 */
  hasMoreHistoryTraces?: boolean;
  /** 正在加载更早一页历史 */
  isLoadingOlderHistory?: boolean;
  /** 触发加载更早一页历史（滚动到顶部时自动触发） */
  onLoadOlderHistory?: () => void | Promise<void>;
  connectionStatus?: ConnectionStatus;
  canSendMessage: boolean;
  tools: ToolState[];
  onToggleTool: (name: string) => void;
  onToggleCategory: (category: ToolCategory, enabled: boolean) => void;
  onToggleAll: (enabled: boolean) => void;
  toolsLoading: boolean;
  enabledToolsCount: number;
  totalToolsCount: number;
  skills: SkillResponse[];
  onToggleSkill: (name: string) => Promise<boolean>;
  onToggleSkillCategory: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAllSkills: (enabled: boolean) => Promise<boolean>;
  skillsLoading: boolean;
  pendingSkillNames: string[];
  skillsMutating: boolean;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  enableSkills: boolean;
  personaPresets: PersonaPreset[];
  personaPresetsTotal: number;
  hasMorePersonaPresets: boolean;
  isLoadingMorePersonaPresets: boolean;
  onLoadMorePersonaPresets: () => void;
  personaPresetsPage: number;
  onPersonaPresetsPageChange: (page: number) => void;
  onPersonaPresetsSearchChange: (query: string) => void;
  onPersonaPresetsTagChange: (tag: string | null) => void;
  selectedPersonaPresetId: string | null;
  selectedPersonaName: string | null;
  selectedPersonaSnapshot: PersonaPresetSnapshot | null;
  personaSkillsControlled: boolean;
  personaPresetsLoading: boolean;
  personaPresetsMutating: boolean;
  onUsePersonaPreset: (
    preset: PersonaPreset,
  ) => Promise<PersonaPresetSnapshot | null>;
  onTogglePersonaPreference: (
    preset: PersonaPreset,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => Promise<void>;
  onCopyPersonaPreset: (preset: PersonaPreset) => Promise<void>;
  onSavePersonaPreset: (
    preset: PersonaPreset | null,
    data: {
      name: string;
      description: string;
      system_prompt: string;
      tags: string[];
      skill_names: string[];
    },
  ) => Promise<void>;
  onClearPersonaPreset: () => void;
  canManagePersonaPresets: boolean;
  agentOptions: Record<string, AgentOption>;
  agentOptionValues: Record<string, boolean | string | number>;
  onToggleAgentOption: (key: string, value: boolean | string | number) => void;
  // Agent mode selector
  agents: AgentInfo[];
  currentAgent: string;
  onSelectAgent: (id: string) => void;
  // Team picker
  selectedTeamId: string | null;
  onSelectTeam: (teamId: string | null) => void;
  onOpenTeamBuilder?: () => void;
  approvals: PendingApproval[];
  onRespondApproval: (
    id: string,
    response: Record<string, unknown>,
    approved: boolean,
  ) => void;
  approvalLoading: boolean;
  onSendMessage: (
    content: string,
    attachments?: MessageAttachment[],
    runOptions?: { enabledSkills?: string[] },
    submissionCallbacks?: ChatSubmissionCallbacks,
  ) => void;
  onStopGeneration: () => void;
  onSteerMessage?: (content: string) => void;
  steerMessages?: import("../../../utils/mergeSteers").SteerItem[];
  onCancelSteer?: (content: string, messageId?: string) => void;
  activeGoal: ActiveGoalSpec | null;
  goalsByRunId: Record<string, ActiveGoalSpec>;
  onClearActiveGoal: () => void;
  attachments: MessageAttachment[];
  onAttachmentsChange: React.Dispatch<
    React.SetStateAction<MessageAttachment[]>
  >;
  externalNavigationToken?: string | null;
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null;
  externalNavigationPreview?: RevealPreviewRequest | null;
  externalNavigationTargetRunId?: string | null;
  externalNavigationTargetRunPending?: boolean;
  externalScrollToBottom?: boolean;
  outlineToggleRef?: React.RefObject<(() => void) | null>;
  // Run mode
  autoModeEnabled?: boolean;
  goalModeEnabled?: boolean;
  onToggleAutoMode?: (enabled: boolean) => void;
  onToggleGoalMode?: (enabled: boolean) => void;
}

export { useCurrentTeam, resolveChatAssistantIdentity };
