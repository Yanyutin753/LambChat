/**
 * 会话级工具/技能开关回调：把 ChatView 里的开关操作同步为
 * session 级（mcp 工具 / 技能）的启用禁用变更。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import type { AgentInfo, Project } from "../../../types";
import { discardSessionWorkspaceSave, readSessionWorkspaceOptions, saveSessionWorkspaceOptions } from "../../../services/api/sessionWorkspace";
import { WORKSPACE_OPTION_KEYS, workspaceOptionPatch } from "../../chat/workspaceSelection";
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
  change: (
    key: string,
    value: boolean | string | number,
  ) => Record<string, boolean | string | number> | void,
  setProject: (id: string | null) => void,
  agentContext?: {
    agents: AgentInfo[];
    currentAgent: string;
    switchAgent: (id: string) => void;
    restoreAgentOptions: (
      values: Record<string, boolean | string | number>,
    ) => void;
  },
  workspace: {
    locked?: boolean;
    prepareChange?: typeof workspaceOptionPatch;
    markIntent?: () => void;
    restore?: (values: Record<string, boolean | string | number>) => void;
  } = {},
) {
  const live = useRef({ sessionId, scope: {}, locked: workspace.locked });
  if (live.current.sessionId !== sessionId) live.current = { sessionId, scope: {}, locked: workspace.locked };
  live.current.locked = workspace.locked;
  const scope = live.current.scope;
  const pending = useRef<Promise<unknown> | null>(null);
  const mounted = useRef(false);
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [workspaceUnconfirmed, setWorkspaceUnconfirmed] = useState(false);
  const unconfirmed = useRef(false);
  const recovering = useRef<object | null>(null);
  useEffect(() => {
    setWorkspaceSaving(false);
    pending.current = null;
    unconfirmed.current = false;
    setWorkspaceUnconfirmed(false);
  }, [sessionId]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const prepareChange = workspace.prepareChange ?? workspaceOptionPatch;
  const restore = workspace.restore;
  const markIntent = workspace.markIntent;
  const retryWorkspaceRead = useCallback(async (expected?: Record<string, boolean | string | number>) => {
    if (!sessionId || !mounted.current || live.current.scope !== scope || recovering.current === scope) return false;
    recovering.current = scope;
    unconfirmed.current = true;
    setWorkspaceUnconfirmed(true);
    setWorkspaceSaving(true);
    try {
      const values = await readSessionWorkspaceOptions(sessionId);
      if (!mounted.current || live.current.scope !== scope) return false;
      if (restore) restore(values);
      else for (const [key, value] of Object.entries(values)) change(key, value);
      unconfirmed.current = false;
      setWorkspaceUnconfirmed(false);
      return !expected || Object.entries(expected).every(([key, value]) => values[key] === value || (value === "" && values[key] === undefined));
    } catch {
      return false;
    } finally {
      if (recovering.current === scope) recovering.current = null;
      if (mounted.current && live.current.scope === scope) setWorkspaceSaving(false);
    }
  }, [sessionId, scope, restore, change]);
  const changeOption = useCallback(
    (key: string, value: boolean | string | number) => {
      if (!mounted.current || live.current.scope !== scope) return false;
      if (!WORKSPACE_OPTION_KEYS.has(key)) { change(key, value); return; }
      if (live.current.locked || pending.current || unconfirmed.current) return false;
      if (!sessionId) { markIntent?.(); change(key, value); return true; }
      const patch = prepareChange(key, value);
      if (!Object.keys(patch).length) return;
      markIntent?.();
      const request = saveSessionWorkspaceOptions(sessionId, patch);
      pending.current = request;
      setWorkspaceSaving(true);
      return request.then(
        () => {
          if (!mounted.current || live.current.scope !== scope) return false;
          change(key, value);
          return true;
        },
          async (error: unknown) => {
            discardSessionWorkspaceSave(sessionId, request);
            if (!mounted.current || live.current.scope !== scope) return false;
            const status = (error as { status?: number } | null)?.status;
            const rejected = status !== undefined && status >= 400 && status < 500 && status !== 408;
            if (!rejected && await retryWorkspaceRead(patch)) return true;
            if (mounted.current && live.current.scope === scope && error instanceof Error) toast.error(error.message);
            return false;
          },
        ).finally(() => {
          if (pending.current === request) pending.current = null;
          if (mounted.current && live.current.scope === scope) setWorkspaceSaving(false);
        });
    },
    [sessionId, change, prepareChange, scope, markIntent, retryWorkspaceRead],
  );
  const selectProject = useCallback(
    (id: string | null, workspace?: Project["workspace"]) => {
      if (!mounted.current || live.current.scope !== scope || live.current.locked || pending.current || unconfirmed.current) return;
      setProject(id);
      if (!sessionId && workspace) {
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
    [sessionId, setProject, change, agentContext, scope],
  );
  return {
    changeOption,
    selectProject,
    workspaceSaving,
    workspaceUnconfirmed,
    retryWorkspaceRead,
    workspaceProps: {
      workspaceLocked: workspace.locked,
      workspaceSaving,
      workspaceUnconfirmed,
      onRetryWorkspaceRead: retryWorkspaceRead,
    },
  };
}
