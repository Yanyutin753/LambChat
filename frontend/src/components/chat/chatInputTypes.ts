import type { FeaturePanel } from "../selectors/FeatureMenu";
import type { SteerItem } from "../../utils/mergeSteers";
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
import type {
  ActiveGoalSpec,
  ChatSubmissionCallbacks,
} from "../../hooks/useAgent/types";

export interface ChatInputProps {
  onSend: (
    message: string,
    options?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
    runOptions?: { enabledSkills?: string[] },
    submissionCallbacks?: ChatSubmissionCallbacks,
  ) => void;
  onStop: () => void;
  /** 运行中插话（Codex 式 steer）：任务运行期间发送的消息进入队列，当前步骤后送达 */
  onSteer?: (content: string, attachments?: MessageAttachment[]) => void;
  steerMessages?: SteerItem[];
  onCancelSteer?: (content: string, messageId?: string) => void;
  isLoading: boolean;
  disabled?: boolean;
  /** Block sending while an ask-human interrupt is awaiting a response. */
  sendBlocked?: boolean;
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
  onSelectTeam?: (teamId: string | null) => void;
  onOpenTeamBuilder?: () => void;
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

  // Run mode
  autoModeEnabled?: boolean;
  goalModeEnabled?: boolean;
  onToggleAutoMode?: (enabled: boolean) => void;
  onToggleGoalMode?: (enabled: boolean) => void;
}
