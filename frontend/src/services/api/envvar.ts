/**
 * Environment Variable API - User Env Var Management
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

// Types
export interface EnvVarResponse {
  key: string;
  value: string;
  created_at?: string;
  updated_at?: string;
}

export interface EnvVarListResponse {
  variables: EnvVarResponse[];
  count: number;
}

export interface EnvVarCreate {
  key: string;
  value: string;
}

export interface EnvVarUpdate {
  value: string;
}

export const envvarApi = {
  /**
   * List all environment variables (values masked)
   */
  async list(): Promise<EnvVarListResponse> {
    return authFetch<EnvVarListResponse>(`${API_BASE}/api/env-vars`);
  },

  /**
   * Get a single environment variable (plain text)
   */
  async get(key: string): Promise<EnvVarResponse> {
    return authFetch<EnvVarResponse>(
      `${API_BASE}/api/env-vars/${encodeURIComponent(key)}`,
    );
  },

  /**
   * Create or update an environment variable
   */
  async set(key: string, value: string): Promise<EnvVarResponse> {
    return authFetch<EnvVarResponse>(
      `${API_BASE}/api/env-vars/${encodeURIComponent(key)}`,
      {
        method: "PUT",
        body: JSON.stringify({ value }),
      },
    );
  },

  /**
   * Create an environment variable
   */
  async create(data: EnvVarCreate): Promise<EnvVarResponse> {
    return authFetch<EnvVarResponse>(`${API_BASE}/api/env-vars`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Bulk update environment variables
   */
  async bulkUpdate(variables: Record<string, string>): Promise<{
    updated_count: number;
    message: string;
  }> {
    return authFetch(`${API_BASE}/api/env-vars/bulk`, {
      method: "PUT",
      body: JSON.stringify({ variables }),
    });
  },

  /**
   * Delete a single environment variable
   */
  async delete(key: string): Promise<void> {
    return authFetch<void>(
      `${API_BASE}/api/env-vars/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    );
  },

  /**
   * Delete all environment variables
   */
  async deleteAll(): Promise<{ message: string }> {
    return authFetch(`${API_BASE}/api/env-vars/all`, {
      method: "DELETE",
    });
  },
};
