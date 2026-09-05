import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { AgentModeSelector } from "../selectors/AgentModeSelector";
import { PersonaPresetSelector } from "../persona/PersonaPresetSelector";
import { TeamPickerModal } from "../team/TeamPickerModal";
import { AgentOptionButton } from "./AgentOptionButton";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import { isShellAvailable } from "../../services/tauri/sandboxShell";
import {
  SANDBOX_AGENT_OPTION_KEY,
  SANDBOX_LOCAL_VALUE,
  adaptSandboxAgentOption,
} from "./sandboxOption";
import type { FeaturePanel } from "../selectors/FeatureMenu";
import type {
  ToolState,
  ToolCategory,
  SkillResponse,
  SkillSource,
  AgentOption,
  AgentInfo,
  PersonaPreset,
  PersonaPresetSnapshot,
} from "../../types";

export interface ChatInputSelectorsProps {
  activePanel: FeaturePanel;
  onActivePanelChange: (panel: FeaturePanel) => void;
  // Tools
  tools?: ToolState[];
  onToggleTool?: (toolName: string) => void;
  onToggleCategory?: (category: ToolCategory, enabled: boolean) => void;
  onToggleAll?: (enabled: boolean) => void;
  enabledToolsCount?: number;
  totalToolsCount?: number;
  // Skills
  skills?: SkillResponse[];
  onToggleSkill?: (name: string) => Promise<boolean>;
  onToggleSkillCategory?: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAllSkills?: (enabled: boolean) => Promise<boolean>;
  pendingSkillNames?: string[];
  skillsMutating?: boolean;
  enabledSkillsCount?: number;
  totalSkillsCount?: number;
  enableSkills?: boolean;
  personaSkillsControlled?: boolean;
  selectedPersonaName?: string | null;
  // Persona presets
  personaPresets?: PersonaPreset[];
  personaPresetsTotal?: number;
  personaPresetsPage?: number;
  onPersonaPresetsPageChange?: (page: number) => void;
  onPersonaPresetsSearchChange?: (query: string) => void;
  onPersonaPresetsTagChange?: (tag: string | null) => void;
  selectedPersonaPresetId?: string | null;
  personaPresetsLoading?: boolean;
  personaPresetsMutating?: boolean;
  onUsePersonaPreset?: (
    preset: PersonaPreset,
  ) => Promise<PersonaPresetSnapshot | null>;
  onTogglePersonaPreference?: (
    preset: PersonaPreset,
    preference: { is_favorite?: boolean; is_pinned?: boolean },
  ) => Promise<void>;
  onCopyPersonaPreset?: (preset: PersonaPreset) => Promise<void>;
  onClearPersonaPreset?: () => void;
  canManagePersonaPresets?: boolean;
  // Agent mode
  agents?: AgentInfo[];
  currentAgent?: string;
  onSelectAgent?: (id: string) => void;
  selectedTeamId?: string | null;
  onSelectTeam?: (teamId: string | null) => void;
  onOpenTeamBuilder?: () => void;
  // Agent options
  agentOptions?: Record<string, AgentOption>;
  agentOptionValues?: Record<string, boolean | string | number>;
  onToggleAgentOption?: (key: string, value: boolean | string | number) => void;
  /** 当前模型思考能力；undefined=未知（不隐藏），false=隐藏思考强度控件 */
  modelSupportsThinking?: boolean;
}

