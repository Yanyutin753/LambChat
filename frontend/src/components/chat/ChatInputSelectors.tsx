import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { Download, Laptop, Monitor, Terminal } from "lucide-react";
import { ToolSelector } from "../selectors/ToolSelector";
import { SkillSelector } from "../selectors/SkillSelector";
import { AgentModeSelector } from "../selectors/AgentModeSelector";
import { PersonaPresetSelector } from "../persona/PersonaPresetSelector";
import { TeamPickerModal } from "../team/TeamPickerModal";
import { AgentOptionButton } from "./AgentOptionButton";
import { isShellAvailable, writeConfirmPolicy } from "../../services/tauri/sandboxShell";
import {
  notifySandboxStatusRefresh,
  useSandboxStatus,
} from "../../hooks/useSandboxStatus";
import { sandboxApiMachines } from "../../services/api/sandbox";
import {
  SANDBOX_AGENT_OPTION_KEY,
  SANDBOX_LOCAL_VALUE,
  SANDBOX_MACHINE_AGENT_OPTION_KEY,
  adaptSandboxAgentOption,
  buildSandboxMachineRows,
  type SandboxMachineRow,
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
  const {
    online: sandboxOnline,
    machines,
    defaultMachineId,
    currentMachineId,
  } = useSandboxStatus();
  const sandboxShell = isShellAvailable();
  const [policyOverride, setPolicyOverride] = useState<string | null>(null);
  const sandboxValue = agentOptionValues[SANDBOX_AGENT_OPTION_KEY] ?? "cloud";
  // 统一面板设备行：存在任一在线机即展示（云端档点设备 = 一键切本地档），
  // 当前设备（壳内 read_machine_id 比对命中）带标识
  const machineRows = machines.some((m) => m.online !== false)
    ? buildSandboxMachineRows(machines, defaultMachineId, currentMachineId, t)
    : [];
  const machineValue =
    typeof agentOptionValues[SANDBOX_MACHINE_AGENT_OPTION_KEY] === "string"
      ? (agentOptionValues[SANDBOX_MACHINE_AGENT_OPTION_KEY] as string)
      : "";
  const selectedMachine =
    machines.find((m) => m.machine_id === (machineValue || defaultMachineId)) ??
    machines.find((m) => m.online !== false);
  const executionPolicy = policyOverride ?? selectedMachine?.confirm_policy ?? "all";
  const handlePolicyChange = async (policy: string) => {
    if (!selectedMachine || selectedMachine.online === false) return;
    try {
      await sandboxApiMachines.updateConfirmPolicy(selectedMachine.machine_id, policy);
      if (selectedMachine.machine_id === currentMachineId && sandboxShell) {
        await writeConfirmPolicy(policy);
      }
      setPolicyOverride(policy);
      // 与偏好设置页同款对账：machines 走 presence 秒推，但 profile 页依赖的
      // status（daemon_confirm_policy）要等 60s 对账轮询——不发本事件会出现
      // 「chat input 已新、偏好设置还旧」的双显不同步
      notifySandboxStatusRefresh();
      toast.success(t("agentOptions.sandboxPolicy.updated"));
    } catch {
      toast.error(t("agentOptions.sandboxPolicy.updateFailed"));
    }
  };
  const handleSelectMachineRow = (row: SandboxMachineRow) => {
    if (row.disabled) {
      // 离线机置灰保留展示仅为告知存在：点击提示不落选为目标
      toast.error(t("agentOptions.sandboxMachine.offlineHint"));
      return;
    }
    // 云端档点设备：一并切本地（档位与执行目标一次到位）
    if (sandboxValue !== SANDBOX_LOCAL_VALUE) {
      onToggleAgentOption?.(SANDBOX_AGENT_OPTION_KEY, SANDBOX_LOCAL_VALUE);
    }
    onToggleAgentOption?.(SANDBOX_MACHINE_AGENT_OPTION_KEY, row.value);
  };
  const machineSection =
    machineRows.length > 0 ? (
      <>
      <div
        className="mt-1 pt-1.5 border-t"
        style={{ borderColor: "var(--theme-border)" }}
        data-sandbox-machine-section
      >
        <div
          className="px-3 pt-1 pb-1.5 text-12 font-medium"
          style={{ color: "var(--theme-text-secondary)" }}
        >
          {t("agentOptions.sandboxMachine.section")}
        </div>
        <div className="flex flex-col gap-1">
          {machineRows.map((row) => {
            const active =
              sandboxValue === SANDBOX_LOCAL_VALUE && row.value === machineValue;
            const PlatformIcon = machinePlatformIcon(row.platform);
            return (
              <button
                key={row.value || "auto"}
                type="button"
                data-sandbox-machine-row
                onClick={() => handleSelectMachineRow(row)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-14 transition-colors text-left cursor-pointer active:scale-[0.98]${
                  row.disabled ? " opacity-50" : ""
                }`}
                style={{
                  background: active
                    ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)"
                    : "transparent",
                  color: active ? "var(--theme-primary)" : "var(--theme-text)",
                }}
              >
                <PlatformIcon size={14} className="shrink-0 opacity-60" />
                <span className="truncate">{row.label}</span>
                {row.isCurrent && (
                  <span
                    data-current-device-badge
                    className="ml-1 shrink-0 px-1.5 py-0.5 rounded-full text-12"
                    style={{
                      color: "var(--theme-primary)",
                      background:
                        "color-mix(in srgb, var(--theme-primary) 12%, transparent)",
                    }}
                  >
                    {t("agentOptions.sandboxMachine.currentDevice")}
                  </span>
                )}
                {active && (
                  <span
                    className="ml-auto text-12"
                    style={{ color: "var(--theme-primary)" }}
                  >
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
      {selectedMachine && (
        <div className="mt-1 pt-1.5 border-t" style={{ borderColor: "var(--theme-border)" }} data-sandbox-policy-section>
          <div className="px-3 pt-1 pb-1.5 text-12 font-medium" style={{ color: "var(--theme-text-secondary)" }}>
            {t("agentOptions.sandboxPolicy.section")}
          </div>
          <div className="flex flex-col gap-1">
            {(["all", "commands", "none"] as const).map((policy) => (
              <button key={policy} type="button" onClick={() => void handlePolicyChange(policy)}
                className="flex items-center gap-3 px-3 py-2 rounded-xl text-14 transition-colors text-left cursor-pointer active:scale-[0.98]"
                style={{ background: executionPolicy === policy ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)" : "transparent", color: executionPolicy === policy ? "var(--theme-primary)" : "var(--theme-text)" }}>
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: executionPolicy === policy ? "var(--theme-primary)" : "var(--theme-border)" }} />
                {t(`agentOptions.sandboxPolicy.${policy}`)}
                {executionPolicy === policy && <span className="ml-auto text-12" style={{ color: "var(--theme-primary)" }}>✓</span>}
              </button>
            ))}
          </div>
        </div>
      )}
      </>
    ) : undefined;

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
              // 离线（壳内或纯 web 本地档置灰可见）：统一提示 + 底部下载引导
              const note = !sandboxOnline
                ? t("agentOptions.sandbox.offlineHint")
                : undefined;
              const downloadFooter = !sandboxOnline ? (
                <button
                  type="button"
                  onClick={() => navigate("/download")}
                  className="flex w-full items-center gap-2 px-3 py-2 rounded-xl text-14 cursor-pointer transition-colors hover:bg-black/5 dark:hover:bg-white/5"
                  style={{ color: "var(--theme-primary)" }}
                  data-sandbox-download-entry
                >
                  <Download size={14} className="shrink-0" />
                  {t("agentOptions.sandbox.downloadEntry")}
                </button>
              ) : undefined;
              // 独立 panel key：与思考档模态互斥，同帧只开一个选项模态；
              // 触发入口在工具栏沙箱 chip 与 RunModePopover 的"沙箱"条目。
              // 统一面板：档位下方注入执行设备列表（选设备 = 定档 + 定目标）。
              return (
                <AgentOptionButton
                  key={key}
                  optionKey={key}
                  option={adapted.option}
                  value={adapted.value}
                  onChange={handleChange}
                  note={note}
                  belowOptions={machineSection}
                  footer={downloadFooter}
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

/** 设备行平台图标：darwin/未知=Laptop，win32=Monitor，linux=Terminal。 */
function machinePlatformIcon(platform?: string) {
  switch (platform) {
    case "win32":
      return Monitor;
    case "linux":
      return Terminal;
    default:
      return Laptop;
  }
}
