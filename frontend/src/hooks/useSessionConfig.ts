/**
 * useSessionConfig - 对话级别的配置管理
 *
 * 管理当前对话的 skills、tools、agent options 配置
 * 这些配置独立于全局配置，只影响当前对话
 *
 * 架构说明：
 * - 全局配置（/skills, /tools 路由）：用户的默认配置，影响所有新建对话
 * - 对话配置（ChatInput 选择器）：当前对话的临时配置，不影响全局
 */

import { useState, useCallback, useEffect, useRef } from "react";
import type { SessionConfig } from "./useAgent/types";

export interface SessionConfigState {
  // 当前对话启用的 skills（名称列表）
  enabledSkills: string[];
  // 当前对话启用的 MCP tools（名称列表）
  enabledMcpTools: string[];
  // Agent options
  agentOptions: Record<string, boolean | string | number>;
}

export interface UseSessionConfigOptions {
  // 从全局配置获取默认值
  getDefaultSkills: () => string[];
  getDefaultMcpTools: () => string[];
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
  setEnabledSkills: (skills: string[]) => void;
  setEnabledMcpTools: (tools: string[]) => void;
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
 *
 * @example
 * ```typescript
 * const {
 *   config,
 *   toggleSkill,
 *   toggleMcpTool,
 *   restoreConfig,
 * } = useSessionConfig({
 *   getDefaultSkills: () => skills.filter(s => s.enabled).map(s => s.name),
 *   getDefaultMcpTools: () => tools.filter(t => t.category === 'mcp' && t.enabled).map(t => t.name),
 *   getDefaultAgentOptions: () => ({}),
 * });
 * ```
 */
export function useSessionConfig(
  options: UseSessionConfigOptions
): UseSessionConfigReturn {
  // 对话级别的配置状态
  const [config, setConfig] = useState<SessionConfigState>(() => ({
    enabledSkills: options.getDefaultSkills(),
    enabledMcpTools: options.getDefaultMcpTools(),
    agentOptions: options.getDefaultAgentOptions(),
  }));

  // 记录是否已经初始化（避免重复初始化）
  const initializedRef = useRef(false);

  // Re-sync defaults when getter results change
  useEffect(() => {
    if (!initializedRef.current) {
      setConfig({
        enabledSkills: options.getDefaultSkills(),
        enabledMcpTools: options.getDefaultMcpTools(),
        agentOptions: options.getDefaultAgentOptions(),
      });
      initializedRef.current = true;
    }
  }, [options]);

  // Toggle skill
  const toggleSkill = useCallback((skillName: string) => {
    setConfig((prev) => {
      const enabled = new Set(prev.enabledSkills);
      if (enabled.has(skillName)) {
        enabled.delete(skillName);
      } else {
        enabled.add(skillName);
      }
      return {
        ...prev,
        enabledSkills: Array.from(enabled),
      };
    });
  }, []);

  // Toggle MCP tool
  const toggleMcpTool = useCallback((toolName: string) => {
    setConfig((prev) => {
      const enabled = new Set(prev.enabledMcpTools);
      if (enabled.has(toolName)) {
        enabled.delete(toolName);
      } else {
        enabled.add(toolName);
      }
      return {
        ...prev,
        enabledMcpTools: Array.from(enabled),
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

  // Batch set enabled skills
  const setEnabledSkills = useCallback((skills: string[]) => {
    setConfig((prev) => ({
      ...prev,
      enabledSkills: skills,
    }));
  }, []);

  // Batch set enabled MCP tools
  const setEnabledMcpTools = useCallback((tools: string[]) => {
    setConfig((prev) => ({
      ...prev,
      enabledMcpTools: tools,
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

  // Reset to defaults
  const resetToDefaults = useCallback(() => {
    setConfig({
      enabledSkills: options.getDefaultSkills(),
      enabledMcpTools: options.getDefaultMcpTools(),
      agentOptions: options.getDefaultAgentOptions(),
    });
  }, [options]);

  // Restore config from session metadata
  const restoreConfig = useCallback((sessionConfig: SessionConfig) => {
    console.log("[useSessionConfig] Restoring config:", sessionConfig);

    setConfig({
      enabledSkills: sessionConfig.enabled_skills || options.getDefaultSkills(),
      enabledMcpTools:
        sessionConfig.enabled_mcp_tools || options.getDefaultMcpTools(),
      agentOptions:
        sessionConfig.agent_options || options.getDefaultAgentOptions(),
    });
  }, [options]);

  // Check if skill is enabled
  const isSkillEnabled = useCallback(
    (skillName: string) => {
      return config.enabledSkills.includes(skillName);
    },
    [config.enabledSkills],
  );

  // Check if MCP tool is enabled
  const isMcpToolEnabled = useCallback(
    (toolName: string) => {
      return config.enabledMcpTools.includes(toolName);
    },
    [config.enabledMcpTools],
  );

  return {
    config,
    toggleSkill,
    toggleMcpTool,
    setAgentOption,
    setEnabledSkills,
    setEnabledMcpTools,
    setAgentOptions,
    resetToDefaults,
    restoreConfig,
    isSkillEnabled,
    isMcpToolEnabled,
  };
}
