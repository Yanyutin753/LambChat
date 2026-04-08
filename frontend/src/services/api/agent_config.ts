/**
 * Agent Config API - Agent 配置相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  GlobalAgentConfigResponse,
  RoleAgentAssignment,
  RoleAgentAssignmentResponse,
  RoleModelAssignment,
  UserAgentPreference,
  UserAgentPreferenceResponse,
  AgentConfig,
} from "../../types";

export const agentConfigApi = {
  /** 获取全局 Agent 配置（需要管理员权限） */
  async getGlobalConfig(): Promise<GlobalAgentConfigResponse> {
    return authFetch<GlobalAgentConfigResponse>(
      `${API_BASE}/api/agent/config/global`,
    );
  },

  /** 更新全局 Agent 配置（需要管理员权限） */
  async updateGlobalConfig(
    agents: AgentConfig[],
  ): Promise<GlobalAgentConfigResponse> {
    return authFetch<GlobalAgentConfigResponse>(
      `${API_BASE}/api/agent/config/global`,
      {
        method: "PUT",
        body: JSON.stringify({ agents }),
      },
    );
  },

  /** 获取角色的可用 Agents（需要管理员权限） */
  async getRoleAgents(roleId: string): Promise<RoleAgentAssignment> {
    return authFetch<RoleAgentAssignment>(
      `${API_BASE}/api/agent/config/roles/${roleId}`,
    );
  },

  /** 设置角色的可用 Agents（需要管理员权限） */
  async updateRoleAgents(
    roleId: string,
    allowedAgents: string[],
  ): Promise<RoleAgentAssignmentResponse> {
    return authFetch<RoleAgentAssignmentResponse>(
      `${API_BASE}/api/agent/config/roles/${roleId}`,
      {
        method: "PUT",
        body: JSON.stringify({ allowed_agents: allowedAgents }),
      },
    );
  },

  /** 获取角色的可用 Models（需要管理员权限） */
  async getRoleModels(roleId: string): Promise<RoleModelAssignment> {
    return authFetch<RoleModelAssignment>(
      `${API_BASE}/api/agent/config/roles/${roleId}/models`,
    );
  },

  /** 设置角色的可用 Models（需要管理员权限） */
  async updateRoleModels(
    roleId: string,
    allowedModels: string[],
  ): Promise<RoleModelAssignment> {
    return authFetch<RoleModelAssignment>(
      `${API_BASE}/api/agent/config/roles/${roleId}/models`,
      {
        method: "PUT",
        body: JSON.stringify({ allowed_models: allowedModels }),
      },
    );
  },

  /** 获取用户的默认 Agent 设置 */
  async getUserPreference(): Promise<UserAgentPreference> {
    return authFetch<UserAgentPreference>(
      `${API_BASE}/api/agent/config/user/preference`,
    );
  },

  /** 设置用户的默认 Agent */
  async setUserPreference(
    agentId: string,
  ): Promise<UserAgentPreferenceResponse> {
    return authFetch<UserAgentPreferenceResponse>(
      `${API_BASE}/api/agent/config/user/preference`,
      {
        method: "PUT",
        body: JSON.stringify({ default_agent_id: agentId }),
      },
    );
  },

  /** 删除用户的默认 Agent 设置 */
  async deleteUserPreference(): Promise<UserAgentPreferenceResponse> {
    return authFetch<UserAgentPreferenceResponse>(
      `${API_BASE}/api/agent/config/user/preference`,
      {
        method: "DELETE",
      },
    );
  },
};
