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
  SendMessageOptions,
} from "../../../hooks/useAgent/types";
import type { RevealPreviewRequest } from "../../chat/ChatMessage/items/revealPreviewData";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../../extensions/pluginOptions";
import { usePluginChatAssistantIdentity } from "../../chat/chatAssistantIdentityResolvers";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

// Plugin-specific assistant identity is resolved by static plugin renderers.

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function useChatAssistantIdentity({
  currentAgent,
  currentPersonaAvatar,
  pluginOptionValues,
  runtimePlugins,
  selectedPersonaName,
}: {
  currentAgent: string;
  currentPersonaAvatar: string | null;
  pluginOptionValues: PluginOptionsMetadata;
  runtimePlugins?: PluginRuntimeContributionStates;
  selectedPersonaName: string | null;
}) {
  const pluginIdentity = usePluginChatAssistantIdentity({
    currentAgent,
    pluginOptionValues,
    runtimePlugins,
  });
  if (pluginIdentity) {
    return pluginIdentity;
  }

  return {
    avatar: currentPersonaAvatar,
    name: selectedPersonaName,
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
  // Agent Team compatibility state; new writes go through plugin options.
  selectedTeamId: string | null;
  pluginOptionValues: PluginOptionsMetadata;
  onPluginOptionChange: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
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
    options?: SendMessageOptions,
  ) => void;
  onStopGeneration: () => void;
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
  runtimePlugins?: PluginRuntimeContributionStates;
}

export { useChatAssistantIdentity };
