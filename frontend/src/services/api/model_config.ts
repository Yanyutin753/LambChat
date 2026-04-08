/**
 * Model Config API - Model 配置相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  GlobalModelConfigResponse,
  RoleModelAssignment,
  RoleModelAssignmentResponse,
  UserAllowedModelsResponse,
  ModelConfig,
  ModelProviderConfig,
  ProviderConfigResponse,
  LLMProvider,
  LLMProviderCreate,
  LLMProviderUpdate,
  LLMProvidersResponse,
  LLMProviderTestResponse,
} from "../../types";
import type { ProviderConfig } from "../../types/model";

export const modelConfigApi = {
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

  /** 获取 Provider 配置（组合 global + providers 接口，需要管理员权限） */
  async getProviderConfig(): Promise<ProviderConfigResponse> {
    const [globalConfig, providers] = await Promise.all([
      authFetch<GlobalModelConfigResponse>(
        `${API_BASE}/api/model/config/global`,
      ),
      authFetch<ProviderConfig[]>(
        `${API_BASE}/api/model/config/providers`,
      ),
    ]);

    const providerMap = new Map<string, ModelProviderConfig>();
    const flatModels: ModelConfig[] = [];

    for (const model of globalConfig.models) {
      const modelId = model.id;
      const providerName = modelId.includes("/")
        ? modelId.split("/")[0]
        : "openai";

      flatModels.push({
        ...model,
        value: modelId,
        label: model.name || modelId,
        provider: providerName,
      });

      if (!providerMap.has(providerName)) {
        const pc = providers.find((p) => p.name === providerName);
        providerMap.set(providerName, {
          provider: providerName,
          label: pc?.display_name || providerName,
          base_url: pc?.api_base || undefined,
          api_key: pc?.api_key,
          has_api_key: !!pc?.api_key,
          clear_api_key: false,
          temperature: 0.7,
          max_tokens: 4096,
          max_retries: 3,
          retry_delay: 1.0,
          models: [],
        });
      }
      providerMap.get(providerName)!.models.push({
        ...model,
        value: modelId,
        label: model.name || modelId,
        provider: providerName,
      });
    }

    return {
      providers: Array.from(providerMap.values()),
      flat_models: flatModels,
      legacy_migration_applied: false,
      legacy_inherited_providers: [],
    };
  },

  /** 更新 Provider 配置（需要管理员权限） */
  async updateProviderConfig(
    newProviders: ModelProviderConfig[],
  ): Promise<ProviderConfigResponse> {
    const allModels: ModelConfig[] = [];
    const providerConfigs: ProviderConfig[] = [];

    for (const p of newProviders) {
      providerConfigs.push({
        name: p.provider,
        display_name: p.label,
        api_key: p.api_key ?? null,
        api_base: p.base_url ?? null,
        enabled: true,
      });

      for (const m of p.models) {
        allModels.push({
          id: m.id || m.value || "",
          name: m.name || m.label || m.id || "",
          description: m.description || "",
          enabled: m.enabled,
          api_key: m.api_key,
          api_base: m.api_base,
        });
      }
    }

    await authFetch(`${API_BASE}/api/model/config/global`, {
      method: "PUT",
      body: JSON.stringify({ models: allModels }),
    });
    await authFetch(`${API_BASE}/api/model/config/providers`, {
      method: "PUT",
      body: JSON.stringify({ providers: providerConfigs }),
    });

    return modelConfigApi.getProviderConfig();
  },

  /** 获取所有 LLM Providers（内置 + 自定义） */
  async getLLMProviders(): Promise<LLMProvidersResponse> {
    return authFetch<LLMProvidersResponse>(
      `${API_BASE}/api/model/config/llm-providers`,
    );
  },

  /** 创建自定义 LLM Provider */
  async createLLMProvider(
    provider: LLMProviderCreate,
  ): Promise<LLMProvider> {
    return authFetch<LLMProvider>(
      `${API_BASE}/api/model/config/llm-providers`,
      {
        method: "POST",
        body: JSON.stringify(provider),
      },
    );
  },

  /** 更新 LLM Provider */
  async updateLLMProvider(
    name: string,
    update: LLMProviderUpdate,
  ): Promise<LLMProvider> {
    return authFetch<LLMProvider>(
      `${API_BASE}/api/model/config/llm-providers/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(update),
      },
    );
  },

  /** 删除自定义 LLM Provider */
  async deleteLLMProvider(name: string): Promise<void> {
    await authFetch(
      `${API_BASE}/api/model/config/llm-providers/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    );
  },

  /** 测试 Provider 连接 */
  async testLLMProvider(
    name: string,
    modelName?: string,
  ): Promise<LLMProviderTestResponse> {
    return authFetch<LLMProviderTestResponse>(
      `${API_BASE}/api/model/config/llm-providers/${encodeURIComponent(name)}/test`,
      {
        method: "POST",
        body: JSON.stringify({ model_name: modelName }),
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
