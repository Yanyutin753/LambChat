/**
 * useConfigPersistence - 统一的配置持久化管理
 *
 * 负责管理对话级别的配置（skills, tools, agent options）的持久化和恢复
 * 采用分层配置策略：对话配置 > 用户配置 > 全局配置
 */

import { useCallback, useRef } from "react";
import type { SessionConfig } from "./useAgent/types";

export interface ConfigPersistenceCallbacks {
  // Skills 管理
  getEnabledSkills: () => string[];
  restoreSkills: (enabledSkills: string[]) => void;

  // MCP Tools 管理
  getEnabledMcpTools: () => string[];
  restoreMcpTools: (enabledTools: string[]) => void;

  // Agent Options 管理
  getAgentOptions: () => Record<string, boolean | string | number>;
  restoreAgentOptions: (options: Record<string, boolean | string | number>) => void;
}

export interface UseConfigPersistenceReturn {
  // 获取当前完整配置（用于发送消息时）
  getCurrentConfig: () => {
    enabled_skills: string[];
    enabled_mcp_tools: string[];
    agent_options: Record<string, boolean | string | number>;
  };

  // 恢复配置（用于加载对话时）
  restoreConfig: (config: SessionConfig) => void;

  // 检查配置是否已修改（用于提示用户保存）
  hasConfigChanged: () => boolean;
}

/**
 * 配置持久化 Hook
 *
 * @param callbacks - 各个配置管理器的回调函数
 * @returns 配置管理接口
 *
 * @example
 * ```typescript
 * const { getCurrentConfig, restoreConfig } = useConfigPersistence({
 *   getEnabledSkills: () => skills.filter(s => s.enabled).map(s => s.name),
 *   restoreSkills: (names) => batchToggleSkills(names, true),
 *   getEnabledMcpTools: () => tools.filter(t => t.category === 'mcp' && t.enabled).map(t => t.name),
 *   restoreMcpTools: (names) => restoreToolsState(names),
 *   getAgentOptions: () => agentOptionValues,
 *   restoreAgentOptions: (opts) => setAgentOptionValues(opts),
 * });
 * ```
 */
export function useConfigPersistence(
  callbacks: ConfigPersistenceCallbacks
): UseConfigPersistenceReturn {
  // 记录初始配置，用于检测变更
  const initialConfigRef = useRef<{
    skills: string[];
    tools: string[];
    options: Record<string, boolean | string | number>;
  } | null>(null);

  /**
   * 获取当前完整配置
   * 在发送消息时调用，将当前状态序列化为配置对象
   */
  const getCurrentConfig = useCallback(() => {
    return {
      enabled_skills: callbacks.getEnabledSkills(),
      enabled_mcp_tools: callbacks.getEnabledMcpTools(),
      agent_options: callbacks.getAgentOptions(),
    };
  }, [callbacks]);

  /**
   * 恢复配置
   * 在加载对话时调用，将保存的配置恢复到当前状态
   *
   * 采用渐进式恢复策略：
   * 1. 先恢复 agent_options（影响最小）
   * 2. 再恢复 skills（可能触发 API 调用）
   * 3. 最后恢复 mcp_tools（可能触发 API 调用）
   */
  const restoreConfig = useCallback(
    (config: SessionConfig) => {
      console.log("[useConfigPersistence] Restoring config:", config);

      // 1. 恢复 agent options
      if (config.agent_options) {
        callbacks.restoreAgentOptions(config.agent_options);
      }

      // 2. 恢复 skills
      if (config.enabled_skills && config.enabled_skills.length > 0) {
        callbacks.restoreSkills(config.enabled_skills);
      }

      // 3. 恢复 MCP tools
      if (config.enabled_mcp_tools && config.enabled_mcp_tools.length > 0) {
        callbacks.restoreMcpTools(config.enabled_mcp_tools);
      }

      // 记录初始配置
      initialConfigRef.current = {
        skills: config.enabled_skills || [],
        tools: config.enabled_mcp_tools || [],
        options: config.agent_options || {},
      };
    },
    [callbacks],
  );

  /**
   * 检查配置是否已修改
   * 用于提示用户保存或警告配置变更
   */
  const hasConfigChanged = useCallback(() => {
    if (!initialConfigRef.current) {
      return false;
    }

    const current = getCurrentConfig();
    const initial = initialConfigRef.current;

    // 比较 skills
    const skillsChanged =
      JSON.stringify([...current.enabled_skills].sort()) !==
      JSON.stringify([...initial.skills].sort());

    // 比较 tools
    const toolsChanged =
      JSON.stringify([...current.enabled_mcp_tools].sort()) !==
      JSON.stringify([...initial.tools].sort());

    // 比较 options
    const optionsChanged =
      JSON.stringify(current.agent_options) !== JSON.stringify(initial.options);

    return skillsChanged || toolsChanged || optionsChanged;
  }, [getCurrentConfig]);

  return {
    getCurrentConfig,
    restoreConfig,
    hasConfigChanged,
  };
}
