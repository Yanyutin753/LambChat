/**
 * Model Config API - Model 配置相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  ProviderModelConfigResponse,
  RoleModelAssignment,
  RoleModelAssignmentResponse,
  UserAllowedModelsResponse,
  ModelProviderConfig,
} from "../../types";

export const modelConfigApi = {
  /** 获取 Provider 分组配置（需要管理员权限） */
  async getProviderConfig(): Promise<ProviderModelConfigResponse> {
    return authFetch<ProviderModelConfigResponse>(
      `${API_BASE}/api/model/config/providers`,
    );
  },

  /** 更新 Provider 分组配置（需要管理员权限） */
  async updateProviderConfig(
    providers: ModelProviderConfig[],
  ): Promise<ProviderModelConfigResponse> {
    return authFetch<ProviderModelConfigResponse>(
      `${API_BASE}/api/model/config/providers`,
      {
        method: "PUT",
        body: JSON.stringify({ providers }),
      },
    );
  },

  /** 获取角色的可用 Models（需要管理员权限） */
  async getRoleModels(roleId: string): Promise<RoleModelAssignment> {
    return authFetch<RoleModelAssignment>(
      `${API_BASE}/api/model/config/roles/${roleId}`,
    );
  },

  /** 设置角色的可用 Models（需要管理员权限） */
  async updateRoleModels(
    roleId: string,
    allowedModels: string[],
  ): Promise<RoleModelAssignmentResponse> {
    return authFetch<RoleModelAssignmentResponse>(
      `${API_BASE}/api/model/config/roles/${roleId}`,
      {
        method: "PUT",
        body: JSON.stringify({ allowed_models: allowedModels }),
      },
    );
  },

  /** 获取当前用户可用的模型列表 */
  async getUserAllowedModels(): Promise<UserAllowedModelsResponse> {
    return authFetch<UserAllowedModelsResponse>(
      `${API_BASE}/api/model/config/user/allowed`,
    );
  },
};
