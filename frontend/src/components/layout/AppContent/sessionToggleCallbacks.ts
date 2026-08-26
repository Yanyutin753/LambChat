/**
 * 会话级工具/技能开关回调：把 ChatView 里的开关操作同步为
 * session 级（mcp 工具 / 技能）的启用禁用变更。
 */

import { useCallback } from "react";
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
