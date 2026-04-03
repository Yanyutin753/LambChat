/**
 * useSessionConfig - 对话级别的配置管理
 *
 * 管理当前对话的 skills、tools、agent options 配置
 * 这些配置独立于全局配置，只影响当前对话
 *
 * 架构说明：
 * - 全局配置（/skills, /tools 路由）：用户的默认配置，影响所有新建对话
 * - 对话配置（ChatInput 选择器）：当前对话的临时配置，不影响全局
 *
 * 使用 blacklist（黑名单）模式：
 * - disabled_skills: 被禁用的 skill 列表（空列表 = 全部启用）
 * - disabled_mcp_tools: 被禁用的 MCP tool 列表（空列表 = 全部启用）
 */

import { useState, useCallback, useEffect, useRef } from "react";
import type { SessionConfig } from "./useAgent/types";

export interface SessionConfigState {
  // 当前对话禁用的 skills（名称列表）
  disabledSkills: string[];
  // 当前对话禁用的 MCP tools（名称列表）
  disabledMcpTools: string[];
  // Agent options
  agentOptions: Record<string, boolean | string | number>;
}

export interface UseSessionConfigOptions {
  // 从全局配置获取默认禁用列表
  getDefaultDisabledSkills?: () => string[];
  getDefaultDisabledMcpTools?: () => string[];
  getDefaultAgentOptions: () => Record<string, boolean | string | number>;
}

export interface UseSessionConfigReturn {
  // 当前配置状态
  config: SessionConfigState;

  // 修改配置
  toggleSkill: (skillName: string) => void;
  toggleMcpTool: (toolName: string) => void;
  setAgentOption: (key: string, value: boolean | string | number) => void;

  // 批量操作
  setDisabledSkills: (skills: string[]) => void;
  setDisabledMcpTools: (tools: string[]) => void;
  setAgentOptions: (options: Record<string, boolean | string | number>) => void;

  // 重置为默认配置
  resetToDefaults: () => void;

  // 恢复保存的配置
  restoreConfig: (config: SessionConfig) => void;

  // 检查某个 skill/tool 是否启用
  isSkillEnabled: (skillName: string) => boolean;
  isMcpToolEnabled: (toolName: string) => boolean;
}

/**
 * 对话配置管理 Hook
 */
export function useSessionConfig(
  options: UseSessionConfigOptions
): UseSessionConfigReturn {
  // 对话级别的配置状态（默认空列表 = 全部启用）
  const [config, setConfig] = useState<SessionConfigState>(() => ({
    disabledSkills: options.getDefaultDisabledSkills?.() || [],
    disabledMcpTools: options.getDefaultDisabledMcpTools?.() || [],
    agentOptions: options.getDefaultAgentOptions(),
  }));

  // 记录是否已经初始化（避免重复初始化）
  const initializedRef = useRef(false);

  // Re-sync defaults when getter results change
  useEffect(() => {
    if (!initializedRef.current) {
      setConfig({
        disabledSkills: options.getDefaultDisabledSkills?.() || [],
        disabledMcpTools: options.getDefaultDisabledMcpTools?.() || [],
        agentOptions: options.getDefaultAgentOptions(),
      });
      initializedRef.current = true;
    }
  }, [options]);

  // Toggle skill (add/remove from disabled list)
  const toggleSkill = useCallback((skillName: string) => {
    setConfig((prev) => {
      const disabled = new Set(prev.disabledSkills);
      if (disabled.has(skillName)) {
        disabled.delete(skillName);
      } else {
        disabled.add(skillName);
      }
      return {
        ...prev,
        disabledSkills: Array.from(disabled),
      };
    });
  }, []);

  // Toggle MCP tool (add/remove from disabled list)
  const toggleMcpTool = useCallback((toolName: string) => {
    setConfig((prev) => {
      const disabled = new Set(prev.disabledMcpTools);
      if (disabled.has(toolName)) {
        disabled.delete(toolName);
      } else {
        disabled.add(toolName);
      }
      return {
        ...prev,
        disabledMcpTools: Array.from(disabled),
      };
    });
  }, []);

  // Set agent option
  const setAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      setConfig((prev) => ({
        ...prev,
        agentOptions: {
          ...prev.agentOptions,
          [key]: value,
        },
      }));
    },
    [],
  );

  // Batch set disabled skills
  const setDisabledSkills = useCallback((skills: string[]) => {
    setConfig((prev) => ({
      ...prev,
      disabledSkills: skills,
    }));
  }, []);

  // Batch set disabled MCP tools
  const setDisabledMcpTools = useCallback((tools: string[]) => {
    setConfig((prev) => ({
      ...prev,
      disabledMcpTools: tools,
    }));
  }, []);

  // Batch set agent options
  const setAgentOptions = useCallback(
    (opts: Record<string, boolean | string | number>) => {
      setConfig((prev) => ({
        ...prev,
        agentOptions: opts,
      }));
    },
    [],
  );

  // Reset to defaults (new conversation)
  const resetToDefaults = useCallback(() => {
    setConfig({
      disabledSkills: options.getDefaultDisabledSkills?.() || [],
      disabledMcpTools: options.getDefaultDisabledMcpTools?.() || [],
      agentOptions: options.getDefaultAgentOptions(),
    });
  }, [options]);

  // Restore config from session metadata
  const restoreConfig = useCallback((sessionConfig: SessionConfig) => {
    console.log("[useSessionConfig] Restoring config:", sessionConfig);

    setConfig({
      disabledSkills: sessionConfig.disabled_skills || [],
      // disabled_tools is a legacy field (pre-split); treat as disabled_mcp_tools if present
      disabledMcpTools:
        sessionConfig.disabled_mcp_tools ?? sessionConfig.disabled_tools ?? [],
      agentOptions:
        sessionConfig.agent_options || options.getDefaultAgentOptions(),
    });
  }, [options]);

  // Check if skill is enabled (not in disabled list)
  const isSkillEnabled = useCallback(
    (skillName: string) => {
      return !config.disabledSkills.includes(skillName);
    },
    [config.disabledSkills],
  );

  // Check if MCP tool is enabled (not in disabled list)
  const isMcpToolEnabled = useCallback(
    (toolName: string) => {
      return !config.disabledMcpTools.includes(toolName);
    },
    [config.disabledMcpTools],
  );

  return {
    config,
    toggleSkill,
    toggleMcpTool,
    setAgentOption,
    setDisabledSkills,
    setDisabledMcpTools,
    setAgentOptions,
    resetToDefaults,
    restoreConfig,
    isSkillEnabled,
    isMcpToolEnabled,
  };
}
