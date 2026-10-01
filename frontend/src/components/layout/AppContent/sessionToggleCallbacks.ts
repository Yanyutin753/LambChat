/**
 * 会话级工具/技能开关回调：把 ChatView 里的开关操作同步为
 * session 级（mcp 工具 / 技能）的启用禁用变更。
 */

import { useCallback } from "react";
import toast from "react-hot-toast";
import type { AgentInfo, Project } from "../../../types";
import { saveSessionWorkspaceOption } from "../../../services/api/sessionWorkspace";
import type {
  SkillResponse,
  SkillSource,
  ToolCategory,
  ToolState,
} from "../../../types";

interface SessionToggleCallbacksInput {
  tools: ToolState[];
  skills: SkillResponse[];
  disabledMcpTools: string[];
  disabledSkills: string[];
  toggleSessionMcpTool: (name: string) => void;
  toggleSessionSkill: (name: string) => void;
}

export function useSessionToggleCallbacks({
  tools,
  skills,
  disabledMcpTools,
  disabledSkills,
  toggleSessionMcpTool,
  toggleSessionSkill,
}: SessionToggleCallbacksInput) {
  const effectiveToggleTool = useCallback(
    (toolName: string) => {
      const tool = tools.find((t) => t.name === toolName);
      if (!tool) return;

      if (tool.category === "mcp") {
        toggleSessionMcpTool(toolName);
      }
    },
    [tools, toggleSessionMcpTool],
  );

  const effectiveToggleCategory = useCallback(
    (category: ToolCategory, enabled: boolean) => {
      if (category === "mcp") {
        tools
          .filter((t) => t.category === "mcp" && !t.system_disabled)
          .forEach((t) => {
            const isInSessionDisabled = disabledMcpTools.includes(t.name);
            if (enabled && isInSessionDisabled) {
              toggleSessionMcpTool(t.name);
            } else if (!enabled && !isInSessionDisabled) {
              toggleSessionMcpTool(t.name);
            }
          });
      }
    },
    [tools, disabledMcpTools, toggleSessionMcpTool],
  );

  const effectiveToggleAll = useCallback(
    (enabled: boolean) => {
      tools
        .filter((t) => t.category === "mcp" && !t.system_disabled)
        .forEach((t) => {
          const isInSessionDisabled = disabledMcpTools.includes(t.name);
          if (enabled && isInSessionDisabled) {
            toggleSessionMcpTool(t.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionMcpTool(t.name);
          }
        });
    },
    [tools, disabledMcpTools, toggleSessionMcpTool],
  );

  const effectiveToggleSkill = useCallback(
    async (name: string): Promise<boolean> => {
      toggleSessionSkill(name);
      return true;
    },
    [toggleSessionSkill],
  );

  const effectiveToggleSkillCategory = useCallback(
    async (category: SkillSource, enabled: boolean): Promise<boolean> => {
      skills
        .filter((s) => s.enabled && s.source === category)
        .forEach((s) => {
          const isInSessionDisabled = disabledSkills.includes(s.name);
          if (enabled && isInSessionDisabled) {
            toggleSessionSkill(s.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionSkill(s.name);
          }
        });
      return true;
    },
    [skills, disabledSkills, toggleSessionSkill],
  );

  const effectiveToggleAllSkills = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      skills
        .filter((s) => s.enabled)
        .forEach((s) => {
          const isInSessionDisabled = disabledSkills.includes(s.name);
          if (enabled && isInSessionDisabled) {
            toggleSessionSkill(s.name);
          } else if (!enabled && !isInSessionDisabled) {
            toggleSessionSkill(s.name);
          }
        });
      return true;
    },
    [skills, disabledSkills, toggleSessionSkill],
  );

  return {
    effectiveToggleTool,
    effectiveToggleCategory,
    effectiveToggleAll,
    effectiveToggleSkill,
    effectiveToggleSkillCategory,
    effectiveToggleAllSkills,
  };
}

/** 工作区选项立即落库；项目只为新会话提供默认值。 */
export function useWorkspaceOptionActions(
  sessionId: string | null,
  change: (key: string, value: boolean | string | number) => void,
  setProject: (id: string | null) => void,
  agentContext?: {
    agents: AgentInfo[];
    currentAgent: string;
    switchAgent: (id: string) => void;
    restoreAgentOptions: (
      values: Record<string, boolean | string | number>,
    ) => void;
  },
) {
  const changeOption = useCallback(
    (key: string, value: boolean | string | number) => {
      if (sessionId) {
        void saveSessionWorkspaceOption(sessionId, key, value).catch(
          (error: unknown) => {
            if (error instanceof Error) toast.error(error.message);
          },
        );
      }
      change(key, value);
    },
    [sessionId, change],
  );
  const selectProject = useCallback(
    (id: string | null, workspace?: Project["workspace"]) => {
      setProject(id);
      if (workspace) {
        const values = {
          sandbox: "local",
          sandbox_machine_id: workspace.machineId,
          sandbox_workspace: JSON.stringify(workspace),
        };
        const current = agentContext?.agents.find(
          (agent) => agent.id === agentContext.currentAgent,
        );
        const capable = agentContext?.agents.find(
          (agent) => agent.supports_sandbox,
        );
        if (agentContext && !current?.supports_sandbox && capable) {
          agentContext.switchAgent(capable.id);
          agentContext.restoreAgentOptions(values);
        } else {
          Object.entries(values).forEach(([key, value]) => change(key, value));
        }
      }
    },
    [setProject, change, agentContext],
  );
  return { changeOption, selectProject };
}