export function ChatInputSelectors({
  activePanel,
  onActivePanelChange,
  tools = [],
  onToggleTool,
  onToggleCategory,
  onToggleAll,
  enabledToolsCount = 0,
  totalToolsCount = 0,
  skills = [],
  onToggleSkill,
  onToggleSkillCategory,
  onToggleAllSkills,
  pendingSkillNames = [],
  skillsMutating = false,
  enabledSkillsCount = 0,
  totalSkillsCount = 0,
  enableSkills = true,
  personaSkillsControlled = false,
  selectedPersonaName,
  personaPresets = [],
  personaPresetsTotal,
  personaPresetsPage,
  onPersonaPresetsPageChange,
  onPersonaPresetsSearchChange,
  onPersonaPresetsTagChange,
  selectedPersonaPresetId,
  personaPresetsLoading = false,
  personaPresetsMutating = false,
  onUsePersonaPreset,
  onTogglePersonaPreference,
  onCopyPersonaPreset,
  onClearPersonaPreset,
  canManagePersonaPresets = false,
  agents = [],
  currentAgent,
  onSelectAgent,
  selectedTeamId,
  onSelectTeam,
  onOpenTeamBuilder,
  agentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
  modelSupportsThinking,
}: ChatInputSelectorsProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  // 沙箱选择器动态适配：壳检测 + daemon 在线状态双条件
  const { online: sandboxOnline } = useSandboxStatus();
  const sandboxShell = isShellAvailable();

  return (
    <>
      {onToggleTool && onToggleCategory && onToggleAll && (
        <ToolSelector
          tools={tools}
          onToggleTool={onToggleTool}
          onToggleCategory={onToggleCategory}
          onToggleAll={onToggleAll}
          enabledCount={enabledToolsCount}
          totalCount={totalToolsCount}
          isOpen={activePanel === "tools"}
          onOpenChange={(open) => onActivePanelChange(open ? "tools" : null)}
        />
      )}
      {enableSkills &&
        onToggleSkill &&
        onToggleSkillCategory &&
        onToggleAllSkills && (
          <SkillSelector
            skills={skills}
            onToggleSkill={onToggleSkill}
            onToggleCategory={onToggleSkillCategory}
            onToggleAll={onToggleAllSkills}
            pendingSkillNames={pendingSkillNames}
            isMutating={skillsMutating}
            enabledCount={enabledSkillsCount}
            totalCount={totalSkillsCount}
            controlledByPersonaName={
              personaSkillsControlled ? selectedPersonaName : null
            }
            isOpen={activePanel === "skills"}
            onOpenChange={(open) => onActivePanelChange(open ? "skills" : null)}
          />
        )}
      {onUsePersonaPreset && onCopyPersonaPreset && onClearPersonaPreset && (
        <PersonaPresetSelector
          presets={personaPresets}
          total={personaPresetsTotal}
          page={personaPresetsPage}
          selectedPresetId={selectedPersonaPresetId}
          isOpen={activePanel === "persona"}
          isLoading={personaPresetsLoading}
          isMutating={personaPresetsMutating}
          canManagePresets={canManagePersonaPresets}
          onOpenChange={(open) => onActivePanelChange(open ? "persona" : null)}
          onPageChange={onPersonaPresetsPageChange}
          onSearchChange={onPersonaPresetsSearchChange}
          onTagChange={onPersonaPresetsTagChange}
          onUsePreset={onUsePersonaPreset}
          onTogglePreference={onTogglePersonaPreference}
          onCopyPreset={onCopyPersonaPreset}
          onManagePresets={() => navigate("/persona")}
          onClearPreset={() => {
            onClearPersonaPreset();
            onActivePanelChange(null);
          }}
        />
      )}
      <AgentModeSelector
        agents={agents}
        currentAgent={currentAgent || ""}
        onSelectAgent={onSelectAgent}
        isOpen={activePanel === "agent"}
        onOpenChange={(open) => onActivePanelChange(open ? "agent" : null)}
      />
      {currentAgent === "team" && onSelectTeam && (
        <TeamPickerModal
          isOpen={activePanel === "team"}
          selectedTeamId={selectedTeamId ?? null}
          onSelect={onSelectTeam}
          onClose={() => onActivePanelChange(null)}
          onCreateNew={() => {
            if (onOpenTeamBuilder) {
              onOpenTeamBuilder();
            } else {
              navigate("/team");
            }
          }}
          onManageTeams={() => navigate("/team")}
        />
      )}
      {agentOptions &&
        onToggleAgentOption &&
        Object.keys(agentOptions).length > 0 &&
        Object.entries(agentOptions)
          .filter(
            ([key, opt]) =>
              opt.options &&
              opt.options.length > 0 &&
              // 仅思考选项按模型能力隐藏；未来其他枚举型选项不受连带影响
              (key !== "enable_thinking" || modelSupportsThinking !== false),
          )
          .map(([key, option]) => {
            const storedValue = agentOptionValues[key] ?? option.default;
            const isSandbox = key === SANDBOX_AGENT_OPTION_KEY;

            // 沙箱选项：按壳/在线状态裁剪档位并回退显示值（不篡改已存会话值）
            const adapted = isSandbox
              ? adaptSandboxAgentOption(
                  option,
                  { shell: sandboxShell, online: sandboxOnline },
                  storedValue,
                )
              : { option, value: storedValue };

            const handleChange = (value: boolean | string | number) => {
              if (isSandbox && value === "local" && !sandboxOnline) {
                // 离线选本地档：五语提示，但选择仍然生效（不拦截用户意图）
                toast.error(t("agentOptions.sandbox.offlineHint"));
              }
              onToggleAgentOption(key, value);
            };

            if (isSandbox) {
              const note =
                !sandboxOnline && sandboxShell
                  ? t("agentOptions.sandbox.offlineHint")
                  : !sandboxOnline && storedValue === SANDBOX_LOCAL_VALUE
                    ? t("agentOptions.sandbox.restoredOffline")
                    : undefined;
              // 独立 panel key：与思考档模态互斥，同帧只开一个选项模态；
              // 触发入口在 RunModePopover 的"沙箱"条目（含 daemon 状态点）。
              return (
                <AgentOptionButton
                  key={key}
                  optionKey={key}
                  option={adapted.option}
                  value={adapted.value}
                  onChange={handleChange}
                  note={note}
                  isOpen={activePanel === "sandbox"}
                  onOpenChange={(open) =>
                    onActivePanelChange(open ? "sandbox" : null)
                  }
                />
              );
            }

            return (
              <AgentOptionButton
                key={key}
                optionKey={key}
                option={adapted.option}
                value={adapted.value}
                onChange={handleChange}
                isOpen={activePanel === "thinking"}
                onOpenChange={(open) =>
                  onActivePanelChange(open ? "thinking" : null)
                }
              />
            );
          })}
    </>
  );
}
