/**
 * Model API - 模型配置 CRUD
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

// ============================================
// API Types
// ============================================

export interface ModelProfile {
  max_input_tokens?: number;
}

/** LLM API provider type (dynamic, from backend PROVIDER_REGISTRY) */
export type ProviderType = string;

/** Shared model option used in selectors and role config */
export interface ModelOption {
  id: string;
  value: string;
  provider?: string;
  label: string;
  description?: string;
}

export interface ModelConfig {
  id?: string;
  value: string;
  provider?: ProviderType;
  label: string;
  description?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  profile?: ModelProfile;
  fallback_model?: string;
  enabled: boolean;
  order: number;
  created_at?: string;
  updated_at?: string;
}

export interface ModelConfigCreate {
  value: string;
  provider?: ProviderType;
  label: string;
  description?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  profile?: ModelProfile;
  fallback_model?: string;
  enabled?: boolean;
  order?: number;
}

export interface ModelConfigUpdate {
  provider?: ProviderType;
  label?: string;
  description?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  profile?: ModelProfile;
  fallback_model?: string;
  enabled?: boolean;
  order?: number;
}

export interface ModelListResponse {
  models: ModelConfig[];
  count: number;
  enabled_count: number;
}

export interface ModelResponse {
  model: ModelConfig;
  message?: string;
}

// ============================================
// API Methods
// ============================================

export const modelApi = {
  /** 列出所有模型 */
  async list(includeDisabled = false): Promise<ModelListResponse> {
    return authFetch<ModelListResponse>(
      `${API_BASE}/api/agent/models/?include_disabled=${includeDisabled}`,
    );
  },

  /** 列出所有可用的模型（任何已认证用户） */
  async listAvailable(): Promise<ModelListResponse> {
    return authFetch<ModelListResponse>(
      `${API_BASE}/api/agent/models/available`,
    );
  },

  /** 获取单个模型 */
  async get(modelId: string): Promise<ModelResponse> {
    return authFetch<ModelResponse>(`${API_BASE}/api/agent/models/${modelId}`);
  },

  /** 创建模型 */
  async create(model: ModelConfigCreate): Promise<ModelResponse> {
    return authFetch<ModelResponse>(`${API_BASE}/api/agent/models/`, {
      method: "POST",
      body: JSON.stringify(model),
    });
  },

  /** 更新模型 */
  async update(
    modelId: string,
    update: ModelConfigUpdate,
  ): Promise<ModelResponse> {
    return authFetch<ModelResponse>(`${API_BASE}/api/agent/models/${modelId}`, {
      method: "PUT",
      body: JSON.stringify(update),
    });
  },

  /** 删除模型 */
  async delete(modelId: string): Promise<void> {
    return authFetch<void>(`${API_BASE}/api/agent/models/${modelId}`, {
      method: "DELETE",
    });
  },

  /** 启用/禁用模型 */
  async toggle(modelId: string, enabled: boolean): Promise<ModelResponse> {
    return authFetch<ModelResponse>(
      `${API_BASE}/api/agent/models/${modelId}/toggle?enabled=${enabled}`,
      {
        method: "POST",
      },
    );
  },

  /** 批量更新顺序 */
  async reorder(modelIds: string[]): Promise<ModelListResponse> {
    return authFetch<ModelListResponse>(
      `${API_BASE}/api/agent/models/reorder`,
      {
        method: "PUT",
        body: JSON.stringify(modelIds),
      },
    );
  },

  /** 批量导入模型 (upsert) */
  async importModels(models: ModelConfigCreate[]): Promise<ModelListResponse> {
    return authFetch<ModelListResponse>(`${API_BASE}/api/agent/models/import`, {
      method: "POST",
      body: JSON.stringify(models),
    });
  },

  /** 批量创建模型（共享配置） */
  async batchCreate(
    shared: Record<string, unknown>,
    models: { value: string; label: string; description?: string }[],
  ): Promise<ModelListResponse> {
    return authFetch<ModelListResponse>(
      `${API_BASE}/api/agent/models/batch-create`,
      {
        method: "POST",
        body: JSON.stringify({ shared, models }),
      },
    );
  },

  /** 删除所有模型 */
  async deleteAll(): Promise<void> {
    return authFetch<void>(`${API_BASE}/api/agent/models/`, {
      method: "DELETE",
    });
  },

  /** 列出所有支持的 LLM 供应商 */
  async listProviders(): Promise<
    { value: string; protocol: string; prefixes: string[] }[]
  > {
    return authFetch(`${API_BASE}/api/agent/models/providers/list`);
  },
};
