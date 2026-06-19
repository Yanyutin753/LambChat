import type { FeaturePanel } from "../selectors/FeatureMenu";
import type {
  ToolState,
  ToolCategory,
  SkillResponse,
  SkillSource,
  AgentOption,
  AgentInfo,
  MessageAttachment,
  PersonaPreset,
  PersonaPresetSnapshot,
} from "../../types";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";

export interface ChatInputProps {
  onSend: (
    message: string,
    options?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
  ) => void;
  onStop: () => void;
  isLoading: boolean;
  disabled?: boolean;
  canSend?: boolean;
  tools?: ToolState[];
  onToggleTool?: (toolName: string) => void;
  onToggleCategory?: (category: ToolCategory, enabled: boolean) => void;
  onToggleAll?: (enabled: boolean) => void;
  toolsLoading?: boolean;
  enabledToolsCount?: number;
  totalToolsCount?: number;
  skills?: SkillResponse[];
  onToggleSkill?: (name: string) => Promise<boolean>;
  onToggleSkillCategory?: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAllSkills?: (enabled: boolean) => Promise<boolean>;
  skillsLoading?: boolean;
  pendingSkillNames?: string[];
  skillsMutating?: boolean;
  enabledSkillsCount?: number;
  totalSkillsCount?: number;
  enableSkills?: boolean;
  personaPresets?: PersonaPreset[];
  personaPresetsTotal?: number;
  personaPresetsPage?: number;
  onPersonaPresetsPageChange?: (page: number) => void;
  onPersonaPresetsSearchChange?: (query: string) => void;
  onPersonaPresetsTagChange?: (tag: string | null) => void;
  selectedPersonaPresetId?: string | null;
  selectedPersonaName?: string | null;
  personaSkillsControlled?: boolean;
  personaPresetsLoading?: boolean;
  personaPresetsMutating?: boolean;
  onUsePersonaPreset?: (
    preset: PersonaPreset,
  ) => Promise<PersonaPresetSnapshot | null>;
  onCopyPersonaPreset?: (preset: PersonaPreset) => Promise<void>;
  onSavePersonaPreset?: (
    preset: PersonaPreset | null,
    data: {
      name: string;
      description: string;
      system_prompt: string;
      tags: string[];
      skill_names: string[];
    },
  ) => Promise<void>;
  onClearPersonaPreset?: () => void;
  canManagePersonaPresets?: boolean;
  agentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
  agents?: AgentInfo[];
  currentAgent?: string;
  onSelectAgent?: (id: string) => void;
  // Team picker
  selectedTeamId?: string | null;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  runtimePlugins?: PluginRuntimeContributionStates;
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
  onMentionQueryChange?: (query: string | null) => void;
  pendingInput?: string | null;
  onPendingInputConsumed?: () => void;
  className?: string;

  /** Active goal — when provided, renders an embedded goal strip inside the input card. */
  activeGoal?: ActiveGoalSpec | null;
  onClearActiveGoal?: () => void;
  goalLabel?: string;
  goalDurationLabel?: string;
  goalClearLabel?: string;

  /** Show the help (?) button — defaults to false. */
  showHelpMenu?: boolean;
  /** Additional className for the help menu (e.g. "sm:hidden" to hide on desktop). */
  helpMenuClassName?: string;

  /** INTERNAL: panel state lifted from ChatInput for ChatView layout. */
  activePanel?: FeaturePanel;
  onActivePanelChange?: (panel: FeaturePanel) => void;
}
